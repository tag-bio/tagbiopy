import datetime
import inspect
import json
import logging
import os

import pandas as pd

from requests.auth import AuthBase

from tagbiopy import logger

THIS_DIR = os.path.dirname(os.path.realpath(__file__))


def accepts(*types):
    """Enforce function argument types. Shamelessly stolen from https://www.python.org/dev/peps/pep-0318

    :param types:
    :return:
    """

    def check_accepts(f):
        assert len(types) == f.func_code.co_argcount

        def new_f(*args, **kwds):
            for (a, t) in zip(args, types):
                assert isinstance(a, t), f'arg {a} does not match {t}'
            return f(*args, **kwds)

        new_f.func_name = f.func_name
        return new_f

    return check_accepts


def check_arg_type(v, arg_type: type, allow_none=True):
    if allow_none and v is None:
        return v

    if not isinstance(v, arg_type):
        msg = f'arg {v!r} type {type(v)} invalid. Choose from {arg_type}'
        log_exception(TypeError, msg)

    return v


def check_list_arg_types(lst: list, arg_type: type, allow_none=True):
    if allow_none and lst is None:
        return lst

    if not isinstance(lst, list):
        msg = f'Argument not a list: type {type(lst)} for {lst}'
        log_exception(TypeError, msg)

    for i, v in enumerate(lst):
        if not isinstance(v, arg_type):
            msg = f'[{i}]: {v!r} type {type(v)} not a {arg_type}'
            log_exception(TypeError, msg)

    return lst


#: arguments of earlier versions that are accepted and ignored, so older code keeps working until it is updated
RETIRED_ARGUMENTS = ('datetimes',)


def drop_retired_arguments(kwargs: dict, where: str) -> dict:
    """Remove retired arguments from kwargs (logging a deprecation warning) before they reach pandas."""
    for name in RETIRED_ARGUMENTS:
        if name in kwargs:
            kwargs.pop(name)
            logger.warning(f'{where}: the {name!r} argument is retired and ignored (dates always arrive as '
                           f'datetimes); remove it -- it will be rejected in a future version')
    return kwargs


def _collapse_lists_by_row(column):
    """A LIST column as "; "-joined strings, row by row in Python (a null inside a list joins as "")."""
    import datetime

    import numpy as np

    # native Parquet dates in a multi-value column keep the engine's yyyy/MM/dd label form
    def _cell_text(x):
        if x is None:
            return ""
        if isinstance(x, datetime.date):
            return x.strftime('%Y/%m/%d')
        return str(x)

    def _collapse_cell(v):
        if v is None:
            return ""
        if isinstance(v, (list, tuple, np.ndarray)):
            return "; ".join(_cell_text(x) for x in v)
        return v

    return column.to_pandas().map(_collapse_cell).values


def _parquet_to_dataframe(content, categories=False) -> pd.DataFrame:
    """A Parquet download as a DataFrame shaped like the CSV path's, with column kinds taken from the schema.

    A multi-value (non-exclusive) categorical is written as parquet LIST<string>; the CSV path delivers the
    same data as one string joined with "; ". Those columns are joined to that exact form in Arrow (a column
    holding a null inside a list takes the row-by-row path), so plugins doing string ops on a multi-value
    categorical work on either path. Native DATE columns become UTC-midnight datetimes, BOOLEAN columns
    pandas' nullable 'boolean'; a column of only nulls keeps its None values.
    """
    import io

    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    table = pq.read_table(io.BytesIO(content))
    by_row = {}
    dates = []
    logicals = []
    for index, field in enumerate(table.schema):
        column = table.column(index)
        present = len(column) == 0 or column.null_count < len(column)
        if pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
            if column.null_count == len(column):
                continue
            value_type = field.type.value_type
            is_date = pa.types.is_date(value_type)
            # Arrow joins only text lists exactly; numbers, logicals and nulls inside a list take the per-row form
            joinable = is_date or pa.types.is_string(value_type) or pa.types.is_large_string(value_type)
            if not joinable or pc.list_flatten(column).null_count > 0:
                by_row[field.name] = _collapse_lists_by_row(column)
                continue
            values = pc.cast(column, pa.list_(pa.string())) if is_date else column
            text = pc.binary_join(values, "; ")
            if is_date:
                text = pc.replace_substring(text, "-", "/")
            table = table.set_column(index, field.name, pc.fill_null(text, ""))
        elif pa.types.is_date(field.type) and column.null_count < len(column):
            dates.append(field.name)
        elif pa.types.is_boolean(field.type) and present:
            logicals.append(field.name)
    _df = table.to_pandas()
    for name, values in by_row.items():
        _df[name] = values
    for name in dates:
        _df[name] = pd.to_datetime(_df[name], utc=True)
    for name in logicals:
        _df[name] = _df[name].astype('boolean')
    # opt-in: single_valued text categoricals (named in the file's tagbio.single_valued metadata) as
    # 'category'; date and logical columns keep their own types
    if categories:
        _single_valued = (table.schema.metadata or {}).get(b'tagbio.single_valued')
        if _single_valued:
            for _col in json.loads(_single_valued):
                if _col in _df.columns and _df[_col].dtype == object:
                    _df[_col] = _df[_col].astype('category')
    return _df


