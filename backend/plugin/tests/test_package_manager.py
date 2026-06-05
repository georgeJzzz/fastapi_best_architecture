import pytest

from backend.common.enums import PluginType
from backend.core.conf import settings
from backend.plugin.package_manager import PluginPackageManager


@pytest.mark.anyio
async def test_plugin_package_manager_rejects_install_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.common.exception import errors

    monkeypatch.setattr(settings, 'ENVIRONMENT', 'prod')

    with pytest.raises(errors.RequestError, match='非开发环境'):
        await PluginPackageManager().install_backend(type=PluginType.git, repo_url='https://example.com/plugin.git')


@pytest.mark.anyio
async def test_plugin_package_manager_marks_backend_install_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import installer
    from backend.plugin import package_manager as package_manager_module

    changed = False
    cache_cleared = False

    async def fake_install_git_plugin(repo_url: str) -> str:
        assert repo_url == 'https://example.com/demo.git'
        return 'demo'

    async def fake_mark_changed() -> None:
        nonlocal changed
        changed = True

    def fake_clear_cache() -> None:
        nonlocal cache_cleared
        cache_cleared = True

    monkeypatch.setattr(settings, 'ENVIRONMENT', 'dev')
    monkeypatch.setattr(installer, 'install_git_plugin', fake_install_git_plugin)
    monkeypatch.setattr(package_manager_module.plugin_runtime_status, 'mark_changed', fake_mark_changed)
    monkeypatch.setattr(package_manager_module.plugin_registry, 'clear_cache', fake_clear_cache)

    plugin_name = await PluginPackageManager().install_backend(
        type=PluginType.git,
        repo_url='https://example.com/demo.git',
    )

    assert plugin_name == 'demo'
    assert changed
    assert cache_cleared
