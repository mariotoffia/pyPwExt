"""Module that handles the environment for PyPwExt core"""
import os


def init_env():
    """ Initializes the environment.

        Copies environment variables to to the required ones for
        AWS lambda powertools.
    """
    if (
        os.environ.get('SERVICE_NAME') is not None and  # noqa: W504
        os.environ.get('POWERTOOLS_SERVICE_NAME') is None
    ):
        os.environ['POWERTOOLS_SERVICE_NAME'] = os.environ.get('SERVICE_NAME')

    if (
        os.environ.get('METRICS_NAMESPACE') is not None and  # noqa: W504
        os.environ.get('POWERTOOLS_METRICS_NAMESPACE') is None
    ):
        # Set metrics namespace as service name
        os.environ['POWERTOOLS_METRICS_NAMESPACE'] = os.environ.get('METRICS_NAMESPACE')
