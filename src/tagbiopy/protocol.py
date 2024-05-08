import json
import os
import pandas as pd

from tagbiopy import logger
from tagbiopy.request import QRequest
from tagbiopy.utils import content_to_dataframe, create_temp_file, list_attributes, load_json, log_exception, now
from tagbiopy.utils import ipynb_to_html


class SDKInput:

    def __init__(self, args):
        self.fc_packet = args.fc_data
        self.input_file = args.user_function
        self.output_type = args.output_type
        self.output_file = args.output_file


class RunNotebook(SDKInput):
    def __init__(self, args):
        super().__init__(args)

        self._prefix, self._suffix = os.path.splitext(os.path.basename(self.input_file))

        self._first_cell = None
        self._modified_notebook_file_input = None
        self._modified_notebook_file_executed = None
        self.tag_result = TagbioResult(path=self.output_file)
        logger.info(f'{self.__class__} initiated')

    def __call__(self):
        self.execute_notebook()

    @property
    def first_cell(self):
        if self._first_cell is None:
            logger.debug(f'{self}: modify first cell')
            self._first_cell = {
                "cell_type": "code",
                "metadata": {
                    "tags": [
                        "parameters"
                    ]
                },
                "outputs": [],
                "source": [
                    "from tagbiopy.protocol import TagbioData, TagbioResult\n",
                    f"tag_data = TagbioData({self.fc_packet!r})\n"
                ]
            }
        return self._first_cell

    @property
    def modified_notebook_file_input(self):
        if self._modified_notebook_file_input is None:

            # Create temporary file where the notebook contents will be stored
            self._modified_notebook_file_input = create_temp_file(
                prefix=f'{self._prefix}-{now(sep="_")}',
                suffix=self._suffix
            )

            # Use the input jupyter notebook and modify its content by fixin' the first cell.
            with open(self._modified_notebook_file_input, 'w') as fh:
                json.dump(
                    self._modify_notebook_content(),
                    fh,
                    indent=2
                )
        return self._modified_notebook_file_input

    @property
    def modified_notebook_file_executed(self):
        prefix, suffix = os.path.splitext(os.path.basename(self.input_file))
        self._modified_notebook_file_executed = self.modified_notebook_file_input.replace(prefix, f'{prefix}_executed')
        return self._modified_notebook_file_executed

    def _modify_notebook_content(self):
        logger.debug(f'{self}: load {self.input_file} in memory')
        with open(self.input_file) as fh:
            s = json.load(fh)

        # Insert the first cell
        s['cells'].insert(0, self.first_cell)

        logger.debug(f'{self}: Modified original notebook content by adding the first cell.')
        return s

    def execute_notebook(self):
        import papermill as pm

        logger.debug(f'{self}: Execute notebook {self.modified_notebook_file_input!r}')
        # Execute jupyter notebook
        _ = pm.execute_notebook(
            input_path=self.modified_notebook_file_input,
            output_path=self.modified_notebook_file_executed,
            kernel_name='python3'
        )

        # Create report from jupyter notebook
        logger.debug(f'{self}: Create report from {self.modified_notebook_file_executed}')
        ipynb_to_html(self.modified_notebook_file_executed, self.tag_result.path)

        logger.info(f'TagResult saved to {self.tag_result.path}')
        print(f'TagResult saved to {self.tag_result.path}')


class RunFunction(SDKInput):

    def __init__(self, args):
        super().__init__(args)

        self._tag_data = None
        self._tag_result = None
        self._user_function = None

    def __call__(self):
        self.user_function(
            tag_data=self.tag_data,
            tag_result=self.tag_result
        )

    @property
    def tag_data(self):
        if self._tag_data is None:
            logger.info('Initialize TagbioData')
            self._tag_data = TagbioData(self.fc_packet)

            logger.info(f'Check TagbioData.df ... ')
            if self._tag_data.df is None:
                logger.info('No data requested')
            else:
                logger.info(f'columns: {self._tag_data.df.columns}')

        return self._tag_data

    @property
    def tag_result(self):
        if self._tag_result is None:
            # Initialize tag_result. If output path is a temp file
            logger.info('Initialize TagbioResult')
            self._tag_result = TagbioResult(
                extension=self.output_type,
                path=self.output_file
            )
            logger.debug(f'tag_result: {self._tag_result}')
        return self._tag_result

    @property
    def user_function(self):
        if self._user_function is None:
            self._user_function = extract_user_function(self.input_file)
        return self._user_function


