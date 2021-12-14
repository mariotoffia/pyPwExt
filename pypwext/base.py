""" Base module of definitions.

    The _SupportsXYZ_ `Prototypes` may be used in various ways.

    ### Example Usage:

    ```
    def persist(stores: Iterable[SupportsToJson]) -> str:
        for store in stores:
            persist(store.json())

    if issubclass(type(o), SupportsToJson):
        return o.json()
    ```

    The `InfoClassification` enumeration is used to classify information in
    e.g. error and log messages.
"""
from dataclasses import is_dataclass
from enum import IntEnum
from typing import Callable, Dict, Any, Protocol, runtime_checkable

# Standard keywords in logging and errors (allows for e.g. search in log-insights)

Classification: str = 'classification'
"""Entry in log that corresponds to `InfoClassification`"""

Message: str = 'msg'
"""The free form message"""

Arguments: str = 'args'
"""Arguments when logging e.g. function arguments"""

Return: str = 'return'
"""The return value when logging function return value."""

Operation: str = 'operation'
"""A semantic operation as pay-invoice, created-offer independent on function name."""

Error: str = 'error'
"""A key to hold one ´PyPwExtError` object or a list of them."""


@runtime_checkable
class SupportsToJson(Protocol):
    """ Protocol for objects that can be serialized to _JSON_.

        For example the `pydantic.BaseModel` supports this protocol.
    """

    def json(self, default: Callable[[Any], str] = None) -> str:
        """ Convert object to a _JSON_ str.

            Args:
                default: Default function to convert non-JSON-able objects.
                         It wil be fed into the _JSON_ encoder. The signature
                         is `default(obj) -> str` where _obj_ is the object to convert.
        """
        ...


@runtime_checkable
class SupportsToCuratedDict(Protocol):
    """ Protocol for objects that can be serialized to a curated dictionary.

        The _curated_ dictionary is a dictionary that contains essential information
        for the object, and with possibly some extra information, modified keys or
        the information is modified in some way.

        For example the `pydantic.BaseModel` supports this protocol.
    """

    def dict(self) -> Dict[Any, str]:
        """Convert object to a curated dictionary instance."""
        ...


class InfoClassification(IntEnum):
    """Classification of the information provided.

        This is used to determine how and where this information may be
        presented/stored or transmitted.

        This is used in errors, logs, and other data that needs to be controlled.
    """
    NA = 0
    """Not applicable."""
    AUTHORIZATION_INFO = 50
    """Contains information that may be presented to some peer to pass e.g. an invocation.

        This could be a OAuth2 Access Token or alike.
    """
    CORPORATE_SENSITIVE_INFO = 70
    """This is data that is sensitive from a PyPwExt point of view. Hence should be handeled with care!"""
    PII = 100
    """Is Personal Identifiable Information and hence is under GDPR regulation."""


def is_dataclass_instance(obj):
    """Checks if obj is a instance of whose class is decorated with a `@dataclass` annotation"""
    return is_dataclass(obj) and not isinstance(obj, type)
