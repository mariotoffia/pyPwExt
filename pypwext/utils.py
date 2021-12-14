"""Miscellaneous utility functions."""

import os
import json
import logging
import re

from typing import Union, Optional, Dict, Any
from requests.structures import CaseInsensitiveDict


def get_log_level(level: Union[str, int, None], default: int = logging.DEBUG) -> int:
    """ Returns the loglevel supplied or gotten from LOG_LEVEL environment.

        If it fails, it will return the default value. If no default value
        is provided it will return logging.DEBUG.
    """
    if isinstance(level, int):
        return level

    log_level: Optional[str] = level or os.getenv('LOG_LEVEL')
    if log_level is None:
        return default

    if isinstance(log_level, str):
        try:
            return logging._nameToLevel[log_level.upper()]
        except KeyError:
            pass

    try:
        return int(log_level)
    except:  # noqa: E722
        return default


def render_arg_env_string(__str: str, in_args: Dict[str, Any]) -> str:
    """
    Render a string with the given arguments. If the format
    string (__str) contains {} segment with upper-case, they
    are treated as environment variables instead of using
    arguments supplied to the render function.

    Args:
        __str:      String to render.
        in_args:    Arguments to use for rendering. See below for how
                    to get the arguments.

    Returns:
        Rendered string.

    If it fails to find a argument specified in the string or
    an environment variable, raise a `ValueError`.

    Example:
    ```
    args_names = func.__code__.co_varnames[:func.__code__.co_argcount]
    in_args = {**dict(zip(args_names, args)), **kwargs}

    render_arg_env_string('{gw_id}.execute-api.{AWS_REGION}.amazonaws.com', in_args)

    """
    if not __str:
        return ''

    original_str = __str

    if '{' not in __str:
        return __str

    # Replace {} with supplied arguments
    for k, v in in_args.items():
        __str = __str.replace('{%s}' % k, str(v), 1)

    # Replace {env} variables in the string.
    for match in re.findall(r'{(.*?)}', __str):
        if not match.isupper():
            continue

        if os.getenv(match) is None:
            raise ValueError(
                'Environment variable {} is not set.' % match
            )

        __str = __str.replace('{%s}' % match, os.getenv(match, ''))

    if '{' not in __str:
        return __str

    raise ValueError(
        f'Unable to render string: {original_str}, still has substitutions left: {__str}'
    )


def try_convert_to_dict(data: Any) -> Union[Dict[str, Any], str, None]:
    """Try to convert the `data` to a dictionary.

    It will try to make sure that the data is converted to a plain `Dict[str, Any]`
    dictionary. If it fails, it will return `None`.
    """
    if not data:
        return None

    if isinstance(data, bytes):
        return try_convert_to_dict(data.decode('utf-8'))

    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    if isinstance(data, CaseInsensitiveDict):
        return {key: value for (key, value) in data.items()}

    return data
