from abc import ABC, abstractmethod
import os
import json
import logging

import pandas as pd
import requests

from tagbiopy import logger, DEFAULT_HOST, DOMAIN, KUNG, KUNG_CAPACITORS
from tagbiopy.utils import get_post_headers, log_exception, to_json, validate

SCHEME = "https"
TIMEOUT = None
API_METHODS = ('/a', '/p', '/q', '/s', '/t')

# In /q requests
HEADER_DELIMITER = ': '
HOST_CONFIG_JSON = os.path.join(os.environ['HOME'], '.tagbio.json')
HOST_CONFIG_YAML = os.path.join(os.environ['HOME'], '.tagbio.yaml')

# Host may be given as TAGBIO_HOST_URL or (the deployed notebook's convention) TAGBIO_BASE_URL.
# When resolving the host, try both names, in this order.
HOST_KEYS = ('TAGBIO_HOST_URL', 'TAGBIO_BASE_URL')

logger = logging.getLogger()


def _in_plugin_context():
    """True when running as an FC engine plugin (the plugin runner, cli.py:main, sets the sentinel).

    In a plugin the connection + auth come ONLY from the engine packet (host + the invoking user's
    token). The SDK must NEVER fall back to ~/.tagbio.json here: the developer's carte-blanche file
    api_key must not ride along (privilege escalation) -- fail loud instead. Ad-hoc scripts (no
    sentinel) use the file as overridable defaults. Mirrors connect_tagbio.R in the R SDK, which sets
    the same TAGBIO_PLUGIN_CONTEXT sentinel.
    """
    return os.environ.get('TAGBIO_PLUGIN_CONTEXT') == '1'


def _plugin_config_override():
    """Explicit dev opt-in to read ~/.tagbio.json even inside a plugin, for locally testing a
    remote cross-FC call. Deliberate and off by default: a test has no user token, so there is
    nothing to escalate over. Production never sets this. Mirrors TAGBIO_PLUGIN_ALLOW_CONFIG in
    the R SDK.
    """
    return os.environ.get('TAGBIO_PLUGIN_ALLOW_CONFIG') == '1'


def _get_env_setting(var, default_value=None):
    if _in_plugin_context() and not _plugin_config_override():
        # Plugins never read ~/.tagbio.json (or ambient env) for connection/auth, unless a dev has
        # explicitly opted in for a test via TAGBIO_PLUGIN_ALLOW_CONFIG.
        return default_value
    # Precedence: ~/.tagbio.json FILE beats environment, resolved PER KEY (a file that sets only some
    # keys falls through to env for the rest, rather than blanking them out). When resolving the host,
    # accept either TAGBIO_HOST_URL or TAGBIO_BASE_URL. Mirrors tagConnect() in the R SDK.
    file_cfg = {}
    if os.path.exists(HOST_CONFIG_JSON):
        from tagbiopy.utils import load_json
        file_cfg = load_json(HOST_CONFIG_JSON)
    elif os.path.exists(HOST_CONFIG_YAML):
        from tagbiopy.utils import load_yaml
        file_cfg = load_yaml(HOST_CONFIG_YAML)

    keys = HOST_KEYS if var == 'TAGBIO_HOST_URL' else (var,)
    for k in keys:                                    # file wins, per key
        v = file_cfg.get(k)
        if v not in (None, ''):
            return v
    for k in keys:                                    # else the environment
        v = os.environ.get(k)
        if v not in (None, ''):
            return v
    return default_value


def _is_localhost(host):
    """True if `host` targets localhost (any port/scheme).

    The FC HTTP server grants all permissions to requests whose server name is 'localhost'
    (flux-http localhost loophole), on any port -- so the SDK treats any localhost host as no-auth
    http, matching the R SDK. Matches the literal name 'localhost' only (not 127.0.0.1), the same
    as the server.
    """
    if not host:
        return False
    name = host.split('://', 1)[-1].split('/', 1)[0].split(':', 1)[0]
    return name == 'localhost'


