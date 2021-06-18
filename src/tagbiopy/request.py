import logging
import json
import requests

from abc import ABC, abstractmethod

from .logging import LOGGER_NAME
from .utils import list_attributes, list_methods, list_properties, log_exception, to_json

SCHEME = 'https'
TIMEOUT = None
DEFAULT_HOST = 'http://localhost:8000'
DOMAIN = 'tag.bio'
API_METHODS = ('/a', '/p', '/q', '/s', '/t')

# In /q requests
HEADER_DELIMITER=': '

logger = logging.getLogger(LOGGER_NAME)


class _Request(ABC):
    """
    The Parent class is a template class for all fc requests. Requires a host and an API method.

    The class handles POST requests using the requests python library. A post request requires
    an url (set at object instantiation) and data, a json-string version of the payload dictionary.

    The url property is generated from the 'host' argument. If the host is 'localhost', then it
    defaults to http://localhost:8000. Otherwise, the url is created from the host names using
    "https://<host>.tag.bio". The API methods are chosen from ('/a', '/p', '/q', '/s', '/t').

    The payload property has setter, getter and deleter. The payload dictionary is prepared by
    the abstract method 'prepare_payload' which is then used to set the payload property. This method
    can only be provided in child classes. When the payload property is set, the data property
    (used in the API calls) is then serialized by applying json.dumps to it.

    These two properties, url and data, are prerequisites for issuing an http POST request. The post
    property holds requests.post object. POST response can be accessed through the 'as_dict' property, which
    is a shorthand for serializing the object.

    In order to change/update the POST request, one needs to modify the payload and then examine the
    content of the post property.

    The subclasses SRequest, PRequest, QRequests, etc. all have the correct url assigned as the character
    in the API method. For example, SRequest handles the '/s' API method.
    """
    method_ = None

    def __init__(self, host:str, api_key:str = None) -> None:
        """
        
        :param host: str.
        """
        logger.info(f'{self.__class__}: Initialize')
        self.host = host
        self._api_key = api_key

        self.api_method = self._validate_api_method()

        self.url = self._set_url(self.host, self.api_method)
        self._payload = None

        logger.debug(f'{self}')
        logger.info(f'{self!r}: Initialized')

    def __repr__(self):
        return f'{self.__class__.__name__}(host={self.host!r})'

    def __str__(self):
        ret = f'{self!r}:\n'
        ret += '  Attributes:\n'
        ret += '\n'.join([f'    {v}' for v in list_attributes(self, include_private=True)])
        ret += '\n'
        ret += '  Properties:\n'
        ret += '\n'.join([f'    {v}' for v in list_properties(self.__class__, include_private=True)])
        ret += '\n'
        ret += '  Methods:\n'
        ret += '\n'.join([f'    {v}' for v in list_methods(self.__class__, include_private=True)])
        return ret

    @staticmethod
    def _set_url(host, api_method):
        if host == 'localhost':
            base_url = DEFAULT_HOST
        else:
            # Not sure how Damir's url method generalizes... 
            #base_url = f'{SCHEME}://{host}.{DOMAIN}'
            base_url = host # temp solution (host is a url...)

        url = f'{base_url}{api_method}'

        return url

    def _validate_api_method(self):
        if self.method_ is None:
            msg = f'{self}: API method not defined'
            log_exception(RuntimeError, msg)
        elif self.method_ not in API_METHODS:
            msg = f'{self.method_}: invalid request type. Choose from {API_METHODS}'
            log_exception(ValueError, msg)
        else:
            return self.method_

    @property
    def as_dict(self):
        return self.post.json()

    @property
    def data(self):
        return json.dumps(self.payload, indent=2, default=to_json)

    @property
    def payload(self):
        if self._payload is None:
            msg = f'{repr(self)}: invalid payload "{self._payload}"'
            log_exception(ValueError, msg)
        return self._payload

    @payload.deleter
    def payload(self):
        self._payload = None

    @payload.setter
    def payload(self, val):
        self._payload = val

    @property
    def post(self) -> requests.post:
        logger.info(f'{self!r}: issue POST request')
        logger.debug(f'{self!r}: requests.post(url={self.url!r}, data={self.data}, timeout={TIMEOUT})')

        user = ""
        pwd = ""

        if self._api_key is not None and self._api_key != "":
            api_data = self._api_key.split(":")
            if len(api_data) != 2:
                msg = f'{repr(self)}: invalid api key'
                log_exception(ValueError, msg)
            else:
                user = api_data[0]
                pwd = api_data[1]

        r = requests.post(self.url, data=self.data, 
                auth=(user, pwd),
                timeout=TIMEOUT)
        logger.debug(f'{self!r}: post headers = {json.dumps(dict(r.headers), indent=2)}')
        if r.status_code > 200:
            msg = f'HTTP {r.request.method} response status code {r.status_code}, message: {r.json()["message"]}'
            log_exception(exception_class=requests.HTTPError, message=msg)

        return r

    @abstractmethod
    def prepare_payload(self, *args, **kwargs):
        return None


