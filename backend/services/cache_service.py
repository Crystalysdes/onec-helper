import json
from typing import Any, Optional
import redis.asyncio as aioredis
from loguru import logger

from backend.config import settings


class CacheService:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def get_redis(self) -> aioredis.Redis:
        if not self._redis:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def get(self, key: str) -> Optional[Any]:
        try:
            r = await self.get_redis()
            value = await r.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Cache get error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, expire: int = 300) -> bool:
        try:
            r = await self.get_redis()
            await r.set(key, json.dumps(value, default=str), ex=expire)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        try:
            r = await self.get_redis()
            await r.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        try:
            r = await self.get_redis()
            keys = await r.keys(pattern)
            if keys:
                return await r.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        try:
            r = await self.get_redis()
            return bool(await r.exists(key))
        except Exception as e:
            logger.warning(f"Cache exists error for {key}: {e}")
            return False

    async def hset(self, name: str, mapping: dict, expire: int = 3600) -> bool:
        try:
            r = await self.get_redis()
            serialized = {k: json.dumps(v, default=str) for k, v in mapping.items()}
            await r.hset(name, mapping=serialized)
            await r.expire(name, expire)
            return True
        except Exception as e:
            logger.warning(f"Cache hset error for {name}: {e}")
            return False

    async def hget(self, name: str, key: str) -> Optional[Any]:
        try:
            r = await self.get_redis()
            value = await r.hget(name, key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Cache hget error for {name}.{key}: {e}")
            return None

    async def close(self):
        if self._redis:
            await self._redis.close()


cache_service = CacheService()
