import os
from abc import ABC, abstractmethod
import json
import logging
import requests


from tagbiopy.utils import normalize_host, to_json
from tagbiopy.config import API_KEY_FILE, load_config


logger = logging.getLogger(__name__)

TIMEOUT = 30
API_METHODS = ('/a', '/p', '/q', '/s', '/t')

# In /q requests
HEADER_DELIMITER = ': '


def _validate(name: str, s: str, allowed: tuple):
    """

    :param name: str, name for s (method, request type, etc.)
    :param s: str
    :param allowed: list, list of allowed values to choose s from
    :return:
    """
    if s not in allowed:
        msg = f'Invalid {name}: {s!r}. Allowed: {allowed!r}'
        raise ValueError(msg)

    return s


def load_api_key(config_file=API_KEY_FILE):
    s = load_config(config_file)

    return s.get('TAGBIO_API_KEY')


class TagBioRequest(ABC):
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
    api_method = None

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        """
        :param fc_name: str, fc name, as in fc-XXXX. Default none, use for running on localhost
        :param host: str, data product host url.
        :param api_key: str; check first if environment variable TAGBIO_API_KEY is set, the
            API_KEY_FILE is present and contains key TAGBIO_API_KEY, and finally the argument api_key
        :param token: str, bearer token, found in request.auth. Use only if api_key is not present

        """
        self.fc_name = fc_name
        self.host = host or os.getenv('TAGBIO_HOST')
        self.api_key = os.getenv('TAGBIO_API_KEY') or load_api_key() or api_key
        self.token = os.getenv('TAGBIO_TOKEN') or token

        # May be used for logging of post_data
        self._indent = None

        self._auth = None
        self._url = None
        self._payload = None

    def __repr__(self):
        args = [f'host={self.host!r}']
        if self.fc_name:
            args.append(f'fc_name={self.fc_name!r}')
        if self.api_key:
            args.append(f"api_key='PROVIDED'")
        if self.token:
            args.append(f"token='PROVIDED'")

        str_repr = f'{self.__class__.__module__}.{self.__class__.__name__}('
        str_repr += ', '.join(args)
        str_repr += ')'
        return str_repr

    @property
    def as_dict(self):
        return self.post.json()

    @property
    def auth(self):
        if self._auth is None:
            # No need for auth if working on localhost
            if self.host is None:
                return self._auth
            # If api_key is present, use it
            if self.api_key is not None:
                from tagbiopy.utils.basic_auth import BasicAuth
                self._auth = BasicAuth(self.api_key)
                return self._auth
            # Use token only if api_key is not present
            else:
                if self.token is not None:
                    from tagbiopy.utils.bearer_auth import BearerAuth
                    self._auth = BearerAuth(self.token)
        return self._auth

    @property
    def post_data(self):
        return json.dumps(self.payload, indent=self._indent, default=to_json)

    @property
    def payload(self):
        if self._payload is None:
            msg = f'{repr(self)}: invalid payload "{self._payload}"'
            logger.error(msg)
            raise ValueError(msg)
        return self._payload

    @payload.deleter
    def payload(self):
        self._payload = None

    @payload.setter
    def payload(self, val):
        self._payload = val

    @property
    def post_kwargs(self):
        kwargs = {
            'timeout': TIMEOUT,
            'headers': {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }
        }
        if self.auth is not None:
            kwargs.update({'auth': self.auth})

        return kwargs

    @property
    def post(self) -> requests.post:
        try:
            logger.info(f'{self!r}: issue POST request to {self.url}')
            logger.debug(f'{self!r}: kwargs={self.post_kwargs}, data={self.post_data}')
            r = requests.post(self.url, data=self.post_data, **self.post_kwargs)

            logger.info(f'POST response status code {r.status_code}, content: {r.content[:70]} ...')
            r.raise_for_status()
            return r
        except (requests.HTTPError, requests.ConnectionError) as e:
            logger.error(f'{self!r}: {e}')
            raise

    @abstractmethod
    def prepare_payload(self, *args, **kwargs):
        return None

    @property
    def url(self):
        if self._url is None:
            self._url = normalize_host(self.host, self.fc_name) + self.api_method

        return self._url


class SRequest(TagBioRequest):
    api_method = '/s'

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        super().__init__(fc_name, host, api_key, token)

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


class PRequest(TagBioRequest):
    api_method = '/p'
    request_types = ('get_tags', 'get_protocols')

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        super().__init__(fc_name, host, api_key, token)
        self._protocols = None

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
        request_type = _validate('request type', request_type, PRequest.request_types)
        return {'request': request_type}


class QRequest(TagBioRequest):
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
    api_method = '/q'
    allowed_methods = ('collection', 'download', 'summary', 'variable')

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        super().__init__(fc_name, host, api_key, token)

        # Initialize collection property. No need for summary (not used)
        # and variable (may take too long to return)
        self._q_collections = None

    @property
    def q_collections(self):
        if self._q_collections is None:
            self.payload = self.prepare_payload(method='collection')
            self._q_collections = self.as_dict
        return self._q_collections

    def get_content(self, script=None, analysis_variables=None, background=None) -> bytes:
        if script is None:
            method = 'download'
        else:
            method = None

        self.payload = self.prepare_payload(
            method=method,
            analysis_variables=analysis_variables,
            background=background,
            script=script
        )

        return self.post.content

    def get_variable_obj(self, analysis_variables):
        self.payload = self.prepare_payload(method='variable', analysis_variables=analysis_variables)
        return self.as_dict

    def prepare_payload(self, method=None, analysis_variables=None, background=None, script=None) -> dict:
        """
        If 'header_delimiter' is not specified, the default is '= '.

        :param method: str
        :param analysis_variables:
        :param background:
        :param script:
        :return: dict, to be serialized into data param in POST request
        """
        if method is not None:
            method = _validate('method', method, QRequest.allowed_methods)

        payload = {
            'header_delimiter': HEADER_DELIMITER,
            'stringify_names': True
        }
        if script is not None:
            payload.update(script)
        else:
            payload.update({'method': method})

            if analysis_variables is not None:
                payload.update({'analysis_variables': analysis_variables})
            if background is not None:
                payload.update({'background': background})

        return payload
