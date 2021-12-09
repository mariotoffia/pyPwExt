"""Defines error base types and standard implementations.

    This module defines the base types `PyPwExtError` and `ErrorCollector` to be
    used to collect and return/raised/log errors.

    NOTE: When using the `ErrorCollector`, use the `ErrorAction` hint to follow
    the recomendation of RAISE or CONTINUE quite strict in order for the
    reader to easily understand the error handling.

    Also make note that the error mechanism do use `HTTPStatus` as the error code.

    The standard error types are:
    - `StdPyPwExtError`: Standard implementation of `PyPwExtError`
    - `StdErrorCollector`: Standard implementation of `ErrorCollector`
    - `PyPwExtErrorWithReturn`: Same as `StdPyPwExtError` but with `return_value` to use return from functions.

    This module exposes a decorator to collect `PyPwExtError` objects. This is useful, when you need to continue
    execution but want to collect errors to either return those. The pypwext response do also make use of the collector
    if it is installed (as with the example below). It may extract all errors and add those into the response.

    ```
    cors_config = CORSConfig(allow_origin="https://example.com", max_age=300)
    app = ApiGatewayResolver(cors=cors_config)
    tracer = Tracer()
    logger = PyPwExtLogger()
    errors = PyPwExtErrorHandler()
    service = PyPwExtService()

    @app.post("/send-contracts")
    @errors.collect(root=True)
    @service.response
    @log.method
    def send_contracts():
        people = json.loads(app.current_event.json_body)

        return PyPwExtResponse(
                status_code=HTTPStatus.OK,
                sent_contracts=[send(person) for person in people])

    @errors.collect
    def send(person):
        response = requests.put(person)

        if response.status_code != HTTPStatus.OK.value:

            raise PyPwExtErrorWithReturn(
                message="Failed to send contract",
                action=ErrorAction.CONTINUE if response.status_code == HTTPStatus.BAD_REQUEST.value else ErrorAction.RAISE
                code=HTTPStatus(response.status_code)
                return_value={'failed':True}
            )

    @logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
    @tracer.capture_lambda_handler
    def lambda_handler(event, context):
        return app.resolve(event, context)
    ```

    If any errors occurs in the send, the collector will collect the errors since `ErrorAction.CONTINUE`. But
    the `@pypwext_response` will create a `Response` object with the collected errors along with the `sent` list.
    In essence, the `@pypwext_response` will add a `error` key in the response body with either a single error
    JSON object or a list of errors.

    If it get a `HTTPStatus.BAD_REQUEST` it will return the collected errors as a JSON object without any in the
    sent since the error it marked "too severe" (`ErrorAction.RAISE`).

    This aligns the error handling in the system and if a `PyPwExtLogger` is installed, it will log the errors
    as well.
"""
import json

from typing_extensions import Protocol
from logging import Logger
from http import HTTPStatus
from enum import IntEnum
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass
from contextvars import ContextVar
from functools import wraps

from pypwext.base import InfoClassification, Message, Classification


class ErrorAction(IntEnum):
    """ErrorAction suggest how to handle an error."""
    INDECISIVE = 0
    """Unknown what action should be taken. User code may do any descition"""
    RAISE = 1
    """Suggested that the code should raise the error or return immediately"""
    CONTINUE = 2
    """Continuation is allowed since can still fulfill its purpose or want to collect all errors."""


