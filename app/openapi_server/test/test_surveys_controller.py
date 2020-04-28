# coding: utf-8

from __future__ import absolute_import
import unittest
import adal
import config

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


class TestDefaultController(BaseTestCase):
    """DefaultController integration test stubs"""

    def test_get_forms_list(self):
        """Test case for get_forms_list

        
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + get_token(),
        }
        response = self.client.open(
            '/surveys',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_registrations_as_csv(self):
        """Test case for get_registrations_as_csv

        Retrieve a csv file
        """
        headers = { 
            'Accept': 'text/csv',
            'Authorization': 'Bearer ' + get_token(),
        }
        response = self.client.open(
            '/surveys/{survey_id}/registrations/csvfiles'.format(survey_id=config.SURVEYS_ID),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_registrations_as_zip(self):
        """Test case for get_registrations_as_zip

        Retrieve a zip file
        """
        headers = { 
            'Accept': 'application/zip',
            'Authorization': 'Bearer ' + get_token(),
        }
        response = self.client.open(
            '/surveys/{survey_id}/registrations/archives'.format(survey_id=config.SURVEYS_ID),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_registrations_attachments(self):
        """Test case for get_registrations_attachments

        Get list of fotos per registrations
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + get_token(),
        }
        response = self.client.open(
            '/surveys/{survey_id}/registrations/{registration_id}/images'.format(survey_id=config.SURVEYS_ID, registration_id=2),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_registrations_list(self):
        """Test case for get_registrations_list

        Get a list of available registrations
        """
        headers = {
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + get_token(),
        }
        response = self.client.open(
            '/surveys/{survey_id}/registrations'.format(survey_id=config.SURVEYS_ID),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_single_images_archive(self):
        """Test case for get_single_images_archive

        Download a single of registrations image folder as a zip archive
        """
        headers = {
            'Accept': 'application/zip',
            'Authorization': 'Bearer ' + get_token(),
        }
        response = self.client.open(
            '/surveys/{survey_id}/registrations/{registration_id}/images/archives'.format(survey_id=config.SURVEYS_ID, registration_id=2),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_surveys_nonce(self):
        """Test case for get_surveys_nonce

        
        """
        headers = { 
            'Accept': 'text/csv',
        }
        response = self.client.open(
            '/surveys/{nonce}'.format(nonce='nonce_example'),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
# flake8: noqa
