from types import SimpleNamespace

import pytest

from backend.common.exception import errors
from backend.common.validation import require_complete_ids


def test_require_complete_ids_accepts_matching_ids() -> None:
    records = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    require_complete_ids(records, [2, 1], msg='资源不存在')


def test_require_complete_ids_accepts_duplicate_requested_ids() -> None:
    records = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    require_complete_ids(records, [1, 1, 2], msg='资源不存在')


def test_require_complete_ids_rejects_missing_id() -> None:
    records = [SimpleNamespace(id=1)]

    with pytest.raises(errors.NotFoundError) as exc_info:
        require_complete_ids(records, [1, 2], msg='资源不存在')

    assert exc_info.value.msg == '资源不存在'
