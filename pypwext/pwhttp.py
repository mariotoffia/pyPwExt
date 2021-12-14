"""Module to handle plain HTTP request with PyPwExt standard re-tries and backoff

    # Basic Usage

    **Simplest possible with all defaults**

    This sample will re-try 10 and use an exponential backoff.
    It also configures which methods and response codes to perform
    the re-try. The others are deemed success or errors.

    ```
    with PyPwExtHTTPSession() as http:
    http.get(
        'https://api.openaq.org/v1/cities',
        params={'country': 'SE'}
    )
    ```

    **When calling an AWS API Gateway endpoint**

    By default the `PyPwExtHTTPSession` will use the `AWS_REGION` environment variable
    to and will search for the pattern `https://{apigw_id}.execute-api.{region}.amazonaws.com`.
    If it finds it, it will configure a `BotoAWSRequestsAuth` for the provided host, region
    and service *execute-api*.

    ```
    with PyPwExtHTTPSession() as http:
    http.get(
        'https://abc123.execute-api.eu-west-1.amazonaws.com/dev/cities',
        params={'country': 'SE'}
    )
    ```

    **Configuring the timeout**

    This sample will log the request and response since it has been configured
    with a `PyPwExtLogger`. It is also possible to configure which classification
    and level the logger should use. This is true for both request and response
    logging.

    ```
    logger = PyPwExtLogger()

    with PyPwExtHTTPSession(
        TimeoutHTTPAdapter(
            timeout=10,
            logger=logger
        )
    ) as http:
        http.get("https://en.wikipedia.org/w/api.php")
    ```

    NOTE:   Since `PyPwExtHTTPSession` do pool connections, it is adviceable to cache
            those in order for faster access.

    The `PyPwExtHTTPSession` also supports decoration of functions to act as HTTP calls.

    **Basic usage**
    ```
    @http(method='GET', url='https://{STAGE}.api.openaq.org/v1/cities', params={'country': '{country}'})
    def cities(country:str, response_body:str, response_code:http.HTTPStatus) -> str:
        if response_code == http.HTTPStatus.OK:
            return f'{country} has {response_body["count"]} cities'
        else:
            raise PyPwExtHTTPError(code=response_code, message=response_body)
    ```

    If using a API Gateway endpoint, it could look like this:
    ```
    @http.method(
        method='GET',
        url='https://{gw_id}.execute-api.{AWS_REGION}.amazonaws.com/dev/cities',
        params={'country': '{country}'}
    )
    def do_http(gw_id: str, country: str, response: requests.Response = None) -> str:
        # Gets the cities from a specific country.
        return f"processed response: {response.text}"

    value = do_http('abc123', 'SE')
    ```

    Invoking the lambda using _FUNC_ (synchronous) is as simple as:
    ```
    @http.method(
        method='FUNC',
        url='arn:aws:lambda:eu-west-1:010711114025:function:mario-unit-test-function',
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

    value = get_cities(country='SE')
    ```

"""
import logging
import requests
import json
import os
import chardet

from typing import Optional, Union, Dict, List, Any
from requests.models import Response, PreparedRequest
from requests.structures import CaseInsensitiveDict
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from http import HTTPStatus
from functools import wraps
from aws_requests_auth.boto_utils import BotoAWSRequestsAuth
from boto3 import client as boto_client
from botocore.exceptions import NoRegionError
from botocore.response import StreamingBody
from botocore.config import Config
from base64 import b64encode
from pydantic import BaseModel
from io import BytesIO

from pypwext.pwlogging import PyPwExtLogger
from pypwext.base import InfoClassification, Classification
from pypwext.utils import get_log_level, render_arg_env_string, try_convert_to_dict
from pypwext.errors import PyPwExtInternalError, PyPwExtHTTPError
from pypwext.encoders import PyPwExtJSONEncoder