def content_to_dataframe(content, index=None, categories=False, **kwargs) -> pd.DataFrame:
    """Take POST content and turns it into a dataframe. Attempt to set dataframe
    index to default ('Unique ID'), and if that fails, just return the dataframe

    :param content: requests.post.content
    :param index: str,
    :param kwargs: dict, pd.DataFrame.read_csv parameters
    :return: pd.DataFrame
    """
    import io

    drop_retired_arguments(kwargs, 'content_to_dataframe')

    # Sniff the response bytes rather than trusting the requested format: parquet files begin with the
    # magic bytes b'PAR1'. Robust to FC version skew -- an older FC that ignored output_type returns CSV
    # and we fall through to the CSV path.
    if isinstance(content, (bytes, bytearray)) and content[:4] == b'PAR1':
        logger.debug(f'Detected parquet response (PAR1); reading with pyarrow')
        try:
            _df = _parquet_to_dataframe(content, categories)
        except ImportError as e:
            raise ImportError(
                "Reading a parquet download requires pyarrow. "
                "Install with: pip install 'tagbiopy[parquet]' (or pip install pyarrow)") from e
        logger.debug(f'Parquet content turned into a {_df.shape} dataframe')
    else:
        logger.debug(f'Encode content')
        encoded_content = str(content, 'utf-8')
        logger.debug(f'Content encoded to utf-8, reading into a dataframe')
        _df = pd.read_csv(io.StringIO(encoded_content), **kwargs)
        logger.debug(f'Content turned into a {_df.shape} dataframe')

    # Use default index if index not specified
    if index is None:
        index = 'Unique ID'
    try:
        return _df.set_index(index)
    except KeyError as e:
        logger.error(e)
        logger.error(f'Index {index!r} not found among dataframe columns {_df.columns}')
    except AttributeError as e:
        # If we do not get back a pd.DataFrame, raise an exception
        logger.error(e)
        raise
    finally:
        return _df


def create_temp_file(prefix=None, suffix='.log', fh=False):
    """
    Creates a temporary file
    :param prefix: str
    :param suffix: str
    :param fh: bool, default False. By default, return the filename, otherwise the filehandle
    :return: filehandle or filename to a temp file
    """
    import tempfile

    fd, log_file = tempfile.mkstemp(prefix=prefix, suffix=suffix)

    if fh:
        return os.fdopen(fd)
    else:
        return log_file


def instance_details(klass_):
    attributes = list_attributes(klass_, include_private=True)
    properties = list_properties(klass_, include_private=True)
    methods = list_methods(klass_, include_private=True)

    ret = f'{klass_!r}:'
    ret += '\n  Attributes:\n'
    ret += '\n'.join([f'  {v}' for v in attributes])
    ret += '\n  Properties:\n'
    ret += '\n'.join([f'  {v}' for v in properties])
    ret += '\n  Methods:\n'
    ret += '\n'.join([f'  {v}' for v in methods])

    return ret


