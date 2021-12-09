import os
import sys
import requests

from logging import LogRecord
from datetime import datetime, timezone
from logging import StreamHandler


class ElasticSearchHandler(StreamHandler):
    """ Port of Anders eslogger to be a handler for python logging standard framework.

        NOTE: If it fails to send to elastic search, it will be logged to stderr.

        ### Standard logging

        ```
        import logging
        from pypwext.elslogging import ElasticSearchHandler

        logger = logging.getLogger(__name__)
        logger.addHandler(ElasticSearchHandler())
        logger.info('Hello world')
        ```

        ### PyPwExt/JSON logging to elastic search

        ```
        from pypwext.elslogging import ElasticSearchHandler
        from pypwext.logging import PyPwExtLogger

        logger = logger = PyPwExtLogger(service="payment", logger_handler=ElasticSearchHandler())
        logger.info('Hello world')
        ```
    """

    def __init__(
            self,
            es_endpoint: str = None,
            service_name: str = None,
            function: str = None,
            environment: str = None):
        """ Initialize the elastic search handler with necessary info.

            Args:
                es_endpoint (str):  The elastic search endpoint.
                                    If not set ES_ENDPOINT env variable will be used.

                service_name (str): The name of this service.
                                    If not set SERVICE_NAME env variable will be used.

                function (str):     The name of the lambda function that is logging.
                                    If not set AWS_LAMBDA_FUNCTION_NAME env variable will be used.

                environment (str):  The environment this service is running in.
                                    If not set ENVIRONMENT env variable will be used.
        """
        self.es_endpoint = es_endpoint or os.getenv('ES_ENDPOINT')
        self.service_name = service_name or os.getenv('SERVICE_NAME')
        self.function = function or os.getenv('AWS_LAMBDA_FUNCTION_NAME')
        self.environment = environment or os.getenv('ENVIRONMENT')

    def emit(self, record: LogRecord):
        """ Emits the record to elastic search REST endpoint.

            If elastic search fails to accept the record, it will be logged to stderr.
        """
        document = {
            'TimeStamp': datetime.now(timezone.utc).isoformat(),
            'Environment': self.environment,
            'Message': self.format(record),
            'Level': record.levelname,
            'System': self.service_name
        }

        if self.function:
            document['Function'] = self.function

        headers = {'Content-Type': 'application/json'}
        url = f'https://{self.es_endpoint}/debuglog/log'

        resp = requests.post(url, json=document, headers=headers)

        if resp.status_code != 201:
            print(document, file=sys.stderr)
            print(
                'Failure posting log to ElasticSearch: '
                f'{resp.status_code} {resp.reason}', file=sys.stderr
            )
