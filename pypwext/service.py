""" Module to support creation of PyPwExt µServices.

    This module makes extensive use of the `PyPwExtService.response` decorator in conjunction
    with the `PyPwExtResponse` data-class.

    The `PyPwExtResponse` is a structured response class that still allow for arbitrary
    return values, custom headers and status codes. However, since it is structured it
    may be used to automatically translated to an API/HTTP Gateway response.

    The `PyPwExtResponse`, `PyPwExtError` and `@pypwext_response` decorator can be used to
    create a microservice that can be consumed by an API (REST, HTTP) Gateway or an ALB.

    If using `PyPwExtService.response` with the API Gateway or ALB, you may use the aws lambda
    powertools to e.g. add a custom header (in addition to explicitly add it using
    the `PyPwExtResponse`) to the `Response` etc.

    # Examples

    ** Simple microservice

    The below service just returns a simple body with a operation and a message.

    ```
    service = PyPwExtService()

    @service.response
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body={
                Operation: 'create-offer',
                Message: 'Hello World!'
            }
        )

    {"operation": "create-offer", "msg": "Hello World!"}
    ```

    It will produce the `Content-Type=application/json` since it is the default.

    ** Microservice that returns a structured error with custom details.

    ```
    service = PyPwExtService()

    @service.response
    def test_svc():
        raise StdPyPwExtError(
            code=HTTPStatus.NOT_FOUND,
            message="Failed to find record for customer: XYZ",
            classification=InfoClassification.CORPORATE_SENSITIVE_INFO,
            details={'route': 'to_path_2'},
        )

    {
        "error": {
            "code": 404,
            "msg": "Failed to find record for customer: XYZ",
            "classification": "CORPORATE_SENSITIVE_INFO",
            "details": {"route": "to_path_2"}
        }
    }
    ```

    ** Microservice that makes use of PyPwExtErrorHandler.collect decorator.

    The following sample, ensures that a `@error.collect` is installed and, returns all
    errors collected during execution. The below sample uses `ErrorAction.CONTINUE` since
    it is a best effort and retries are only done for those who fails.

    This also showcases the combination of `@pypwext_log` and `@error.collect`; both
    have pypwext semantics.

    ```
    logger = PyPwExtLogger(default_logger=True, service='my-service')
    errors = PyPwExtErrorHandler()
    service = PyPwExtService()

    @errors.collect
    @logger.method
    def send_offer(customer: str) -> str:
        # send offer to customer -> result NOT_FOUND -> raise
        if customer != "nisse@manpower.com":
            raise PyPwExtErrorWithReturn(
                action=ErrorAction.CONTINUE,
                code=HTTPStatus.NOT_FOUND,
                message=f"Failed to find record for customer: {customer}",
                details={'customer': customer}
            )

        return customer

    @errors.collect(root=True)
    @service.response
    def test_svc(customers: List[str]):
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            updated=list(filter(partial(is_not, None), [send_offer(c) for c in customers])),
            operation="create-offer"
        )

    {
        "updated": ["nisse@manpower.com"],
        "operation": "create-offer",
        "error": [
            {
                "code": 404,
                "msg": "Failed to find record for customer: mario.toffia@pypwext.se",
                "classification": "NA",
                "details": {"customer": "mario.toffia@pypwext.se"}
            },
            {
                "code": 404,
                "msg": "Failed to find record for customer: ivar@ikea.se",
                "classification": "NA",
                "details": {"customer": "ivar@ikea.se"}
            }
        ]
    }
    ```

    The above example succeeded with one but failed with the other two. The error may be put into a queue for re-try.

    ** Microservice that uses strongly typed entities

    ```
    class OrderItem(BaseModel):
        id: int
        quantity: int
        description: str


    class Order(BaseModel):
        id: int
        description: str
        items: List[OrderItem]
        optional_field: Optional[str]

    service = PyPwExtService()

    @service.response
    @event_parser(model=Order)
    def handler(event: Order, context: LambdaContext):

        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            updated=[item for item in event.items],
            operation="create-offer"
        )

    {
        "operation": "create-offer",
        "updated": [{"id": 1015938732, "quantity": 1, "description": "item xpto"}]
    }
    ```

    The `@service.response` uses the `PyPwExtJSONEncoder` that supports `BaseModel` derived or
    @dataclass decorated classes out of the box.
"""
from http import HTTPStatus
from functools import wraps
from json import dumps
from enum import IntEnum
from dataclasses import dataclass

from typing import Dict, Callable, List, Optional, Union, Any, Type

from aws_lambda_powertools.utilities.parser.types import Model
from aws_lambda_powertools.utilities.parser import parse
from aws_lambda_powertools.utilities.parser.envelopes import BaseEnvelope
from aws_lambda_powertools.event_handler.api_gateway import ApiGatewayResolver, Response

from pydantic import ValidationError

from pypwext.errors import (
    ErrorAction,
    PyPwExtError,
    PyPwExtErrorWithReturn,
    get_current_collector
)

