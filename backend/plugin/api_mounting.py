import os
import warnings

from fastapi import APIRouter, Depends

from backend.common.dataclasses import PluginEntry
from backend.core.path_conf import PLUGIN_DIR
from backend.plugin.errors import PluginConfigError, PluginInjectError
from backend.plugin.status import PluginStatusChecker
from backend.utils.dynamic_import import import_module_cached


class PluginApiMounting:
    """Plugin API mounting Module，集中插件路由发现、目标路由查找和状态依赖注入。"""

    def build_router(self, ordered_plugins: list[PluginEntry]) -> APIRouter:
        for plugin in ordered_plugins:
            if plugin.api is not None:
                self.inject_extend_router(plugin)

        from backend.app.router import router as main_router

        for plugin in ordered_plugins:
            if plugin.routers is not None:
                self.inject_app_router(plugin, main_router)

        return main_router

    def inject_extend_router(self, plugin: PluginEntry) -> None:
        plugin_api_path = PLUGIN_DIR / plugin.name / 'api'
        if not os.path.exists(plugin_api_path):
            raise PluginConfigError(f'插件 {plugin.name} 缺少 api 目录，请检查插件文件是否完整')

        for root, _, api_files in os.walk(plugin_api_path):
            for file in api_files:
                if not (file.endswith('.py') and file != '__init__.py'):
                    continue

                file_config = plugin.api[file[:-3]]
                prefix = file_config['prefix']
                tags = file_config['tags']

                file_path = os.path.join(root, file)
                path_to_module_str = os.path.relpath(file_path, PLUGIN_DIR).replace(os.sep, '.')[:-3]
                module_path = f'backend.plugin.{path_to_module_str}'

                try:
                    module = import_module_cached(module_path)
                    plugin_router = getattr(module, 'router', None)
                    if not plugin_router:
                        warnings.warn(
                            self.invalid_router_msg(plugin.name, module_path, '扩展级'),
                            FutureWarning,
                        )
                        continue

                    relative_path = os.path.relpath(root, plugin_api_path)
                    target_module_path = f'backend.app.{plugin.extend}.api.{relative_path.replace(os.sep, ".")}'
                    target_module = import_module_cached(target_module_path)
                    target_router = getattr(target_module, 'router', None)

                    if not target_router or not isinstance(target_router, APIRouter):
                        raise PluginInjectError(self.invalid_router_msg(plugin.name, module_path, '扩展级'))

                    target_router.include_router(
                        router=plugin_router,
                        prefix=prefix,
                        tags=[tags] if tags else [],
                        dependencies=[Depends(PluginStatusChecker(plugin.name))],
                    )
                except Exception as e:
                    raise PluginInjectError(f'扩展级插件 {plugin.name} 路由注入失败：{e!s}') from e

    def inject_app_router(self, plugin: PluginEntry, target_router: APIRouter) -> None:
        module_path = f'backend.plugin.{plugin.name}.api.router'
        try:
            module = import_module_cached(module_path)
            routers = plugin.routers
            if not routers or not isinstance(routers, list):
                raise PluginConfigError(f'应用级插件 {plugin.name} 配置文件存在错误，请检查')

            for router in routers:
                plugin_router = getattr(module, router, None)
                if not plugin_router or not isinstance(plugin_router, APIRouter):
                    raise PluginInjectError(self.invalid_router_msg(plugin.name, module_path, '应用级'))

                target_router.include_router(plugin_router, dependencies=[Depends(PluginStatusChecker(plugin.name))])
        except Exception as e:
            raise PluginInjectError(f'应用级插件 {plugin.name} 路由注入失败：{e!s}') from e

    @staticmethod
    def invalid_router_msg(plugin: str, module_path: str, level: str) -> str:
        return f'{level}插件 {plugin} 模块 {module_path} 中没有有效的 router，请检查插件文件是否完整'


plugin_api_mounting = PluginApiMounting()
