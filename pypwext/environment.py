"""Module that handles the environment for PyPwExt core"""
import os


def init_env():
    """ Initializes the environment.

        Copies environment variables to to the required ones for
        AWS lambda powertools.
    """
    if (
        os.environ.get('LOGGING_LEVEL') is not None and  # noqa: W504
        os.environ.get('LOG_LEVEL') is None
    ):
        # Lambda Powertools uses LOG_LEVEL, but we use LOGGING_LEVEL
        os.environ['LOG_LEVEL'] = os.environ.get('LOGGING_LEVEL')

    if (
        os.environ.get('SERVICE_NAME') is not None and  # noqa: W504
        os.environ.get('POWERTOOLS_SERVICE_NAME') is None
    ):
        # Lambda Powertools uses POWERTOOLS_SERVICE_NAME, but we use SERVICE_NAME
        os.environ['POWERTOOLS_SERVICE_NAME'] = os.environ.get('SERVICE_NAME')

    if (
        os.environ.get('METRICS_NAMESPACE') is not None and  # noqa: W504
        os.environ.get('POWERTOOLS_METRICS_NAMESPACE') is None
    ):
        # Set metrics namespace as service name
        os.environ['POWERTOOLS_METRICS_NAMESPACE'] = os.environ.get('METRICS_NAMESPACE')
