import pytest

from fastapi import FastAPI

from backend.common.dataclasses import PluginEntry
from backend.common.enums import PluginType
from backend.plugin import PluginLifecycle


def test_plugin_lifecycle_delegates_registry_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    lifecycle = PluginLifecycle()
    plugins = [PluginEntry(name='notice'), PluginEntry(name='dict')]
    ordered = [plugins[1], plugins[0]]

    def fake_order(value: list[PluginEntry]) -> list[PluginEntry]:
        assert value is plugins
        return ordered

    monkeypatch.setattr(lifecycle_module.plugin_registry, 'order', fake_order)

    assert lifecycle.order(plugins) is ordered


def test_plugin_lifecycle_delegates_runtime_status_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    def fake_parse_enable(plugin_info: str | None, default_status: int) -> str:
        assert plugin_info == 'raw-plugin-info'
        assert default_status == 0
        return 'parsed'

    monkeypatch.setattr(lifecycle_module.plugin_runtime_status, 'parse_enable', fake_parse_enable)

    assert PluginLifecycle.parse_enable('raw-plugin-info', 0) == 'parsed'


def test_plugin_lifecycle_build_router_uses_registry_and_api_mounting(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    lifecycle = PluginLifecycle()
    extend_plugins = [PluginEntry(name='dict')]
    app_plugins = [PluginEntry(name='notice')]
    ordered_plugins = [PluginEntry(name='dict'), PluginEntry(name='notice')]
    router_marker = object()

    monkeypatch.setattr(lifecycle, 'parse_config', lambda: (extend_plugins, app_plugins))
    monkeypatch.setattr(lifecycle, 'order', lambda plugins: ordered_plugins)

    def fake_build_router(plugins: list[PluginEntry]) -> object:
        assert plugins is ordered_plugins
        return router_marker

    monkeypatch.setattr(lifecycle_module.plugin_api_mounting, 'build_router', fake_build_router)

    assert lifecycle.build_router() is router_marker


def test_plugin_lifecycle_delegates_hook_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    app = FastAPI()
    registered = False

    def fake_register_hooks(value: FastAPI) -> None:
        nonlocal registered
        assert value is app
        registered = True

    monkeypatch.setattr(lifecycle_module.plugin_hooks, 'register_hooks', fake_register_hooks)

    PluginLifecycle().register_hooks(app)

    assert registered


@pytest.mark.anyio
async def test_plugin_lifecycle_delegates_backend_install(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    async def fake_install_backend(
        *,
        type: PluginType,
        file=None,  # noqa: ANN001
        repo_url: str | None = None,
    ) -> str:
        assert type == PluginType.git
        assert file is None
        assert repo_url == 'https://example.com/plugin.git'
        return 'demo'

    monkeypatch.setattr(lifecycle_module.plugin_package_manager, 'install_backend', fake_install_backend)

    assert await PluginLifecycle().install_backend(type=PluginType.git, repo_url='https://example.com/plugin.git') == 'demo'


def test_plugin_lifecycle_delegates_requirement_install(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    installed: list[str] = []

    monkeypatch.setattr(lifecycle_module.plugin_package_manager, 'install_requirements', installed.append)

    PluginLifecycle().install_requirements('dict')

    assert installed == ['dict']


@pytest.mark.anyio
async def test_plugin_lifecycle_delegates_requirement_uninstall(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.plugin import lifecycle as lifecycle_module

    uninstalled: list[str] = []

    async def fake_uninstall_requirements(plugin: str) -> None:
        uninstalled.append(plugin)

    monkeypatch.setattr(lifecycle_module.plugin_package_manager, 'uninstall_requirements', fake_uninstall_requirements)

    await PluginLifecycle().uninstall_requirements('dict')

    assert uninstalled == ['dict']
