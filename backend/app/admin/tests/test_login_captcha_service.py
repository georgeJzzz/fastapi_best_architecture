import pytest

from backend.app.admin.service import login_captcha_service as service_module
from backend.common.exception import errors


class FakeStore:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.saved: list[tuple[str, str, int]] = []
        self.discarded: list[str] = []

    async def save(self, uuid: str, code: str, *, expires_in: int) -> None:
        self.saved.append((uuid, code, expires_in))

    async def get(self, uuid: str) -> str | None:
        return self.value

    async def discard(self, uuid: str) -> None:
        self.discarded.append(uuid)


class FakeGenerator:
    @staticmethod
    async def generate() -> tuple[str, str]:
        return 'base64-image', 'AbC1'


@pytest.mark.anyio
async def test_login_captcha_create_stores_generated_code(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_login_config(db) -> None:  # noqa: ANN001
        return None

    fake_store = FakeStore('AbC1')
    service = service_module.LoginCaptchaService(store=fake_store, generator=FakeGenerator())
    monkeypatch.setattr(service_module, 'load_login_config', fake_load_login_config)
    monkeypatch.setattr(service_module, 'uuid4_str', lambda: 'captcha-id')
    monkeypatch.setattr(service_module.settings, 'LOGIN_CAPTCHA_ENABLED', True)
    monkeypatch.setattr(service_module.settings, 'LOGIN_CAPTCHA_EXPIRE_SECONDS', 300)

    result = await service.create(db=None)

    assert result.uuid == 'captcha-id'
    assert result.image == 'base64-image'
    assert fake_store.saved == [('captcha-id', 'AbC1', 300)]


@pytest.mark.anyio
async def test_login_captcha_verify_consumes_valid_captcha() -> None:
    fake_store = FakeStore('AbC1')
    service = service_module.LoginCaptchaService(store=fake_store)

    await service.verify(uuid='captcha-id', captcha='abc1')

    assert fake_store.discarded == ['captcha-id']


@pytest.mark.anyio
async def test_login_captcha_verify_rejects_missing_value() -> None:
    with pytest.raises(errors.RequestError):
        await service_module.login_captcha_service.verify(uuid=None, captcha='abc1')


@pytest.mark.anyio
async def test_login_captcha_verify_rejects_mismatch() -> None:
    fake_store = FakeStore('AbC1')
    service = service_module.LoginCaptchaService(store=fake_store)

    with pytest.raises(errors.CustomError):
        await service.verify(uuid='captcha-id', captcha='wrong')

    assert fake_store.discarded == []


@pytest.mark.anyio
async def test_login_captcha_verify_if_enabled_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load_login_config(db) -> None:  # noqa: ANN001
        return None

    fake_store = FakeStore('AbC1')
    service = service_module.LoginCaptchaService(store=fake_store)
    monkeypatch.setattr(service_module, 'load_login_config', fake_load_login_config)
    monkeypatch.setattr(service_module.settings, 'LOGIN_CAPTCHA_ENABLED', False)

    await service.verify_if_enabled(None, uuid=None, captcha=None)

    assert fake_store.discarded == []


@pytest.mark.anyio
async def test_login_captcha_discard_deletes_captcha() -> None:
    fake_store = FakeStore('AbC1')
    service = service_module.LoginCaptchaService(store=fake_store)

    await service.discard('captcha-id')

    assert fake_store.discarded == ['captcha-id']
