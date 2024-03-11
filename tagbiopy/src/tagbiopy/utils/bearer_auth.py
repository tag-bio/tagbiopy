from requests.auth import AuthBase


class BearerAuth(AuthBase):
    def __init__(self, _auth):
        self.auth = _auth

    def __call__(self, _r):
        _r.headers["authorization"] = self.auth
        return _r

