# DevLink — Codex Master Prompt

You are building **DevLink**, a developer networking platform where engineers find
project collaborators and referrals. This is a portfolio project demonstrating
production-grade SWE skills: REST API design, JWT auth, WebSocket, Redis caching,
AI-powered matching, CI/CD, and test coverage.

## Tech stack (non-negotiable)
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2
- **Database**: PostgreSQL 16
- **Cache / pub-sub**: Redis 7
- **Frontend**: React 18 + TypeScript, React Query v5, React Router v6, Tailwind CSS
- **AI**: OpenAI `gpt-4o-mini` via `openai` SDK (skill extraction + vector matching)
- **Realtime**: WebSocket (FastAPI native)
- **Infra**: Docker Compose, Nginx, GitHub Actions

## Repository layout (already scaffolded)
```
devlink/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # one file per resource
│   │   ├── core/               # config, security, dependencies
│   │   ├── db/                 # session, base
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # business logic (no DB calls in endpoints)
│   │   └── tests/              # pytest
│   ├── alembic/                # migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── lib/                # axios client, queryClient
│   ├── Dockerfile
│   └── package.json
├── infra/
│   └── nginx.conf
├── .github/workflows/
│   └── ci.yml
├── docker-compose.yml
└── .env.example
```

---

## Phase 1 — Core REST API + JWT Auth
**Goal**: Working backend with auth and user profiles. Frontend not required yet.

### Task 1-A: Project bootstrap
Create these files exactly:

**`backend/requirements.txt`**
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
pydantic[email]==2.7.1
pydantic-settings==2.2.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
redis==5.0.4
openai==1.30.1
httpx==0.27.0
pytest==8.2.1
pytest-asyncio==0.23.7
pytest-cov==5.0.0
httpx==0.27.0
```

**`backend/app/core/config.py`**
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "DevLink"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/db

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OpenAI
    OPENAI_API_KEY: str = ""

settings = Settings()
```

**`backend/app/core/security.py`**
Implement:
- `hash_password(plain: str) -> str` using passlib bcrypt
- `verify_password(plain: str, hashed: str) -> bool`
- `create_access_token(data: dict, expires_delta: timedelta | None) -> str` — signs a JWT with `exp` claim
- `create_refresh_token(subject: str) -> str` — longer-lived JWT stored in httpOnly cookie
- `decode_token(token: str) -> dict` — raises `HTTPException 401` on invalid/expired

**`backend/app/db/session.py`**
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_size=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

### Task 1-B: User model + auth endpoints

**`backend/app/models/user.py`** — SQLAlchemy model:
```python
# Fields: id (UUID PK), email (unique), username (unique), hashed_password,
# bio, avatar_url, github_url, skills (ARRAY[Text]),
# created_at, updated_at, is_active (default True)
```

**`backend/app/schemas/user.py`** — Pydantic schemas:
- `UserCreate`: email, username, password (min 8 chars)
- `UserRead`: id, email, username, bio, skills, github_url, created_at
- `UserUpdate`: bio, avatar_url, github_url, skills (all optional)
- `Token`: access_token, token_type
- `TokenRefresh`: refresh_token

**`backend/app/api/v1/endpoints/auth.py`** — endpoints:
- `POST /auth/register` → create user, return `UserRead`
- `POST /auth/login` → verify credentials, return `Token`, set refresh token as httpOnly cookie
- `POST /auth/refresh` → read cookie, issue new access token
- `POST /auth/logout` → clear cookie

**`backend/app/api/v1/endpoints/users.py`**:
- `GET /users/me` → current user (requires Bearer token)
- `PUT /users/me` → update profile
- `GET /users/{username}` → public profile
- `GET /users/` → list users, support `?skill=python&page=1&size=20` (cursor-based preferred)

**Dependency** `backend/app/core/deps.py`:
```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    # decode JWT, fetch user from DB, raise 401 if not found/inactive
```

### Task 1-C: Alembic + first migration
```bash
alembic init alembic
# configure alembic/env.py to use async engine and import all models
alembic revision --autogenerate -m "create users table"
alembic upgrade head
```

