from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.endpoints import ai, auth, chat, follows, posts, users
from app.core.config import settings
from app.core.rate_limit import limiter, rate_limit_exceeded_handler

app = FastAPI(title=settings.APP_NAME, version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(follows.router, prefix="/api/v1/users", tags=["follows"])
app.include_router(posts.router, prefix="/api/v1/posts", tags=["posts"])
app.include_router(posts.feed_router, prefix="/api/v1/feed", tags=["feed"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(chat.websocket_router, tags=["chat"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])


@app.get("/health", response_model=dict[str, str])
async def health() -> dict[str, str]:
    return {"status": "ok"}
