from abc import ABC, abstractmethod
import json

import requests

from tagbiopy import logger, DEFAULT_HOST
from tagbiopy.utils import get_post_headers, log_exception, to_json

SCHEME = 'https'
TIMEOUT = None
API_METHODS = ('/a', '/p', '/q', '/s', '/t')

# In /q requests
HEADER_DELIMITER = ': '


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

    def __init__(self, host: str, api_key: str = None) -> None:
        """

        :param host: str.
        """
        logger.info(f'{self.__class__}: Initialize')
        self._host = host
        self.api_key = api_key

        self._api_method = None
        self._auth = None
        self._url = None
        self._payload = None

        self._user = None
        self._pwd = None

        logger.info(f'{self!r}: Initialized')

    def __repr__(self):
        str_repr = f'{self.__class__.__name__}('
        str_repr += ', '.join([f'{v!r}' for v in [self.host, self.api_key] if v])
        str_repr += ')'
        return str_repr

    @property
    def api_method(self):
        if self._api_method is None:
            msg = f'{self!r}: '
            if self.method_ is None:
                msg += f'API method not defined. Choose from {API_METHODS}'
                log_exception(RuntimeError, msg)
            elif self.method_ not in API_METHODS:
                msg += f'API method {self.method_!r} illegal. Choose from {API_METHODS}'
                log_exception(ValueError, msg)
            else:
                self._api_method = self.method_
        return self._api_method

    @property
    def as_dict(self):
        return self.post.json()

    @property
    def data(self):
        return json.dumps(self.payload, indent=2, default=to_json)

    @property
    def host(self):
        if self._host is None:
            self._host = DEFAULT_HOST
        return self._host

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

        post_kwargs = {
            'data': self.data,
            'timeout': TIMEOUT
        }

        # If api_key is passed, it looks like: "email:uuid". Therefore, split on ':' and
        # pass the elements of the list as the username and password in HTTPBasicAuth
        if self.api_key:
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(*self.api_key.split(':'))
            post_kwargs.update({'auth': auth})

        try:
            r = requests.post(self.url, **post_kwargs)
            logger.debug(f'{self!r}: {get_post_headers(r)}')
            if r.ok:
                return r
            else:
                msg = f'HTTP {r.request.method} response status code {r.status_code}, content: {r.content}'
                log_exception(exception_class=requests.HTTPError, message=msg)
        except ConnectionRefusedError as e:
            log_exception(ConnectionRefusedError, str(e))

    @abstractmethod
    def prepare_payload(self, *args, **kwargs):
        return None

    @property
    def pwd(self):
        if self._pwd is None:
            if self.api_key and ':' in self.api_key:
                self._pwd = self.api_key.split(':')[1]
        return self._pwd

    @property
    def url(self):
        if self._url is None:
            self._url = f'{self.host}{self.api_method}'
        return self._url

    @property
    def user(self):
        if self._user is None:
            if self.api_key and ':' in self.api_key:
                self._user = self.api_key.split(':')[0]
        return self._user


class SRequest(_Request):
    method_ = '/s'

    def __init__(self, host: str, api_key: str = None) -> None:
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

    def __init__(self, host: str, api_key: str = None) -> None:
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

    def __init__(self, host: str, api_key: str = None) -> None:
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

        logger.debug(f'{self!r}: payload: {json.dumps(ret, indent=2, default=to_json)}')

        return ret
