"""插件系统公开 Interface。

外部业务代码优先从这里导入 `plugin_lifecycle`，避免依赖插件系统内部 Implementation 文件。
"""

from backend.plugin.lifecycle import PluginLifecycle, plugin_lifecycle
from backend.plugin.features import PluginFeatureGateway, plugin_features

__all__ = [
    'PluginFeatureGateway',
    'PluginLifecycle',
    'plugin_features',
    'plugin_lifecycle',
]
