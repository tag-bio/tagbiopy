from requests.auth import HTTPBasicAuth


class BasicAuth(HTTPBasicAuth):
    # If api_key is passed, it looks like: "email:uuid". Therefore, split on ':' and
    # pass the elements of the list as the username and password in HTTPBasicAuth

    def __init__(self, api_key: str):
        """
        Initilize the BasicAuth class

        :param api_key: str, generated from the front end
        """
        self.username, self.password = api_key.split(':')
        super(BasicAuth, self).__init__(username=self.username, password=self.password)
