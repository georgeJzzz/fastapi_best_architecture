from typing import Any

from fastapi import APIRouter, FastAPI, UploadFile

from backend.common.dataclasses import PluginEntry
from backend.common.enums import PluginType
from backend.plugin.api_mounting import plugin_api_mounting
from backend.plugin.hooks_runtime import plugin_hooks
from backend.plugin.package_manager import plugin_package_manager
from backend.plugin.registry import plugin_registry
from backend.plugin.runtime_status import plugin_runtime_status


class PluginLifecycle:
    """插件生命周期 Module，集中插件发现、配置、排序、路由和 hooks 装配。"""

    def is_installed(self, plugin_name: str) -> bool:
        return plugin_registry.is_installed(plugin_name)

    def get_required(self) -> tuple[str, ...]:
        return plugin_registry.get_required()

    def check_required(self) -> None:
        plugin_registry.check_required()

    def discover(self) -> tuple[str, ...]:
        return plugin_registry.discover()

    def clear_cache(self) -> None:
        plugin_registry.clear_cache()

    def enabled_names(self, plugins: tuple[str, ...] | None = None) -> set[str]:
        return plugin_runtime_status.enabled_names(plugins or self.discover())

    @staticmethod
    def parse_enable(plugin_info: str | None, default_status: int) -> str:
        return plugin_runtime_status.parse_enable(plugin_info, default_status)

    async def ensure_enabled(self, plugin: str) -> None:
        await plugin_runtime_status.ensure_enabled(plugin)

    async def cached_plugin_infos(self) -> list[dict[str, Any]]:
        return await plugin_runtime_status.cached_infos()

    async def changed(self) -> str | None:
        return await plugin_runtime_status.changed()

    async def toggle_status(self, plugin: str) -> None:
        await plugin_runtime_status.toggle(plugin)

    async def mark_changed(self) -> None:
        await plugin_runtime_status.mark_changed()

    async def install_backend(
        self,
        *,
        type: PluginType,
        file: UploadFile | None = None,
        repo_url: str | None = None,
    ) -> str:
        return await plugin_package_manager.install_backend(type=type, file=file, repo_url=repo_url)

    async def uninstall_backend(self, plugin: str) -> None:
        await plugin_package_manager.uninstall_backend(plugin)

    async def build_package(self, plugin: str):
        return await plugin_package_manager.build_package(plugin)

    def install_requirements(self, plugin: str) -> None:
        plugin_package_manager.install_requirements(plugin)

    async def uninstall_requirements(self, plugin: str) -> None:
        await plugin_package_manager.uninstall_requirements(plugin)

    def load_config(self, plugin: str) -> dict[str, Any]:
        return plugin_registry.load_config(plugin)

    def load_settings(self, model_fields: dict[str, Any]) -> dict[str, Any]:
        return plugin_registry.load_settings(model_fields)

    def parse_config(self) -> tuple[list[PluginEntry], list[PluginEntry]]:
        return plugin_registry.parse_config()

    def order(self, plugins: list[PluginEntry]) -> list[PluginEntry]:
        return plugin_registry.order(plugins)

    def ordered_enabled(self) -> list[PluginEntry]:
        return plugin_registry.ordered_enabled()

    def models(self) -> list[object]:
        return plugin_registry.models()

    def build_router(self) -> APIRouter:
        extend_plugins, app_plugins = self.parse_config()
        ordered_plugins = self.order(extend_plugins + app_plugins)
        return plugin_api_mounting.build_router(ordered_plugins)

    def inject_extend_router(self, plugin: PluginEntry) -> None:
        plugin_api_mounting.inject_extend_router(plugin)

    def inject_app_router(self, plugin: PluginEntry, target_router: APIRouter) -> None:
        plugin_api_mounting.inject_app_router(plugin, target_router)

    def register_hooks(self, app: FastAPI) -> None:
        plugin_hooks.register_hooks(app)

    def init_otel_hooks(self, app: FastAPI) -> None:
        plugin_hooks.init_otel_hooks(app)

    def register_lifespan_hook(self, plugin: str, module: Any) -> None:
        plugin_hooks.register_lifespan_hook(plugin, module)

    def run_setup_hook(self, plugin: str, module: Any, app: FastAPI) -> None:
        plugin_hooks.run_setup_hook(plugin, module, app)

    def run_otel_hook(self, plugin: str, module: Any, app: FastAPI) -> None:
        plugin_hooks.run_otel_hook(plugin, module, app)

    def _hook_modules(self) -> list[tuple[str, Any]]:
        return plugin_hooks.hook_modules()

    @staticmethod
    def _invalid_router_msg(plugin: str, module_path: str, level: str) -> str:
        return plugin_api_mounting.invalid_router_msg(plugin, module_path, level)

    @staticmethod
    def _changed_key() -> str:
        return plugin_runtime_status.changed_key()

    @staticmethod
    def _log():  # noqa: ANN205
        from backend.common.log import log

        return log


plugin_lifecycle = PluginLifecycle()
