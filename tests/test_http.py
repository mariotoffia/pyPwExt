import logging
import io
import pytest
import os
import json

from requests.adapters import Response
from http import HTTPStatus
from typing import Dict, Any
from unittest.mock import patch

from pypwext.pwlogging import PyPwExtLogger
from pypwext.errors import PyPwExtError, PyPwExtHTTPError
from pypwext.pwhttp import LambdaResponse, PyPwExtHTTPSession

from .test_logging import get_new_logger_name


def test_no_region_and_no_aws_regin_env_var_raises_error():
    with pytest.raises(PyPwExtError):
        with PyPwExtHTTPSession():
            pass


def test_default_pypwext_http_session_produces_no_json_content_type_and_accept_headers():
    try:
        os.environ['AWS_REGION'] = 'eu-west-1'

        with io.StringIO() as s:

            logger = PyPwExtLogger(
                service=get_new_logger_name(),
                logger_handler=logging.StreamHandler(s),
                level=logging.DEBUG
            )

            with PyPwExtHTTPSession(logger=logger, api_gateway_mapping=False) as http:
                http.get(
                    'https://api.openaq.org/v1/cities',
                    params={'country': 'SE'},
                    verify=False
                )

            value = s.getvalue()
            vd = json.loads(value.splitlines()[0])

            assert '"url":"https://api.openaq.org/v1/cities?country=SE"' in value
            assert '"Connection":"keep-alive"' in value
            assert '"classification":"NA' in value
            assert '"Content-Type":"application/json"' in value
            assert '"status":200' in value
            assert '"name":"openaq-api"' in value
            assert f'"service":"{logger.service}"' in value
            assert vd['message']['request']['headers']['Content-Type'] == 'application/json'
            assert vd['message']['request']['headers']['Accept'] == 'application/json'
    finally:
        del os.environ['AWS_REGION']


def test_default_headers_are_merged_with_explicit_set():

    try:
        os.environ['AWS_REGION'] = 'eu-west-1'

        with io.StringIO() as s:
            logger = PyPwExtLogger(
                service=get_new_logger_name(),
                logger_handler=logging.StreamHandler(s),
                level=logging.DEBUG
            )

            with PyPwExtHTTPSession(
                logger=logger,
                api_gateway_mapping=False,
                headers={
                    'Content-Type': 'application/text',
                    'Accept': 'application/json'
                }
            ) as http:
                http.get(
                    'https://api.openaq.org/v1/cities',
                    params={'country': 'SE'},
                    headers={'Content-Type': 'application/json'},
                    verify=False
                )

            value = json.loads(s.getvalue().splitlines()[0])
            headers = value['message']['request']['headers']
            assert headers.get('Content-Type') == 'application/json'
            assert headers.get('Accept') == 'application/json'
    finally:
        del os.environ['AWS_REGION']


@pytest.mark.skip(reason="must setup a lambda environment on github account")
def test_api_gateway_execute_adds_headers():

    import requests

    the_headers = None

    def send(request, **kwargs):
        nonlocal the_headers
        the_headers = request.headers

    try:
        os.environ['AWS_REGION'] = 'eu-west-1'
        os.environ['AWS_ACCESS_KEY_ID'] = 'test'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'

        with patch.object(
            requests.sessions.Session, 'send', side_effect=send
        ):
            with PyPwExtHTTPSession(api_gateway_mapping=False) as http:
                http.get(
                    'https://abc123.execute-api.eu-west-1.amazonaws.com/dev/cities',
                    params={'country': 'SE'}
                )

        assert the_headers['x-amz-date'] is not None
        assert 'Credential=test' in the_headers['Authorization']
        assert 'SignedHeaders=host;x-amz-date' in the_headers['Authorization']
        assert 'AWS4-HMAC-SHA256' in the_headers['Authorization']
        assert 'Signature=' in the_headers['Authorization']
    finally:
        del os.environ['AWS_REGION']
        del os.environ['AWS_ACCESS_KEY_ID']
        del os.environ['AWS_SECRET_ACCESS_KEY']


def test_decorator_simple():
    with PyPwExtHTTPSession(api_gateway_mapping=False) as http:

        @http.method(url='https://api.openaq.org/v1/cities', params={'country': '{country}'}, verify_ssl=False)
        def get_cities(country: str, response: Response = None) -> str:

            if response.status_code == HTTPStatus.OK.value:
                return response.text
            else:
                raise PyPwExtHTTPError(
                    code=response.status_code,
                    message=f'Failed to get cities from {country}'
                )

        value = get_cities(country='SE')
        assert '{"country":"SE","name":"Västernorrland","city":"Västernorrland","count":81637329,"locations":2}' in value


