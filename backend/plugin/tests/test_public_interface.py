from backend.plugin import PluginLifecycle, plugin_lifecycle


def test_plugin_package_exports_lifecycle_interface() -> None:
    """插件系统包级 Interface 暴露兼容的 Plugin lifecycle。"""
    assert isinstance(plugin_lifecycle, PluginLifecycle)
