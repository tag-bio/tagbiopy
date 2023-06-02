import json
import pandas as pd

from tagbiopy import logger
from tagbiopy.request import QRequest, HEADER_DELIMITER
from tagbiopy.utils import content_to_dataframe, list_attributes, load_json, log_exception


def flatten_single_element_list(_dict):
    ret = {}
    for k, v in _dict.items():
        if isinstance(v, list):
            if len(v) == 1:
                ret[k] = v[0]
            else:
                ret[k] = [w for w in v]
    return ret


def load_function(filename):
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
    message += f' in {filename}'
    message += '\nFound {}'.format(', '.join([v[0] for v in _fs]))
    message += '\nPlease create a function with (TagbioData, TagbioResult) arguments.'

    log_exception(RuntimeError, message)


class FCPacket:

    def __init__(self, filename):
        self.filename = filename
        # Serialize the entire packet received from the FC
        self._packet = load_json(self.filename)

        # Get the 'fc' part
        self._request = self._packet.get('request')
        self._fc = self._packet.get('fc')

        self.script = self._packet.get('script')
        self.background = self.script.get('background')
        self.analysis_variables = self.script.get('analysis_variables')
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
        logger.debug(f'{self!r}: script: {json.dumps(self.script, indent=4)}')

        if self.background is not None:
            logger.debug(f'{self!r}: background: {json.dumps(self.background, indent=4)}')
        else:
            logger.debug(f'{self!r}: No background')

        if self.analysis_variables is not None:
            logger.debug(f'{self!r}: analysis variables: {json.dumps(self.analysis_variables, indent=4)}')
        else:
            logger.debug(f'{self!r}: No analysis variables')


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
    _extensions = ('html', 'jpeg', 'pdf', 'png', 'svg', 'csv')

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

    def __repr__(self):
        args = []
        if self.extension:
            args.append(f'extension={self.extension!r}')
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
    def df(self):
        return self._df

    @df.deleter
    def df(self):
        del self._df

    @df.setter
    def df(self, data_frame):
        self._df = data_frame

    @property
    def extension(self):
        if self._extension not in self._extensions:
            msg = f'{self!r}: Extension {self._extension!r} not valid. Chose from {self._extensions}'
            log_exception(ValueError, msg)
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
                message = 'Please create either a matplotlib or plotly figure'
                log_exception(ValueError, message)

        elif what == 'data':
            path = self.path
            if self.extension != 'csv':
                message = 'Your output extension is {}. Setting to "csv"'.format(self.extension)
                logger.warning(message)
                path = self.path + '.csv'
            logger.info('Storing TagbioResult data to {}'.format(path))
            float_format = '%.4f'
            self.df.to_csv(path, float_format=float_format)
            logger.info('Stored')
