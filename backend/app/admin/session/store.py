import json

from typing import Protocol

from backend.core.conf import settings
from backend.database.redis import RedisCli, redis_client


class SessionStore(Protocol):
    """Storage adapter for User session state."""

    async def store_access_token(
        self,
        user_id: int,
        session_uuid: str,
        access_token: str,
        *,
        extra_info: dict,
        expires_in: int,
    ) -> None: ...

    async def store_refresh_token(
        self,
        user_id: int,
        session_uuid: str,
        refresh_token: str,
        *,
        expires_in: int,
    ) -> None: ...

    async def get_access_token(self, user_id: int, session_uuid: str) -> str | None: ...

    async def get_refresh_token(self, user_id: int, session_uuid: str) -> str | None: ...

    async def list_access_tokens(self) -> list[str]: ...

    async def get_extra_info(self, user_id: int, session_uuid: str) -> dict | None: ...

    async def online_session_uuids(self) -> set[str]: ...

    async def has_other_access_sessions(self, user_id: int, session_uuid: str) -> bool: ...

    async def delete_session(self, user_id: int, session_uuid: str) -> None: ...

    async def revoke_user(self, user_id: int, *, keep_session_uuid: str | None = None) -> None: ...

    async def invalidate_user_cache(self, user_id: int) -> None: ...

    async def get_user_cache(self, user_id: int) -> str | None: ...

    async def set_user_cache(self, user_id: int, value: str, *, expires_in: int) -> None: ...


class SessionKeys:
    """Centralized User session key construction."""

    @staticmethod
    def access(user_id: int, session_uuid: str) -> str:
        return f'{settings.TOKEN_REDIS_PREFIX}:{user_id}:{session_uuid}'

    @staticmethod
    def access_prefix(user_id: int) -> str:
        return f'{settings.TOKEN_REDIS_PREFIX}:{user_id}:'

    @staticmethod
    def all_access_prefix() -> str:
        return f'{settings.TOKEN_REDIS_PREFIX}:'

    @staticmethod
    def refresh(user_id: int, session_uuid: str) -> str:
        return f'{settings.TOKEN_REFRESH_REDIS_PREFIX}:{user_id}:{session_uuid}'

    @staticmethod
    def refresh_prefix(user_id: int) -> str:
        return f'{settings.TOKEN_REFRESH_REDIS_PREFIX}:{user_id}:'

    @staticmethod
    def extra(user_id: int, session_uuid: str) -> str:
        return f'{settings.TOKEN_EXTRA_INFO_REDIS_PREFIX}:{user_id}:{session_uuid}'

    @staticmethod
    def extra_prefix(user_id: int) -> str:
        return f'{settings.TOKEN_EXTRA_INFO_REDIS_PREFIX}:{user_id}:'

    @staticmethod
    def user_cache(user_id: int) -> str:
        return f'{settings.JWT_USER_REDIS_PREFIX}:{user_id}'