### Task 1-D: Tests (write these BEFORE endpoints are final)
**`backend/app/tests/api/test_auth.py`**:
```python
# Use pytest-asyncio + httpx AsyncClient
# Test: register → 201, duplicate email → 409, login → 200 + token,
#       login wrong password → 401, /me without token → 401,
#       /me with token → 200 + correct user data,
#       refresh token → new access token, logout → cookie cleared
```

**`backend/app/tests/api/test_users.py`**:
```python
# Test: GET /users/me, PUT /users/me (partial update), GET /users/{username},
#       GET /users/?skill=python pagination
```

---

## Phase 2 — Follow system + Feed + Redis cache
**Goal**: Social graph (follow/unfollow), activity feed cached in Redis.

### Task 2-A: Follow model
```python
# models/follow.py
# Table: follows — follower_id (FK users), following_id (FK users)
# Composite PK, unique constraint, prevent self-follow in service layer
```

### Task 2-B: Follow endpoints
**`backend/app/api/v1/endpoints/follows.py`**:
- `POST /users/{username}/follow` — follow a user
- `DELETE /users/{username}/follow` — unfollow
- `GET /users/{username}/followers?page=1&size=20`
- `GET /users/{username}/following?page=1&size=20`

### Task 2-C: Activity feed with Redis
**`backend/app/services/feed_service.py`**:
```python
# When user A follows user B, push B's recent 10 posts into A's feed list in Redis
# Feed key: "feed:{user_id}"  — Redis List, max 200 entries, LPUSH + LTRIM
# GET /feed/ reads from Redis first; falls back to DB on cache miss
# Cache TTL: 10 minutes
# Invalidate on: new post, unfollow
```

### Task 2-D: Post model
```python
# models/post.py
# Fields: id (UUID), author_id (FK), title, body, tags (ARRAY[Text]),
#         created_at, updated_at
# Endpoint: POST /posts/, GET /posts/{id}, DELETE /posts/{id}
```

---

## Phase 3 — WebSocket Chat + AI Skill Matching

### Task 3-A: WebSocket chat
**`backend/app/api/v1/endpoints/chat.py`**:
```python
# GET /chat/rooms/ — list rooms user is in
# POST /chat/rooms/ — create or get DM room between two users
# WS  /ws/chat/{room_id}?token=<jwt>

# ConnectionManager class:
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}  # room_id → connections

    async def connect(self, ws: WebSocket, room_id: str): ...
    async def disconnect(self, ws: WebSocket, room_id: str): ...
    async def broadcast(self, message: dict, room_id: str): ...
    # Persist message to DB before broadcasting
    # Use Redis pub/sub so multiple backend instances share state
```

Message schema:
```json
{ "type": "message", "content": "hello", "sender_id": "uuid", "timestamp": "ISO8601" }
```

### Task 3-B: AI skill matching
**`backend/app/services/ai_service.py`**:
```python
# 1. extract_skills(resume_text: str) -> list[str]
#    — prompt: "Extract a JSON array of technical skills from this resume. 
#               Return ONLY the JSON array, no explanation."
#    — parse response, deduplicate, lowercase

# 2. get_skill_embedding(skills: list[str]) -> list[float]
#    — join skills as comma-separated string
#    — call openai.embeddings.create(model="text-embedding-3-small", input=...)
#    — return embedding vector

# 3. match_users(current_user_id: str, db, top_k=10) -> list[UserRead]
#    — fetch all users with non-empty skills from DB
#    — compute cosine similarity between current user embedding and each other user
#    — return top_k sorted by similarity score
#    — cache result in Redis for 1 hour: "match:{user_id}"
```

**Endpoint**:
- `POST /ai/extract-skills` — body: `{ "resume_text": "..." }`, returns `{ "skills": [...] }`
- `GET /ai/matches` — returns top 10 matched users

---

## Phase 4 — Docker, CI/CD, Tests

