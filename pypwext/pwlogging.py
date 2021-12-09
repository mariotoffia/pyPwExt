"""PyPwExt logging module.

    This module provides a simple logging interface. It is based on the `aws_lambda_powertools.logging` module. It provides a
    `PyPwExtLogger` class that adds a few extra fields and a `PyPwExtJSONFormatter` class that handles most common types and protocols.
    It also adds an additional log level `VERBOSE` that is used to log verbose information.

    Since it is based on [aws_lambda_powertools.logging](https://awslabs.github.io/aws-lambda-powertools-python/latest/core/logger/)
    it is capable of logging lambda context and other information such as xray_trace_id. The `PyPwExtLogger`
    is automatically capable to add `correlation_id' when a correlation has successfully been made.

    To use the AWS lambda powertools, either deploy it with the lambda or add it as a lambda layer
    [arn:aws:lambda:{region}:017000801446:layer:AWSLambdaPowertoolsPython:3](https://awslabs.github.io/aws-lambda-powertools-python/latest)

    In order to have xray_trace_id in the log, the lambda must be deployed with the xray-tracing lambda layer
    see [xray documentation](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html).

    # Quick examples

    ** Example using correlation id

    ```
    logger = PyPwExtLogger(service="payment")

    @logger.inject_lambda_context(correlation_id_path="headers.my_request_id_header")
    def handler(event, context):
        log.info({Message: "Processing Person", Classification: InfoClassification.PII})

    {"correlation_id": "12881873-pn-ab12", "...": "..."}
    ```

    This will inject the correlation id from the header `my_request_id_header` into the log
    each log statement.

    ** Log the lambda context info automatically

    ```
    logger = Logger(service="payment")

    @logger.inject_lambda_context(log_event=True)
    def handler(event, context):
    ```

    # Environment variables

    The logger adheres to two environment variables that will override any settings:

    + `LOG_LEVEL`: The log level to use, e.g. DEBUG or VERBOSE.
    + `POWERTOOLS_SERVICE_NAME`: The service name to use, e.g. "payment"

    # PyPwExt logger

    The `PyPwExtJSONFormatter` most prominently supports the `base.SupportsToJson` protocol.
    It is also possible to add custom JSON formatting by submitting a custom_encoder,
    `Optional[Callable[[Any], str]]` to add more support without updating the core logger.

    The `PyPwExtLogger` adds the fields `classification` of which reflects the `base.InfoClassification`,
    `type` that can be any of `LogEntryType`, such as AUDIT. It also specifies `args` and `return` for
    function based logging.

    It also adds semantics on the actual log output such as `"operation"` or `"error"` with constants
    to allow for less error prone logging.

    ```
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
    ```


    NOTE:   The `PyPwExtJSONEncoder`is reuseable and could be used in other parts of the code since it is
            not bound to the logger. It is a `json.JSONEncoder` subclass. That can be used to do `encode`
            or provided in `json.dumps` with `lambda o: PyPwExtJSONEncoder().dump(o)` as default parameter.

    # Sample Usage

    ** The simplest form is to instantiate and use the `PyPwExtLogger` class directly.

    >>> logger = PyPwExtLogger(service='payment-service')
    >>>
    >>> def pay():
            logger.info({
                "operation": "payment_finished",
                "credit_card_id": 777111333,
                Classification: InfoClassification.CORPORATE_SENSITIVE_INFO,
                LogType: LogEntryType.AUDIT
            })
    >>>
    >>> pay()
    {
        "level":"INFO",
        "location":"pay:21",
        "message":{
            "operation":"payment_finished",
            "credit_card_id":777111333
        },
        "timestamp":"2021-11-16 22:27:35,206+0100",
        "service":"payment-service",
        "classification":"CORPORATE_SENSITIVE_INFO",
        "type":"AUDIT"
    }

    ** Using decorator to automatically log arguments, return or exceptions on a function

    >>> logger = PyPwExtLogger(service='payment')
    >>>
    >>> @logger.method
    >>> def my_func(path: str, user: str):
            return {"POST": f"https://{user}:@{path}", "id": "Hello World", "ret": 17}
    >>>
    >>> my_func("/things/myStuff", "nisse")
    {
        "level":"INFO",
        "location":"my_func:174",
        "message":{
            "msg":"Entering my_func",
            "args":{
                "path":"/things/myStuff",
                "user":"nisse"
            }
        },
        "timestamp":"2021-11-16 22:43:19,155+0100",
        "service":"payment",
        "classification":"NA",
        "type":"STD"
    }
    {
        "level":"INFO",
        "location":"my_func:174",
        "message":{
            "msg":"Exiting my_func",
            "return":{
                "POST":"https://nisse:@/things/myStuff",
                "id":"Hello World",
                "ret":17
            }
        },
        "timestamp":"2021-11-16 22:43:19,157+0100",
        "service":"payment",
        "classification":"NA",
        "type":"STD"
    }

    ** Exceptions in log

    >>> logger = PyPwExtLogger(service='my-service')
    >>>
    >>> try:
            raise Exception("Something went wrong")
    >>> except:
            logger.exception(f"This is an exception", exc_info=True, stack_info=True)
    {
        "level":"ERROR",
        "location":"test_log_exception_manually:287",
        "message":{"msg":"This is an exception"},
        "timestamp":"2021-11-16 23:09:50,339+0100",
        "service":"my-service",
        "classification":"NA",
        "type":"STD",
        "exception":"Traceback (most recent call last): /.../pypwext-shared/tests/core/test_logging.py....",
        "exception_name":"Exception"
    }
"""
import logging
import json

