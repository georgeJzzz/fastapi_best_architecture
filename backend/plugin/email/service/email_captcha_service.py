import random

from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.context import ctx
from backend.common.exception import errors
from backend.common.response.response_code import CustomErrorCode
from backend.core.conf import settings
from backend.database.redis import redis_client


class EmailCaptchaService:
    """电子邮件验证码服务"""

    @staticmethod
    def key(ip: str) -> str:
        """获取电子邮件验证码缓存键"""
        return f'{settings.EMAIL_CAPTCHA_REDIS_PREFIX}:{ip}'

    @staticmethod
    def generate_code() -> str:
        """生成电子邮件验证码"""
        return ''.join([str(random.randint(1, 9)) for _ in range(6)])

    async def send(self, *, db: AsyncSession, recipients: str | list[str], ip: str | None = None) -> None:
        """发送电子邮件验证码"""
        current_ip = ip or ctx.ip
        code = self.generate_code()
        await redis_client.set(
            self.key(current_ip),
            code,
            ex=settings.EMAIL_CAPTCHA_EXPIRE_SECONDS,
        )
        content = {'code': code, 'expired': int(settings.EMAIL_CAPTCHA_EXPIRE_SECONDS / 60)}
        await self.send_email(db, recipients, 'FBA 验证码', content, 'captcha.html')

    async def verify(self, *, captcha: str, ip: str | None = None) -> None:
        """验证并消费电子邮件验证码"""
        current_ip = ip or ctx.ip
        captcha_code = await redis_client.get(self.key(current_ip))
        if not captcha_code:
            raise errors.RequestError(msg='验证码已失效，请重新获取')
        if captcha != captcha_code:
            raise errors.CustomError(error=CustomErrorCode.CAPTCHA_ERROR)
        await redis_client.delete(self.key(current_ip))

    @staticmethod
    async def send_email(db, recipients, subject: str, content: str | dict, template: str | None = None) -> None:  # noqa: ANN001
        """发送电子邮件"""
        from backend.plugin.email.utils.send import send_email

        await send_email(db, recipients, subject, content, template)


email_captcha_service: EmailCaptchaService = EmailCaptchaService()