class LambdaResponse(BaseModel, arbitrary_types_allowed=True):
    """Response model for lambda functions

    The arbitrary_types_allowed is set to `True` due to `StreamingBody`
    is not a `BaseModel`
    """
    StatusCode: int
    """HTTP status code

    The HTTP status code is in the 200 range for a successful request.
    For the RequestResponse invocation type, this status code is `HTTPStatus.OK`.
    For the Event invocation type, this status code is `HTTPStatus.ACCEPTED`.
    For the DryRun invocation type, the status code is `HTTPStatus.NO_CONTENT`.
    """
    FunctionError: Optional[str] = None
    """Error message if any errors occurred during the function execution.

    If present, indicates that an error occurred during function execution.
    Details about the error are included in the response payload.
    """
    LogResult: Optional[str] = None
    """Log result if enabled.

    The last 4 KB of the execution log, which is base64 encoded.
    """
    ResponseMetadata: Optional[Dict[str, Any]] = None
    """Metadata of the response from Lambda."""

    Payload: Optional[StreamingBody] = None
    """The response from the function, or an error object."""
    ExecutedVersion: Optional[str] = None
    """The version of the function that executed.

    The version of the function that executed. When you invoke a function
    with an alias, this indicates which version the alias resolved to.
    """

    def payload_as_dict(self) -> Dict[str, Any]:
        """ Return the payload as a dict.

        Returns:
             The payload as a dict. If no payload an empty dict is returned.
        """
        if self.Payload is None:
            return {}

        return json.loads(self.payload_as_text())

    def payload_as_text(self, encoding: Optional[str] = 'unicode-escape') -> str:
        """ Return the payload as a string.

        Args:
            encoding:   The encoding to use. If None, the encoding is guessed.
                        Default is `unicode-escape`.

        Returns:
             The payload as a string. If no payload an empty string is returned.
        """
        if self.Payload is None:
            return ''

        data = self.Payload.read()

        if encoding is None:
            encoding = chardet.detect(data)['encoding']

        try:
            return str(data, encoding, errors='replace')
        except (LookupError, TypeError):
            return str(data, errors='replace')


