import json
from collections.abc import AsyncGenerator
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import settings


def room_channel(room_id: UUID | str) -> str:
    return f"room:{room_id}"


class RedisChatPublisher:
    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis or Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._owns_connection = redis is None

    async def publish(self, room_id: UUID | str, message: dict[str, str]) -> None:
        await self.redis.publish(room_channel(room_id), json.dumps(message))

    async def close(self) -> None:
        if self._owns_connection:
            await self.redis.aclose()


class RedisChatSubscriber:
    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis or Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._owns_connection = redis is None

    async def subscribe(
        self, room_id: UUID | str
    ) -> AsyncGenerator[dict[str, str], None]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(room_channel(room_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if not isinstance(data, str):
                    continue
                yield json.loads(data)
        finally:
            await pubsub.unsubscribe(room_channel(room_id))
            await pubsub.aclose()

    async def close(self) -> None:
        if self._owns_connection:
            await self.redis.aclose()