def test_decorated_api_gw_auth():

    import requests

    the_headers = None

    def send(request, **kwargs):
        nonlocal the_headers
        the_headers = request.headers
        resp = requests.Response()
        resp.status_code = 200

        resp._content = f"message: {request.body.decode('utf-8')}".encode('utf-8')
        resp.request = request
        return resp

    try:
        os.environ['AWS_REGION'] = 'eu-west-1'
        os.environ['AWS_ACCESS_KEY_ID'] = 'test'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'

        with patch.object(
            requests.sessions.Session, 'send', side_effect=send
        ):
            with PyPwExtHTTPSession() as http:

                @http.method(
                    method='POST',
                    url='https://{gw_id}.execute-api.{AWS_REGION}.amazonaws.com/dev/cities',
                    params={'country': '{country}'},
                    body='body'
                )
                def do_http(gw_id: str, country: str, body: str, response: requests.Response = None) -> str:
                    """Gets the cities from a specific country."""
                    return f'processed response: {response.text}'

                value = do_http('abc123', 'SE', 'the body')
                assert 'processed response: message: the body' in value

        assert the_headers['x-amz-date'] is not None
        assert 'Credential=test' in the_headers['Authorization']
        assert 'SignedHeaders=host;x-amz-date' in the_headers['Authorization']
        assert 'AWS4-HMAC-SHA256' in the_headers['Authorization']
        assert 'Signature=' in the_headers['Authorization']
    finally:
        del os.environ['AWS_REGION']
        del os.environ['AWS_ACCESS_KEY_ID']
        del os.environ['AWS_SECRET_ACCESS_KEY']


@pytest.mark.skip(reason="must setup a lambda on other account to test it from GitHub Actions")
def test_decorator_lambda_func():
    with PyPwExtHTTPSession(api_gateway_mapping=False) as http:

        @http.method(
            method='FUNC',
            url='arn:aws:lambda:eu-west-1:<account>:function:mario-unit-test-function',
            params={'country': '{country}'}
        )
        def get_cities(country: str, response: LambdaResponse = None) -> str:

            if response.StatusCode == HTTPStatus.OK.value:
                return response.payload_as_text()
            else:
                raise PyPwExtHTTPError(
                    code=response.StatusCode,
                    message=f'Failed to get cities from {country}',
                    details={
                        'error': response.payload_as_text()
                    }
                )

        try:
            value = get_cities(country='SE')
        except Exception as e:
            value = e.details['error']
        assert '{"country": "SE", "name": "Västernorrland", "city": "Västernorrland", "count": 81637329, "locations": 2}' in value


@pytest.mark.skip(reason="must setup a lambda on other account to test it from GitHub Actions")
def test_manual_lambda_func_invoke():
    with PyPwExtHTTPSession(api_gateway_mapping=False) as http:
        result = http.func(
            url='mario-unit-test-function',
            params={'country': 'SE'})

        assert result.StatusCode == HTTPStatus.OK.value
        assert '"city": "Västernorrland"' in result.payload_as_text()


@pytest.mark.skip(reason="must setup a lambda on other account to test it from GitHub Actions")
def test_decorator_lambda_func_partial_arn():

    with PyPwExtHTTPSession(api_gateway_mapping=False) as http:

        @http.method(
            method='FUNC',
            url='function:mario-unit-test-function',
            params={'country': '{country}'}
        )
        def get_cities(country: str, response: LambdaResponse = None) -> str:

            if response.StatusCode == HTTPStatus.OK.value:
                return response.payload_as_text()
            else:
                raise PyPwExtHTTPError(
                    code=response.StatusCode,
                    message=f'Failed to get cities from {country}',
                    details={
                        'error': response.payload_as_text()
                    }
                )

        try:
            value = get_cities(country='SE')
        except Exception as e:
            value = e.details['error']
        assert '{"country": "SE", "name": "Västernorrland", "city": "Västernorrland", "count": 81637329, "locations": 2}' in value


@pytest.mark.skip(reason="must setup a lambda on other account to test it from GitHub Actions")
def test_decorator_lambda_event():
    with PyPwExtHTTPSession(api_gateway_mapping=False) as http:

        @http.method(
            method='EVENT',
            url='arn:aws:lambda:eu-west-1:<account>:function:mario-unit-test-function',
            body='body'
        )
        def get_cities(body: Dict[str, Any], response: LambdaResponse = None) -> str:

            if response.StatusCode == HTTPStatus.ACCEPTED.value:
                return json.dumps(response.ResponseMetadata)
            else:
                raise PyPwExtHTTPError(
                    code=response.StatusCode,
                    message=f'Failed to get cities from {body}',
                    details={
                        'error': response.payload_as_text()
                    }
                )

        try:
            value = get_cities({'country': 'SE'})
        except Exception as e:
            value = e.details['error']
        assert ' "HTTPStatusCode": 202' in value
