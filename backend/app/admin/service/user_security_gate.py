import math

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exception import errors
from backend.core.conf import settings
from backend.database.redis import redis_client
from backend.utils.dynamic_config import load_user_security_config
from backend.utils.timezone import timezone


class UserSecurityGate:
    """用户安全门禁"""

    @staticmethod
    def lock_key(user_id: int) -> str:
        """获取用户锁定缓存键"""
        return f'{settings.USER_LOCK_REDIS_PREFIX}:{user_id}'

    @staticmethod
    def failure_key(user_id: int) -> str:
        """获取登录失败次数缓存键"""
        return f'{settings.LOGIN_FAILURE_PREFIX}:{user_id}'

    async def check_login_allowed(self, *, user_id: int, user_status: int) -> None:
        """检查用户是否允许登录"""
        if not user_status:
            raise errors.AuthorizationError(msg='用户已被锁定, 请联系统管理员')

        locked_until_str = await redis_client.get(self.lock_key(user_id))
        if not locked_until_str:
            return

        locked_until = timezone.from_str(locked_until_str)
        now = timezone.now()
        if locked_until > now:
            remaining_minutes = math.ceil((locked_until - now).total_seconds() / 60)
            raise errors.AuthorizationError(msg=f'账号已被锁定，请在 {remaining_minutes} 分钟后重试')

        await self.clear(user_id)

    async def record_login_failure(self, *, db: AsyncSession, user_id: int) -> None:
        """记录登录失败并在达到阈值时锁定用户"""
        await load_user_security_config(db)

        if settings.USER_LOCK_THRESHOLD == 0:
            return

        failure_count = await redis_client.get(self.failure_key(user_id))
        failure_count = int(failure_count) if failure_count else 0
        failure_count += 1
        await redis_client.set(
            self.failure_key(user_id),
            str(failure_count),
            ex=settings.USER_LOCK_SECONDS,
        )

        if failure_count >= settings.USER_LOCK_THRESHOLD:
            locked_until = timezone.now() + timedelta(seconds=settings.USER_LOCK_SECONDS)
            await redis_client.set(
                self.lock_key(user_id),
                timezone.to_str(locked_until),
                ex=settings.USER_LOCK_SECONDS,
            )
            raise errors.AuthorizationError(msg='登录失败次数过多，账号已被锁定')

    async def clear(self, user_id: int) -> None:
        """清除用户登录锁定和失败计数"""
        await redis_client.delete(self.lock_key(user_id))
        await redis_client.delete(self.failure_key(user_id))


user_security_gate: UserSecurityGate = UserSecurityGate()
