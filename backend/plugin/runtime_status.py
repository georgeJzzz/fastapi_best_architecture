import json

from typing import Any

from backend.common.enums import StatusType
from backend.plugin.errors import PluginInjectError
from backend.utils.async_helper import run_await


class PluginRuntimeStatus:
    """插件运行状态 Module，集中 Redis 状态、changed 标记和启用状态解析。"""

    @staticmethod
    def parse_enable(plugin_info: str | None, default_status: int) -> str:
        if not plugin_info:
            return str(default_status)

        try:
            return json.loads(plugin_info)['plugin']['enable']
        except Exception:
            return str(default_status)

    @staticmethod
    def cache_key(plugin: str) -> str:
        from backend.core.conf import settings

        return f'{settings.PLUGIN_REDIS_PREFIX}:{plugin}'

    @staticmethod
    def changed_key() -> str:
        from backend.core.conf import settings

        return f'{settings.PLUGIN_REDIS_PREFIX}:changed'

    def enabled_names(self, plugin_names: tuple[str, ...]) -> set[str]:
        from backend.database.redis import RedisCli

        enabled_plugins = set(plugin_names)
        current_redis_client = RedisCli()
        run_await(current_redis_client.init)()

        try:
            for plugin in plugin_names:
                plugin_info = run_await(current_redis_client.get)(self.cache_key(plugin))
                if self.parse_enable(plugin_info, StatusType.enable.value) != str(StatusType.enable.value):
                    enabled_plugins.discard(plugin)
        finally:
            run_await(current_redis_client.aclose)()

        return enabled_plugins

    async def ensure_enabled(self, plugin: str) -> None:
        from backend.common.exception import errors
        from backend.database.redis import redis_client

        plugin_info = await redis_client.get(self.cache_key(plugin))
        if not plugin_info:
            self._log().error('插件状态未初始化或丢失，需重启服务自动修复')
            raise PluginInjectError('插件状态未初始化或丢失，请联系系统管理员')

        if self.parse_enable(plugin_info, StatusType.disable.value) != str(StatusType.enable.value):
            raise errors.ServerError(msg=f'插件 {plugin} 未启用，请联系系统管理员')

    async def cached_infos(self) -> list[dict[str, Any]]:
        from backend.core.conf import settings
        from backend.database.redis import redis_client

        changed_key = self.changed_key()
        keys = [key for key in await redis_client.get_prefix(f'{settings.PLUGIN_REDIS_PREFIX}:') if key != changed_key]
        if not keys:
            return []

        result = []
        plugin_infos = await redis_client.mget(*keys)
        for info in plugin_infos:
            if info is None:
                continue

            plugin_info = json.loads(info)
            if isinstance(plugin_info, dict):
                result.append(plugin_info)

        return result

    async def changed(self) -> str | None:
        from backend.database.redis import redis_client

        return await redis_client.get(self.changed_key())

    async def toggle(self, plugin: str) -> None:
        from backend.common.exception import errors
        from backend.database.redis import redis_client

        plugin_key = self.cache_key(plugin)
        plugin_info = errors.require_found(await redis_client.get(plugin_key), msg='插件不存在')
        parsed_plugin_info = json.loads(plugin_info)

        new_status = (
            str(StatusType.enable.value)
            if parsed_plugin_info['plugin']['enable'] == str(StatusType.disable.value)
            else str(StatusType.disable.value)
        )
        parsed_plugin_info['plugin']['enable'] = new_status
        await redis_client.set(plugin_key, json.dumps(parsed_plugin_info, ensure_ascii=False))
        await self.mark_changed()

    async def mark_changed(self) -> None:
        from backend.database.redis import redis_client

        await redis_client.set(self.changed_key(), 'true')

    @staticmethod
    def _log():  # noqa: ANN205
        from backend.common.log import log

        return log


plugin_runtime_status = PluginRuntimeStatus()
