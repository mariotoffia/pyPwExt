import os

from pypwext.environment import init_env


def test_init_env():

    def check_delete(s: str):
        if os.environ.get(s):
            del os.environ[s]

    check_delete('LOG_LEVEL')
    check_delete('POWERTOOLS_SERVICE_NAME')
    check_delete('POWERTOOLS_METRICS_NAMESPACE')

    logging_level = os.environ.get('LOGGING_LEVEL')
    service_name = os.environ.get('SERVICE_NAME')

    os.environ['LOGGING_LEVEL'] = 'test-level'
    os.environ['SERVICE_NAME'] = 'test-service'

    init_env()

    try:

        assert os.environ['LOG_LEVEL'] == 'test-level'
        assert os.environ['POWERTOOLS_SERVICE_NAME'] == 'test-service'
        assert os.environ['POWERTOOLS_METRICS_NAMESPACE'] == 'test-service'

    finally:

        check_delete('LOG_LEVEL')
        check_delete('POWERTOOLS_SERVICE_NAME')
        check_delete('POWERTOOLS_METRICS_NAMESPACE')

        if logging_level:
            os.env['LOGGING_LEVEL'] = logging_level

        if service_name:
            os.environ['SERVICE_NAME'] = service_name
