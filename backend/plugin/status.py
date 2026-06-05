from fastapi import Request

from backend.plugin.runtime_status import plugin_runtime_status


def get_plugin_enable(plugin_info: str | None, default_status: int) -> str:
    """
    解析插件启用状态

    :param plugin_info: 插件缓存信息
    :param default_status: 默认状态值
    :return:
    """
    return plugin_runtime_status.parse_enable(plugin_info, default_status)


class PluginStatusChecker:
    """插件状态检查器"""

    def __init__(self, plugin: str) -> None:
        """
        初始化插件状态检查器

        :param plugin: 插件名称
        :return:
        """
        self.plugin = plugin

    async def __call__(self, request: Request) -> None:
        """
        验证插件状态

        :param request: FastAPI 请求对象
        :return:
        """
        await plugin_runtime_status.ensure_enabled(self.plugin)
