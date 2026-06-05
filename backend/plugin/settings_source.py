from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

from backend.plugin import plugin_lifecycle


class PluginSettingsSource(PydanticBaseSettingsSource):
    """从所有插件的 plugin.toml 加载配置的自定义配置源"""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """获取单个字段的值"""
        # 不在这里实现，使用 __call__ 批量加载
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """加载所有插件配置"""
        return plugin_lifecycle.load_settings(self.settings_cls.model_fields)