from pypwext.encoders import PyPwExtJSONEncoder
from pypwext.environment import init_env
from pypwext.errors import PyPwExtHTTPError

# Make sure to initialize the pypwext core environment
init_env()


class ResponseType(IntEnum):
    """The type of response the `@pypwext_response` decorator shall produce"""
    API_GATEWAY_REST = 1
    """This is when the payload is API Gateway V1 response"""
    API_GATEWAY_HTTP = 2
    """A HTTP Gateway response (API Gateway V2 response)"""
    ALB = 3
    """A ALB response type"""


@dataclass
class PyPwExtResponse:
    """The response object for the `@pypwext_response` decorator.

        It adheres to `SupportsToCuratedDic` protocol.
    """

    def __init__(
        self,
        status_code: HTTPStatus = HTTPStatus.OK,
        content_type: Optional[str] = 'application/json',
        body: Union[str, bytes, Dict[str, Any], None] = None,
        headers: Optional[Dict[str, str]] = None,
        error: Union[List[PyPwExtError], PyPwExtError, None] = None,
        **kwargs,
    ) -> None:
        """ Initialize a `PyPwExtResponse`

            If the body is empty or a `Dict[str, Any]` it supports additional
            arbitrary extra arguments. Those argument names will be the key
            in the body and its value will be the value.
        """
        if type(body) is not str:
            if body is None:
                body = {}

            for k, v in kwargs.items():
                body[k] = v

        self._body = body

        if type(status_code) is int:
            self._status_code = HTTPStatus(status_code)
        else:
            self._status_code = status_code

        self._headers = headers

        if isinstance(error, List):
            self._error = error
        elif isinstance(error, PyPwExtError):
            self._error = [error]
        else:
            self._error = []

        self._content_type = content_type

    @property
    def status_code(self) -> HTTPStatus:
        """The status code of the response"""
        return self._status_code

    @property
    def content_type(self) -> Union[str, None]:
        """The content type of the response"""
        return self._content_type

    @property
    def body(self) -> Union[str, bytes, Dict[str, Any]]:
        """The HTTP body to be returned"""
        return self._body

    @property
    def headers(self) -> Dict[str, str]:
        """The additional headers to respond with."""
        return self._headers

    @property
    def error(self) -> List[PyPwExtError]:
        """The errors to be returned as error key in body"""
        return self._error

    def dict(self) -> Dict[str, Any]:
        """ Convert the response to a `Dict[Any, str]`

            It will merge errors into the body if it is
            not of `str` type. Otherwise it will place
            a `dict` with `{'error': '...'} as the body.
        """
        data = {
            'status_code': str(self._status_code),
            'content_type': self._content_type,
            'body': self._body or {},
            'headers': self._headers,
        }

        if self._error:
            if type(data.body) == Dict[str, Any]:
                data.body['error'] = self._error_to_list_or_object_dict()
            else:
                data.body = {'error': self._error_to_list_or_object_dict()}

        return data

    def _error_to_list_or_object_dict(self) -> Dict[str, Any]:
        """Convert the error to a list or object of `PyPwExtError` dictionaries"""
        if len(self._error) == 0:
            return None

        if len(self._error) == 1:
            return self._error[0].dict()

        return [e.dict() for e in self._error]