class Run:

    def __init__(self, args):
        message = 'Execute {what} from {where!r}'
        if args.user_function.endswith('.py'):
            logger.info(message.format(what='user function', where=args.user_function))
            self._class = RunFunction(args)
        elif args.user_function.endswith('.ipynb'):
            logger.info(message.format(what='jupyter notebook', where=args.user_function))
            self._class = RunNotebook(args)
        else:
            msg = f'Invalid input: {args.user_function!r}. Provide either a .py or .ipynb'
            log_exception(RuntimeError, msg)

    def __call__(self):
        return self._class.__call__()


def extract_user_function(filename):
    import importlib.machinery
    import inspect

    m = importlib.machinery.SourceFileLoader('tgb', filename).load_module()
    _fs = inspect.getmembers(m, inspect.isfunction)
    for _function_name, _function in _fs:
        _function_args = inspect.getfullargspec(_function).args
        if _function_args == ['tag_data', 'tag_result']:
            return _function

    message = 'Invalid function'
    if len(_fs) > 1:
        message += 's'
    message += f' in {filename!r}:'
    message += '\nFound {}'.format(', '.join([v[0] for v in _fs]))
    message += '\nPlease create a function with (tag_data: TagbioData, tag_result: TagbioResult) arguments.'

    log_exception(RuntimeError, message)


def flatten_single_element_list(_dict):
    ret = {}
    for k, v in _dict.items():
        if isinstance(v, list):
            if len(v) == 1:
                ret[k] = v[0]
            else:
                ret[k] = [w for w in v]
    return ret


def load_function(args):
    filename = args.user_function
    if filename.endswith('.py'):
        return extract_user_function(filename)
    elif filename.endswith('.ipynb'):
        fc_packet = args.fc_data
        pass
    else:
        msg = f'Illegal user_function {filename!r}. Should be either a .py or .ipynb file.'
        log_exception(RuntimeError, msg)


class FCPacket:

    def __init__(self, filename, uid=None):
        """
        Turn fc-packet.json into an object
        :param filename: str, path to fc-packet json
        :param uid: str, default tag.bio entity ID ('Unique ID'). For older data products, specify uid. This will be the
            index in the returned dataframe.
        """
        self.filename = filename
        # Serialize the entire packet received from the FC
        self._packet = load_json(self.filename)

        self.uid = uid

        # Get the 'fc' part
        self._request = self._packet.get('request')
        self._fc = self._packet.get('fc')

        self.script = self._packet.get('script')
        self._background = None
        self._analysis_variables = None
        #
        # self.analysis_variables = self.script.get('analysis_variables')
        self._log_script()

        self.name = self._fc.get('name')
        self.url = self._fc.get('url')
        # Hostname is the url w/o the trailing slash
        self.host = self.url[:-1]
        self.api_key = self._packet.get('api_key')
        self.token = self._request.get('auth')

        # Take care of passthrough arguments
        self.passthrough_arguments = PassThroughArguments(self._packet.get('passthrough_arguments'))

        logger.info(f'{self!r} initialized')

    def __repr__(self):
        ret = self.__class__.__name__
        ret += f'(filename={self.filename!r})'
        return ret

    def _log_script(self):
        if self.script is not None:
            logger.debug(f'{self!r}: script: {json.dumps(self.script, indent=4)}')
        else:
            logger.debug(f'{self!r}: No script(!)')

        if self.background is not None:
            # logger.debug(f'{self!r}: background: {json.dumps(self.background, indent=4)}')
            logger.debug(f'{self!r}: background: {self.background}')
        else:
            logger.debug(f'{self!r}: No background')

        if self.analysis_variables is not None:
            logger.debug(f'{self!r}: analysis variables: {json.dumps(self.analysis_variables, indent=4)}')
        else:
            logger.debug(f'{self!r}: No analysis variables')

    @property
    def background(self):
        if self._background is None:
            if self.script is not None:
                self._background = self.script.get('background')
        return self._background

    @property
    def analysis_variables(self):
        if self._analysis_variables is None:
            if self.script is not None:
                self._analysis_variables = self.script.get('analysis_variables')
        return self._analysis_variables


class PassThroughArguments:

    def __init__(self, passthrough_dict):
        """
        :type passthrough_dict: dict
        """
        self._dict = {}
        if isinstance(passthrough_dict, dict):
            self._dict = flatten_single_element_list(passthrough_dict)
            self.__dict__.update(self._dict)
        self._attributes = None

        logger.debug(f'{self!r} initialized')

    def __repr__(self):
        ret = self.__class__.__name__
        ret += f'(passthrough_dict={self._dict})'

        return ret

    @property
    def attributes(self):
        if self._attributes is None:
            self._attributes = list_attributes(self)
        return self._attributes

    def get(self, name):
        if name not in self.attributes:
            message = f'{name}: Invalid attribute name.'
            message += f' Please choose from: {self.attributes}'
            raise ValueError(message)
        return getattr(self, name)