class Session(ABC):
    """
    The Parent class is a template class for all fc requests. Requires a host and an API method.

    The class handles POST requests using the requests python library. A post request requires
    an url (set at object instantiation) and data, a json-string version of the payload dictionary.

    The url property is generated from the 'host' argument. If the host is 'localhost', then it
    defaults to http://localhost:8000. Otherwise, the url is created from the host names using
    "https://<host>". The API methods are chosen from ('/a', '/p', '/q', '/s', '/t').

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
    colum_map = {
        'key': 'Name',
        'description': 'Description',
        'displayname': 'Title',
        'link': 'Reference',
        'url': 'url',
        'entity_name_singular': 'Entity',
    }

    def __init__(self, host: str, api_key: str = None, token: str = None) -> None:
        """

        :param host: str, data product host url.
        :param fc_name: str, fc name, as in fc-XXXX. Default none, use for running on localhost
        :param api_key: str
        :param token: str, bearer token, found in request.auth
        """
        logger.info(f'{self.__class__}: Initialize')

        self.host = self._set_host(host)
        self.api_key = self._set_api_key(api_key)
        self.token = token

        # Reset for localhost
        if _is_localhost(self.host):
            self.fc_name = None
            self.api_key = None
            self.token = None

        self._auth = None
        self._products_url = None

        logger.info(f'{self!r}: Initialized')

    def __repr__(self):
        args = [f'host={self.host!r}']
        if self.api_key:
            args.append('api_key=PROVIDED')

        str_repr = f'{self.__class__.__name__}('
        str_repr += ', '.join(args)
        str_repr += ')'
        return str_repr

    def _set_host(self, host):
        # Resolve the host (explicit arg, else env / ~/.tagbio.json, else localhost), then classify:
        # a localhost host (any port) is no-auth http; anything else is a remote host over https.
        if host is None:
            host = _get_env_setting('TAGBIO_HOST_URL', default_value=DEFAULT_HOST)
        if _is_localhost(host):
            if not host.startswith(('http://', 'https://')):
                host = f'http://{host}'
        elif host.startswith('http://'):
            host = host.replace('http://', 'https://')
        elif not host.startswith('https://'):
            host = f'https://{host}'
        return host

    def _set_api_key(self, api_key):
        if _is_localhost(self.host):
            # We don't need an API key on localhost
            logger.debug(f'API key not needed on {self.host}')
            return

        if api_key is None:
            api_key = _get_env_setting('TAGBIO_API_KEY')

        return api_key

    @property
    def auth(self):
        if self._auth is None:
            # A token (delegated user auth) takes priority; otherwise basic auth from the api_key
            # ("email:uuid"). Localhost needs no auth.
            if self.token:
                from .utils import BearerAuth
                self._auth = BearerAuth(self.token)
            elif self.api_key and not _is_localhost(self.host):
                self._auth = tuple(self.api_key.split(':'))
            elif not _is_localhost(self.host):
                msg = f'{self!r}: Invalid authentication host {self.host!r}'
                logger.warning(msg)
                raise RuntimeError(msg)
            else:
                msg = f'{self!r}: No authentication provided, no authentication needed with {self.host!r}'
                logger.debug(msg)

        return self._auth

    @property
    def post(self) -> requests.post:
        logger.debug(f'{self!r}: issue POST request to {self.products_url!r}')
        if self.products_url is None:
            return

        try:
            r = requests.get(self.products_url, auth=self.auth)
            logger.debug(f'{self!r}: headers: {get_post_headers(r)}')
            logger.info(
                f'HTTP {r.request.method} response status code {r.status_code}, content: {r.content[:70]}'
            )
            r.raise_for_status()
            return r
        except (requests.HTTPError, requests.ConnectionError) as e:
            logger.error(e)
            raise

    def summary(self, ):
        if self.post is None:
            logger.warning(f'{self!r}: No information on other data products from {self.host!r}')
            return
        s = self.post.json()
        df = pd.DataFrame(s)
        columns = [v for v in self.colum_map.keys()]
        df = df[columns]
        return df.rename(columns=self.colum_map)

    @property
    def products_url(self):
        if self._products_url is None:
            if not _is_localhost(self.host):
                self._products_url = os.path.join(self.host, KUNG_CAPACITORS)
            else:
                self._products_url = None
        return self._products_url


class _Request(ABC):
    """
    The Parent class is a template class for all fc requests. Requires a host and an API method.

    The class handles POST requests using the requests python library. A post request requires
    an url (set at object instantiation) and data, a json-string version of the payload dictionary.

    The url property is generated from the 'host' argument. If the host is 'localhost', then it
    defaults to http://localhost:8000. Otherwise, the url is created from the host names using
    "https://<host>". The API methods are chosen from ('/a', '/p', '/q', '/s', '/t').

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

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        """

        :param host: str, data product host url.
        :param fc_name: str, fc name, as in fc-XXXX. Default none, use for running on localhost
        :param api_key: str
        :param token: str, bearer token, found in request.auth
        """
        logger.info(f'{self.__class__}: Initialize')
        self.fc_name = fc_name
        self.host = self._set_host(host)
        self.api_key = self._set_api_key(api_key)
        self.token = token

        # Reset for localhost
        if _is_localhost(self.host):
            self.fc_name = None
            self.api_key = None
            self.token = None

        self._api_method = None
        self._auth = None
        self._url = None
        self._payload = None

        self._user = None
        self._pwd = None
        self._auth = None

        # json.dump and json.dumps argument
        self.indent = None

        logger.info(f'{self!r}: Initialized')

    def __repr__(self):
        args = [f'host={self.host!r}']
        if self.fc_name:
            args.append(f'fc_name={self.fc_name!r}')
        if self.api_key:
            args.append('api_key=PROVIDED')
        if self.token:
            args.append('token=PROVIDED')

        str_repr = f'{self.__class__.__name__}('
        str_repr += ', '.join(args)
        str_repr += ')'
        return str_repr

    def _set_host(self, host):
        # Resolve the host (explicit arg, else env / ~/.tagbio.json, else localhost), THEN classify
        # and build the URL -- uniformly, whether the host was passed or resolved from config. This is
        # what fixes the bare FC(fc_name=...) case: a remote host resolved from ~/.tagbio.json now gets
        # the /<KUNG>/<fc_name> path appended, instead of hitting a bare /q (405).
        if host is None:
            host = _get_env_setting('TAGBIO_HOST_URL', default_value=DEFAULT_HOST)
        if _is_localhost(host):
            # localhost, any port: a single FC over http, no /<KUNG>/<fc_name> path, no auth
            if not host.startswith(('http://', 'https://')):
                host = f'http://{host}'
            if self.fc_name is not None:
                self.fc_name = None
        else:
            # remote: <KUNG>/<fc_name>; strip a trailing slash first so we don't build '//'
            host = host.rstrip('/')
            # Respect an explicit scheme (R parity): an internal cluster endpoint is plain http
            # (e.g. http://kung.tagbio-app.svc.cluster.local:8000) and force-upgrading it to https
            # yields an SSL WRONG_VERSION_NUMBER. Only default to https when no scheme was given.
            if not host.startswith(('http://', 'https://')):
                host = f'{SCHEME}://{host}'
            if KUNG not in host:
                host = f'{host}/{KUNG}'
            if self.fc_name is not None and self.fc_name not in host:
                host = f'{host}/{self.fc_name}'
        return host

    def _set_api_key(self, api_key):
        if _is_localhost(self.host):
            # We don't need an API key on localhost
            logger.debug(f'API key not needed on {self.host}')
            return

        # Ad-hoc default: fall back to ~/.tagbio.json for the api_key. In a plugin this is a no-op --
        # _get_env_setting refuses the file when the plugin sentinel is set (see _in_plugin_context).
        if api_key is None:
            api_key = _get_env_setting('TAGBIO_API_KEY')

        return api_key

    @property
    def api_method(self):
        if self._api_method is None:
            msg = f'{self!r}: '
            if self.method_ is None:
                msg += f'API method not defined. Choose from {API_METHODS}'
                logger.warning(msg)
                raise RuntimeError(msg)
            elif self.method_ not in API_METHODS:
                msg += f'API method {self.method_!r} illegal. Choose from {API_METHODS}'
                logger.warning(msg)
                raise ValueError(msg)
            else:
                self._api_method = self.method_
        return self._api_method

    @property
    def as_dict(self):
        return self.post.json()

    @property
    def auth(self):
        if self._auth is None:
            # If api_key is passed, it looks like: "email:uuid". Therefore, split on ':' and
            # pass the elements of the list as the username and password in HTTPBasicAuth
            http_basic_auth = None
            bearer_auth = None
            if self.api_key:
                if not _is_localhost(self.host):
                    from requests.auth import HTTPBasicAuth
                    http_basic_auth = HTTPBasicAuth(*self.api_key.split(':'))

            if self.token:
                from .utils import BearerAuth
                bearer_auth = BearerAuth(self.token)

            # If both defined, use token. Token always has the highest priority.
            # Then go one by one
            if http_basic_auth is not None and bearer_auth is not None:
                self._auth = bearer_auth
            elif bearer_auth is not None:
                self._auth = bearer_auth
            elif http_basic_auth is not None:
                self._auth = http_basic_auth
            else:
                if not _is_localhost(self.host):
                    msg = f'{self!r}: Invalid authentication host {self.host!r}'
                    logger.warning(msg)
                    raise RuntimeError(msg)
                else:
                    msg = f'{self!r}: No authentication provided, no authentication needed with {self.host!r}'
                    logger.debug(msg)

        return self._auth

    @property
    def data(self):
        return json.dumps(self.payload, indent=self.indent, default=to_json)

    @property
    def payload(self):
        if self._payload is None:
            msg = f'{repr(self)}: invalid payload "{self._payload}"'
            logger.warning(msg)
            raise ValueError(msg)
        return self._payload

    @payload.deleter
    def payload(self):
        self._payload = None

    @payload.setter
    def payload(self, val):
        self._payload = val

    @property
    def _post_kwargs(self):
        kwargs = {
            'data': self.data,
            'timeout': TIMEOUT
        }

        if self.auth is not None:
            kwargs.update({'auth': self.auth})

        return kwargs

    @property
    def post(self) -> requests.post:
        logger.info(f'{self!r}: issue POST request')
        # Note: do not indent json passed to reqests.post
        self.indent = None
        logger.info(f'{self!r}: requests.post(url={self.url!r})')
        # For logging: set indent to 2 in self.data
        self.indent = 2
        logger.debug(f'{self!r}: _post_kwargs = {self._post_kwargs}')
        # Reset json to no indent
        self.indent = None

        try:
            r = requests.post(self.url, **self._post_kwargs)
            logger.debug(f'{self!r}: headers: {get_post_headers(r)}')
            logger.info(
                f'HTTP {r.request.method} response status code {r.status_code}, content: {r.content[:70]}'
            )
            r.raise_for_status()
            return r
        except (requests.HTTPError, requests.ConnectionError) as e:
            logger.error(e)
            raise

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
            self._url = self.host + self.api_method
        return self._url

    @property
    def user(self):
        if self._user is None:
            if self.api_key and ':' in self.api_key:
                self._user = self.api_key.split(':')[0]
        return self._user


