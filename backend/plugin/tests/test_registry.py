import pytest

from pydantic_core import PydanticUndefined

from backend.common.dataclasses import PluginEntry
from backend.plugin.errors import PluginConfigError
from backend.plugin.registry import PluginRegistry


def test_plugin_registry_orders_dependencies_before_dependents() -> None:
    registry = PluginRegistry()

    ordered = registry.order(
        [
            PluginEntry(name='notice', depends_on=['dict']),
            PluginEntry(name='dict'),
            PluginEntry(name='config', depends_on=['dict']),
        ]
    )

    assert [plugin.name for plugin in ordered] == ['dict', 'notice', 'config']


def test_plugin_registry_rejects_missing_dependency() -> None:
    registry = PluginRegistry()

    with pytest.raises(PluginConfigError, match='依赖插件 dict'):
        registry.order([PluginEntry(name='notice', depends_on=['dict'])])


def test_plugin_registry_rejects_dependency_cycle() -> None:
    registry = PluginRegistry()

    with pytest.raises(PluginConfigError, match='循环依赖'):
        registry.order(
            [
                PluginEntry(name='notice', depends_on=['dict']),
                PluginEntry(name='dict', depends_on=['notice']),
            ]
        )


def test_plugin_registry_loads_plugin_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    class RequiredField:
        default = PydanticUndefined

    class DefaultedField:
        default = 'already configured'

    registry = PluginRegistry()

    monkeypatch.setattr(registry, 'discover', lambda: ('email', 'oauth2'))
    monkeypatch.setattr(
        registry,
        'load_config',
        lambda plugin: {
            'email': {
                'settings': {
                    'EMAIL_HOST': 'smtp.example.com',
                    'EMAIL_PORT': 465,
                }
            },
            'oauth2': {
                'settings': {
                    'OAUTH2_STATE_EXPIRE_SECONDS': 300,
                }
            },
        }[plugin],
    )

    plugin_settings = registry.load_settings(
        {
            'EMAIL_HOST': RequiredField(),
            'EMAIL_PORT': DefaultedField(),
        }
    )

    assert plugin_settings == {
        'EMAIL_HOST': 'smtp.example.com',
        'OAUTH2_STATE_EXPIRE_SECONDS': 300,
    }
