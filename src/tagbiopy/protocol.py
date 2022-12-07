import json
import logging
import os

import pandas as pd
import requests

from tagbiopy import logger
from tagbiopy.fc import FC
from tagbiopy.utils import content_to_dataframe, load_json, log_exception


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


def _set_payload(target, api_key=None, **kwargs):
    if target == 'protocol_instance':
        ret = {
            'zip': True,
            'groups': ['developer']
        }
    elif target == 'script':
        if api_key is None:
            api_key = ''
        ret = {
            'api_key': api_key
        }
    else:
        msg = f'Invalid target: {target}. Should be either "protocol_instance" or "script"'
        log_exception(ValueError, msg)
        return

    ret.update(kwargs)

    return json.dumps(ret, indent=2)


class FCPacket:

    def __init__(self, filename):
        self.__filename = filename
        # Serialize the entire packet received from the FC
        self._packet = load_json(self.__filename)

        # Get the 'fc' part
        self._fc = self._packet.get('fc')

        self.name = self._fc.get('name')
        self._url = None
        self.api_key = self._packet.get('api_key', "")

        # Establish what kind of protocol is requested
        self.protocol_instance = self._packet.get('protocol_instance')
        self.script = self._packet.get('script')
        self._test_protocol()

        # Take care of passthrough arguments
        self.passthrough_arguments = PassThroughArguments(self._packet.get('passthrough_arguments'))

        # Payload
        self._payload = None

        logger.debug(f'{self!r} initialized')

    def __repr__(self):
        ret = self.__class__.__name__
        ret += f'(filename={self.__filename!r})'
        return ret

    def __str__(self):
        name = [
            f'name={self.name!r}',
            f'url={self.url!r}',
            f'packet:\n{json.dumps(self._packet, indent=2)}']
        return f'{self.__class__!r}: {", ".join(name)}'

    def _test_protocol(self):
        if self.protocol_instance is None and self.script is None:
            msg = 'You need to pass either a "protocol_instance" or a "download_script"'
            log_exception(ValueError, msg)

    @property
    def payload(self):
        if self._payload is None:
            if self.protocol_instance:
                _protocol_instance = {'protocol_instance': self.protocol_instance}
                self._payload = _set_payload(target='protocol_instance', **_protocol_instance)
            elif self.script:
                _script = self.script
                _script.update({'passthrough_arguments': self._packet.get('passthrough_arguments')})
                self._payload = _set_payload(target='script', **_script)
        return self._payload

    @property
    def url(self):
        if self._url is None:
            self._url = os.path.join(self._fc.get('url'), 'q')
        if self._url is None:
            raise ValueError('No url in the packet: {}'.format(str(self._packet)))
        return self._url

    @property
    def post(self):
        logger.info(f'{self!r}: issue POST request')
        logger.debug(f'{self!r}: requests.post(url={self.url!r}, data={self.payload})')
        r = requests.post(self.url, data=self.payload)
        logger.debug(f'{self!r}: post headers = {json.dumps(dict(r.headers), indent=2)}')
        if r.status_code > 200:
            msg = f'HTTP {r.request.method} response status code {r.status_code}, message: {r.json()["message"]}'
            log_exception(exception_class=requests.HTTPError, message=msg)
        return r


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

    def __str__(self):
        ret = '<class {}:'.format(self.__class__.__name__)
        ret += ', attributes: '
        ret += ', '.join(['{} ({})'.format(k, str(type(getattr(self, k)))) for k in self.attributes])
        ret += '>'
        return ret

    @property
    def attributes(self):
        if self._attributes is None:
            self._attributes = sorted([k for k in self.__dict__.keys() if not k.startswith('_')])
        return self._attributes

    def get(self, name):
        if name not in self.attributes:
            message = f'{name}: Invalid attribute name.'
            message += f' Please choose from: {self.attributes}'
            raise ValueError(message)
        return getattr(self, name)


class TagbioData:

    def __init__(self, fc_packet):
        self.__fc_packet = fc_packet
        self.fc_packet = FCPacket(self.__fc_packet)
        self.passthrough_arguments = self.fc_packet.passthrough_arguments

        self._df = None
        self._entity_collection = None

        logger.debug(f'{self!r} initialized')

    def __repr__(self):
        ret = self.__class__.__name__
        ret += f'(fc_packet={self.__fc_packet!r}, '
        ret += f'entity_collection={self.entity_collection!r})'
        return ret

    def __str__(self):
        ret = '<class {}:'.format(self.__class__.__name__)
        ret += ' df: {}'.format(str(self.df.shape))
        ret += '>'
        return ret

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            self._df = content_to_dataframe(self.fc_packet.post.content, self.entity_collection)
            logger.debug(f'df shape: {self._df.columns}')
            logger.debug(f'Default columns: {self._df.columns}')
        return self._df

    @property
    def entity_collection(self) -> str:
        if self._entity_collection is None:
            self._entity_collection = FC().entity_collection.collection
        return self._entity_collection


class TagbioResult:
    _extensions = ('html', 'jpeg', 'pdf', 'png', 'svg', 'csv')

    def __init__(self, extension='html', path=None, path_mutable=True):
        """
        :param extension: str, type of output where the df is going to go
        :param path: path, private, where the df will be stored
        """

        if extension not in self._extensions:
            message = f'Extension "{extension}" not valid.'
            message += ' Please choose from {}'.format(', '.join(self._extensions))
            log_exception(ValueError, message)

        self.extension = extension
        # Keep the path private
        self.__path = path
        self._path_mutable = path_mutable

        # For lazy loading of the dataframe
        self._df = None
        # Handle on the figure plotted from the _df
        self._fig = None

    def __repr__(self):
        ret = self.__class__.__name__
        ret += f'(extension={self.extension}, '
        ret += f'path={self.path}, '
        ret += f'path_mutable={self._path_mutable})'
        return ret

    def __str__(self):
        ret = '<class {}:'.format(self.__class__.__name__)
        ret += f' extension: {self.extension}'
        if self.fig is not None:
            ret += ', fig: {}'.format(type(self.fig))
        if self.__path is not None:
            ret += ', path (private): {}'.format(self.__path)
        if self.df is not None:
            ret += ', dataframe shape: {}'.format(str(self.df.shape))
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
