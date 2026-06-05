import json

import pytest

from backend.core.conf import settings
from backend.plugin.runtime_status import PluginRuntimeStatus


class FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}
        self.set_calls: list[tuple[str, str]] = []

    async def get_prefix(self, prefix: str) -> list[str]:
        return [key for key in self.values if key.startswith(prefix)]

    async def mget(self, *keys: str) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str) -> None:
        self.values[key] = value
        self.set_calls.append((key, value))


def test_plugin_runtime_status_parses_plugin_enable_status() -> None:
    runtime_status = PluginRuntimeStatus()

    assert runtime_status.parse_enable(None, 1) == '1'
    assert runtime_status.parse_enable('not json', 0) == '0'
    assert runtime_status.parse_enable('{"plugin": {"enable": "1"}}', 0) == '1'


@pytest.mark.anyio
async def test_plugin_runtime_status_reads_cached_infos_without_changed_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.database import redis as redis_module

    monkeypatch.setattr(settings, 'PLUGIN_REDIS_PREFIX', 'fba:plugin')
    fake_redis = FakeRedis(
        {
            'fba:plugin:dict': json.dumps({'plugin': {'name': 'dict'}}),
            'fba:plugin:changed': 'true',
        }
    )
    monkeypatch.setattr(redis_module, 'redis_client', fake_redis)

    assert await PluginRuntimeStatus().cached_infos() == [{'plugin': {'name': 'dict'}}]


@pytest.mark.anyio
async def test_plugin_runtime_status_toggles_status_and_marks_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.database import redis as redis_module

    monkeypatch.setattr(settings, 'PLUGIN_REDIS_PREFIX', 'fba:plugin')
    fake_redis = FakeRedis(
        {
            'fba:plugin:dict': json.dumps({'plugin': {'name': 'dict', 'enable': '1'}}),
        }
    )
    monkeypatch.setattr(redis_module, 'redis_client', fake_redis)

    await PluginRuntimeStatus().toggle('dict')

    assert json.loads(fake_redis.values['fba:plugin:dict'])['plugin']['enable'] == '0'
    assert fake_redis.values['fba:plugin:changed'] == 'true'
