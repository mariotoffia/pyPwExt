# flake8: noqa
from pypwext.errors import StdErrorCollector, StdPyPwExtError, ErrorAction
from pypwext.base import InfoClassification
from pypwext.errors import PyPwExtErrorHandler

from http import HTTPStatus


def test_std_pypwext_error_has_sensible_defaults():
    """Test to make sure that `StdPyPwExtError` has sensible defaults."""
    x = StdPyPwExtError('Test message')

    assert x.dict() == {"code": 400, "action": "RAISE", "msg": "Test message", "classification": "NA"}


def test_std_pypwext_error_no_inner_json():
    """
    Test that the std_pypwext_error function returns a JSON-serializable object.
    """
    x = StdPyPwExtError(
        "Test message",
        code=HTTPStatus.NOT_FOUND,
        action=ErrorAction.CONTINUE,
        classification=InfoClassification.PII,
        details={"response": {"status": "not found"}},
    )

    assert x.json() == (
        '{"code": 404, "action": "CONTINUE", "msg": "Test message", '
        '"classification": "PII", "details": {"response": {"status": "not found"}}}')


def test_std_pypwext_error_single_inner_json():
    """
    Test that the std_pypwext_error function returns a JSON-serializable object with an inner _JSON_.
    """
    x = StdPyPwExtError("Outer error", inner=StdPyPwExtError("Inner error"))

    assert x.json() == (
        '{"code": 400, "action": "RAISE", "msg": "Outer error", "classification": "NA", '
        '"inner": {"code": 400, "action": "RAISE", "msg": "Inner error", "classification": "NA"}}')


def test_error_collector_has_errors_matcher_simple():
    """Test to make sure that the `has_errors_matcher` predicate works as expected."""
    c = StdErrorCollector() \
        .add(StdPyPwExtError('Test message')) \
        .add(StdPyPwExtError(
            code=HTTPStatus.PARTIAL_CONTENT,
            message='Test message 2')
    )

    assert c.has_errors_matcher(lambda x: x.code == HTTPStatus.PARTIAL_CONTENT)
    assert c.has_errors_matcher(lambda x: x.code == HTTPStatus.NOT_FOUND) is False
    assert c.has_errors_matcher(lambda x: x.code == HTTPStatus.BAD_REQUEST)


def test_error_collector_get_errors_matcher_simple():
    """Test to make sure that the `get_errors_matcher` predicate works as expected."""
    c = StdErrorCollector() \
        .add(StdPyPwExtError('Test message')) \
        .add(StdPyPwExtError(
            code=HTTPStatus.PARTIAL_CONTENT,
            message='Test message 2')
    )

    x1 = c.get_errors_matcher(lambda x: x.code == HTTPStatus.PARTIAL_CONTENT)
    x2 = c.get_errors_matcher(lambda x: x.code == HTTPStatus.BAD_REQUEST)
    x3 = c.get_errors_matcher(lambda x: x.code == HTTPStatus.NOT_FOUND)
    assert len(x1) == 1
    assert len(x2) == 1
    assert len(x3) == 0
    assert x1[0].code == HTTPStatus.PARTIAL_CONTENT
    assert x2[0].code == HTTPStatus.BAD_REQUEST


def test_error_collector_get_error_with_highest_status_code():
    c = StdErrorCollector() \
        .add(StdPyPwExtError('Test message')) \
        .add(StdPyPwExtError(
            code=HTTPStatus.PARTIAL_CONTENT,
            message='Test message 2')
    )

    assert c.get_highest().code == HTTPStatus.BAD_REQUEST


def test_collect_error_handler():
    handler = PyPwExtErrorHandler()

    @handler.collect(root=True)
    def main():
        @handler.collect
        def test_handler():
            raise StdPyPwExtError(
                'This will be collected',
                action=ErrorAction.CONTINUE
            )

        test_handler()
        collector = handler.collector()
        assert len(collector.errors) == 1
        assert collector.errors[0].message == 'This will be collected'
        assert collector.errors[0].action == ErrorAction.CONTINUE

    main()
