# flake8: noqa
from http import HTTPStatus
from logging import log
from typing import List, Optional
from operator import is_not
from functools import partial
from json import dumps

from aws_lambda_powertools.event_handler.api_gateway import Response
from aws_lambda_powertools.utilities.parser import event_parser, BaseModel
from aws_lambda_powertools.utilities.typing import LambdaContext

from pypwext.errors import PyPwExtErrorWithReturn, StdPyPwExtError, PyPwExtErrorHandler
from pypwext.service import PyPwExtResponse, PyPwExtService
from pypwext.base import InfoClassification, Message, Operation


def test__service_with_str_body_success():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body='Hello World!'
        )

    response = test_svc()
    assert type(response) == Response
    assert response.status_code == HTTPStatus.OK.value
    assert response.body == 'Hello World!'
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test__service_with_dict_body_success():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body={
                Operation: 'create-offer',
                Message: 'Hello World!'
            }
        )

    response = test_svc()
    assert type(response) == Response
    assert response.status_code == HTTPStatus.OK.value
    assert response.body == '{"operation": "create-offer", "msg": "Hello World!"}'
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test__service_with_str_body_with_error_will_replace_body_with_error():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body='Hello World!',
            error=StdPyPwExtError(
                code=HTTPStatus.NOT_FOUND,
                message="Failed to find record"
            )
        )

    response = test_svc()

    assert type(response) == Response
    assert response.status_code == HTTPStatus.NOT_FOUND.value
    assert response.body == '{"error": {"code": 404, "msg": "Failed to find record", "classification": "NA"}}'
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test__service_just_status_code_will_omit_error_key():

    # just_status_code=True is the default
    service = PyPwExtService()

    @service.response()
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body='Hello World!',
            error=StdPyPwExtError(
                code=HTTPStatus.NOT_FOUND,
                message="Failed to find record"
            )
        )

    response = test_svc()

    assert type(response) == Response
    assert response.status_code == HTTPStatus.NOT_FOUND.value
    assert response.body == 'Hello World!'
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test__service_with_dict_body_with_error_will_add_error_key_in_body():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body={
                Operation: 'create-offer',
                Message: 'Hello World!'
            },
            error=StdPyPwExtError(
                code=HTTPStatus.NOT_FOUND,
                message="Failed to find record"
            )
        )

    response = test_svc()
    assert type(response) == Response
    assert response.status_code == HTTPStatus.NOT_FOUND.value
    assert response.body == ('{"operation": "create-offer", "msg": "Hello World!", '
                             '"error": {"code": 404, "msg": "Failed to find record", "classification": "NA"}}')
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test_service_highest_status_code_wins_is_the_default():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body={
                Operation: 'create-offer',
                Message: 'Hello World!'
            },
            error=[
                StdPyPwExtError(
                    code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    message="Server down"
                ),
                StdPyPwExtError(
                    code=HTTPStatus.NOT_FOUND,
                    message="Failed to find record"
                )
            ]
        )

    response = test_svc()
    assert type(response) == Response
    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR.value
    assert response.headers == {'Content-Type': 'application/json'}


def test_service_highest_status_code_can_be_overridden():
    service = PyPwExtService()

    @service.response(just_status_code=False, code_from_error=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body={
                Operation: 'create-offer',
                Message: 'Hello World!'
            },
            error=[
                StdPyPwExtError(
                    code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    message="Server down"
                ),
                StdPyPwExtError(
                    code=HTTPStatus.NOT_FOUND,
                    message="Failed to find record"
                )
            ]
        )

    response = test_svc()
    assert type(response) == Response
    assert response.status_code == HTTPStatus.OK.value
    assert '"code": 500' in response.body
    assert response.headers == {'Content-Type': 'application/json'}


def test__service_pass_through_non_pypwext_responses():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        return {
            'statusCode': HTTPStatus.OK.value,
            'body': 'Hello World!',
        }

    response = test_svc()
    assert type(response) == dict
    assert response['statusCode'] == HTTPStatus.OK.value
    assert response['body'] == 'Hello World!'


def test__service_raise_in_main_continue_will_return_error_in_body():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        raise StdPyPwExtError(
            code=HTTPStatus.NOT_FOUND,
            message="Failed to find record for customer: XYZ",
            classification=InfoClassification.CORPORATE_SENSITIVE_INFO,
            details={'route': 'to_path_2'},
        )

    response = test_svc()
    assert type(response) is Response
    assert response.status_code is HTTPStatus.NOT_FOUND.value
    assert response.body == ('{"error": {"code": 404, "msg": "Failed to find record for customer: XYZ", '
                             '"classification": "CORPORATE_SENSITIVE_INFO", "details": {"route": "to_path_2"}}}')


