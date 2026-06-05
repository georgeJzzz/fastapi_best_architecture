from collections.abc import Callable
from types import SimpleNamespace

import pytest

from backend.common.exception import errors
from backend.plugin.features import PluginFeatureGateway


def _installed_plugins(*names: str) -> Callable[[str], bool]:
    installed = set(names)
    return lambda plugin: plugin in installed


@pytest.mark.anyio
async def test_plugin_feature_gateway_reads_config_values(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = PluginFeatureGateway()
    expected_db = object()

    class FakeConfigService:
        async def get_all(self, *, db, type) -> list[dict[str, str]]:  # noqa: ANN001
            assert db is expected_db
            assert type == 'login'
            return [{'key': 'LOGIN_CAPTCHA_ENABLED', 'value': 'true'}]

    def fake_import_module_cached(module_path: str) -> object:
        if module_path == 'backend.plugin.config.enums':
            return SimpleNamespace(ConfigType=SimpleNamespace(login='login'))
        if module_path == 'backend.plugin.config.service.config_service':
            return SimpleNamespace(config_service=FakeConfigService())
        raise AssertionError(module_path)

    monkeypatch.setattr('backend.plugin.features.plugin_lifecycle.is_installed', _installed_plugins('config'))
    monkeypatch.setattr('backend.plugin.features.import_module_cached', fake_import_module_cached)

    configs = await gateway.config_values(db=expected_db, config_type_attr='login')  # type: ignore[arg-type]

    assert configs == {'LOGIN_CAPTCHA_ENABLED': 'true'}


@pytest.mark.anyio
async def test_plugin_feature_gateway_skips_missing_config_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('backend.plugin.features.plugin_lifecycle.is_installed', _installed_plugins())

    configs = await PluginFeatureGateway().config_values(db=object(), config_type_attr='login')  # type: ignore[arg-type]

    assert configs is None


@pytest.mark.anyio
async def test_plugin_feature_gateway_verifies_email_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    class FakeEmailCaptchaService:
        async def verify(self, *, captcha: str) -> None:
            captured.append(captcha)

    monkeypatch.setattr('backend.plugin.features.plugin_lifecycle.is_installed', _installed_plugins('email'))
    monkeypatch.setattr(
        'backend.plugin.features.import_module_cached',
        lambda module_path: SimpleNamespace(email_captcha_service=FakeEmailCaptchaService()),
    )

    await PluginFeatureGateway().verify_email_captcha(captcha='123456')

    assert captured == ['123456']


@pytest.mark.anyio
async def test_plugin_feature_gateway_rejects_missing_email_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('backend.plugin.features.plugin_lifecycle.is_installed', _installed_plugins())

    with pytest.raises(errors.ServerError, match='电子邮件插件未安装'):
        await PluginFeatureGateway().verify_email_captcha(captcha='123456')


@pytest.mark.anyio
async def test_plugin_feature_gateway_deletes_oauth2_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    db = object()
    calls: list[tuple[object, int]] = []

    class FakeUserSocialDao:
        async def delete_by_user_id(self, db, user_id: int) -> int:  # noqa: ANN001
            calls.append((db, user_id))
            return 1

    monkeypatch.setattr('backend.plugin.features.plugin_lifecycle.is_installed', _installed_plugins('oauth2'))
    monkeypatch.setattr(
        'backend.plugin.features.import_module_cached',
        lambda module_path: SimpleNamespace(user_social_dao=FakeUserSocialDao()),
    )

    count = await PluginFeatureGateway().delete_oauth2_bindings_by_user_id(db, 7)  # type: ignore[arg-type]

    assert count == 1
    assert calls == [(db, 7)]


@pytest.mark.anyio
async def test_plugin_feature_gateway_runs_casbin_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    request = object()
    captured: list[object] = []

    async def fake_casbin_verify(value) -> None:  # noqa: ANN001
        captured.append(value)

    monkeypatch.setattr('backend.plugin.features.plugin_lifecycle.is_installed', _installed_plugins('casbin_rbac'))
    monkeypatch.setattr(
        'backend.plugin.features.import_module_cached',
        lambda module_path: SimpleNamespace(casbin_verify=fake_casbin_verify),
    )

    await PluginFeatureGateway().casbin_verify(request)  # type: ignore[arg-type]

    assert captured == [request]
