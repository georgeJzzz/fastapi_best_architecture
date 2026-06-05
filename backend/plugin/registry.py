import json
import os

from functools import lru_cache
from typing import Any

import rtoml

from pydantic_core import PydanticUndefinedType

from backend.common.dataclasses import PluginEntry
from backend.common.enums import PluginLevelType, StatusType
from backend.core.path_conf import PLUGIN_DIR
from backend.plugin.errors import PluginConfigError, PluginInjectError
from backend.plugin.runtime_status import plugin_runtime_status
from backend.plugin.validator import validate_plugin_config
from backend.utils.async_helper import run_await
from backend.utils.dynamic_import import get_model_objects


class PluginRegistry:
    """插件注册表 Module，集中插件发现、配置解析、依赖排序和模型发现。"""

    def is_installed(self, plugin_name: str) -> bool:
        return (PLUGIN_DIR / plugin_name / '__init__.py').exists()

    def get_required(self) -> tuple[str, ...]:
        from backend.core.conf import settings

        required_plugins = list(settings.PLUGIN_REQUIRED)
        if not settings.RBAC_ROLE_MENU_MODE and 'casbin_rbac' not in required_plugins:
            required_plugins.append('casbin_rbac')
        return tuple(required_plugins)

    def check_required(self) -> None:
        missing_plugins = [name for name in self.get_required() if not self.is_installed(name)]
        if missing_plugins:
            raise PluginInjectError(f'当前系统缺少以下插件: {", ".join(missing_plugins)}，请先安装对应插件')

    @lru_cache(maxsize=128)
    def discover(self) -> tuple[str, ...]:
        plugin_packages = []

        for item in os.listdir(PLUGIN_DIR):
            item_path = PLUGIN_DIR / item
            if not os.path.isdir(item_path) and item == '__pycache__':
                continue
            if os.path.isdir(item_path) and '__init__.py' in os.listdir(item_path):
                plugin_packages.append(item)

        return tuple(plugin_packages)

    def clear_cache(self) -> None:
        self.discover.cache_clear()

    def load_config(self, plugin: str) -> dict[str, Any]:
        toml_path = PLUGIN_DIR / plugin / 'plugin.toml'
        if not os.path.exists(toml_path):
            raise PluginInjectError(f'插件 {plugin} 缺少 plugin.toml 配置文件，请检查插件是否合法')

        with open(toml_path, encoding='utf-8') as f:
            return rtoml.load(f)

    def load_settings(self, model_fields: dict[str, Any]) -> dict[str, Any]:
        merged_settings: dict[str, Any] = {}

        for plugin in self.discover():
            try:
                plugin_config = self.load_config(plugin)
            except PluginInjectError:
                continue
            plugin_settings = plugin_config.get('settings', {})
            if isinstance(plugin_settings, dict):
                merged_settings.update(plugin_settings)

        filtered_settings: dict[str, Any] = {}
        for key, value in merged_settings.items():
            field_info = model_fields.get(key)
            if field_info is not None:
                if isinstance(field_info.default, PydanticUndefinedType):
                    filtered_settings[key] = value
            else:
                filtered_settings[key] = value

        return filtered_settings

    def parse_config(self) -> tuple[list[PluginEntry], list[PluginEntry]]:
        from backend.core.conf import settings
        from backend.database.redis import RedisCli

        plugins = self.discover()
        extend_plugins: list[PluginEntry] = []
        app_plugins: list[PluginEntry] = []

        current_redis_client = RedisCli()
        run_await(current_redis_client.init)()

        try:
            exclude_keys = [plugin_runtime_status.cache_key(key) for key in plugins]
            run_await(current_redis_client.delete_prefix)(
                settings.PLUGIN_REDIS_PREFIX,
                exclude=exclude_keys,
            )

            for plugin in plugins:
                plugin_config = self.load_config(plugin)
                plugin_type = validate_plugin_config(plugin, plugin_config)

                plugin_config['plugin']['name'] = plugin
                plugin_cache_key = plugin_runtime_status.cache_key(plugin)
                plugin_cache_info = run_await(current_redis_client.get)(plugin_cache_key)
                plugin_config['plugin']['enable'] = plugin_runtime_status.parse_enable(
                    plugin_cache_info, StatusType.enable.value
                )

                plugin_entry = PluginEntry(
                    name=plugin,
                    depends_on=plugin_config['plugin'].get('depends_on'),
                    extend=plugin_config['app']['extend'] if plugin_type == PluginLevelType.extend else None,
                    routers=plugin_config['app']['router'] if plugin_type == PluginLevelType.app else None,
                    api=plugin_config['api'] if plugin_type == PluginLevelType.extend else None,
                )

                if plugin_type == PluginLevelType.extend:
                    extend_plugins.append(plugin_entry)
                else:
                    app_plugins.append(plugin_entry)

                run_await(current_redis_client.set)(plugin_cache_key, json.dumps(plugin_config, ensure_ascii=False))

            run_await(current_redis_client.delete)(plugin_runtime_status.changed_key())
        finally:
            run_await(current_redis_client.aclose)()

        return extend_plugins, app_plugins

    def order(self, plugins: list[PluginEntry]) -> list[PluginEntry]:
        plugin_map = {plugin.name: plugin for plugin in plugins}
        ordered_plugins: list[PluginEntry] = []
        visited: set[str] = set()
        visiting: list[str] = []

        def visit(plugin: PluginEntry) -> None:
            if plugin.name in visited:
                return
            if plugin.name in visiting:
                cycle_start = visiting.index(plugin.name)
                cycle_path = [*visiting[cycle_start:], plugin.name]
                raise PluginConfigError(f'插件存在循环依赖: {" -> ".join(cycle_path)}')

            if plugin.depends_on is not None:
                visiting.append(plugin.name)
                for dep_name in plugin.depends_on:
                    dep_plugin = plugin_map.get(dep_name)
                    if dep_plugin is None:
                        raise PluginConfigError(f'插件 {plugin.name} 依赖插件 {dep_name}，但插件 {dep_name} 不存在')
                    visit(dep_plugin)
                visiting.pop()

            visited.add(plugin.name)
            ordered_plugins.append(plugin)

        for plugin in plugins:
            visit(plugin)

        return ordered_plugins

    def ordered_enabled(self) -> list[PluginEntry]:
        enabled_plugins = plugin_runtime_status.enabled_names(self.discover())
        extend_plugins, app_plugins = self.parse_config()
        plugins: list[PluginEntry] = [plugin for plugin in extend_plugins + app_plugins if plugin.name in enabled_plugins]

        try:
            return self.order(plugins)
        except PluginConfigError as e:
            self._log().error(f'插件依赖解析失败: {e}')
            raise

    def models(self) -> list[object]:
        objs = []

        for plugin in self.discover():
            module_path = f'backend.plugin.{plugin}.model'
            model_objs = get_model_objects(module_path)
            if model_objs:
                objs.extend(model_objs)

        return objs

    @staticmethod
    def _log():  # noqa: ANN205
        from backend.common.log import log

        return log


plugin_registry = PluginRegistry()
