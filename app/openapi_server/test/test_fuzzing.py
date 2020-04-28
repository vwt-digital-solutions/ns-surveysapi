# flake8: noqa
import adal

import config
from openapi3_fuzzer import FuzzIt
from openapi_server.test import BaseTestCase


def get_token():
    """
    Create a token for testing
    :return:
    """
    oauth_expected_authenticator = config.OAUTH_E2E_AUTHORITY_URI
    client_id = config.OAUTH_E2E_APPID
    client_secret = config.OAUTH_E2E_CLIENT_SECRET
    resource = config.OAUTH_E2E_EXPECTED_AUDIENCE

    # get an Azure access token using the adal library
    context = adal.AuthenticationContext(oauth_expected_authenticator)
    token_response = context.acquire_token_with_client_credentials(
        resource, client_id, client_secret)

    access_token = token_response.get('accessToken')
    return access_token


class TestvAPI(BaseTestCase):

    def test_fuzzing(self):
        FuzzIt("../openapi/openapi.yaml", get_token(), self)
