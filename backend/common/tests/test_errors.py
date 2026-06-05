import pytest

from backend.common.exception import errors


def test_require_found_returns_value() -> None:
    value = {'id': 1}

    assert errors.require_found(value, msg='资源不存在') is value


def test_require_found_raises_not_found_for_falsy_value() -> None:
    with pytest.raises(errors.NotFoundError) as exc_info:
        errors.require_found(None, msg='资源不存在')

    assert exc_info.value.msg == '资源不存在'
