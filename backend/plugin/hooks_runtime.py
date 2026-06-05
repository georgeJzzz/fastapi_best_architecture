import inspect

from typing import Any

from fastapi import FastAPI

from backend.common.enums import LifespanStage
from backend.common.lifespan import lifespan_manager
from backend.plugin.errors import PluginInjectError
from backend.plugin.registry import plugin_registry
from backend.utils.async_helper import run_await
from backend.utils.dynamic_import import import_module_cached


class PluginHooks:
    """插件 hooks Module，集中 lifespan、setup 和 otel hooks 的发现与执行。"""

    def register_hooks(self, app: FastAPI) -> None:
        def run_setup_hook(plugin: str, module: Any) -> None:
            try:
                self.register_lifespan_hook(plugin, module)
            except Exception as e:
                self._log().exception(f'插件 {plugin} lifespan hooks 执行失败: {e}')
                raise PluginInjectError(f'插件 {plugin} lifespan hooks 执行失败：{e!s}') from e
            try:
                self.run_setup_hook(plugin, module, app)
            except Exception as e:
                self._log().exception(f'插件 {plugin} setup hooks 执行失败: {e}')
                raise PluginInjectError(f'插件 {plugin} setup hooks 执行失败：{e!s}') from e

        for plugin, module in self.hook_modules():
            run_setup_hook(plugin, module)

    def init_otel_hooks(self, app: FastAPI) -> None:
        def run_otel_hook(plugin: str, module: Any) -> None:
            try:
                self.run_otel_hook(plugin, module, app)
            except Exception as e:
                self._log().exception(f'插件 {plugin} otel hook 执行失败: {e}')
                raise PluginInjectError(f'插件 {plugin} otel hook 执行失败：{e!s}') from e

        for plugin, module in self.hook_modules():
            run_otel_hook(plugin, module)

    def register_lifespan_hook(self, plugin: str, module: Any) -> None:
        lifespan_hook = getattr(module, 'lifespan', None)
        if lifespan_hook is None:
            return

        if not callable(lifespan_hook):
            self._log().warning(f'插件 {plugin} 的 lifespan 不是可调用对象，已跳过')
            return

        lifespan_manager.register(lifespan_hook, stage=LifespanStage.plugin)  # type: ignore[call-overload]
        self._log().info(f'插件 {plugin} lifespan hook 注册成功')

    def run_setup_hook(self, plugin: str, module: Any, app: FastAPI) -> None:
        setup_hook = getattr(module, 'setup', None)
        if setup_hook is None:
            return

        if not callable(setup_hook):
            self._log().warning(f'插件 {plugin} 的 setup 不是可调用对象，已跳过')
            return

        setup_result = setup_hook(app)
        if inspect.isawaitable(setup_result):
            run_await(lambda: setup_result)()  # type: ignore
        self._log().info(f'插件 {plugin} setup hook 执行成功')

    def run_otel_hook(self, plugin: str, module: Any, app: FastAPI) -> None:
        otel_hook = getattr(module, 'otel', None)
        if otel_hook is None:
            return

        if not callable(otel_hook):
            self._log().warning(f'插件 {plugin} 的 otel 不是可调用对象，已跳过')
            return

        otel_result = otel_hook(app)
        if inspect.isawaitable(otel_result):
            run_await(lambda: otel_result)()  # type: ignore
        self._log().info(f'插件 {plugin} otel hook 执行成功')

    def hook_modules(self) -> list[tuple[str, Any]]:
        plugin_hook_modules: list[tuple[str, Any]] = []

        for plugin in plugin_registry.ordered_enabled():
            module_path = f'backend.plugin.{plugin.name}.hooks'
            try:
                module = import_module_cached(module_path)
            except ModuleNotFoundError as e:
                if e.name == module_path:
                    continue
                self._log().warning(f'插件 {plugin.name} hooks 加载失败: {e}')
                continue
            except Exception as e:
                self._log().warning(f'插件 {plugin.name} hooks 加载失败: {e}')
                continue

            plugin_hook_modules.append((plugin.name, module))

        return plugin_hook_modules

    @staticmethod
    def _log():  # noqa: ANN205
        from backend.common.log import log

        return log


plugin_hooks = PluginHooks()
