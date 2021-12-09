# flake8: noqa
import logging
import io
import os
import random
import string

from typing import Tuple

from pypwext.base import InfoClassification, Message, Classification, Arguments, Return, Operation
from pypwext.logging import PyPwExtLogger, LogEntryType, LogType, VERBOSE


def get_new_logger_name() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def test_std_json_logging_just_message():
    with io.StringIO() as s:
        logger = PyPwExtLogger(service=get_new_logger_name(), logger_handler=logging.StreamHandler(s))

        def pay():
            logger.info("payment_finished")

        pay()
        value = s.getvalue()

        assert '"msg":"payment_finished"' in value
        assert '"timestamp"' in value
        assert '"level":"INFO"' in value
        assert '"classification":"NA"' in value
        assert '"type":"STD"' in value
        assert f'"service":"{logger.service}"' in value
        assert '"location":"pay:' in value


def test_level_verbose_is_working():

    with io.StringIO() as s:
        logger = PyPwExtLogger(
            service=get_new_logger_name(),
            logger_handler=logging.StreamHandler(s),
            level=VERBOSE
        )

        def pay():
            logger.verbose("payment_finished")

        pay()
        value = s.getvalue()

        assert '"msg":"payment_finished"' in value
        assert '"timestamp"' in value
        assert '"level":"VERBOSE"' in value
        assert '"classification":"NA"' in value
        assert '"type":"STD"' in value
        assert f'"service":"{logger.service}"' in value
        assert '"location":"pay:' in value


def test_json_logging_with_extra_fields():
    with io.StringIO() as s:
        logger = PyPwExtLogger(service=get_new_logger_name(), logger_handler=logging.StreamHandler(s))

        def pay():
            logger.info({
                Operation: "payment_finished",
                "credit_card_id": 777111333,
                Classification: InfoClassification.CORPORATE_SENSITIVE_INFO,
                LogType: LogEntryType.AUDIT
            })

        pay()
        value = s.getvalue()

        assert '"operation":"payment_finished"' in value
        assert '"timestamp"' in value
        assert '"level":"INFO"' in value
        assert '"classification":"CORPORATE_SENSITIVE_INFO"' in value
        assert '"type":"AUDIT"' in value
        assert f'"service":"{logger.service}"' in value
        assert '"msg":""' not in value
        assert '"credit_card_id":777111333' in value
        assert '"location":"pay:' in value


def test_json_logging_with_semantics():
    with io.StringIO() as s:
        logger = PyPwExtLogger(service=get_new_logger_name(), logger_handler=logging.StreamHandler(s))

        def pay_by_id(amount: int, credit_card_id: str) -> Tuple[bool, str]:
            logger.info({
                Operation: "pay",
                Classification: InfoClassification.CORPORATE_SENSITIVE_INFO,
                LogType: LogEntryType.AUDIT,
                Arguments: {"amount": amount, "credit_card_id": credit_card_id}})

            logger.info({
                Operation: "pay",
                Classification: InfoClassification.CORPORATE_SENSITIVE_INFO,
                LogType: LogEntryType.AUDIT,
                Return: {"success": True, "info": credit_card_id}})

        pay_by_id(200, '777111333')
        value = s.getvalue()

        assert '"operation":"pay"' in value
        assert '"timestamp"' in value
        assert '"level":"INFO"' in value
        assert '"classification":"CORPORATE_SENSITIVE_INFO"' in value
        assert '"type":"AUDIT"' in value
        assert f'"service":"{logger.service}"' in value
        assert '"msg":""' not in value
        assert '"credit_card_id":"777111333"' in value
        assert '"location":"pay_by_id:' in value


def test_std_json_logging_supports_json():
    with io.StringIO() as s:
        logger = PyPwExtLogger(service=get_new_logger_name(), logger_handler=logging.StreamHandler(s))

        class TestClass:
            def json(self):
                return {"test": 123}

        def pay():
            logger.info({
                Message: "payment_finished",
                "obj": TestClass()
            })

        pay()
        value = s.getvalue()

        assert '"msg":"payment_finished"' in value
        assert '"timestamp"' in value
        assert '"level":"INFO"' in value
        assert '"classification":"NA"' in value
        assert '"type":"STD"' in value
        assert f'"service":"{logger.service}"' in value
        assert '"location":"pay:' in value
        assert '{"test":123}' in value


def test_log_decorator_simple_no_logger():

    with io.StringIO() as output:

        logger = PyPwExtLogger(
            service=get_new_logger_name(),
            logger_handler=logging.StreamHandler(output)
        )

        @logger.method(level=logging.INFO)
        def my_func():
            return "Hello World"

        my_func()

        value = output.getvalue()

        assert '"msg":"Entering my_func"' in value
        assert '"args":{}' in value
        assert '"msg":"Exiting my_func"' in value
        assert '"return":"Hello World"' in value


def test_log_decorator_simple_with_logger():

    with io.StringIO() as output:

        logger = PyPwExtLogger(
            service=get_new_logger_name(),
            level=logging.DEBUG,
            logger_handler=logging.StreamHandler(output)
        )

        @logger.method
        def my_func():
            return "Hello World"

        my_func()

        value = output.getvalue()

        assert '"msg":"Entering my_func"' in value
        assert '"args":{}' in value
        assert '"msg":"Exiting my_func"' in value
        assert '"return":"Hello World"' in value


