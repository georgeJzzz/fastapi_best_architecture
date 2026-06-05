import json

from typing import Any

from backend.common.exception import errors
from backend.core.conf import settings
from backend.database.db import uuid4_str
from backend.database.redis import redis_client
from backend.plugin.oauth2.enums import UserSocialAuthType


class OAuth2StateService:
    """OAuth2 状态服务"""

    @staticmethod
    def key(state: str) -> str:
        """获取 OAuth2 state 缓存键"""
        return f'{settings.OAUTH2_STATE_REDIS_PREFIX}:{state}'

    @staticmethod
    def generate_state() -> str:
        """生成 OAuth2 state"""
        return uuid4_str()

    async def create_login(self) -> str:
        """创建 OAuth2 登录 state"""
        return await self.create({'type': UserSocialAuthType.login.value})

    async def create_binding(self, *, user_id: int) -> str:
        """创建 OAuth2 绑定 state"""
        return await self.create({'type': UserSocialAuthType.binding.value, 'user_id': user_id})

    async def create(self, payload: dict[str, Any]) -> str:
        """创建 OAuth2 state"""
        state = self.generate_state()
        await redis_client.set(
            self.key(state),
            json.dumps(payload),
            ex=settings.OAUTH2_STATE_EXPIRE_SECONDS,
        )
        return state

    async def consume(self, state: str | None) -> dict[str, Any]:
        """消费 OAuth2 state"""
        if not state:
            raise errors.ForbiddenError(msg='OAuth2 状态信息缺失')

        state_data = await redis_client.get(self.key(state))
        if not state_data:
            raise errors.ForbiddenError(msg='OAuth2 状态信息无效或缺失')

        await redis_client.delete(self.key(state))
        return json.loads(state_data)


oauth2_state_service: OAuth2StateService = OAuth2StateService()