def dict2obj(d):
    # using json.loads method and passing json.dumps
    # method and custom object hook as arguments
    class Obj:

        # constructor
        def __init__(self, _d):
            self.__dict__.update(_d)

    return json.loads(json.dumps(d), object_hook=Obj)


def extract_data_reference_type(d, use_pop=False):
    # Implemented on 2021-02-18
    # For compatibility with pre and post 2.52.4. compatibility

    if 'variable_type' in d:
        k = 'variable_type'
    else:
        k = 'data_reference_type'

    if use_pop:
        return d.pop(k)
    else:
        return d[k]


def generate_repr(instance):
    arguments, defaults = inspect_function_arguments(instance.__init__)
    args = []

    # Drop self, and go over all non-default arguments
    for i in range(1, len(arguments) - len(defaults)):
        arg_name = arguments[i]
        value = getattr(instance, arg_name)
        args.append(f'{arg_name}={value!r}')

    # Now report default arguments only if their calling values have changed
    for i in range(len(defaults)):
        arg_name = arguments[-len(defaults) + i]
        default_value = defaults[i]
        value = getattr(instance, arg_name)
        if value == default_value:
            continue
        args.append(f'{arg_name}={value!r}')

    ret = instance.__class__.__name__
    ret += '(' + ', '.join(args) + ')'
    return ret


def get_bash_command_stdout(command, workdir):
    import subprocess
    return subprocess.run(
        command.split(),
        check=True,
        capture_output=True,
        cwd=workdir
    ).stdout.decode('utf-8').strip()


def get_default_args(func):
    signature = inspect.signature(func)
    return {
        k: v.default
        for k, v in signature.parameters.items()
        if v.default is not inspect.Parameter.empty
    }


def get_current_branch(repo_dir=THIS_DIR):
    command = 'git branch --show-current'
    return get_bash_command_stdout(command, repo_dir)


def get_current_sha(repo_dir=THIS_DIR):
    command = f'git rev-parse HEAD'
    return get_bash_command_stdout(command, repo_dir)


def get_post_headers(r):
    return f'post headers: {json.dumps(dict(r.headers), indent=2)}'


def get_typename(v):
    return type(v).__name__


def inspect_function_arguments(func):
    """Inspects function and returns arguments and default values.

    :param func: function
    :return: 2-tuple of a list of arguments and a list of default values. The default values can be
    mapped to the end of the list of arguments
    """
    import inspect

    argspec = inspect.getfullargspec(func)
    arguments = argspec.args
    defaults = argspec.defaults

    return arguments, defaults


def ipynb_to_html(notebook_file, output_file, title=None, tag_data=None, plain=False):
    """
    Turn an executed jupyter notebook into an html report embeddable into the front end, with code cells hidden.

    By default the report is a Tag.bio report page: the same header (title, user, date, data date, app link),
    table of contents and styling as R Markdown apps (see tagbiopy.report). The title is ``title`` or else the
    notebook's first heading. The header details come from ``tag_data`` (a TagbioData, FCPacket or packet path)
    or else from the plugin running in this process.

    :param notebook_file: str, path to ipynb
    :param output_file: str, path to the output
    :param title: str, optional report title
    :param tag_data: optional TagbioData / FCPacket / packet file path for the header details
    :param plain: bool, True for the plain nbconvert page (no Tag.bio header)
    :return: None
    """
    if not plain:
        try:
            from tagbiopy.report import notebook_report
            packet = getattr(tag_data, 'fc_packet', tag_data)
            if isinstance(packet, str):
                from tagbiopy.protocol import FCPacket
                packet = FCPacket(packet)
            notebook_report(notebook_file, output_file, title=title, fc_packet=packet)
            return
        except Exception as e:
            # never fail an app over its look: fall back to the plain page
            logger.warning(f'Tag.bio report page failed ({e!r}); writing the plain nbconvert page instead')

    import subprocess
    import shutil

    # Run the notebook
    command = 'jupyter nbconvert --to html --no-input --output '
    command += f'{output_file} {notebook_file}'
    command_split = command.split()
    subprocess.run(command_split).check_returncode()

    # Note: regardless of the output_file name, nbconvert will always
    # attach ".html" to the output file.

    shutil.copy(f'{output_file}.html', output_file)