class TagbioData:

    def __init__(self, fc_packet):
        self.fc_packet = FCPacket(fc_packet)
        self.passthrough_arguments = self.fc_packet.passthrough_arguments

        self._q_request = None
        self._df = None

        logger.debug(f'{self!r} initialized')

    def __repr__(self):
        ret = self.__class__.__name__
        ret += f'(fc_packet={self.fc_packet.filename!r}, '
        return ret

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            content = self.q_request.get_content(script=self.fc_packet.script)
            self._df = content_to_dataframe(content)

            logger.debug(f'{self}: shape {self._df.shape}, columns: {self._df.columns}')
        return self._df

    @property
    def q_request(self):
        if self._q_request is None:
            self._q_request = QRequest(
                host=self.fc_packet.host,
                api_key=self.fc_packet.api_key,
                token=self.fc_packet.token
            )
        return self._q_request


class TagbioResult:
    _extensions = ('html', 'json', 'jpeg', 'pdf', 'png', 'svg', 'csv')

    def __init__(self, extension='html', path=None, path_mutable=True):
        """
        :param extension: str, type of output where the df is going to go
        :param path: path, private, where the df will be stored
        """

        self._extension = extension

        # Keep the path private
        self.__path = path
        self._path_mutable = path_mutable

        # For lazy loading of the dataframe
        self._df = None
        # Handle on the figure plotted from the _df
        self._fig = None
        # Content returned by an LLM
        self._content = None

    def __repr__(self):
        args = [f'extension={self._extension!r}']
        if self.path:
            args.append(f'path={self.path!r}')
        if self._path_mutable:
            args.append(f'path_mutable={self._path_mutable}')
        return f'{self.__class__.__name__}({", ".join(args)})'

    def __str__(self):
        ret = f'<class {self.__class__.__name__}: '
        ret += f'extension: {self.extension}'
        if self.fig is not None:
            ret += f', fig: {type(self.fig)}'
        if self.__path is not None:
            ret += f', path (private): {self.__path}'
        if self.df is not None:
            ret += ', dataframe shape: {self.df.shape}'
        ret += '>'
        return ret

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, s):
        self._content = s

    @property
    def df(self):
        return self._df

    @df.setter
    def df(self, data_frame):
        self._df = data_frame

    @property
    def extension(self):
        if self._extension not in self._extensions:
            msg = f'{self!r}: Extension {self._extension!r} not valid. Chose from {self._extensions}'
            logger.debug(msg)
            raise ValueError(msg)

        return self._extension

    @property
    def fig(self):
        return self._fig

    @fig.deleter
    def fig(self):
        del self._fig

    @fig.setter
    def fig(self, value):
        self._fig = value

    @property
    def path(self):
        return self.__path

    @path.deleter
    def path(self):
        if self._path_mutable:
            self.__path = None

    @path.setter
    def path(self, value):
        if self._path_mutable:
            self.__path = value
        else:
            self.__path = None

    def save(self, what='fig', **kwargs):

        if what == 'fig':
            if self.fig is None:
                raise RuntimeError(f'{self}: No figure generated')

            import matplotlib.figure
            import plotly.graph_objects

            if isinstance(self.fig, plotly.graph_objects.Figure):
                if self.extension == 'html':
                    self.fig.write_html(self.path, **kwargs)
                else:
                    self.fig.write_image(self.path, format=self.extension, **kwargs)
            elif isinstance(self.fig, matplotlib.figure.Figure):
                self.fig.savefig(self.path, format=self.extension, bbox_inches='tight', **kwargs)
            else:
                raise ValueError('Please create either a matplotlib or plotly figure')

            logger.debug(f'{self}: figure stored to {self.path}')

        elif what == 'data':
            if self.df is None:
                raise RuntimeError(f'{self}: No data')

            path = self.path
            if self.extension != 'csv':
                message = 'Your output extension is {}. Setting to "csv"'.format(self.extension)
                logger.warning(message)
                path = self.path + '.csv'
            logger.info('Storing TagbioResult data to {}'.format(path))
            float_format = '%.4f'
            self.df.to_csv(path, float_format=float_format)
            logger.debug(f'{self} pd.DataFrame stored to {self.path}')

        else:
            
            if self.content is None:
                raise RuntimeError(f'{self}: No content created')

            with open(self.path, 'w') as fh:
                if isinstance(self.content, dict):
                    fh.write(json.dumps(self.content, indent=2, default=str))
                else:
                    fh.write(self.content)
            logger.info(f'Note: {what!r} content stored to {self.path}')
            logger.debug(f'Content ({what!r}_: {self.content!r}')
