import io

import anyio

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from backend.common.enums import PluginType
from backend.core.path_conf import PLUGIN_DIR
from backend.plugin.registry import plugin_registry
from backend.plugin.runtime_status import plugin_runtime_status


class PluginPackageManager:
    """插件包管理 Module，集中后端插件安装、卸载、打包和依赖处理 workflow。"""

    async def install_backend(
        self,
        *,
        type: PluginType,
        file: UploadFile | None = None,
        repo_url: str | None = None,
    ) -> str:
        from backend.common.exception import errors
        from backend.core.conf import settings
        from backend.plugin.installer import install_git_plugin, install_zip_plugin

        if settings.ENVIRONMENT != 'dev':
            raise errors.RequestError(msg='禁止在非开发环境下安装插件')
        if type == PluginType.zip:
            if not file:
                raise errors.RequestError(msg='ZIP 压缩包不能为空')
            plugin_name = await install_zip_plugin(file)
        else:
            if not repo_url:
                raise errors.RequestError(msg='Git 仓库地址不能为空')
            plugin_name = await install_git_plugin(repo_url)

        await plugin_runtime_status.mark_changed()
        plugin_registry.clear_cache()
        return plugin_name

    async def uninstall_backend(self, plugin: str) -> None:
        from backend.common.exception import errors
        from backend.core.conf import settings
        from backend.database.redis import redis_client
        from backend.plugin.installer import remove_plugin, zip_plugin
        from backend.plugin.requirements import uninstall_requirements_async
        from backend.utils.timezone import timezone

        if settings.ENVIRONMENT != 'dev':
            raise errors.RequestError(msg='禁止在非开发环境下卸载插件')
        if plugin in plugin_registry.get_required():
            raise errors.RequestError(msg=f'插件 {plugin} 为必需插件，禁止卸载')

        plugin_dir = anyio.Path(PLUGIN_DIR / plugin)
        if not await plugin_dir.exists():
            raise errors.NotFoundError(msg='插件不存在')

        await uninstall_requirements_async(plugin)
        backup_file = PLUGIN_DIR / f'{plugin}.{timezone.now().strftime("%Y%m%d%H%M%S")}.backup.zip'
        await run_in_threadpool(zip_plugin, plugin_dir, backup_file)
        await run_in_threadpool(remove_plugin, plugin_dir)
        await redis_client.delete(plugin_runtime_status.cache_key(plugin))
        await plugin_runtime_status.mark_changed()
        plugin_registry.clear_cache()

    async def build_package(self, plugin: str) -> io.BytesIO:
        from backend.common.exception import errors
        from backend.plugin.installer import zip_plugin

        plugin_dir = anyio.Path(PLUGIN_DIR / plugin)
        if not await plugin_dir.exists():
            raise errors.NotFoundError(msg='插件不存在')

        bio = io.BytesIO()
        await run_in_threadpool(zip_plugin, plugin_dir, bio)
        bio.seek(0)
        return bio

    def install_requirements(self, plugin: str) -> None:
        from backend.plugin.requirements import install_requirements

        install_requirements(plugin)

    async def uninstall_requirements(self, plugin: str) -> None:
        from backend.plugin.requirements import uninstall_requirements_async

        await uninstall_requirements_async(plugin)


plugin_package_manager = PluginPackageManager()
