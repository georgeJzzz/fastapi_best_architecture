import asyncio

import pytest

from backend.app.admin.session import (
    FakeCookieAdapter,
    InMemorySessionStore,
    InMemoryUserSnapshotAdapter,
    UserSessionContext,
    UserSessionManager,
    UserSessionUser,
)
from backend.common.exception import errors


def _user(*, multi_login: bool = False) -> UserSessionUser:
    return UserSessionUser(
        id=1,
        username='admin',
        nickname='Admin',
        is_multi_login=multi_login,
    )


def test_create_stores_tokens_and_sets_refresh_cookie() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        manager = UserSessionManager(store)
        cookie = FakeCookieAdapter()

        tokens = await manager.create(
            _user(),
            context=UserSessionContext(ip='127.0.0.1', os='Windows', browser='Chrome', device='PC'),
            cookie=cookie,
        )

        key = (1, tokens.session_uuid)
        assert store.access_tokens[key] == tokens.access_token
        assert store.refresh_tokens[key] == tokens.refresh_token
        assert store.extra_infos[key]['username'] == 'admin'
        assert store.extra_infos[key]['ip'] == '127.0.0.1'
        assert cookie.refresh_token == tokens.refresh_token
        assert cookie.refresh_token_expires == tokens.refresh_token_expire_time

    asyncio.run(run())


def test_create_revokes_previous_sessions_when_multi_login_is_disabled() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        manager = UserSessionManager(store)

        first = await manager.create(_user(), context=UserSessionContext(), cookie=FakeCookieAdapter())
        second = await manager.create(_user(), context=UserSessionContext(), cookie=FakeCookieAdapter())

        assert (1, first.session_uuid) not in store.access_tokens
        assert (1, first.session_uuid) not in store.refresh_tokens
        assert (1, second.session_uuid) in store.access_tokens
        assert (1, second.session_uuid) in store.refresh_tokens

    asyncio.run(run())


def test_end_ignores_bad_tokens_and_deletes_valid_session() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        manager = UserSessionManager(store)
        create_cookie = FakeCookieAdapter()
        end_cookie = FakeCookieAdapter()

        tokens = await manager.create(_user(), context=UserSessionContext(), cookie=create_cookie)
        key = (1, tokens.session_uuid)

        await manager.end('not-a-token', None, cookie=end_cookie)
        assert key in store.access_tokens
        assert end_cookie.deleted_refresh_token is True

        await manager.end(tokens.access_token, tokens.refresh_token, cookie=end_cookie)
        assert key not in store.access_tokens
        assert key not in store.refresh_tokens
        assert key not in store.extra_infos
        assert end_cookie.deleted_refresh_token is True

    asyncio.run(run())


def test_revoke_user_can_keep_one_session_and_clears_user_cache() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        manager = UserSessionManager(store)

        first = await manager.create(_user(multi_login=True), context=UserSessionContext(), cookie=FakeCookieAdapter())
        second = await manager.create(_user(multi_login=True), context=UserSessionContext(), cookie=FakeCookieAdapter())
        store.user_cache.add(1)

        await manager.revoke_user(1, keep_session_uuid=second.session_uuid)

        assert (1, first.session_uuid) not in store.access_tokens
        assert (1, first.session_uuid) not in store.refresh_tokens
        assert (1, second.session_uuid) in store.access_tokens
        assert (1, second.session_uuid) in store.refresh_tokens
        assert 1 not in store.user_cache

    asyncio.run(run())


def test_refresh_rotates_tokens_and_sets_new_refresh_cookie() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        user = _user()
        manager = UserSessionManager(store, InMemoryUserSnapshotAdapter({user.id: user}))
        create_cookie = FakeCookieAdapter()
        refresh_cookie = FakeCookieAdapter()

        old_tokens = await manager.create(user, context=UserSessionContext(), cookie=create_cookie)
        new_tokens = await manager.refresh(
            None,  # type: ignore[arg-type]
            old_tokens.refresh_token,
            context=UserSessionContext(ip='127.0.0.1'),
            cookie=refresh_cookie,
        )

        assert (1, old_tokens.session_uuid) not in store.access_tokens
        assert (1, old_tokens.session_uuid) not in store.refresh_tokens
        assert (1, new_tokens.session_uuid) in store.access_tokens
        assert (1, new_tokens.session_uuid) in store.refresh_tokens
        assert new_tokens.access_token != old_tokens.access_token
        assert new_tokens.refresh_token != old_tokens.refresh_token
        assert refresh_cookie.refresh_token == new_tokens.refresh_token
        assert store.extra_infos[(1, new_tokens.session_uuid)]['ip'] == '127.0.0.1'

    asyncio.run(run())


def test_authenticate_access_token_accepts_current_token() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        manager = UserSessionManager(store)

        tokens = await manager.create(_user(), context=UserSessionContext(), cookie=FakeCookieAdapter())
        payload = await manager.authenticate_access_token(tokens.access_token)

        assert payload.user_id == 1
        assert payload.session_uuid == tokens.session_uuid

    asyncio.run(run())


def test_authenticate_access_token_rejects_invalid_or_revoked_token() -> None:
    async def run() -> None:
        store = InMemorySessionStore()
        manager = UserSessionManager(store)

        with pytest.raises(errors.TokenError):
            await manager.authenticate_access_token('not-a-token')

        tokens = await manager.create(_user(), context=UserSessionContext(), cookie=FakeCookieAdapter())
        await manager.revoke_session(1, tokens.session_uuid)

        with pytest.raises(errors.TokenError):
            await manager.authenticate_access_token(tokens.access_token)

    asyncio.run(run())


def test_user_cache_round_trip_and_invalidation() -> None:
    async def run() -> None:
        store = InMemorySessionStore()

        await store.set_user_cache(1, '{"id":1}', expires_in=60)
        assert await store.get_user_cache(1) == '{"id":1}'
        assert 1 in store.user_cache

        await store.invalidate_user_cache(1)

        assert await store.get_user_cache(1) is None
        assert 1 not in store.user_cache

    asyncio.run(run())
