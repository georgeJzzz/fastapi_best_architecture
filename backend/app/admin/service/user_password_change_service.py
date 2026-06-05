from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.crud.crud_user import user_dao
from backend.app.admin.crud.crud_user_password_history import user_password_history_dao
from backend.app.admin.schema.user_password_history import CreateUserPasswordHistoryParam
from backend.app.admin.session import user_session_manager
from backend.app.admin.service.user_password_policy import user_password_policy
from backend.common.exception import errors


class UserPasswordChangeService:
    """用户密码变更服务"""

    async def reset_by_admin(self, *, db: AsyncSession, user_id: int, new_password: str) -> int:
        """管理员重置用户密码。"""
        user = errors.require_found(await user_dao.get(db, user_id), msg='用户不存在')

        await user_password_policy.validate_new(db=db, user_id=user.id, new_password=new_password)
        count = await user_dao.reset_password(db, user.id, new_password)
        await self._complete(db=db, user_id=user.id, previous_password=user.password)
        return count

    async def update_own(
        self,
        *,
        db: AsyncSession,
        user_id: int,
        old_password: str,
        new_password: str,
        confirm_password: str,
    ) -> int:
        """用户修改自己的密码。"""
        user = errors.require_found(await user_dao.get(db, user_id), msg='用户不存在')

        if user.password and not user_password_policy.verify(old_password, user.password):
            raise errors.RequestError(msg='原密码错误')

        if new_password != confirm_password:
            raise errors.RequestError(msg='两次密码输入不一致')

        await user_password_policy.validate_new(db=db, user_id=user.id, new_password=new_password)
        count = await user_dao.reset_password(db, user.id, new_password)
        await self._complete(db=db, user_id=user.id, previous_password=user.password)
        return count

    @staticmethod
    async def _complete(*, db: AsyncSession, user_id: int, previous_password: str | None) -> None:
        if previous_password:
            history_obj = CreateUserPasswordHistoryParam(user_id=user_id, password=previous_password)
            await user_password_history_dao.create(db, history_obj)
        await user_dao.update_password_changed_time(db, user_id)
        await user_session_manager.revoke_user(user_id)


user_password_change_service: UserPasswordChangeService = UserPasswordChangeService()
