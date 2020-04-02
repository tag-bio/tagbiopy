import json
import os

from collections import namedtuple

import requests

from tagbiopy.exceptions import TagbioPyError


def fc_decoder(name, packet):
    if isinstance(packet, str):
        packet = json.dumps(packet)

    return namedtuple(name, packet.keys())(*packet.values())


def json_to_object(packet):
    import types

    return json.loads(packet, object_hook=lambda d: types.SimpleNamespace(**d))


def load_json(filename):
    with open(filename) as fh:
        return json.load(fh)


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
    raise TagbioPyError(message)


def serialize(packet):
    if isinstance(packet, str):
        packet = json.loads(packet)

    if isinstance(packet, dict):
        return packet

    raise TagbioPyError('packet type: {}'.format(type(packet)))


def set_payload(target='protocol_instance', api_key=None, **kwargs):
    if target == 'protocol_instance':
        ret = {
            'zip': True,
            'groups': ['developer']
        }
    else:
        if api_key is None:
            api_key = ''
        ret = {
            'api_key': api_key
        }

    ret.update(kwargs)

    return json.dumps(ret, indent=2)


def turn_to_df(content):
    import pandas as pd
    import io

    encoded_content = str(content, 'utf-8')
    return pd.read_csv(io.StringIO(encoded_content))


class FC:

    def __init__(self, filename):

        # Serialize the entire packet received from the FC
        self._packet = load_json(filename)

        # Get the 'fc' part
        self._fc = self._packet.get('fc')

        self.name = self._fc.get('name')
        self._url = None
        self.api_key = self._packet.get('api_key', "")

        # Establish what kind of protocol is requested
        self.protocol_instance = self._packet.get('protocol_instance')
        self.script = self._packet.get('script')
        self.test_passed_protocol()

        # Take care of passthrough arguments
        self.passthrough_arguments = self._packet.get('passthrough_arguments')

        # Payload
        self._payload = None

        # Requests object instance
        self._r = None

    def __repr__(self):
        ret = 'class {}: name: {}, url: {}'.format(self.__class__.__name__, self.name, self.url)
        ret += ', packet: \n'
        ret += json.dumps(self._packet, indent=2)
        return '<{}>'.format(ret)

    def test_passed_protocol(self):
        if self.protocol_instance is None and self.script is None:
            raise TagbioPyError('You need to pass either a protocol_instance or a download_script')

    @property
    def payload(self):
        if self._payload is None:
            if self.protocol_instance:
                _protocol_instance = {'protocol_instance': self.protocol_instance}
                self._payload = set_payload(target='protocol_instance', **_protocol_instance)
            elif self.script:
                _script = self.script
                _script.update({'passthrough_arguments': self.passthrough_arguments})
                self._payload = set_payload(target='script', **_script)
        return self._payload

    @property
    def url(self):
        if self._url is None:
            self._url = os.path.join(self._fc.get('url'), 'q')
        if self._url is None:
            raise TagbioPyError('No url in the packet: {}'.format(str(self._packet)))
        return self._url


class TagbioData:

    def __init__(self, url, payload):
        self.url = url
        self.payload = payload

        self._r = None
        self._df = None

    @property
    def df(self):
        if self._df is None:
            self._df = turn_to_df(self.r.content)
        return self._df

    @property
    def r(self):
        if self._r is None:
            self._r = requests.post(self.url, data=self.payload)
        return self._r

    def get_data_frame(self, entity_id=None, collection=None):
        if entity_id is None and collection is None:
            return self.df

        columns = [entity_id]
        values = [v for v in self.df.columns if v.startswith(collection)]
        columns.extend(values)

        ret = self.df.copy()[columns]
        ret = ret.set_index(entity_id)
        return ret


class TagbioResult:

    _extensions = ('html', 'jpeg', 'pdf', 'png', 'svg', 'csv')

    def __init__(self, extension='pdf', path=None, path_mutable=True):
        """
        :param extension: str, type of output where the df is going to go
        :param path: path, private, where the df will be stored
        """

        if extension not in self._extensions:
            message = f'Extension "{extension}" not valid.'
            message += ' Please choose from {}'.format(', '.join(self._extensions))
            raise TagbioPyError(message)

        self.extension = extension
        # Keep the path private
        self.__path = path
        self._path_mutable = path_mutable

        # For lazy loading of the dataframe
        self._df = None
        # Handle on the figure plotted from the _df
        self._fig = None

    def __repr__(self):
        ret = '<class {}:'.format(self.__class__.__name__)
        ret += f' extension: {self.extension}'
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
            del self.__path

    @path.setter
    def path(self, value):
        if self._path_mutable:
            self.__path = value

    def save(self):
        print(self)
        if self.extension == 'csv':
            float_format = '%.4f'
            self.df.to_csv(self.path, float_format=float_format)
        else:
            self.fig.savefig(self.path, format=self.extension)
