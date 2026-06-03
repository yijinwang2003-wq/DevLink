# DevLink

[![CI](https://github.com/yijinwang2003-wq/DevLink/actions/workflows/ci.yml/badge.svg)](https://github.com/yijinwang2003-wq/DevLink/actions/workflows/ci.yml)

DevLink is a backend-focused developer networking platform for finding project
collaborators and referral connections. The current implementation covers
production-style REST APIs, JWT authentication, PostgreSQL persistence, Redis
feed caching, WebSocket chat, AI skill matching, Docker validation, CI, and test
coverage.

Live API: TODO

Current scope: backend Phases 1, 2, 3A, 3B, and CI/build validation. OAuth and
frontend work are intentionally not included yet.

## Tech Stack

| Area | Technology |
|---|---|
| Backend API | Python, FastAPI, Pydantic v2 |
| Persistence | PostgreSQL 16, SQLAlchemy 2.x async ORM |
| Migrations | Alembic |
| Authentication | JWT access tokens, httpOnly refresh token cookie |
| Cache / Pub-Sub | Redis 7 |
| Realtime | FastAPI WebSocket |
| AI | OpenAI `gpt-4o-mini`, `text-embedding-3-small` |
| Rate limiting | SlowAPI |
| Testing | pytest, pytest-asyncio, pytest-cov, httpx |
| Quality | Ruff format/check |
| Infra | Docker Compose, backend Dockerfile, GitHub Actions, Railway config |

## Architecture Overview

```mermaid
flowchart TB
    REST[REST API Clients] -->|HTTP JSON| Docker[Dockerized Backend]
    WSClients[WebSocket Clients] -->|/ws/chat/{room_id}?token=jwt| Docker

    subgraph DockerRuntime[Docker / Docker Compose]
        Docker --> FastAPI[FastAPI App]
        FastAPI --> API[API Layer]
        FastAPI --> WSEndpoint[WebSocket Endpoint]
        API --> Services[Service Layer]
        WSEndpoint --> Services
        Services --> PG[(PostgreSQL 16)]
        Services --> Redis[(Redis 7)]
    end

    Services --> Auth[Auth]
    Services --> Users[Users]
    Services --> Follows[Follows]
    Services --> Posts[Posts]
    Services --> Feed[Feed Cache]
    Services --> Chat[Chat Rooms]
    Services --> AI[AI Matching]
    AI --> OpenAI[OpenAI API]
    AI --> Embeddings[Stored User Embeddings]
    Embeddings --> PG

    GHA[GitHub Actions] -->|ruff check / pytest / docker build| Docker
```

The API layer is intentionally thin: FastAPI endpoints validate input, resolve
dependencies, and call service functions. Business logic lives in `app/services`,
while SQLAlchemy models and Alembic migrations own persistence.

## Production Engineering Highlights

- JWT authentication uses short-lived access tokens and an httpOnly refresh
  token cookie.
- SlowAPI rate limiting applies a global `100/minute` limit per IP and tighter
  `5/minute` limits on registration and login.
- SQLAlchemy is configured with async sessions and PostgreSQL-backed models.
- Alembic migrations track every schema change for users, follows, posts, chat
  rooms, chat messages, and user embeddings.
- Redis caches personalized feed IDs and keeps feed reads fast after cache warmup.
- WebSocket chat authenticates the connection with a JWT query token and checks
  room membership before accepting the socket.
- Chat messages are persisted to PostgreSQL before broadcast, so delivery does
  not race ahead of durable storage.
- AI skill extraction uses `gpt-4o-mini`; skill matching uses persisted
  `text-embedding-3-small` vectors to avoid repeated embedding calls for every
  candidate.
- Match results are cached in Redis under `match:{user_id}` for one hour.
- Redis Pub/Sub publisher/subscriber classes are prepared for cross-worker chat
  delivery in a future scaling pass.
- CI runs lint, tests, and backend Docker build validation.
- The backend is Dockerized with a production-style Uvicorn entrypoint.

## Core Flows

### Auth Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Auth API
    participant S as Auth/User Services
    participant DB as PostgreSQL

    C->>API: POST /api/v1/auth/register
    API->>S: validate and hash password
    S->>DB: create user
    DB-->>S: user
    S-->>API: UserRead
    API-->>C: 201 Created

    C->>API: POST /api/v1/auth/login
    API->>S: verify credentials
    S->>DB: load user by email
    S-->>API: access token + refresh token
    API-->>C: JWT body + httpOnly refresh cookie
```

Access tokens are sent as Bearer tokens. Refresh tokens are stored in an
httpOnly cookie and rotated through `/api/v1/auth/refresh`.

### Feed And Redis Cache Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Feed API
    participant FS as Feed Service
    participant R as Redis
    participant DB as PostgreSQL

    C->>API: GET /api/v1/feed/?page=1&size=20
    API->>FS: get_feed_posts(user_id)
    FS->>R: read feed:{user_id}
    alt cache hit
        R-->>FS: post ids
        FS->>DB: load posts by ids
    else cache miss
        FS->>DB: query followed users' posts
        FS->>R: cache feed ids with TTL
    end
    FS-->>API: posts
    API-->>C: PostRead[]
```

Redis stores personalized feed IDs under `feed:{user_id}` with a 10 minute TTL.
Follow, unfollow, and post creation paths update or invalidate the cache.

### WebSocket Chat Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant WS as /ws/chat/{room_id}
    participant CS as Chat Service
    participant DB as PostgreSQL
    participant R as Redis Pub/Sub Prep

    C->>WS: connect ?token=<jwt>
    WS->>CS: authenticate token and check room membership
    CS->>DB: load room/user access
    CS-->>WS: accept socket
    loop message
        C->>WS: {"type":"message","content":"hello"}
        WS->>CS: validate max 2000 chars
        CS->>DB: persist ChatMessage and update room.updated_at
        CS-->>WS: broadcast to in-memory room sockets
        CS-.->R: room:{room_id} publisher/subscriber foundation
    end
    WS-->>C: heartbeat {"type":"ping"} every 30s
```

The current chat path works for a single FastAPI instance. Redis channel classes
are present for future horizontal scaling, using one channel per room:
`room:{room_id}`.

### AI Matching And Embedding Persistence Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as AI API
    participant AS as AI Service
    participant DB as PostgreSQL
    participant R as Redis
    participant OAI as OpenAI

    C->>API: POST /api/v1/ai/extract-skills
    API->>AS: extract_skills(resume_text)
    AS->>OAI: gpt-4o-mini
    OAI-->>AS: JSON skill array
    AS-->>API: normalized skills

    C->>API: GET /api/v1/ai/matches
    API->>AS: match_users(current_user)
    AS->>R: read match:{user_id}
    alt cache hit
        R-->>AS: user ids + scores
        AS->>DB: load matched users
    else cache miss
        AS->>DB: load current user and candidates
        AS->>DB: read stored embeddings
        opt missing embedding
            AS->>OAI: text-embedding-3-small
            AS->>DB: persist users.embedding
        end
        AS->>R: cache ids + scores for 1 hour
    end
    AS-->>API: matched users with similarity scores
```

User embeddings are stored on the `users.embedding` JSON column. Embeddings are
generated when users are created, regenerated when skills change, and lazily
created during matching if an existing profile is missing an embedding.

## API Reference

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | No | Create a user account |
| `POST` | `/api/v1/auth/login` | No | Return an access token and set refresh cookie |
| `POST` | `/api/v1/auth/refresh` | Cookie | Issue a new access token |
| `POST` | `/api/v1/auth/logout` | Cookie | Clear refresh cookie |

### Users

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/users/me` | Bearer | Read current user profile |
| `PUT` | `/api/v1/users/me` | Bearer | Update profile fields and skills |
| `GET` | `/api/v1/users/` | No | List users with `skill`, `page`, and `size` filters |
| `GET` | `/api/v1/users/{username}` | No | Read a public profile |

### Follows

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/users/{username}/follow` | Bearer | Follow a user |
| `DELETE` | `/api/v1/users/{username}/follow` | Bearer | Unfollow a user |
| `GET` | `/api/v1/users/{username}/followers` | No | List followers with pagination |
| `GET` | `/api/v1/users/{username}/following` | No | List followed users with pagination |

### Posts And Feed

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/posts/` | Bearer | Create a post |
| `GET` | `/api/v1/posts/{post_id}` | No | Read a post |
| `DELETE` | `/api/v1/posts/{post_id}` | Bearer | Delete your own post |
| `GET` | `/api/v1/feed/` | Bearer | Read personalized Redis-backed feed |

### Chat

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/chat/rooms/` | Bearer | List rooms for current user |
| `POST` | `/api/v1/chat/rooms/` | Bearer | Create or get a direct-message room |
| `GET` | `/api/v1/chat/rooms/{room_id}/messages?page=1&size=50` | Bearer | List room messages, newest first |
| `WS` | `/ws/chat/{room_id}?token=<jwt>` | Query token | Connect to authenticated chat room |

WebSocket messages larger than 2000 characters are rejected with
`WS_1003_UNSUPPORTED_DATA`. The server sends heartbeat pings every 30 seconds.

### AI

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/ai/extract-skills` | Bearer | Extract normalized technical skills from resume text |
| `GET` | `/api/v1/ai/matches?top_k=10` | Bearer | Return matched users with similarity scores |
| `POST` | `/api/v1/ai/reindex/{user_id}` | Bearer admin placeholder | Regenerate and persist one user's embedding |

## Local Development

Create a local environment file from the example and fill in required secrets:

```bash
cp .env.example .env
```

Start only the services needed for backend development:

```bash
docker compose up -d postgres redis
docker compose ps
```

Run the backend API locally after services are healthy:

```bash
cd backend
make run
```

API docs are available at `http://localhost:8000/docs`.

Run backend checks:

```bash
cd backend
make format
make lint
make test
```

If your local PostgreSQL volume only contains the default `devlink` database,
create the test database once:

```bash
docker exec devlink-starter-postgres-1 psql -U devlink -d devlink -c "CREATE DATABASE devlink_test;"
```

Apply migrations:

```bash
cd backend
make migrate
```

Create a new migration after model changes:

```bash
cd backend
../.venv/bin/alembic revision --autogenerate -m "describe change"
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Async SQLAlchemy URL, for example `postgresql+asyncpg://devlink:devlink@localhost:5432/devlink` |
| `REDIS_URL` | Yes | Redis URL, for example `redis://localhost:6379/0` |
| `SECRET_KEY` | Yes | JWT signing secret |
| `ALGORITHM` | No | JWT algorithm, defaults to `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | Refresh token lifetime |
| `OPENAI_API_KEY` | AI matching | Required for live skill extraction and embedding generation |
| `DISABLE_RATE_LIMITING` | No | Set to `true` only for tests or controlled local debugging |

## Docker Commands

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
docker compose ps
```

Both services include healthchecks. PostgreSQL uses `pg_isready`; Redis uses
`redis-cli ping`.

View service logs:

```bash
docker compose logs postgres
docker compose logs redis
```

Build the backend image locally:

```bash
docker build ./backend -t devlink-backend:ci
```

## Testing

The AI matching backend branch currently validates with:

```text
41 passed
87% coverage
```

Coverage includes auth, users, follows, posts/feed, chat room APIs, chat service
message persistence, message history pagination, WebSocket authorization, AI
skill extraction, embedding persistence, match ranking, Redis fallback, and
reindexing.

Use the same local validation commands before opening or merging a pull request:

```bash
cd backend
../.venv/bin/ruff format app
../.venv/bin/ruff check app
../.venv/bin/python -m pytest --cov=app -v
```

The same checks are available through `backend/Makefile`:

```bash
cd backend
make format
make lint
make test
```

## WebSocket Chat Usage

Create or get a direct-message room with:

```http
POST /api/v1/chat/rooms/
Authorization: Bearer <access_token>
Content-Type: application/json

{"recipient_username":"alice"}
```

Connect to the room with the access token as a query parameter:

```text
ws://localhost:8000/ws/chat/{room_id}?token=<access_token>
```

Send messages as JSON:

```json
{"type":"message","content":"hello"}
```

The server persists the message, refreshes the room `updated_at`, then broadcasts
the saved message to connected sockets in that room. Message history is available
through `GET /api/v1/chat/rooms/{room_id}/messages?page=1&size=50`.

## AI Matching API Examples

Extract skills:

```http
POST /api/v1/ai/extract-skills
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "resume_text": "Backend engineer using Python, FastAPI, PostgreSQL, Redis."
}
```

Example response:

```json
{
  "skills": ["python", "fastapi", "postgresql", "redis"]
}
```

Get matches:

```http
GET /api/v1/ai/matches?top_k=10
Authorization: Bearer <access_token>
```

Example response:

```json
[
  {
    "id": "8f4b2d88-7e53-4e6f-83a7-2c9e2d5b8c10",
    "email": "alice@example.com",
    "username": "alice",
    "bio": "Backend engineer",
    "avatar_url": null,
    "skills": ["python", "fastapi", "redis"],
    "github_url": "https://github.com/alice",
    "created_at": "2026-06-03T20:00:00Z",
    "similarity_score": 0.91
  }
]
```

Reindex one user embedding:

```http
POST /api/v1/ai/reindex/{user_id}
Authorization: Bearer <admin_access_token>
```

Example response:

```json
{
  "user_id": "8f4b2d88-7e53-4e6f-83a7-2c9e2d5b8c10",
  "embedding_dimensions": 1536
}
```

## Deployment

Live API: TODO

The backend includes a Dockerfile used by CI build validation and Railway
deployment:

```bash
docker build ./backend -t devlink-backend:ci
```

The image installs Python dependencies from `backend/requirements.txt`, copies
the backend application into `/app`, and starts Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Docker Compose provides PostgreSQL 16 and Redis 7 for local integration testing.
GitHub Actions runs lint, tests against service containers, and backend Docker
build validation on pushes and pull requests.

Railway deployment files:

- `railway.toml` points Railway at `backend/Dockerfile`, uses `/health` as the
  healthcheck, and starts Uvicorn on `$PORT`.
- `backend/Procfile` provides the same web process command for Procfile-based
  deployment flows.

Required deployment environment variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Production PostgreSQL async URL |
| `REDIS_URL` | Production Redis URL |
| `SECRET_KEY` | JWT signing secret |
| `OPENAI_API_KEY` | OpenAI API key for AI matching |
| `ALGORITHM` | Optional, defaults to `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Optional refresh token TTL |