@dataclass
class PyPwExtError(Exception):
    """The `PyPwExtError` is the base PyPwExt error that is able to collect more information.

        This is used to allow e.g. responses of a _REST_ API to be returned with or enough
        information to be logged and handled.

        `PyPwExtError` implement both the `SupportsJSON` and `SupportsToCuratedDic` protocol.
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args)

    @property
    def code(self) -> HTTPStatus:
        """_[mandatory]_ Code is the HTTP status code as form of an error/success code."""
        ...

    @property
    def action(self) -> ErrorAction:
        """_[mandatory]_ The action describes/indicates what to do when encountering this error."""
        ...

    @property
    def message(self) -> str:
        """_[mandatory]_ Message of the error occurred."""
        ...

    @property
    def classification(self) -> InfoClassification:
        """_[mandatory]_ The classification of the data/message in this error"""
        ...

    @property
    def details(self) -> Dict[str, Any]:
        """_[optional]_ Any type of extra details that gives this error a context.

            Details may be e.g. response from a REST API call or an
            _SQS_ event.
        """
        ...

    @property
    def inner(self) -> Optional['PyPwExtError']:
        """_[optional]_ An inner error that is encapsulated in this error."""
        ...

    def dict(self) -> Dict[Any, str]:
        """Returns a dictionary representation of a `PyPwExtError`"""
        d = {
            'code': self.code.value,
            'action': self.action.name,
            Message: self.message,
            Classification: self.classification.name
        }

        if self.details:
            d['details'] = self.details
        if self.inner:
            d['inner'] = self.inner.dict()

        return d

    def json(self, default: Callable[[Any], str] = None) -> str:
        """Returns a JSON representation of a `PyPwExtError`"""
        return json.dumps(self.dict(), default=default)


class ErrorCollector(Protocol):
    """The `ErrorCollector` is used to aggregate errors if continuation is required.

        All errors may then be presented in e.g. response on a _REST_ call.

        `ErrorCollector` implement the `SupportsJSON` protocol.
    """

    @property
    def errors(self) -> List[PyPwExtError]:
        """Returns the current set of collected errors."""
        ...

    def add(self, err: PyPwExtError) -> 'ErrorCollector':
        """Adds a single `PyPwExtError` into the collector."""
        ...

    def clear(self) -> 'ErrorCollector':
        """Clears the current set of collected errors."""
        ...

    def has_errors(self) -> bool:
        """Returns True if there are any errors in the collector."""
        return len(self.errors) > 0

    def has_errors_matcher(self, matcher: Callable[[PyPwExtError], bool]) -> bool:
        """ Returns true if any of the errors matches *matcher*.

            ### Example
            >>> from pypwext.errors import StdErrorCollector
            >>> from pypwext.errors import StdPyPwExtError, ErrorAction
            >>> from http import HTTPStatus
            >>>
            >>> x = StdErrorCollector()
            >>> x.add(StdPyPwExtError(code=HTTPStatus.BAD_REQUEST, message='Missing parameters'))
            >>> x.has_errors_matcher(lambda e: e.code == HTTPStatus.BAD_REQUEST)
            >>> True
        """
        return len(self.get_errors_matcher(matcher=matcher)) > 0

    def get_errors_matcher(self, matcher: Callable[[PyPwExtError], bool]) -> List[PyPwExtError]:
        """ Gets all errors matching the *matcher*

            See `has_errors_matcher` for more example usage.
        """
        return list(filter(matcher, self.errors))

    def get_highest(self) -> Optional[PyPwExtError]:
        """ Returns the error with the highest status code.

            If there are no errors, it returns None.
        """
        if self.has_errors():
            return max(self.errors, key=lambda e: e.code)
        return None

    def dict(self) -> Dict[str, Any]:
        """ Returns a dictionary representation of all errors.

            If only single error, it will be a dictionary, otherwise it will
            be rendered as an array of dictionaries.
        """
        if len(self.errors()) == 1:
            result = self.errors[0].dict()
        else:
            result = [e.dict() for e in self.errors]

        return result

    def json(self, default: Callable[[Any], str] = None) -> str:
        """Returns a _JSON_ representation for all errors.

            If only single error, it will be a _JSON_ object, otherwise it will
            be rendered as an array of _JSON_ objects.
        """
        return json.dumps(self.dict(), default=default)


class StdErrorCollector(ErrorCollector):
    """This is a standard implementation of the `ErrorCollector`"""

    def __init__(self):
        self._errors = []

    def add(self, err: PyPwExtError) -> 'ErrorCollector':
        self._errors.append(err)
        return self

    @property
    def errors(self) -> List[PyPwExtError]:
        return self._errors

    def clear(self) -> 'ErrorCollector':
        self._errors = []
        return self


@dataclass
class StdPyPwExtError(PyPwExtError):
    """Standard implementation of `PyPwExtError`"""
    @property
    def code(self) -> HTTPStatus:
        return self._code

    @property
    def action(self) -> ErrorAction:
        return self._action

    @property
    def message(self) -> str:
        return self._message

    @property
    def classification(self) -> InfoClassification:
        return self._classification

    @property
    def details(self) -> Dict[str, Any]:
        return self._details

    @property
    def inner(self) -> Optional[PyPwExtError]:
        return self._inner

    def __init__(
            self, message: str,
            code: HTTPStatus = HTTPStatus.BAD_REQUEST,
            action: ErrorAction = ErrorAction.RAISE,
            classification: InfoClassification = InfoClassification.NA,
            details: Dict[str, Any] = None,
            inner: PyPwExtError = None) -> None:

        super().__init__(message)

        if type(code) == int:
            code = HTTPStatus(code)

        self._code = code
        self._action = action
        self._message = message
        self._classification = classification
        self._details = details
        self._inner = inner

    def __str__(self) -> str:
        return f'{self.message}'

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}(code={self.code.name}, '
            f'action={self.action.name}, message={self.message}, '
            f'classification={self.classification.name}, details={self.details}, '
            f'inner={repr(self.inner) if self.inner else ""})')


@dataclass
class PyPwExtHTTPError(StdPyPwExtError):
    """Used when any HTTP error occurs."""

    def __init__(
            self, message: str,
            code: Union[HTTPStatus, int] = HTTPStatus.BAD_REQUEST,
            action: ErrorAction = ErrorAction.RAISE,
            classification: InfoClassification = InfoClassification.NA,
            details: Dict[str, Any] = None,
            inner: PyPwExtError = None) -> None:

        super().__init__(message, code, action, classification, details, inner)


@dataclass
class PyPwExtInternalError(StdPyPwExtError):
    """Used when any PyPwExt `core` internal error occurs."""

    def __init__(
            self, message: str,
            code: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR,
            action: ErrorAction = ErrorAction.RAISE,
            classification: InfoClassification = InfoClassification.NA,
            details: Dict[str, Any] = None,
            inner: PyPwExtError = None) -> None:

        super().__init__(message, code, action, classification, details, inner)


@dataclass
class PyPwExtErrorWithReturn(StdPyPwExtError):
    """ Implements `PyPwExtError` with a opaque return value.

        This error should be used when a function want to still return
        a value and raise an error that can be continues. Therefore
        the default action is `ErrorAction.CONTINUE`.

        The return value is opaque and is not part of the `json` or
        `dict` methods.
    """

    def __init__(
            self,
            message: str,
            return_value: Any = None,
            code: HTTPStatus = HTTPStatus.BAD_REQUEST,
            action: ErrorAction = ErrorAction.CONTINUE,
            classification: InfoClassification = InfoClassification.NA,
            details: Dict[str, Any] = None,
            inner: PyPwExtError = None) -> None:

        super().__init__(
            message,
            code,
            action,
            classification,
            details,
            inner)

        self._return_value = return_value

    @property
    def return_value(self) -> Any:
        """Returns the set return value"""
        return self._return_value


_current_collector = ContextVar('current_collector')
"""Internal context variable to keep track on the current `ErrorCollector`"""


def get_current_collector() -> ErrorCollector:
    """ Returns the current `ErrorCollector`

        This may be used in functions that wishes to by itself
        examine or otherwise handle the collected errors.

    """
    return _current_collector.get(None)


class PyPwExtErrorHandler():
    def __init__(
        self,
        logger: Optional[Logger] = None
    ) -> None:
        """Creates a new PyPwExt error handler

        Args:
            logger: The `Logger` to use for logging any errors encountered. If it is not
                    provided. The errors will be silentely added to the collector.
        """
        self.logger = logger

    def collector(self, safe=True) -> ErrorCollector:
        """Get the current collector (if any installed).

        Args:
            safe:   If `True` dummy collector will be returned if
                    no collector is installed.

        Returns:
            The current collector or `None` if none is installed.

        Internally it uses `get_current_collector`.
        """
        c = get_current_collector()

        if c is None and safe:
            return StdErrorCollector()

        return c

    def collect(
            self,
            _func: Optional[Callable] = None,
            root: bool = False,
            stack_info: bool = True) -> Callable:
        """ This will add error collection on a function`

            Args:
                root:   If True, this will be the root collector and make sure
                        that it installs a new `ErrorCollector` as the current collector.

            This only captures `PyPwExtError` objects. If any other it will be raised as normal.

            You may access the current `ErrorCollector` using `get_current_collector()` at any
            path in the code. If no collector is installed, it will raise the errors as normal.

            When the function exits, that has the `collect(root=True)` decorator, the
            current collector will be removed.
        """
        def decorator(func):

            @wraps(func)
            def wrapper(*args, **kwargs):

                token = None
                if root and get_current_collector() is None:
                    token = _current_collector.set(StdErrorCollector())

                try:
                    return func(*args, **kwargs)
                except PyPwExtError as e:

                    if self.logger:
                        self.logger.exception(
                            f'Function: {func.__name__} raised an error',
                            stack_info=stack_info
                        )

                    collector = get_current_collector()
                    if collector:
                        collector.add(e)

                    if e.action == ErrorAction.RAISE or not collector:
                        raise

                    if type(e) == PyPwExtErrorWithReturn:
                        return e.return_value
                    else:
                        return None

                except:  # noqa: E722

                    if self.logger:
                        self.logger.exception(
                            f'Function: {func.__name__} raised an error',
                            stack_info=stack_info
                        )

                    raise

                finally:
                    if token:
                        _current_collector.reset(token)

            return wrapper

        if _func is None:
            return decorator
        else:
            return decorator(_func)