def test_log_decorator_with_arguments():

    with io.StringIO() as output:

        logger = PyPwExtLogger(
            service=get_new_logger_name(),
            level=logging.DEBUG,
            logger_handler=logging.StreamHandler(output)
        )

        @logger.method
        def my_func(path: str, user: str):
            return {"POST": f"https://{user}:@{path}", "id": "Hello World", "ret": 17}

        my_func("/things/myStuff", "nisse")

        value = output.getvalue()

        assert '"msg":"Entering my_func"' in value
        assert '"args":{' in value
        assert '"path":"/things/myStuff"' in value
        assert '"user":"nisse"' in value
        assert '"msg":"Exiting my_func"' in value
        assert '"return":{' in value
        assert '"id":"Hello World"' in value
        assert '"ret":17' in value
        assert '"POST":"https://nisse:@/things/myStuff"' in value


def test_log_decorator_with_pypwext_log_level_env():

    try:
        os.environ["LOG_LEVEL"] = "INFO"

        with io.StringIO() as output:

            logger = PyPwExtLogger(
                service=get_new_logger_name(),
                logger_handler=logging.StreamHandler(output)
            )

            @logger.method
            def my_func(path: str, user: str):
                return {"POST": f"https://{user}:@{path}", "id": "Hello World", "ret": 17}

            my_func("/things/myStuff", "nisse")

            value = output.getvalue()

            assert '"msg":"Entering my_func"' in value
            assert '"args":{' in value
            assert '"path":"/things/myStuff"' in value
            assert '"user":"nisse"' in value
            assert '"msg":"Exiting my_func"' in value
            assert '"return":{' in value
            assert '"id":"Hello World"' in value
            assert '"ret":17' in value
            assert '"POST":"https://nisse:@/things/myStuff"' in value
    finally:
        del os.environ["LOG_LEVEL"]


def test_log_decorator_with_different_in_and_return_levels():

    try:
        os.environ["LOG_LEVEL"] = "INFO"

        with io.StringIO() as output:

            logger = PyPwExtLogger(
                service=get_new_logger_name(),
                logger_handler=logging.StreamHandler(output)
            )

            @logger.method(level=logging.DEBUG, out_level=logging.INFO)
            def my_func(path: str, user: str):
                return {"POST": f"https://{user}:@{path}", "id": "Hello World", "ret": 17}

            my_func("/things/myStuff", "nisse")

            value = output.getvalue()

            assert '"msg":"Entering my_func"' not in value
            assert '"args":{' not in value
            assert '"path":"/things/myStuff"' not in value
            assert '"user":"nisse"' not in value
            assert '"msg":"Exiting my_func"' in value
            assert '"return":{' in value
            assert '"id":"Hello World"' in value
            assert '"ret":17' in value
            assert '"POST":"https://nisse:@/things/myStuff"' in value
    finally:
        del os.environ["LOG_LEVEL"]


def test_log_decorator_with_service_env():

    try:
        os.environ['POWERTOOLS_SERVICE_NAME'] = get_new_logger_name()

        with io.StringIO() as output:

            logger = PyPwExtLogger(
                level=logging.DEBUG,
                logger_handler=logging.StreamHandler(output)
            )

            @logger.method
            def my_func():
                return "Hello World"

            my_func()

            value = output.getvalue()

            assert f'"service":"{logger.service}"' in value
    finally:
        del os.environ['POWERTOOLS_SERVICE_NAME']


def test_log_exception_manually():

    with io.StringIO() as output:

        logger = PyPwExtLogger(
            service=get_new_logger_name(),
            level=logging.DEBUG,
            logger_handler=logging.StreamHandler(output)
        )

        try:
            raise Exception("Something went wrong")
        except:  # noqa: E722
            logger.exception("This is an exception", exc_info=True, stack_info=True)

        value = output.getvalue()
        assert '"level":"ERROR"' in value
        assert '"message":{"msg":"This is an exception"}' in value
        assert '"timestamp":"' in value
        assert '"service":"' in value
        assert '"classification":"NA"' in value
        assert '"type":"STD"' in value
        assert '"exception":"Traceback (most recent call last):\\n  File \\"' in value
        assert 'raise Exception(\\"Something went wrong\\")\\nException: Something went wrong"' in value
        assert '"exception_name":"Exception"' in value


def test_logging_keywords_is_controllable():

    with io.StringIO() as output:

        logger = PyPwExtLogger(
            service=get_new_logger_name(),
            level=logging.DEBUG,
            logger_handler=logging.StreamHandler(output)
        )

        @logger.method(
            classification=InfoClassification.CORPORATE_SENSITIVE_INFO,
            type=LogEntryType.STD, operation="payment",
            out_classification=InfoClassification.PII,
            out_type=LogEntryType.AUDIT,
            out_operation="payment",
            eq_keywords=False
        )
        def pay(token: str, amount: int) -> str:
            return f'You paid ${amount} Mario'

        pay("abc123", 100)
        value = output.getvalue()
        assert '"classification":"CORPORATE_SENSITIVE_INFO"' in value
        assert '"type":"STD"' in value
        assert '"classification":"PII"' in value
        assert '"type":"AUDIT"' in value
        assert '"operation":"payment"' in value