### Task 4-A: Docker Compose
**`docker-compose.yml`**:
```yaml
# Services: postgres, redis, backend (uvicorn), frontend (vite dev OR nginx),
#           nginx (reverse proxy)
# backend depends_on: postgres (healthcheck), redis
# Mount: ./backend:/app for hot reload in dev
# .env file injected via env_file
# Healthchecks on postgres and redis
```

**`backend/Dockerfile`**:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Task 4-B: GitHub Actions CI
**`.github/workflows/ci.yml`**:
```yaml
# Trigger: push to main, PR to main
# Jobs:
#   lint:   ruff check + ruff format --check
#   test:   spin up postgres + redis services, run pytest --cov=app --cov-report=xml
#   build:  docker build backend (no push, just validate)
# Fail PR if coverage < 70%
```

### Task 4-C: pytest fixtures
**`backend/app/tests/conftest.py`**:
```python
# Fixtures:
# - event_loop: session-scoped
# - db: async test DB session with rollback after each test
# - client: AsyncClient(app=app, base_url="http://test")
# - test_user: created user in DB
# - auth_headers: {"Authorization": "Bearer <token>"} for test_user
# - second_user + second_auth_headers: for follow/chat tests
```

### Task 4-D: Coverage targets
Write tests until `pytest --cov` reports ≥70%. Priority order:
1. `test_auth.py` — all auth flows
2. `test_users.py` — profile CRUD + search
3. `test_follows.py` — follow/unfollow/list
4. `test_posts.py` — CRUD + feed
5. `test_ai_service.py` — mock OpenAI calls with `unittest.mock.patch`

---

## Phase 5 — React Frontend (do this last)

### Task 5-A: Setup
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install @tanstack/react-query axios react-router-dom tailwindcss
npx tailwindcss init -p
```

### Task 5-B: API client
**`frontend/src/lib/apiClient.ts`**:
```typescript
// axios instance with baseURL from VITE_API_URL env var
// Request interceptor: attach Bearer token from localStorage
// Response interceptor: on 401, call /auth/refresh, retry original request once
// On second 401, redirect to /login
```

### Task 5-C: Pages to build
1. `/register` + `/login` — forms with React Hook Form + Zod validation
2. `/feed` — paginated post list, infinite scroll with React Query `useInfiniteQuery`
3. `/profile/:username` — avatar, skills badges, follow button, post list
4. `/matches` — AI-matched developer cards with similarity context
5. `/chat` — room list sidebar + WebSocket message thread
   - Use `useWebSocket` custom hook wrapping native WebSocket
   - Reconnect on disconnect with exponential backoff

### Task 5-D: Custom hooks (one per concern)
```typescript
// hooks/useAuth.ts       — login, logout, register, current user
// hooks/useFollow.ts     — follow/unfollow with optimistic update
// hooks/useWebSocket.ts  — connect, send, receive, reconnect logic
// hooks/useSkillMatch.ts — fetch /ai/matches
```

---

## Non-negotiable code quality rules

1. **No business logic in endpoint files** — endpoints only validate input, call a service, return output
2. **No raw SQL** — use SQLAlchemy ORM only
3. **Every endpoint has a Pydantic response_model** — no `dict` returns
4. **Secrets in `.env` only** — never hardcoded, never committed (`.env` in `.gitignore`)
5. **`.env.example`** must exist with all keys and placeholder values
6. **Migrations for every model change** — never modify tables manually
7. **Type hints everywhere** in Python — no bare `Any` unless unavoidable
8. **No `print()` in production code** — use `logging` module
9. **CORS configured explicitly** — only allow `http://localhost:5173` in dev, real domain in prod
10. **README.md** must include: architecture diagram reference, `docker compose up` quickstart, env var table, API endpoint table

---

## How to use this prompt with Claude Code

Start a new Claude Code session and say:

> "Read CODEX_PROMPT.md in this repo. Start with Phase 1, Task 1-A. Create all the bootstrap files, then proceed through 1-B, 1-C, 1-D in order. After each task, run the tests and confirm they pass before moving on."

Then for each subsequent phase:
> "Phase 1 is complete and all tests pass. Now implement Phase 2."