class SRequest(_Request):
    method_ = '/s'

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


class PRequest(_Request):
    method_ = '/p'
    request_types = ('get_tags', 'get_protocols')

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        super().__init__(fc_name, host, api_key, token)
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
        request_type = validate('request type', request_type, PRequest.request_types)
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

    def __init__(self, fc_name: str = None, host: str = None, api_key: str = None,
                 token: str = None) -> None:
        super().__init__(fc_name, host, api_key, token)

        # Initialize collection property. No need for summary (not used)
        # and variable (may take too long to return)
        self._q_collections = None

    def __str__(self):
        ret = super().__str__()
        ret += f'\n  Payload method can be any of {QRequest.allowed_methods}'
        return ret

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
        If 'header_delimiter' is not specified, the default is '= '

        :param method: str
        :param analysis_variables:
        :param background:
        :param script:
        :return: dict, to be serialized into data param in POST request
        """
        if method is not None:
            method = validate('method', method, QRequest.allowed_methods)

        ret = {
            'header_delimiter': HEADER_DELIMITER,
            'stringify_names': True
        }
        if script is not None:
            ret.update(script)
        else:
            ret.update({'method': method})

            if analysis_variables is not None:
                ret.update({'analysis_variables': analysis_variables})
            if background is not None:
                ret.update({'background': background})

        logger.debug(f'{self!r}: payload: {json.dumps(ret, indent=2, default=to_json)}')

        return ret