class PyPwExtHTTPSession(requests.Session):
    """ PyPwExtHTTPSession is both a session and can decorate HTTP methods.

        # Basic Usage

        ```
        with PyPwExtHTTPSession() as http:
        http.get(
            'https://api.openaq.org/v1/cities',
            params={'country': 'SE'}
        )
        ```
        or via decorator
        ```
        @http(method='GET', url='https://{STAGE}.api.openaq.org/v1/cities', params={'country': '{country}'})
        def cities(country:str, response_body:str, response_code:http.HTTPStatus) -> str:
            if response_code == http.HTTPStatus.OK:
                return f'{country} has {response_body["count"]} cities'
            else:
                raise PyPwExtHTTPError(code=response_code, message=response_body)
        ```

        See module documentation for more information.
    """

    def __init__(
            self,
            adapter: Optional[HTTPAdapter] = None,
            retry: Optional[Retry] = None,
            logger: Optional[PyPwExtLogger] = None,
            api_gateway_mapping: bool = True,
            region: Optional[str] = None,
            headers: Optional[Dict[str, str]] = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            lambda_config: Optional[Config] = None,
    ):
        """Creates a `requests.Session` configured using a HTTPAdapter and Retry.

        Args:
            adapter:    The `HTTPAdapter` to use. If omitted the default
                        `PyPwExtHTTPAdapter` will be used.

            retry:      The `Retry` to use. If omitted the default `PyPwExtRetry`
                        will be used.

            logger:     The `PyPwExtLogger` to use. Only used when request and
                        response logging is wanted.

            api_gateway_mapping:    If set to `True` each get, post, put, delete will be
                                    examined if the *url* has a *execute-api* in the url.
                                    It will then make sure to set the auth to a
                                    `BotoAWSRequestsAuth` object.

            region:     The AWS region to use. This overrides the default behaviour to use
                        *AWS_REGION* environment variable.

            headers:    A dictionary of headers to add to each request in addition to the
                        manually added. Manually added are **always** overriding the default.
                        Defaults are `application/json`.

            lambda_config:  Advanced configuration for lambda. This is only used when a `FUNC`
                            or a `EVENT` method is used. If none is provided, a healthy default
                            is provided. For more information how to use botocore `Config` object, consult
                            https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html#botocore-config.

        Returns:
            A new `requests.Session` configured using the given `HTTPAdapter` and `Retry`.

        If no `headers` the default is used it will set both `Content-Type` and `Accept` to
        ```
        {'Content-Type': 'application/json', 'Accept': 'application/json'}
        ```

        The default behaviour is to use the *AWS_REGION* in combination with *execute-api*
        to detect if it is a API Gateway request. If the region is set explicitly it will
        ise that instead of the environment variable *AWS_REGION*.

        NOTE:   If user sets the auth manually, the auto-mapping of `BotoAWSRequestsAuth`
                will be disabled.

        If the region is not specified, the *AWS_REGION* environment variable is not set
        and the *api_gateway_mapping* is set to `True`, it will raise a `PyPwExtError` with
        code `HTTPStatus.BAD_REQUEST`.
        """
        super().__init__()

        self.adapter = adapter or PyPwExtHTTPAdapter(logger=logger)
        self.adapter.max_retries = retry or PyPwExtRetry()
        self.api_gateway_mapping = api_gateway_mapping
        self.region = region or os.environ.get('AWS_REGION')
        self.headers = headers or {}

        initial_config = Config(
            region_name=self.region,
            connect_timeout=60,
            read_timeout=60,
            retries={
                'total_max_attempts': 10,
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        )

        if lambda_config:
            initial_config = initial_config.merge(lambda_config)

        self.lambda_config = initial_config

        try:
            self.lambda_client = boto_client('lambda', config=self.lambda_config)
        except NoRegionError:
            pass

        self.logger = logger
        if self.logger is None:
            self.logger = PyPwExtLogger()
            self.logger.setLevel(get_log_level(logging.DEBUG))

        if self.api_gateway_mapping and self.region is None:
            raise PyPwExtInternalError(message='AWS_REGION not set and api_gateway_mapping is True')

        self.logger = logger

        self.mount('http://', self.adapter)
        self.mount('https://', self.adapter)

    def prepare_request(self, request):
        """Overridden to set the auth **if** it is a API Gateway request."""

        if request.auth is None and self.api_gateway_mapping:

            idx: int = request.url.find(
                f'.execute-api.{self.region}.amazonaws.com'
            )

            if idx > 0:
                request.auth = BotoAWSRequestsAuth(
                    aws_host=request.url[8:idx + 27 + len(self.region)],
                    aws_region=self.region,
                    aws_service='execute-api',
                )

        if self.headers:
            if request.headers is None:
                request.headers = CaseInsensitiveDict()

            for key, value in self.headers.items():
                if not request.headers.get(key):
                    request.headers[key] = value

        return super().prepare_request(request)

    def method(
            Self,
            _func=None,
            method: str = 'GET',
            url: str = '',
            verify_ssl: bool = True,
            headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, str]] = None,
            body: Optional[str] = None):
        """Decorates the given function with a `PyPwExtHTTPSession` session.

        Args:
            method:     The HTTP method to use: GET, PUT, POST, PATH, DELETE.
                        If LAMBDA invoke, use 'FUNC' or 'EVENT' (async) instead.

            url:        The URL to use. The url string will be interpreted as
                        a format string and evaluated each invocation. When all
                        characters within {} are upper-case, those are replaced
                        with the environment variable. The rest is replaced with
                        the arguments passed to the function.

            verify_ssl: If set to `False` the SSL certificate will not be verified.
                        Default is `True`.

            headers:    A dictionary of headers to add to each request in addition
                        to the defaults set ni `PyPwExtHTTPSession` constructor.
                        The value of each element is also interpreted as with the
                        `url` argument.

            params:     A dictionary of parameters to add to each request. The value of each
                        element is also interpreted as with the `url` argument.

            body:       If any body data is to be sent. This is the name of the parameter
                        containing the body data. If the parameter is not a string, it is
                        formatted using the `PyPwExtJSONEncoder`.

        Returns:
            The decorated function.

        The decorated function will be called, if any of the following parameters are present as
        optional.

        * response: `requests.Response` (or `LambdaResponse` if method is 'FUNC' or 'EVENT')
        * response_body: `str`
        * response_code: `http.HTTPStatus`

        Otherwise it will automatically return the `requests.Response` object if operation succeeded.
        If the operation got a status code above 299, it will raise a `PyPwExtHTTPError` with the status
        code and the response body set in the error.

        If the function is invoked, the function code is responsible to return appropriately.

        Example:

        ```
        @http(method='GET', url='https://{STAGE}.api.openaq.org/v1/cities', params={'country': '{country}'})
        def cities(country:str, response_body:str, response_code:http.HTTPStatus):
            if response_code == http.HTTPStatus.OK:
                return f'{country} has {response_body["count"]} cities'
            else:
                raise PyPwExtHTTPError(code=response_code, message=response_body)
        ```

        When using the `FUNC` or `EVENT` method, the boto3 library invoke will be used
        to call the function. In the `url` parameter is the function name and body is passed
        as usual to the function. The `ClientContext` will be base64 encoded if `params` object
        is present.

        The client context dictionary will be placed under the `custom` property as specified in
        https://docs.aws.amazon.com/lambda/latest/dg/python-context.html. Hence it is retrieveable
        in the lambda by:

        >>> context.client_context.custom['<dict-key-here>']

        The `url` can have the following formats:
        * my-function:v1 (the alias, in this case `v1`, is optional).
        * arn:aws:lambda:us-west-2:123456789012:function:my-function (the complete ARN to the function).
        * 123456789012:function:my-function (a partial ARN to the function).
        """
        def decorator(func):

            @ wraps(func)
            def wrapper(*args, **kwargs):

                # Get the function arguments
                args_names = func.__code__.co_varnames[:func.__code__.co_argcount]
                in_args = {**dict(zip(args_names, args)), **kwargs}

                try:
                    nonlocal url
                    url = render_arg_env_string(url, in_args)

                    if headers:
                        for k, v in headers.items():
                            headers[k] = render_arg_env_string(v, in_args)

                    if params:
                        for k, v in params.items():
                            params[k] = render_arg_env_string(v, in_args)

                except ValueError as e:
                    raise PyPwExtInternalError(message=str(e))

                # Extract the body data
                body_data: bytes = None
                original_body: Optional[Any] = None

                if body and body in in_args:

                    original_body = in_args[body]

                    if original_body is None:
                        body_data = b''
                    elif isinstance(original_body, str):
                        body_data = original_body.encode('utf-8')
                    elif not isinstance(original_body, bytes):
                        try:
                            body_data = json.dumps(original_body, cls=PyPwExtJSONEncoder).encode('utf-8')
                        except Exception as e:
                            raise PyPwExtInternalError(message=str(e))
                    else:
                        # bytes
                        body_data = original_body

                # Invoke the HTTP method
                response: requests.Response = None
                if 'GET' in method:
                    response = Self.get(url=url, params=params, headers=headers, data=body_data, verify=verify_ssl)
                elif 'POST' in method:
                    response = Self.post(url=url, params=params, headers=headers, data=body_data, verify=verify_ssl)
                elif 'PUT' in method:
                    response = Self.put(url=url, params=params, headers=headers, data=body_data, verify=verify_ssl)
                elif 'DELETE' in method:
                    response = Self.delete(url=url, params=params, headers=headers, data=body_data, verify=verify_ssl)
                elif 'PATCH' in method:
                    response = Self.patch(url=url, params=params, headers=headers, data=body_data, verify=verify_ssl)
                elif 'FUNC' in method:
                    response = Self.func(url=url, params=params, data=body_data)
                elif 'EVENT' in method:
                    response = Self.event(url=url, data=body_data)
                else:
                    raise PyPwExtInternalError(message=f'Unsupported HTTP method: {method}')

                if response is None:
                    raise PyPwExtInternalError(message=f'HTTP {url} returned None')

                # pass the result to method
                method_handles: bool = False
                varnames = func.__code__.co_varnames
                if 'response' in varnames:

                    kwargs['response'] = response
                    method_handles = True

                if 'response_body' in varnames:

                    if isinstance(response, LambdaResponse) and response.Payload is not None:
                        if method == 'FUNC':
                            kwargs['response_body'] = response.Payload.read().decode('utf-8')
                        else:
                            # EVENT do not have any data in the payload
                            kwargs['response_body'] = json.dumps(response.ResponseMetadata, cls=PyPwExtJSONEncoder)
                    else:
                        kwargs['response_body'] = response.text

                    method_handles = True

                if 'response_code' in varnames:

                    if isinstance(response, LambdaResponse):
                        kwargs['response_code'] = response.StatusCode
                    else:
                        kwargs['response_code'] = response.status_code

                    method_handles = True

                # Method do not handle response
                if not method_handles:
                    if response.status_code > 299:
                        raise PyPwExtHTTPError(
                            status_code=response.status_code,
                            message=response.text
                        )

                    return response

                # Method handles the response
                return func(*args, **kwargs)

            return wrapper

        if _func is None:
            return decorator

        return decorator(_func)

    def func(
            self,
            url: str,
            params: Optional[Dict[str, str]] = None,
            data: Optional[bytes] = None) -> LambdaResponse:
        """Invokes a lambda based on name, partial name or ARN."""
        return self._invoke_lambda(False, url, data, params)

    def event(
            self,
            url: str,
            data: Optional[bytes] = None) -> LambdaResponse:
        """Invokes a lambda, async, based on name, partial name or ARN."""
        return self._invoke_lambda(True, url, data)

    def _invoke_lambda(
            self,
            is_event: bool,
            function_name: str,
            body_data: Optional[bytes],
            client_context: Optional[Dict[str, str]] = None) -> LambdaResponse:
        """Invoke the lambda function."""

        if not self.lambda_client:
            raise PyPwExtInternalError(message='Lambda client is not initialized (not in AWS environment?)')

        type = 'Event' if is_event else 'RequestResponse'

        try:
            # log the invocation
            if self.logger:
                self.logger.log(
                    self.adapter.level,
                    {
                        Classification: self.adapter.before_classification.name,
                        'request': {
                            'type': type,
                            'function': function_name,
                            'body': None if body_data is None else try_convert_to_dict(body_data),
                            'client_context': {} if client_context is None else client_context
                        },
                    }
                )

            # invoke the lambda function
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType=type,
                Payload=body_data if body_data else b'',
                ClientContext='' if client_context is None else b64encode(
                    json.dumps(
                        {'custom': client_context}
                    ).encode('utf-8')
                ).decode('utf-8')
            )

            response = LambdaResponse.parse_obj(response)

        except Exception as e:

            response = LambdaResponse(
                StatusCode=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                FunctionError=str(e),
                Payload=StreamingBody(BytesIO(b''), 0)
            )

        # Log the response
        if self.logger:
            d = {
                'status': response.StatusCode,
            }

            if response.FunctionError:
                d['error'] = response.FunctionError
            if response.ExecutedVersion:
                d['executed_version'] = response.ExecutedVersion
            if response.LogResult:
                d['trace'] = response.LogResult
            if response.ResponseMetadata:
                d['response_metadata'] = response.ResponseMetadata

            text = response.payload_as_text()
            if text != '':
                d['body'] = try_convert_to_dict(text)

            self.logger.log(
                self.adapter.out_level,
                {
                    Classification: self.adapter.after_classification.name,
                    'response': d
                },
            )

        return response


