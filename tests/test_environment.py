import os

from pypwext.environment import init_env


def test_init_env():

    def check_delete(s: str):
        if os.environ.get(s):
            del os.environ[s]

    check_delete('POWERTOOLS_SERVICE_NAME')
    check_delete('POWERTOOLS_METRICS_NAMESPACE')

    service_name = os.environ.get('SERVICE_NAME')
    metrics_namespace = os.environ.get('METRICS_NAMESPACE')

    os.environ['SERVICE_NAME'] = 'test-service'
    os.environ['METRICS_NAMESPACE'] = 'test-namespace'

    init_env()

    try:

        assert os.environ['POWERTOOLS_SERVICE_NAME'] == 'test-service'
        assert os.environ['POWERTOOLS_METRICS_NAMESPACE'] == 'test-namespace'

    finally:

        check_delete('POWERTOOLS_SERVICE_NAME')
        check_delete('POWERTOOLS_METRICS_NAMESPACE')

        if service_name:
            os.environ['SERVICE_NAME'] = service_name

        if metrics_namespace:
            os.environ['METRICS_NAMESPACE'] = metrics_namespace