class SRequest(_Request):
    method_ = '/s'

    def __init__(self, host:str, api_key:str = None) -> None:
        super().__init__(host, api_key)

        self.payload = self.prepare_payload()

    def _timestamp_to_str(self, k):
        from datetime import datetime
        t = int(self.as_dict[k])
        return datetime.fromtimestamp(int(t) // 1000).strftime('%F %X')

    @property
    def data_timestamp(self):
        k = 'data_timestamp'
        return self._timestamp_to_str(k)

    @property
    def start_time(self):
        k = 'start_time'
        return self._timestamp_to_str(k)

    def prepare_payload(self):
        return {}


class PRequest(_Request):
    method_ = '/p'
    request_types = ('get_tags', 'get_protocols')

    def __init__(self, host:str, api_key:str = None) -> None:
        super().__init__(host, api_key)
        self._protocols = None

    @staticmethod
    def _validate_request_type(s):
        if s not in PRequest.request_types:
            msg = f'{s}: invalid request type. Choose from {PRequest.request_types}'
            log_exception(ValueError, msg)
        return s

    @property
    def tags(self):
        self.payload = self.prepare_payload(request_type='get_tags')
        return self.post.json()

    @property
    def protocols(self):
        if self._protocols is None:
            self.payload = self.prepare_payload(request_type='get_protocols')
            self._protocols = self.post.json()
        return [k for k in self._protocols]

    def get_protocol(self, protocol_name):
        try:
            if protocol_name not in self.protocols:
                raise ValueError(f'{protocol_name}: invalid protocol name. Choose from {self.protocols}')
        except ValueError as e:
            logger.info(e, exc_info=True)
            raise

        return self._protocols[protocol_name]

    def prepare_payload(self, request_type):
        request_type = self._validate_request_type(request_type)
        return {'request': request_type}


class QRequest(_Request):
    """Handles '/q' API requests.

    The Parent class is a template class for all fc requests. Requires a host and an API method.
    The intent of the parent class is to handle POST requests using the requests python library.

    POST requests are executed using two parameters: url and data only. The url instance variable
    is set at object instantiation, while data is a json-serialized payload dictionary.

    The url property is generated from the 'host' argument. If host is None, then host defaults to
    http://localhost:8000. Otherwise, the url is created from the host names using
    "https://<host>.tag.bio".

    The payload property has setter, getter and deleter. The payload property is a dictionary
    prepared by the abstract method 'prepare_payload'. Note that setting the payload property
    also sets the data property which is the json-serialized version of the payload.

    These two properties, url and data, are prerequisites for issuing an http POST request. The
    post property holds requests.post object. POST response can be accessed through the 'as_dict'
    property, which is a shorthand for serializing the object, or 'content' which is used when
    creating dataframes.

    In order to change/update the POST request, one needs to modify the payload and then examine the
    content of the post property.
    """
    method_ = '/q'
    allowed_methods = ('collection', 'download', 'summary', 'variable')

    def __init__(self, host:str, api_key:str = None) -> None:
        super().__init__(host, api_key)

        # Initialize collection property. No need for summary (not used)
        # and variable (may take too long to return)
        self._collections = None

    def __str__(self):
        ret = super().__str__()
        ret += f'\n  Payload method can be any of {QRequest.allowed_methods}'
        return ret

    @staticmethod
    def _validate_method(s):
        """

        :param s: str, one of
        :return:
        """
        if s not in QRequest.allowed_methods:
            msg = f'{s}: invalid method. Choose from {QRequest.allowed_methods}'
            log_exception(ValueError, msg)
        return s

    @property
    def collections(self):
        if self._collections is None:
            self.payload = self.prepare_payload(method='collection')
            self._collections = self.as_dict
        return self._collections

    def get_content(self, analysis_variables=None, background=None) -> bytes:
        self.payload = self.prepare_payload('download', analysis_variables, background)
        return self.post.content

    def get_variable_obj(self, analysis_variables):
        self.payload = self.prepare_payload(method='variable', analysis_variables=analysis_variables)
        return self.as_dict

    def prepare_payload(self, method, analysis_variables=None, background=None) -> dict:
        """
        If 'header_delimiter' is not specified, the default is '='

        :param method: str
        :param analysis_variables:
        :param background:
        :return: dict, to be serialized into data param in POST request
        """
        method = self._validate_method(method)
        ret = {
            'script': {
                'method': method,
                'header_delimiter': HEADER_DELIMITER
            },
            'stringify_names': True
        }
        if analysis_variables is not None:
            ret['script'].update({'analysis_variables': analysis_variables})
        if background is not None:
            ret['script'].update({'background': background})

        return ret
