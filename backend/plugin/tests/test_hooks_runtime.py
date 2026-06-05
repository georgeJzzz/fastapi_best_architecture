from types import SimpleNamespace

from fastapi import FastAPI

from backend.common.dataclasses import PluginEntry
from backend.plugin.hooks_runtime import PluginHooks


def test_plugin_hooks_runs_setup_hook() -> None:
    app = FastAPI()
    called: list[FastAPI] = []

    module = SimpleNamespace(setup=lambda current_app: called.append(current_app))

    PluginHooks().run_setup_hook('dict', module, app)

    assert called == [app]


def test_plugin_hooks_runs_otel_hook() -> None:
    app = FastAPI()
    called: list[FastAPI] = []

    module = SimpleNamespace(otel=lambda current_app: called.append(current_app))

    PluginHooks().run_otel_hook('dict', module, app)

    assert called == [app]


def test_plugin_hooks_skips_missing_hook_modules(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        'backend.plugin.hooks_runtime.plugin_registry.ordered_enabled',
        lambda: [PluginEntry(name='dict')],
    )

    def fake_import_module_cached(module_path: str):  # noqa: ANN001
        raise ModuleNotFoundError(name=module_path)

    monkeypatch.setattr('backend.plugin.hooks_runtime.import_module_cached', fake_import_module_cached)

    assert PluginHooks().hook_modules() == []
