"""Module that handles encoding of PyPwExt supported types"""

import traceback

from json import JSONEncoder
from datetime import date, datetime, time
from typing import Optional, Callable, Any, Union, Dict
from inspect import istraceback
from dataclasses import asdict

from pypwext.base import SupportsToCuratedDict, is_dataclass_instance, SupportsToJson
from pypwext.errors import PyPwExtError


class PyPwExtJSONEncoder(JSONEncoder):
    """Overrides the default JSON Encoder to handle types without custom encoders in code."""

    def __init__(self, prehook: Optional[Callable[[Any], str]] = None, *args, **kwargs):
        """Creates a new `PyPwExtJSONEncoder`.

            Args:
                prehook:    A function that will be called before encoding. If it returns `None`, the
                            `PyPwExtJSONEncoder` will try to encode the value.
        """
        super().__init__(*args, **kwargs)

        self._prehook = prehook

    def default(self, o: Any) -> Union[str, Dict[str, Any]]:
        """default handles various objects o that is not usually encodeable by `JSONEncoder`"""

        if self._prehook:
            value = self._prehook(o)
            if value:
                return value

        if o is None:
            return 'None'
        if isinstance(o, PyPwExtError):
            return o.json()
        if isinstance(o, Exception):
            return o.__str__()
        if isinstance(o, (date, datetime, time)):
            return o.isoformat()
        if istraceback(o):
            return ''.join(traceback.format_tb(o)).strip()

        try:
            if issubclass(type(o), SupportsToCuratedDict):
                return o.dict()
        except TypeError:
            pass

        if is_dataclass_instance(o):
            return asdict(o)

        try:
            if issubclass(type(o), SupportsToJson):
                return o.json()
        except TypeError:
            pass

        try:
            return super().default(o)
        except TypeError:
            try:
                return str(o)
            except:  # noqa: E722
                print(f'failed to encode {type(o)}')
                return None
