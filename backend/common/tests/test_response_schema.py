from backend.common.response.response_code import CustomResponseCode
from backend.common.response.response_schema import response_base


def test_success_by_count_returns_success_for_positive_count() -> None:
    response = response_base.success_by_count(1)

    assert response.code == CustomResponseCode.HTTP_200.code


def test_success_by_count_returns_fail_for_zero_count() -> None:
    response = response_base.success_by_count(0)

    assert response.code == CustomResponseCode.HTTP_400.code
