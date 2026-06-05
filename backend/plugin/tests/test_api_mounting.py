from types import SimpleNamespace

import pytest

from fastapi import APIRouter

from backend.common.dataclasses import PluginEntry
from backend.plugin.api_mounting import PluginApiMounting
from backend.plugin.errors import PluginInjectError


def test_plugin_api_mounting_injects_app_router(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_router = APIRouter()

    @plugin_router.get('/demo')
    async def demo():  # noqa: ANN202
        return {'ok': True}

    def fake_import_module_cached(module_path: str):  # noqa: ANN001
        assert module_path == 'backend.plugin.notice.api.router'
        return SimpleNamespace(v1=plugin_router)

    target_router = APIRouter()
    monkeypatch.setattr('backend.plugin.api_mounting.import_module_cached', fake_import_module_cached)

    PluginApiMounting().inject_app_router(
        PluginEntry(name='notice', routers=['v1']),
        target_router,
    )

    assert any(route.path == '/demo' for route in target_router.routes)


def test_plugin_api_mounting_rejects_missing_app_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'backend.plugin.api_mounting.import_module_cached',
        lambda module_path: SimpleNamespace(),
    )

    with pytest.raises(PluginInjectError, match='应用级插件 notice 路由注入失败'):
        PluginApiMounting().inject_app_router(
            PluginEntry(name='notice', routers=['v1']),
            APIRouter(),
        )