def list_attributes(instance, include_private=False):
    public_attributes = []
    private_attributes = []
    for k in instance.__dict__:
        if k.startswith('_'):
            private_attributes.append(k)
        else:
            public_attributes.append(k)

    ret = sorted([v for v in public_attributes])
    if include_private:
        ret.extend(sorted([v for v in private_attributes]))
    return ret


def list_methods(_class, include_private=False):
    public_methods = []
    private_methods = []
    for m in dir(_class):
        if m.startswith('__') or not callable(getattr(_class, m)):
            continue

        if m.startswith('_'):
            private_methods.append(m)
        else:
            public_methods.append(m)

    ret = sorted([v for v in public_methods])
    if include_private:
        ret.extend(sorted([v for v in private_methods]))

    return ret


def list_properties(_class, include_private=False):
    public_properties = []
    private_properties = []
    for p in dir(_class):
        if not isinstance(getattr(_class, p), property):
            continue
        if p.startswith('_'):
            private_properties.append(p)
        else:
            public_properties.append(p)
    ret = sorted([v for v in public_properties])
    if include_private:
        ret.extend(sorted([v for v in private_properties]))
    return ret


def load_yaml(yaml_file, catch_error=True):
    import yaml

    with open(yaml_file) as fh:
        try:
            s = yaml.safe_load(fh)
        except yaml.YAMLError as e:
            logger.error(e, exc_info=True)
            if catch_error:
                raise

    return s


def load_json(filename, catch_error=True):
    with open(filename) as fh:
        try:
            s = json.load(fh)
        except json.JSONDecodeError as e:
            logger.error(e, exc_info=True)
            if catch_error:
                raise

    return s


def log_exception(exception_class, message: str, level=logging.DEBUG, cause=None, terminate=True):
    if cause is None:
        try:
            raise exception_class(message)
        except exception_class as e:
            logger.log(level=level, msg=e, exc_info=True)
            if terminate:
                raise
    else:
        try:
            raise exception_class(message) from cause
        except exception_class as e:
            logger.log(level=level, msg=e, exc_info=True)
            if terminate:
                raise


def now(sep=None):
    ret = datetime.datetime.now().strftime('%F %X').replace(':', '-')
    if isinstance(sep, str):
        ret = ret.replace(' ', sep)
    return ret


def print_ts(s, **kwargs):
    print(f'{datetime.datetime.now().strftime("%F %X.%f")} {s}', **kwargs)


def returns(rtype):
    """Enforce function return types. Shamelessly stolen from https://www.python.org/dev/peps/pep-0318

    :param rtype:
    :return:
    """

    def check_returns(f):
        def new_f(*args, **kwds):
            result = f(*args, **kwds)
            assert isinstance(result, rtype), f'Return value {result} does not match {rtype}'
            return result

        new_f.func_name = f.func_name
        return new_f

    return check_returns


def set_fc_host(fc: str):
    """
    Set fc-host in the format
    :param fc: str, such fc-abc, fc-xyz, etc.
    :return: str, url to the fc endpoint
    """
    base_url = os.environ['TAGBIO_BASE_URL']

    return base_url + f'/fc-svc/{fc}'


def to_json(variable_object):
    return variable_object.as_dict


def validate(name, s, allowed):
    """
    Check if s is in the allowed list. If not, raise ValueError
    :param name: str, what should s be called (method, request type, etc).
    :param s: str
    :param allowed: List[str] of s to choose from
    :return:
    """

    if s not in allowed:
        log_exception(
            ValueError,
            f'{s}: invalid {name}. Choose from {allowed}.'
        )

    return s


class BearerAuth(AuthBase):
    def __init__(self, _auth):
        self.auth = _auth

    def __call__(self, _r):
        _r.headers["authorization"] = self.auth
        return _r
