import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from example_agents_project.cache import (
    init_client,
    close_client,
    add_event_id,
    exists_event_id,
    delete_event_id,
    exists_user_token,
    set_user_token,
    remove_user_token,
    acquire_lock,
    release_lock,
)


@pytest.fixture
def mock_redis():
    mock_redis_instance = AsyncMock()
    mock_redis_instance.initialize = AsyncMock()
    mock_redis_instance.close = AsyncMock()
    mock_redis_instance.connection_pool = AsyncMock()
    mock_redis_instance.connection_pool.disconnect = AsyncMock()
    mock_redis_instance.set = AsyncMock()
    mock_redis_instance.get = AsyncMock()
    mock_redis_instance.delete = AsyncMock()
    mock_redis_instance.sismember = AsyncMock()
    mock_redis_instance.sadd = AsyncMock()
    mock_redis_instance.srem = AsyncMock()

    with patch("example_agents_project.cache.Redis", return_value=mock_redis_instance):
        yield mock_redis_instance


@pytest.mark.asyncio
async def test_init_client(mock_redis):
    await init_client()
    mock_redis.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_close_client(mock_redis):
    await init_client()
    await close_client()
    mock_redis.close.assert_called_once()
    mock_redis.connection_pool.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_add_event_id(mock_redis):
    await init_client()
    await add_event_id("test_event")
    mock_redis.set.assert_called_once_with("event:test_event", "test_event", ex=3600)


@pytest.mark.asyncio
async def test_exists_event_id(mock_redis):
    await init_client()
    mock_redis.get.return_value = "test_event"
    exists = await exists_event_id("test_event")
    assert exists is True
    mock_redis.get.assert_called_once_with("event:test_event")


@pytest.mark.asyncio
async def test_exists_event_id_not_found(mock_redis):
    await init_client()
    mock_redis.get.return_value = None
    exists = await exists_event_id("test_event")
    assert exists is False
    mock_redis.get.assert_called_once_with("event:test_event")


@pytest.mark.asyncio
async def test_delete_event_id(mock_redis):
    await init_client()
    await delete_event_id("test_event")
    mock_redis.delete.assert_called_once_with("event:test_event")


@pytest.mark.asyncio
async def test_exists_user_token(mock_redis):
    await init_client()
    mock_redis.sismember.return_value = 1
    exists = await exists_user_token("test_user")
    assert exists is True
    mock_redis.sismember.assert_called_once_with("tokens", "test_user")


@pytest.mark.asyncio
async def test_set_user_token(mock_redis):
    await init_client()
    await set_user_token("test_user", {})
    mock_redis.sadd.assert_called_once_with("tokens", "test_user")


@pytest.mark.asyncio
async def test_remove_user_token(mock_redis):
    await init_client()
    await remove_user_token("test_user")
    mock_redis.srem.assert_called_once_with("tokens", "test_user")


@pytest.mark.asyncio
async def test_acquire_lock(mock_redis):
    await init_client()
    mock_redis.set.return_value = True
    acquired = await acquire_lock("test_user")
    assert acquired is True
    mock_redis.set.assert_called_with("lock:test_user", "true", ex=3600, nx=True)


@pytest.mark.asyncio
async def test_release_lock(mock_redis):
    await init_client()
    await release_lock("test_user")
    mock_redis.delete.assert_called_once_with("lock:test_user")
