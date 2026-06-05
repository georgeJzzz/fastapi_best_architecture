from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exception import errors
from backend.plugin.lifecycle import plugin_lifecycle
from backend.utils.dynamic_import import import_module_cached
from backend.utils.serializers import select_list_serialize


class PluginFeatureGateway:
    """可选插件能力网关，集中业务外部对插件能力的调用。"""

    async def config_values(self, *, db: AsyncSession, config_type_attr: str) -> dict[str, str] | None:
        """读取参数配置插件中的动态配置。"""
        if not plugin_lifecycle.is_installed('config'):
            return None

        try:
            config_enums = import_module_cached('backend.plugin.config.enums')
            config_service_module = import_module_cached('backend.plugin.config.service.config_service')
        except ImportError as e:
            raise ImportError('参数配置插件用法导入失败，请联系系统管理员') from e

        config_type = getattr(config_enums.ConfigType, config_type_attr)
        dynamic_config = await config_service_module.config_service.get_all(db=db, type=config_type)
        if not dynamic_config:
            return {}

        config_list = select_list_serialize(dynamic_config) if hasattr(dynamic_config[0], '__table__') else dynamic_config
        return {dc['key']: dc['value'] for dc in config_list}

    async def verify_email_captcha(self, *, captcha: str) -> None:
        """验证电子邮件验证码。"""
        if not plugin_lifecycle.is_installed('email'):
            raise errors.ServerError(msg='电子邮件插件未安装，请联系系统管理员')

        try:
            email_service_module = import_module_cached('backend.plugin.email.service.email_captcha_service')
        except ImportError as e:
            raise errors.ServerError(msg='电子邮件插件用法导入失败，请联系系统管理员') from e

        await email_service_module.email_captcha_service.verify(captcha=captcha)

    async def delete_oauth2_bindings_by_user_id(self, db: AsyncSession, user_id: int) -> int | None:
        """删除 OAuth2 插件中的用户社交账号绑定。"""
        if not plugin_lifecycle.is_installed('oauth2'):
            return None

        try:
            user_social_module = import_module_cached('backend.plugin.oauth2.crud.crud_user_social')
        except ImportError as e:
            raise errors.ServerError(msg='OAuth2 插件用法导入失败，请联系系统管理员') from e

        return await user_social_module.user_social_dao.delete_by_user_id(db, user_id)

    async def casbin_verify(self, request: Request) -> None:
        """执行 Casbin RBAC 插件鉴权。"""
        if not plugin_lifecycle.is_installed('casbin_rbac'):
            raise errors.ServerError(msg='Casbin RBAC 插件未安装，请联系系统管理员')

        try:
            casbin_module = import_module_cached('backend.plugin.casbin_rbac.rbac')
        except ImportError as e:
            raise errors.ServerError(msg='Casbin RBAC 插件用法导入失败，请联系系统管理员') from e

        await casbin_module.casbin_verify(request)


plugin_features = PluginFeatureGateway()
