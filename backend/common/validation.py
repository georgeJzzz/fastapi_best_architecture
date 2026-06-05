from collections.abc import Iterable
from typing import Any

from backend.common.exception import errors


def require_complete_ids(records: Iterable[Any], requested_ids: Iterable[int], *, msg: str) -> None:
    """要求查询结果覆盖所有请求 ID"""
    requested_id_set = set(requested_ids)
    if {record.id for record in records} != requested_id_set:
        raise errors.NotFoundError(msg=msg)