from typing import Optional, Union, IO, Callable, Any, Dict
from functools import wraps
from enum import IntEnum

from pypwext.base import (
    InfoClassification,
    Message,
    Classification,
    Operation,
    Arguments,
    Return
)

from pypwext.encoders import PyPwExtJSONEncoder
from pypwext.utils import get_log_level

from aws_lambda_powertools.logging.logger import PowertoolsFormatter, Logger

LogType: str = 'type'
"""The `LogEntryType` to add to the log."""

VERBOSE = logging.DEBUG - 1
"""Verbose log level.

This is an addition of the log levels to allow for verbose level logging.
"""


class LogEntryType(IntEnum):
    """Specifies the log entry type."""
    STD = 0
    """Standard log entry."""
    AUDIT = 1
    """Audit log entry."""


class PyPwExtLogger(Logger):
    """ Override `Logger` to add pypwext specific fields to have a equal and conformat logs.

        # Sample usage

        >>> from pypwext.base import InfoClassification
        >>> from pypwext.logging import PyPwExtLogger, Classification, LogType, LogEntryType
        >>>
        >>> logger = PyPwExtLogger(service="payment")
                def pay():
                    logger.info({
                        "operation": "payment_finished",
                        "credit_card_id": 777111333,
                        Classification: InfoClassification.CORPORATE_SENSITIVE_INFO,
                        LogType: LogEntryType.AUDIT
                    })
        >>>
        >>> pay()
        {
            "level":"INFO",
            "location":"pay:24",
            "message":{
                "operation":"payment_finished",
                "credit_card_id":777111333
            },
            "timestamp":"2021-11-16 15:58:41,874+0100",
            "service":"payment",
            "classification":"CORPORATE_SENSITIVE_INFO",
            "type":"AUDIT"
        }
    """

    def __init__(
            self,
            service: Optional[str] = None,
            level: Union[str, int, None] = None,
            child: bool = False,
            sampling_rate: Optional[float] = None,
            stream: Optional[IO[str]] = None,
            logger_formatter: Optional[PowertoolsFormatter] = None,
            logger_handler: Optional[logging.Handler] = None,
            custom_encoder: Optional[Callable[[Any], str]] = None,
            **kwargs):
        """See `Logger` for more information about initialization.

            Additional Args:
                default_logger(bool):                   If `True` the logger will be set as the default logger.
                json_serializer(Callable[[Dict], str]): Function that serializes the log entry to JSON, default is `json.dumps`.
                custom_encoder(Callable[[Any], str]):   Function that encodes the json data, default is `PyPwExtJSONEncoder`
        """

        encoder = PyPwExtJSONEncoder(custom_encoder)

        super().__init__(
            service=service,
            level=level,
            child=child,
            sampling_rate=sampling_rate,
            stream=stream,
            logger_formatter=logger_formatter,
            logger_handler=logger_handler,
            json_default=lambda o: encoder.default(o),
            **kwargs)

        # This is the actual addition
        logging.addLevelName(VERBOSE, "VERBOSE")

        self.append_keys(
            classification=InfoClassification.NA.name,
            type=LogEntryType.STD.name
        )

    def verbose(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.log(VERBOSE, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.log(logging.INFO, msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self.log(logging.WARN, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.log(logging.CRITICAL, msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        """Overridden to ensure required fields are added to the log."""

        if not isinstance(msg, dict):
            msg = {
                Message: msg,
                Classification: InfoClassification.NA.name,
                LogType: LogEntryType.STD.name
            }

        clzf = msg.get(Classification)
        if clzf:
            del msg[Classification]

            if isinstance(clzf, InfoClassification):
                clzf = clzf.name

            self.append_keys(classification=clzf)

        log_type = msg.get(LogType)
        if log_type:
            del msg[LogType]

            if isinstance(log_type, LogEntryType):
                log_type = log_type.name

            self.append_keys(type=log_type)

        operation = msg.get(Operation)
        if operation:
            del msg[Operation]

            self.append_keys(operation=operation)
        else:
            self.remove_keys(Operation)

        if msg.get(Message) == '':
            del msg[Message]

        corr_id = super().get_correlation_id()
        if corr_id:
            self.append_keys(correlation_id=corr_id)
        else:
            self.remove_keys('correlation_id')

        super().log(level, msg, *args, **kwargs, stacklevel=3)

    def serialize(self, log: Dict[str, Any]) -> str:
        return json.dumps(log, cls=self.json_encoder)

    def method(
            self,
            _func: Optional[Callable] = None,
            level: Union[str, int, None] = None,
            out_level: Union[str, int, None] = None,
            classification: InfoClassification = InfoClassification.NA,
            type: LogEntryType = LogEntryType.STD,
            operation: Optional[str] = None,
            out_classification: InfoClassification = InfoClassification.NA,
            out_type: LogEntryType = LogEntryType.STD,
            out_operation: Optional[str] = None,
            eq_keywords: bool = True,
            stack_info: bool = True,
            log_exception: bool = True):
        """ Decorator to log entry and exit arguments on a function.

            Args:
                level:          If set, the log level will be set to this value, otherwise it will use the
                                environment variable `LOG_LEVEL`. If both are missing, DEBUG is used.

                out_level:      If set, the return level will be set to this value, otherwise it will use
                                the environment variable `LOG_LEVEL`. If both are missing, INFO is used.

                classification: The classification of the entry log. Default is `InfoClassification.NA`.

                type:           The type of the entry log. Default is `LogEntryType.STD`.

                operation:      The operation of the entry log. Default is `None`.

                out_classification: The classification of the exit log. Default is `InfoClassification.NA`.

                out_type:       The type of the exit log. Default is `LogEntryType.STD`.

                out_operation:  The operation of the exit log. Default is `None`.

                eq_keywords:    If `True`, the keywords for entering the same as return. Hence skip set all out_* parameters.
                                Default is `True`.

                service_name:   If set, it will use this name when creating the default logger. If logger is
                                provided or the default logger do already exists, this parameter will be ignored.

                log_exception:  If set to `False` it will **not** log exception. Default is `True`.


            If the service is not specified, it will use the `POWERTOOLS_SERVICE_NAME` environment
            variable to determine the service. When the function throws an exception, it will automatically log the
            exception and re-raise the error again.

        """
        def decorator(func):

            if eq_keywords:
                o_classification = classification
                o_type = type
                o_operation = operation
            else:
                o_classification = out_classification
                o_type = out_type
                o_operation = out_operation

            @wraps(func)
            def wrapper(*args, **kwargs):

                # Get the log levels
                in_level = get_log_level(level, logging.DEBUG)
                return_level = get_log_level(out_level, logging.INFO)

                # Get the function arguments
                args_names = func.__code__.co_varnames[:func.__code__.co_argcount]
                in_args = {**dict(zip(args_names, args)), **kwargs}

                # Log the function call
                entry_log = {
                    Message: f'Entering {func.__name__}',
                    Arguments: in_args,
                    Classification: classification.name,
                    LogType: type.name
                }

                if operation:
                    entry_log[Operation] = operation

                self.log(in_level, entry_log)

                try:

                    value = func(*args, **kwargs)

                    # Log the return
                    exit_log = {
                        Message: f'Exiting {func.__name__}',
                        Return: value,
                        Classification: o_classification.name,
                        LogType: o_type.name
                    }

                    if out_operation:
                        exit_log[Operation] = o_operation

                    self.log(return_level, exit_log)

                    return value

                except:  # noqa: E722

                    if not log_exception:
                        raise

                    exception_log = {
                        Message: f'Exception in {func.__name__}',
                        Arguments: in_args,
                        Classification: o_classification.name,
                        LogType: o_type.name
                    }

                    if out_operation:
                        exception_log[Operation] = o_operation

                    self.exception(exception_log, stack_info=stack_info)
                    raise

            return wrapper

        if _func is None:
            return decorator
        else:
            return decorator(_func)
