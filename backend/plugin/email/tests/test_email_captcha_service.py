import pytest

from backend.common.exception import errors
from backend.plugin.email.service import email_captcha_service as service_module


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
async def test_email_captcha_send_stores_code_and_sends_email(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[object, str | list[str], str, dict[str, int | str], str]] = []
    fake_redis = FakeRedis()

    async def fake_send_email(db, recipients, subject, content, template=None) -> None:  # noqa: ANN001
        sent.append((db, recipients, subject, content, template))

    monkeypatch.setattr(service_module, 'redis_client', fake_redis)
    monkeypatch.setattr(service_module.email_captcha_service, 'send_email', fake_send_email)
    monkeypatch.setattr(service_module.email_captcha_service, 'generate_code', lambda: '123456')
    monkeypatch.setattr(service_module.settings, 'EMAIL_CAPTCHA_EXPIRE_SECONDS', 180)

    await service_module.email_captcha_service.send(db=None, recipients='user@example.com', ip='127.0.0.1')

    assert fake_redis.set_calls == [
        (service_module.email_captcha_service.key('127.0.0.1'), '123456', 180)
    ]
    assert sent == [
        (None, 'user@example.com', 'FBA 验证码', {'code': '123456', 'expired': 3}, 'captcha.html')
    ]


@pytest.mark.anyio
async def test_email_captcha_verify_consumes_valid_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis('123456')
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)

    await service_module.email_captcha_service.verify(captcha='123456', ip='127.0.0.1')

    assert fake_redis.deleted == [service_module.email_captcha_service.key('127.0.0.1')]


@pytest.mark.anyio
async def test_email_captcha_verify_rejects_expired_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis(None)
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)

    with pytest.raises(errors.RequestError):
        await service_module.email_captcha_service.verify(captcha='123456', ip='127.0.0.1')


@pytest.mark.anyio
async def test_email_captcha_verify_rejects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis('123456')
    monkeypatch.setattr(service_module, 'redis_client', fake_redis)

    with pytest.raises(errors.CustomError):
        await service_module.email_captcha_service.verify(captcha='654321', ip='127.0.0.1')

    assert fake_redis.deleted == []
