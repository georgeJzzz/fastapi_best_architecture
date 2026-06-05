from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.crud.crud_user_password_history import user_password_history_dao
from backend.common.exception import errors
from backend.core.conf import settings
from backend.utils.dynamic_config import load_user_security_config
from backend.utils.pattern_validate import is_has_letter, is_has_number, is_has_special_char


class UserPasswordPolicy:
    """用户密码策略"""

    def __init__(self) -> None:
        self.password_hash = PasswordHash((BcryptHasher(),))

    def hash(self, password: str, salt: bytes | None) -> str:
        """生成密码哈希"""
        return self.password_hash.hash(password, salt=salt)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.password_hash.verify(plain_password, hashed_password)

    async def validate_new(self, *, db: AsyncSession, user_id: int, new_password: str) -> None:
        """验证新密码是否符合用户密码策略"""
        await load_user_security_config(db)
        self._validate_shape(new_password)
        await self._validate_history(db=db, user_id=user_id, new_password=new_password)

    @staticmethod
    def _validate_shape(new_password: str) -> None:
        if len(new_password) < settings.USER_PASSWORD_MIN_LENGTH:
            raise errors.RequestError(msg=f'密码长度不能少于 {settings.USER_PASSWORD_MIN_LENGTH} 个字符')

        if len(new_password) > settings.USER_PASSWORD_MAX_LENGTH:
            raise errors.RequestError(msg=f'密码长度不能超过 {settings.USER_PASSWORD_MAX_LENGTH} 个字符')

        if not is_has_number(new_password):
            raise errors.RequestError(msg='密码必须包含数字')

        if not is_has_letter(new_password):
            raise errors.RequestError(msg='密码必须包含字母')

        if settings.USER_PASSWORD_REQUIRE_SPECIAL_CHAR and not is_has_special_char(new_password):
            raise errors.RequestError(msg='密码必须包含特殊字符（如：!@#$%）')

    async def _validate_history(self, *, db: AsyncSession, user_id: int, new_password: str) -> None:
        password_history = await user_password_history_dao.get_by_user_id(db, user_id)

        for hist in password_history[: settings.USER_PASSWORD_HISTORY_CHECK_COUNT]:
            if self.verify(new_password, hist.password):
                raise errors.RequestError(
                    msg=f'新密码不能与最近 {settings.USER_PASSWORD_HISTORY_CHECK_COUNT} 次使用的密码相同'
                )


user_password_policy: UserPasswordPolicy = UserPasswordPolicy()