class RedisSessionStore:
    """Redis adapter for User session state."""

    def __init__(self, redis: RedisCli = redis_client) -> None:
        self.redis = redis

    async def store_access_token(
        self,
        user_id: int,
        session_uuid: str,
        access_token: str,
        *,
        extra_info: dict,
        expires_in: int,
    ) -> None:
        await self.redis.set(SessionKeys.access(user_id, session_uuid), access_token, ex=expires_in)
        if extra_info:
            await self.redis.set(
                SessionKeys.extra(user_id, session_uuid),
                json.dumps(extra_info, ensure_ascii=False),
                ex=expires_in,
            )

    async def store_refresh_token(
        self,
        user_id: int,
        session_uuid: str,
        refresh_token: str,
        *,
        expires_in: int,
    ) -> None:
        await self.redis.set(SessionKeys.refresh(user_id, session_uuid), refresh_token, ex=expires_in)

    async def get_access_token(self, user_id: int, session_uuid: str) -> str | None:
        return await self.redis.get(SessionKeys.access(user_id, session_uuid))

    async def get_refresh_token(self, user_id: int, session_uuid: str) -> str | None:
        return await self.redis.get(SessionKeys.refresh(user_id, session_uuid))

    async def list_access_tokens(self) -> list[str]:
        keys = await self.redis.get_prefix(SessionKeys.all_access_prefix())
        if not keys:
            return []
        return [token for token in await self.redis.mget(*keys) if token]

    async def get_extra_info(self, user_id: int, session_uuid: str) -> dict | None:
        extra_info = await self.redis.get(SessionKeys.extra(user_id, session_uuid))
        return json.loads(extra_info) if extra_info else None

    async def online_session_uuids(self) -> set[str]:
        return set(await self.redis.smembers(settings.TOKEN_ONLINE_REDIS_PREFIX))

    async def has_other_access_sessions(self, user_id: int, session_uuid: str) -> bool:
        current_key = SessionKeys.access(user_id, session_uuid)
        token_keys = await self.redis.get_prefix(SessionKeys.access_prefix(user_id))
        return any(key != current_key for key in token_keys)

    async def delete_session(self, user_id: int, session_uuid: str) -> None:
        await self.redis.delete(
            SessionKeys.access(user_id, session_uuid),
            SessionKeys.refresh(user_id, session_uuid),
            SessionKeys.extra(user_id, session_uuid),
        )

    async def revoke_user(self, user_id: int, *, keep_session_uuid: str | None = None) -> None:
        await self.redis.delete_prefix(
            SessionKeys.access_prefix(user_id),
            exclude=SessionKeys.access(user_id, keep_session_uuid) if keep_session_uuid else None,
        )
        await self.redis.delete_prefix(
            SessionKeys.refresh_prefix(user_id),
            exclude=SessionKeys.refresh(user_id, keep_session_uuid) if keep_session_uuid else None,
        )
        await self.redis.delete_prefix(
            SessionKeys.extra_prefix(user_id),
            exclude=SessionKeys.extra(user_id, keep_session_uuid) if keep_session_uuid else None,
        )
        await self.invalidate_user_cache(user_id)

    async def invalidate_user_cache(self, user_id: int) -> None:
        await self.redis.delete(SessionKeys.user_cache(user_id))

    async def get_user_cache(self, user_id: int) -> str | None:
        return await self.redis.get(SessionKeys.user_cache(user_id))

    async def set_user_cache(self, user_id: int, value: str, *, expires_in: int) -> None:
        await self.redis.set(SessionKeys.user_cache(user_id), value, ex=expires_in)


class InMemorySessionStore:
    """In-memory adapter for User session tests."""

    def __init__(self) -> None:
        self.access_tokens: dict[tuple[int, str], str] = {}
        self.refresh_tokens: dict[tuple[int, str], str] = {}
        self.extra_infos: dict[tuple[int, str], dict] = {}
        self.online_sessions: set[str] = set()
        self.user_cache: set[int] = set()
        self.user_cache_values: dict[int, str] = {}

    async def store_access_token(
        self,
        user_id: int,
        session_uuid: str,
        access_token: str,
        *,
        extra_info: dict,
        expires_in: int,
    ) -> None:
        self.access_tokens[(user_id, session_uuid)] = access_token
        if extra_info:
            self.extra_infos[(user_id, session_uuid)] = dict(extra_info)

    async def store_refresh_token(
        self,
        user_id: int,
        session_uuid: str,
        refresh_token: str,
        *,
        expires_in: int,
    ) -> None:
        self.refresh_tokens[(user_id, session_uuid)] = refresh_token

    async def get_access_token(self, user_id: int, session_uuid: str) -> str | None:
        return self.access_tokens.get((user_id, session_uuid))

    async def get_refresh_token(self, user_id: int, session_uuid: str) -> str | None:
        return self.refresh_tokens.get((user_id, session_uuid))

    async def list_access_tokens(self) -> list[str]:
        return list(self.access_tokens.values())

    async def get_extra_info(self, user_id: int, session_uuid: str) -> dict | None:
        return self.extra_infos.get((user_id, session_uuid))

    async def online_session_uuids(self) -> set[str]:
        return set(self.online_sessions)

    async def has_other_access_sessions(self, user_id: int, session_uuid: str) -> bool:
        return any(key[0] == user_id and key[1] != session_uuid for key in self.access_tokens)

    async def delete_session(self, user_id: int, session_uuid: str) -> None:
        key = (user_id, session_uuid)
        self.access_tokens.pop(key, None)
        self.refresh_tokens.pop(key, None)
        self.extra_infos.pop(key, None)

    async def revoke_user(self, user_id: int, *, keep_session_uuid: str | None = None) -> None:
        keep = (user_id, keep_session_uuid) if keep_session_uuid else None
        for store in [self.access_tokens, self.refresh_tokens, self.extra_infos]:
            for key in list(store):
                if key[0] == user_id and key != keep:
                    store.pop(key, None)
        await self.invalidate_user_cache(user_id)

    async def invalidate_user_cache(self, user_id: int) -> None:
        self.user_cache.discard(user_id)
        self.user_cache_values.pop(user_id, None)

    async def get_user_cache(self, user_id: int) -> str | None:
        return self.user_cache_values.get(user_id)

    async def set_user_cache(self, user_id: int, value: str, *, expires_in: int) -> None:
        self.user_cache.add(user_id)
        self.user_cache_values[user_id] = value