class PyPwExtRetry(Retry):
    """ A Retry with a custom `classification` and `level`.

        It has some *sensible* default for backoff and what
        type of errors and methods to retry.
    """

    def __init__(
            self,
            total: int = 11,
            backoff_factor: int = 1,
            status_forcelist: List[int] = [429, 500, 502, 503, 504],
            allowed_methods: List[str] = ['HEAD', 'GET', 'PUT', 'DELETE', 'OPTIONS', 'TRACE'],
            **kwargs):
        """Default `Retry` configuration for a HTTP request.

            :param total:               Total number of retries. Default is 10.

            :param backoff_factor:      Backoff factor. One gives 0.5, 1, 2, 4, 8, 16, 32,
                                        64, 128, 256 seconds.

            :param status_forcelist:    List of status codes that should be retried.

            :param method_whitelist:    List of HTTP methods that should be retried.
        """

        super().__init__(
            total=total,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=allowed_methods,
            **kwargs
        )


class PyPwExtHTTPAdapter(HTTPAdapter):
    """Is a `HTTPAdapter` but adds a timeout in seconds for the send operation."""

    def __init__(
            self,
            timeout: Optional[int] = None,
            logger: Optional[PyPwExtLogger] = None,
            level: Union[str, int, None] = None,
            out_level: Union[str, int, None] = None,
            before_classification: InfoClassification = InfoClassification.NA,
            after_classification: InfoClassification = InfoClassification.NA,
            *args, **kwargs):
        """ Creates a `PyPwExtHTTPAdapter`.

            Args:
                timeout:    The timeout in seconds for the send operation.
                            Default is 30 seconds.

                logger:     The logger to use if before send, after send and
                            logging is wanted.

                level:      If set, the log level will be set to this value, otherwise it will use the
                            environment variable `LOG_LEVEL`. If both are missing, DEBUG is used.

                out_level:  If set, the return level will be set to this value, otherwise it will use
                            the environment variable `LOG_LEVEL`. If both are missing, INFO is used.

                before_classification:  The classification to use for the before sending the request logging.

                after_classification:   The classification to use for the after sending the request logging.
        """

        if timeout:
            self.timeout = timeout
        else:
            self.timeout = 30  # seconds

        self.logger = logger

        self.level = get_log_level(level)
        self.out_level = get_log_level(out_level)

        self.before_classification = before_classification
        self.after_classification = after_classification

        super().__init__(*args, **kwargs)

    def send(self, request: PreparedRequest, **kwargs) -> Response:
        """ Sends a response with a timeout.

            If a logger is set, it will log the request before and after the request.
        """
        timeout = kwargs.get('timeout')
        if timeout is None:
            kwargs['timeout'] = self.timeout

        if self.logger:
            self.logger.log(
                self.level,
                {
                    Classification: self.before_classification.name,
                    'request':
                    {
                        key: try_convert_to_dict(value) for (key, value) in request.__dict__.items()
                        if key not in ['hooks', '_body_position', '_cookies'] and value is not None
                    }
                }
            )

        response = super().send(request, **kwargs)

        if self.logger:
            d = {
                'header': try_convert_to_dict(response.headers),
                'status': response.status_code
            }

            text = response.text
            if text:
                d['body'] = try_convert_to_dict(text)

            self.logger.log(
                self.out_level,
                {
                    Classification: self.after_classification.name,
                    'response': d
                },
            )

        return response
