from fast_captcha import img_captcha
from starlette.concurrency import run_in_threadpool

from backend.app.admin.schema.captcha import GetCaptchaDetail
from backend.common.exception import errors
from backend.common.i18n import t
from backend.common.response.response_code import CustomErrorCode
from backend.core.conf import settings
from backend.database.db import uuid4_str
from backend.database.redis import redis_client
from backend.utils.dynamic_config import load_login_config


class LoginCaptchaStore:
    """登录验证码存储 adapter"""

    @staticmethod
    def _key(uuid: str) -> str:
        return f'{settings.LOGIN_CAPTCHA_REDIS_PREFIX}:{uuid}'

    async def save(self, uuid: str, code: str, *, expires_in: int) -> None:
        await redis_client.set(self._key(uuid), code, ex=expires_in)

    async def get(self, uuid: str) -> str | None:
        return await redis_client.get(self._key(uuid))

    async def discard(self, uuid: str) -> None:
        await redis_client.delete(self._key(uuid))


class CaptchaGenerator:
    """验证码图片生成 adapter"""

    @staticmethod
    async def generate() -> tuple[str, str]:
        img, code = await run_in_threadpool(img_captcha, img_byte='base64')
        return img, code


class LoginCaptchaService:
    """登录验证码服务"""

    def __init__(
        self,
        *,
        store: LoginCaptchaStore | None = None,
        generator: CaptchaGenerator | None = None,
    ) -> None:
        self.store = store or LoginCaptchaStore()
        self.generator = generator or CaptchaGenerator()

    async def create(self, db) -> GetCaptchaDetail:  # noqa: ANN001
        """创建登录验证码"""
        await load_login_config(db)
        img, code = await self.generator.generate()
        captcha_uuid = uuid4_str()
        await self.store.save(
            captcha_uuid,
            code,
            expires_in=settings.LOGIN_CAPTCHA_EXPIRE_SECONDS,
        )
        return GetCaptchaDetail(
            is_enabled=settings.LOGIN_CAPTCHA_ENABLED,
            expire_seconds=settings.LOGIN_CAPTCHA_EXPIRE_SECONDS,
            uuid=captcha_uuid,
            image=img,
        )

    async def verify(self, *, uuid: str | None, captcha: str | None) -> None:
        """验证并消费登录验证码"""
        if not uuid or not captcha:
            raise errors.RequestError(msg=t('error.captcha.invalid'))

        captcha_code = await self.store.get(uuid)
        if not captcha_code:
            raise errors.RequestError(msg=t('error.captcha.expired'))

        if captcha_code.lower() != captcha.lower():
            raise errors.CustomError(error=CustomErrorCode.CAPTCHA_ERROR)

        await self.store.discard(uuid)

    async def verify_if_enabled(self, db, *, uuid: str | None, captcha: str | None) -> None:  # noqa: ANN001
        """启用登录验证码时验证并消费验证码"""
        await load_login_config(db)
        if settings.LOGIN_CAPTCHA_ENABLED:
            await self.verify(uuid=uuid, captcha=captcha)

    async def discard(self, uuid: str) -> None:
        """丢弃登录验证码"""
        await self.store.discard(uuid)


login_captcha_service: LoginCaptchaService = LoginCaptchaService()
