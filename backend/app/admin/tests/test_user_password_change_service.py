from types import SimpleNamespace

import pytest

from backend.app.admin.service import user_password_change_service as service_module
from backend.common.exception import errors


@pytest.mark.anyio
async def test_user_password_change_service_resets_password_by_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    saved_history: list[tuple[int, str]] = []
    changed_users: list[int] = []
    revoked_users: list[int] = []
    reset_calls: list[tuple[int, str]] = []
    validated: list[tuple[int, str]] = []

    async def fake_create_password_history(db, obj) -> None:  # noqa: ANN001
        saved_history.append((obj.user_id, obj.password))

    async def fake_get_user(db, user_id: int):  # noqa: ANN001
        return SimpleNamespace(id=user_id, password='old-password-hash')

    async def fake_validate_new(*, db, user_id: int, new_password: str) -> None:  # noqa: ANN001
        validated.append((user_id, new_password))

    async def fake_reset_password(db, user_id: int, password: str) -> int:  # noqa: ANN001
        reset_calls.append((user_id, password))
        return 1

    async def fake_update_password_changed_time(db, user_id: int) -> None:  # noqa: ANN001
        changed_users.append(user_id)

    async def fake_revoke_user(user_id: int) -> None:
        revoked_users.append(user_id)

    monkeypatch.setattr(service_module.user_password_history_dao, 'create', fake_create_password_history)
    monkeypatch.setattr(service_module.user_dao, 'get', fake_get_user)
    monkeypatch.setattr(service_module.user_password_policy, 'validate_new', fake_validate_new)
    monkeypatch.setattr(service_module.user_dao, 'reset_password', fake_reset_password)
    monkeypatch.setattr(service_module.user_dao, 'update_password_changed_time', fake_update_password_changed_time)
    monkeypatch.setattr(service_module.user_session_manager, 'revoke_user', fake_revoke_user)

    count = await service_module.user_password_change_service.reset_by_admin(
        db=None,
        user_id=7,
        new_password='new-password',
    )

    assert count == 1
    assert validated == [(7, 'new-password')]
    assert reset_calls == [(7, 'new-password')]
    assert saved_history == [(7, 'old-password-hash')]
    assert changed_users == [7]
    assert revoked_users == [7]


@pytest.mark.anyio
async def test_user_password_change_service_updates_own_password(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    async def fake_get_user(db, user_id: int):  # noqa: ANN001
        return SimpleNamespace(id=user_id, password='old-password-hash')

    async def fake_validate_new(*, db, user_id: int, new_password: str) -> None:  # noqa: ANN001
        events.append(f'validate:{user_id}:{new_password}')

    async def fake_reset_password(db, user_id: int, password: str) -> int:  # noqa: ANN001
        events.append(f'reset:{user_id}:{password}')
        return 1

    async def fake_complete(*, db, user_id: int, previous_password: str | None) -> None:  # noqa: ANN001
        events.append(f'complete:{user_id}:{previous_password}')

    monkeypatch.setattr(service_module.user_dao, 'get', fake_get_user)
    monkeypatch.setattr(service_module.user_password_policy, 'verify', lambda plain, hashed: plain == 'old-password')
    monkeypatch.setattr(service_module.user_password_policy, 'validate_new', fake_validate_new)
    monkeypatch.setattr(service_module.user_dao, 'reset_password', fake_reset_password)
    monkeypatch.setattr(service_module.user_password_change_service, '_complete', fake_complete)

    count = await service_module.user_password_change_service.update_own(
        db=None,
        user_id=7,
        old_password='old-password',
        new_password='new-password',
        confirm_password='new-password',
    )

    assert count == 1
    assert events == [
        'validate:7:new-password',
        'reset:7:new-password',
        'complete:7:old-password-hash',
    ]


@pytest.mark.anyio
async def test_user_password_change_service_rejects_wrong_old_password(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_user(db, user_id: int):  # noqa: ANN001
        return SimpleNamespace(id=user_id, password='old-password-hash')

    monkeypatch.setattr(service_module.user_dao, 'get', fake_get_user)
    monkeypatch.setattr(service_module.user_password_policy, 'verify', lambda plain, hashed: False)

    with pytest.raises(errors.RequestError):
        await service_module.user_password_change_service.update_own(
            db=None,
            user_id=7,
            old_password='wrong-password',
            new_password='new-password',
            confirm_password='new-password',
        )


@pytest.mark.anyio
async def test_user_password_change_service_skips_empty_password_history(monkeypatch: pytest.MonkeyPatch) -> None:
    saved_history: list[tuple[int, str]] = []
    changed_users: list[int] = []
    revoked_users: list[int] = []

    async def fake_create_password_history(db, obj) -> None:  # noqa: ANN001
        saved_history.append((obj.user_id, obj.password))

    async def fake_update_password_changed_time(db, user_id: int) -> None:  # noqa: ANN001
        changed_users.append(user_id)

    async def fake_revoke_user(user_id: int) -> None:
        revoked_users.append(user_id)

    monkeypatch.setattr(service_module.user_password_history_dao, 'create', fake_create_password_history)
    monkeypatch.setattr(service_module.user_dao, 'update_password_changed_time', fake_update_password_changed_time)
    monkeypatch.setattr(service_module.user_session_manager, 'revoke_user', fake_revoke_user)

    await service_module.user_password_change_service._complete(db=None, user_id=7, previous_password=None)

    assert saved_history == []
    assert changed_users == [7]
    assert revoked_users == [7]