def test__service_raise_in_main_continue_as_pypwext_error_with_return_will_put_return_as_body():
    service = PyPwExtService()

    @service.response(just_status_code=False)
    def test_svc():
        raise PyPwExtErrorWithReturn(
            code=HTTPStatus.NOT_FOUND,
            message="Failed to find record for customer: XYZ",
            return_value={'route': 'to_path_2'},
            classification=InfoClassification.CORPORATE_SENSITIVE_INFO,
        )

    response = test_svc()
    assert type(response) is Response
    assert response.status_code is HTTPStatus.NOT_FOUND.value
    assert response.body == ('{"route": "to_path_2", "error": {"code": 404, "msg": '
                             '"Failed to find record for customer: XYZ", "classification": "CORPORATE_SENSITIVE_INFO"}}')


def test_service_with_dict_body_with_collected_error_will_add_error_key_in_body():
    errors = PyPwExtErrorHandler()
    service = PyPwExtService()

    @errors.collect
    def send_offer(customer: str) -> str:
        # send offer to customer -> result NOT_FOUND -> raise
        raise PyPwExtErrorWithReturn(
            code=HTTPStatus.NOT_FOUND,
            message=f"Failed to find record for customer: {customer}",
            return_value="my bad"
        )

    @errors.collect(root=True)
    @service.response(just_status_code=False)
    def test_svc():
        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            body={
                Operation: 'create-offer',
                Message: send_offer("mario.toffia@pypwext.se")
            }
        )

    response = test_svc()
    assert type(response) == Response
    assert response.status_code == HTTPStatus.NOT_FOUND.value
    assert response.body == ('{"operation": "create-offer", "msg": "my bad", "error": '
                             '{"code": 404, "msg": "Failed to find record for customer: '
                             'mario.toffia@pypwext.se", "classification": "NA"}}')
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test_service_with_dict_body_with_collected_many_error_will_add_error_key_with_error_list_in_body():
    errors = PyPwExtErrorHandler()
    service = PyPwExtService()

    @errors.collect
    def send_offer(customer: str) -> str:
        # send offer to customer -> result NOT_FOUND -> raise
        if customer != "nisse@manpower.com":
            raise PyPwExtErrorWithReturn(
                code=HTTPStatus.NOT_FOUND,
                message=f"Failed to find record for customer: {customer}",
                details={'customer': customer}
            )

        return customer

    @errors.collect(root=True)
    @service.response(just_status_code=False)
    def test_svc(customers: List[str]):

        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            updated=list(filter(partial(is_not, None), [send_offer(c) for c in customers])),
            operation="create-offer"
        )

    response = test_svc(["mario.toffia@pypwext.se", "nisse@manpower.com", "ivar@ikea.se"])

    assert type(response) == Response
    assert response.status_code == HTTPStatus.NOT_FOUND.value
    assert response.body == ('{"updated": ["nisse@manpower.com"], "operation": "create-offer", '
                             '"error": [{"code": 404, "msg": "Failed to find record for customer: mario.toffia@pypwext.se", '
                             '"classification": "NA", "details": {"customer": "mario.toffia@pypwext.se"}}, '
                             '{"code": 404, "msg": "Failed to find record for customer: ivar@ikea.se", "classification": '
                             '"NA", "details": {"customer": "ivar@ikea.se"}}]}')
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded


def test_service_with_parsed_event_shall_succeed():

    class PyPwExtModel(BaseModel):
        pypwext_id: str

    class OrderItem(BaseModel):
        id: int
        quantity: int
        description: str

    class Order(PyPwExtModel):
        id: int
        description: str
        items: List[OrderItem]
        optional_field: Optional[str]

    from pypwext.pwlogging import PyPwExtLogger
    service = PyPwExtService()

    @service.response(just_status_code=False)
    @event_parser(model=Order)
    def handler(event: Order, _):

        if not event.pypwext_id:
            raise StdPyPwExtError(
                code=HTTPStatus.BAD_REQUEST,
                message="Missing pypwext_id",
            )

        return PyPwExtResponse(
            status_code=HTTPStatus.OK,
            updated=[item for item in event.items],
            operation="create-order",
        )

    payload = {
        "pypwext_id": "12345",
        "id": 10876546789,
        "description": "My order",
        "items": [
            {
                "id": 1015938732,
                "quantity": 1,
                "description": "item xpto"
            }
        ]
    }

    event = dumps(payload)
    response = handler(event=event, context=LambdaContext())
    assert type(response) == Response
    assert response.status_code == HTTPStatus.OK.value
    assert response.body == ('{"updated": [{"id": 1015938732, "quantity": 1, '
                             '"description": "item xpto"}], "operation": "create-order"}')
    assert response.headers == {'Content-Type': 'application/json'}
    assert not response.base64_encoded
