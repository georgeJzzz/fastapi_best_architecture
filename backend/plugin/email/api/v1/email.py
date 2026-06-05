from typing import Annotated

from fastapi import APIRouter, Body

from backend.common.response.response_schema import ResponseModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.database.db import CurrentSession
from backend.plugin.email.service.email_captcha_service import email_captcha_service

router = APIRouter()


@router.post('/captcha', summary='发送电子邮件验证码', dependencies=[DependsJwtAuth])
async def send_email_captcha(
    db: CurrentSession,
    recipients: Annotated[str | list[str], Body(embed=True, description='邮件接收者')],
) -> ResponseModel:
    await email_captcha_service.send(db=db, recipients=recipients)
    return response_base.success()
