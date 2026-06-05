from fastapi import APIRouter, Depends
from pyrate_limiter import Duration, Rate

from backend.app.admin.schema.captcha import GetCaptchaDetail
from backend.app.admin.service.login_captcha_service import login_captcha_service
from backend.common.response.response_schema import ResponseSchemaModel, response_base
from backend.database.db import CurrentSession
from backend.utils.limiter import RateLimiter

router = APIRouter()


@router.get(
    '/captcha',
    summary='获取登录验证码',
    dependencies=[Depends(RateLimiter(Rate(5, Duration.SECOND * 30)))],
)
async def get_captcha(db: CurrentSession) -> ResponseSchemaModel[GetCaptchaDetail]:
    data = await login_captcha_service.create(db)
    return response_base.success(data=data)
