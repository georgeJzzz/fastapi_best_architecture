from datetime import datetime, timedelta, timezone as datetime_timezone

import pytest

from backend.app.admin.service import user_security_gate as service_module
from backend.common.exception import errors


class FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        self.set_calls.append((key, value, ex or 0))

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class FakeTimezone:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, 0, tzinfo=datetime_timezone.utc)

    def now(self) -> datetime:
        return self.current

    @staticmethod
    def from_str(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @staticmethod
    def to_str(value: datetime) -> str:
        return value.isoformat()


@pytest.mark.anyio
async def test_user_security_gate_rejects_disabled_user() -> None:
    with pytest.raises(errors.AuthorizationError):
        await service_module.user_security_gate.check_login_allowed(user_id=1, user_status=0)


@pytest.mark.anyio
async def test_user_security_gate_rejects_active_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_timezone = FakeTimezone()
    locked_until = fake_timezone.to_str(fake_timezone.now() + timedelta(minutes=2))
    fake_redis = FakeRedis({service_module.user_security_gate.lock_key(1): locked_until})
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module, 'timezone', fake_timezone)

    with pytest.raises(errors.AuthorizationError) as exc_info:
        await service_module.user_security_gate.check_login_allowed(user_id=1, user_status=1)

    assert '2 分钟后重试' in exc_info.value.msg
    assert fake_redis.deleted == []


@pytest.mark.anyio
async def test_user_security_gate_clears_expired_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_timezone = FakeTimezone()
    locked_until = fake_timezone.to_str(fake_timezone.now() - timedelta(minutes=1))
    fake_redis = FakeRedis({service_module.user_security_gate.lock_key(1): locked_until})
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module, 'timezone', fake_timezone)

    await service_module.user_security_gate.check_login_allowed(user_id=1, user_status=1)

    assert fake_redis.deleted == [
        service_module.user_security_gate.lock_key(1),
        service_module.user_security_gate.failure_key(1),
    ]


@pytest.mark.anyio
async def test_user_security_gate_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_user_security_config(db) -> None:  # noqa: ANN001
        return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module, 'load_user_security_config', fake_load_user_security_config)
    monkeypatch.setattr(service_module.settings, 'USER_LOCK_THRESHOLD', 3)
    monkeypatch.setattr(service_module.settings, 'USER_LOCK_SECONDS', 180)

    await service_module.user_security_gate.record_login_failure(db=None, user_id=1)

    assert fake_redis.set_calls == [
        (service_module.user_security_gate.failure_key(1), '1', 180)
    ]


@pytest.mark.anyio
async def test_user_security_gate_locks_when_threshold_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_user_security_config(db) -> None:  # noqa: ANN001
        return None

    fake_timezone = FakeTimezone()
    fake_redis = FakeRedis({service_module.user_security_gate.failure_key(1): '2'})
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module, 'timezone', fake_timezone)
    monkeypatch.setattr(service_module, 'load_user_security_config', fake_load_user_security_config)
    monkeypatch.setattr(service_module.settings, 'USER_LOCK_THRESHOLD', 3)
    monkeypatch.setattr(service_module.settings, 'USER_LOCK_SECONDS', 180)

    with pytest.raises(errors.AuthorizationError):
        await service_module.user_security_gate.record_login_failure(db=None, user_id=1)

    assert fake_redis.set_calls == [
        (service_module.user_security_gate.failure_key(1), '3', 180),
        (
            service_module.user_security_gate.lock_key(1),
            fake_timezone.to_str(fake_timezone.now() + timedelta(seconds=180)),
            180,
        ),
    ]
