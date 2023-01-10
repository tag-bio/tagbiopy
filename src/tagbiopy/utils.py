import datetime
import inspect
import json
import logging
import os

import pandas as pd

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


def content_to_dataframe(content, index=None, **kwargs) -> pd.DataFrame:
    """Takes POST content and turns it into an indexed dataframe.

    :param content: requests.post.content
    :param index: str,
    :param kwargs: dict, pd.DataFrame.read_csv parameters
    :return: pd.DataFrame
    """
    import io

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
        msg = f'Index {index!r} not found among dataframe columns {_df.columns}'
        log_exception(exception_class=ValueError, message=msg, cause=e)


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


def get_post_request_status(r):
    if r.status_code > 200:
        return f'HTTP {r.request.method} response status code {r.status_code}, message: {r.json()["message"]}'
    else:
        return 'OK'


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


def load_yaml(yaml_file):
    import yaml

    with open(yaml_file) as fh:
        try:
            config = yaml.safe_load(fh)
        except yaml.YAMLError as e:
            logger.error(e, exc_info=True)
            raise

    return config


def load_json(filename):
    with open(filename) as fh:
        return json.load(fh)


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


def run_notebook(notebook_file, output_file):
    """

    We do not show the input cells when turning a jupyter notebook into a html report.

    jupyter nbconvert --execute --no-input --to html --template classic --output test.html ml-pymd.ipynb
    :param notebook_file: str, path to ipynb
    :param output_file: str, path to the output
    :return: None
    """
    import subprocess

    # Run the notebook
    subprocess.run(
        ['jupyter', 'nbconvert', '--to', 'html',
         '--no-input', '--output',
         output_file, notebook_file]
    )

    # Note: regardless of the output_file name, nbconvert will always
    # attach ".html" to the output file.

    expected_file = output_file.replace('.html', '')
    os.rename(
        output_file,
        expected_file
    )

    return expected_file


def to_json(variable_object):
    return variable_object.as_dict
