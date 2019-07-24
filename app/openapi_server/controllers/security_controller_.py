import config
import logging
from jwkaas import JWKaas

my_jwkaas = None
my_e2e_jwkaas = None

if hasattr(config, 'OAUTH_JWKS_URL'):
    my_jwkaas = JWKaas(config.OAUTH_EXPECTED_AUDIENCE,
                       config.OAUTH_EXPECTED_ISSUER,
                       jwks_url=config.OAUTH_JWKS_URL)


if hasattr(config, 'OAUTH_E2E_JWKS_URL'):
    my_e2e_jwkaas = JWKaas(config.OAUTH_E2E_EXPECTED_AUDIENCE,
                       config.OAUTH_E2E_EXPECTED_ISSUER,
                       jwks_url=config.OAUTH_E2E_JWKS_URL)


def refine_token_info(token_info):
    # no special extensions
    return token_info


def info_from_OAuth2AzureAD(token):
    """
    Validate and decode token.
    Returned value will be passed in 'token_info' parameter of your operation function, if there is one.
    'sub' or 'uid' will be set in 'user' parameter of your operation function, if there is one.
    'scope' or 'scopes' will be passed to scope validation function.

    :param token Token provided by Authorization header
    :type token: str
    :return: Decoded token information or None if token is invalid
    :rtype: dict | None
    """
    intermediate_token = my_jwkaas.get_connexion_token_info(token)

    # e2e tweaks
    if not intermediate_token and my_e2e_jwkaas:
        logging.warning(f'Token is not production, checking e2e')
        token_info = my_e2e_jwkaas.get_connexion_token_info(token)
        if token_info and 'appid' in token_info and token_info['appid'] == config.OAUTH_E2E_APPID:
            logging.warning(f"Using e2e access token for appid {token_info['appid']}")
            intermediate_token = {'scopes': ['surveys.read'], 'sub': 'e2e'}

    return refine_token_info(intermediate_token)
