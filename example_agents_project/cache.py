import os
from dotenv import load_dotenv
from redis.asyncio import Redis
import time
import asyncio

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

_redis_client: Redis = None


async def init_client():
    global _redis_client
    _redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    await _redis_client.initialize()


def get_client() -> Redis:
    return _redis_client


async def close_client():
    await _redis_client.close()
    await _redis_client.connection_pool.disconnect()


async def add_event_id(event_id: str):
    """Add event_id to cache with a 1-hour TTL."""
    client = get_client()
    await client.set(f"event:{event_id}", event_id, ex=3600)


async def exists_event_id(event_id: str) -> bool:
    """Check if event_id exists in cache."""
    client = get_client()
    event_id = await client.get(f"event:{event_id}")
    return True if event_id is not None else False


async def delete_event_id(event_id: str):
    """Delete event_id from cache."""
    client = get_client()
    await client.delete(f"event:{event_id}")


async def exists_user_token(user_id: str) -> bool:
    """Check if user_id exists in cache."""
    client = get_client()
    exists = await client.sismember("tokens", user_id)
    return True if exists == 1 else False


async def set_user_token(user_id: str, tokens: dict):
    """Set user tokens in Redis."""
    client = get_client()
    await client.sadd("tokens", user_id)


async def remove_user_token(user_id: str):
    """Delete user tokens from Redis."""
    client = get_client()
    await client.srem("tokens", user_id)


async def acquire_lock(user_id: str, timeout_secs: int = 10) -> bool:
    """Attempt to acquire the lock for a specific user_id within a timeout period."""
    client = get_client()
    end_time = time.time() + timeout_secs
    while time.time() < end_time:
        if await client.set(f"lock:{user_id}", "true", ex=3600, nx=True):
            return True
        await asyncio.sleep(0.1)
    return False


async def release_lock(user_id: str):
    """Release the lock on user_id."""
    client = get_client()
    await client.delete(f"lock:{user_id}")
