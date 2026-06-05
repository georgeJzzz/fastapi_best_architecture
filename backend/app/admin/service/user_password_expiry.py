from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.exception import errors
from backend.core.conf import settings
from backend.utils.dynamic_config import load_user_security_config
from backend.utils.timezone import timezone


class UserPasswordExpiry:
    """用户密码过期策略"""

    async def check(self, *, db: AsyncSession, password_changed_time: datetime | None) -> int | None:
        """检查密码是否过期，并返回提醒剩余天数"""
        await load_user_security_config(db)

        if settings.USER_PASSWORD_EXPIRY_DAYS == 0:
            return None

        if not password_changed_time:
            raise errors.AuthorizationError(msg='密码已过期，请修改密码后重新登录')

        expiry_time = password_changed_time + timedelta(days=settings.USER_PASSWORD_EXPIRY_DAYS)
        days_remaining = (expiry_time - timezone.now()).days

        if days_remaining < 0:
            raise errors.AuthorizationError(msg='密码已过期，请修改密码后重新登录')

        if days_remaining <= settings.USER_PASSWORD_REMINDER_DAYS:
            return days_remaining

        return None


user_password_expiry: UserPasswordExpiry = UserPasswordExpiry()
