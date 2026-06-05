import json

import pytest

from backend.common.exception import errors
from backend.plugin.oauth2.enums import UserSocialAuthType
from backend.plugin.oauth2.service import oauth2_state_service as service_module


class FakeRedis:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.set_calls: list[tuple[str, str, int]] = []
        self.deleted: list[str] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls.append((key, value, ex or 0))

    async def get(self, key: str) -> str | None:
        return self.value

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


@pytest.mark.anyio
async def test_oauth2_state_create_login_stores_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module.oauth2_state_service, 'generate_state', lambda: 'state-id')
    monkeypatch.setattr(service_module.settings, 'OAUTH2_STATE_EXPIRE_SECONDS', 300)

    state = await service_module.oauth2_state_service.create_login()

    assert state == 'state-id'
    assert fake_redis.set_calls == [
        (
            service_module.oauth2_state_service.key('state-id'),
            json.dumps({'type': UserSocialAuthType.login.value}),
            300,
        )
    ]


@pytest.mark.anyio
async def test_oauth2_state_create_binding_stores_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module.oauth2_state_service, 'generate_state', lambda: 'state-id')

    await service_module.oauth2_state_service.create_binding(user_id=42)

    payload = json.loads(fake_redis.set_calls[0][1])
    assert payload == {'type': UserSocialAuthType.binding.value, 'user_id': 42}


@pytest.mark.anyio
async def test_oauth2_state_consume_returns_payload_and_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis(json.dumps({'type': UserSocialAuthType.login.value}))
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)

    payload = await service_module.oauth2_state_service.consume('state-id')

    assert payload == {'type': UserSocialAuthType.login.value}
    assert fake_redis.deleted == [service_module.oauth2_state_service.key('state-id')]


@pytest.mark.anyio
async def test_oauth2_state_consume_rejects_missing_state() -> None:
    with pytest.raises(errors.ForbiddenError):
        await service_module.oauth2_state_service.consume(None)


@pytest.mark.anyio
async def test_oauth2_state_consume_rejects_unknown_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis(None)
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)

    with pytest.raises(errors.ForbiddenError):
        await service_module.oauth2_state_service.consume('state-id')

    assert fake_redis.deleted == []