class PyPwExtService():
    """Base service class for PyPwExt Micro services

    As with all elements of this core library, it is a opt-in. Hence use what
    you need.
    """

    def __init__(
            self,
            encoder: Optional[Callable[[Any], str]] = None) -> None:
        """Initialize a `PyPwExtService`

        Args:
            encoder: The encoder to use first, for the response.
        """
        self.encoder = PyPwExtJSONEncoder(encoder)

    def parse(
        self,
        app: ApiGatewayResolver,
        model: Type[Model],
        envelope: Optional[BaseEnvelope] = None
    ) -> Model:
        """Translate the body data to a model.

        Args:
            app:        The app that is used to parse the body.

            model:      The model to use to parse the body.

            envelope:   An optional envelope to parse out the body data
                        to actually parse the model. If omitted, it uses
                        the `current_event.body` by default.

        Returns:
            Model: The parsed model.

        If it fails it will raise a `PyPwExtHTTPError` with the status code
        of `HTTPStatus.BAD_REQUEST` if validation error, otherwise
        `HTTPStatus.INTERNAL_SERVER_ERROR`.

        NOTE:   Use the pre-defined envelopes e.g. `envelope=envelopes.EVENTBRIDGE`
                or create your own.
        """
        try:

            if envelope:
                return parse(event=app.current_event, model=model, envelope=envelope)

            return parse(event=app.current_event.body, model=model)
        except ValidationError as e:
            raise PyPwExtHTTPError(message=str(e), code=HTTPStatus.BAD_REQUEST)

        except Exception as e:
            raise PyPwExtHTTPError(
                f'Failed to parse from body: {str(e)}',
                code=HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def response(
            self,
            _func: Optional[Callable] = None,
            type: ResponseType = ResponseType.API_GATEWAY_REST,
            always_return: bool = True,
            code_from_error: bool = True,
            just_status_code: bool = True) -> Callable[[Callable], Callable]:
        """ This create a response object from a `PyPwExtResponse` or if any error has been raised/collected.

        Args:
            type:           The type of response to be returned. Default is `ResponseType.API_GATEWAY_REST`

            always_return:  If `True` it will always return a response object. If `False` it will only return a response
                            object if there are no errors or errors with a action of `ErrorAction.CONTINUE`. Default is `True`.

            root:           If True, this will be the root `@pypwext_response` and make sure
                            that it installs a new `ErrorCollector` as the current collector.

            code_from_error:    If `True`, it will use the collected errors `statusCode` to compute
                                a status code. If set to `False` it will use the `PyPwExtResponse`
                                status code. Default is `True`.

            just_status_code:   Do not include any error in the response. Instead just set the status code
                                from the errors if *code_from_error* is `True`. This option defaults to `True`.

        It will produce a `Response` based on the `type` parameter. If the return is not a `PyPwExtResponse` it
        will silently return it and do no additional processing.

        When *code_from_error* is set to true it will use the collected errors `statusCode` to compute by
        checking the highest error code and then use that as the status code.
        """
        def decorator(func):

            @wraps(func)
            def wrapper(*args, **kwargs):

                try:

                    value = func(*args, **kwargs)

                    # Just pass all non PyPwExtResponses through
                    if not isinstance(value, PyPwExtResponse):
                        return value

                    return self._handle_pypwext_response(
                        value,
                        type,
                        code_from_error,
                        just_status_code
                    )

                except PyPwExtError as e:
                    # Check if we're collecting errors
                    collector = get_current_collector()

                    if collector:
                        collector.add(e)

                    if not always_return and e.action == ErrorAction.RAISE:
                        raise

                    body = {}
                    if isinstance(e, PyPwExtErrorWithReturn):
                        body = e.return_value

                    return self._handle_pypwext_response(
                        PyPwExtResponse(
                            body=body,
                            status_code=e.code,
                            error=None if collector else [e]),
                        type,
                        code_from_error,
                        just_status_code
                    )

                except:  # noqa: E722

                    if not always_return:
                        raise

                    if (
                        type == ResponseType.API_GATEWAY_REST or  # noqa: W504
                        type == ResponseType.API_GATEWAY_HTTP or  # noqa: W504
                        type == ResponseType.ALB
                    ):
                        return Response(
                            status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                            content_type='application/json',
                            body=dumps({'error': 'Internal Server Error'})
                        )

                    return dumps({'status': 500, 'error': 'Internal Server Error'})

            return wrapper

        # Wrap it in a error collector
        if _func:
            return decorator(_func)
        else:
            return decorator

    def _handle_pypwext_response(
            self,
            value: PyPwExtResponse,
            type: ResponseType,
            code_from_error: bool,
            just_status_code: bool) -> Union[Response, str]:
        """Handles the PyPwExt Response and returns a Response or a JSON string

            It will check if there are any collected errors and if so, it will
            add those to the body.

            This is a helper function to the `pypwext_response` decorator.
        """

        # Add any collected errors if any
        collector = get_current_collector()

        if collector:
            if value._error is None:
                value._error = []

            value._error.extend(collector.errors)

        # If errors, set highest status code
        if (
                code_from_error and  # noqa: W504
                value.error and  # noqa: W504
                value.status_code == HTTPStatus.OK
        ):
            value._status_code = max(e.code for e in value.error)

        # If just status code -> clear the errors
        if just_status_code:
            value._error = None

        # API Gateway or ALB -> Response
        if (
            type == ResponseType.API_GATEWAY_REST or  # noqa: W504
            type == ResponseType.API_GATEWAY_HTTP or  # noqa: W504
            type == ResponseType.ALB
        ):
            return self._pypwext_response_to_apiproxy_response(value)

        # Not known response type -> just dump dict as JSON
        return dumps(value.dict(), default=self.encoder.default)

    def _pypwext_response_to_apiproxy_response(
            self,
            value: PyPwExtResponse) -> Response:
        """Converts a `PyPwExtResponse` to an `aws_lambda_powertools.event_handler.api_gateway.Response` object.

        Args:
            value:      The `PyPwExtResponse` to convert

            encoder:    The encoder to use for the body.
        """

        body = value.body
        if value.error:
            if type(value.body) is str or type(value.body) is bytes:
                body = {'error': value._error_to_list_or_object_dict()}
            else:
                body['error'] = value._error_to_list_or_object_dict()

        # Clean out action from errors
        if type(body) is dict:
            if 'error' in body:
                if type(body['error']) is list:
                    # Delete all action leafs from errors
                    for err in body['error']:
                        if 'action' in err:
                            del err['action']
                elif 'action' in body['error']:
                    # Single error return
                    del body['error']['action']

            body = dumps(body, default=self.encoder.default)

        return Response(
            status_code=value.status_code.value,
            content_type=value.content_type,
            headers=value.headers,
            body=body
        )
