from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Path, Query

from backend.app.admin.schema.token import GetTokenDetail
from backend.app.admin.session import user_session_manager
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsSuperUser

router = APIRouter()


@router.get('', summary='获取在线用户', dependencies=[DependsSuperUser])
async def get_sessions(
    username: Annotated[str | None, Query(description='用户名')] = None,
) -> ResponseSchemaModel[list[GetTokenDetail]]:
    data = [GetTokenDetail(**asdict(session)) for session in await user_session_manager.list_online(username=username)]
    return response_base.success(data=data)


@router.delete(
    '/{pk}',
    summary='强制下线',
    dependencies=[DependsSuperUser],
)
async def delete_session(
    pk: Annotated[int, Path(description='用户 ID')],
    session_uuid: Annotated[str, Query(description='会话 UUID')],
) -> ResponseModel:
    await user_session_manager.revoke_session(pk, session_uuid)
    return response_base.success()
