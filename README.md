# DevLink

DevLink is a backend-focused developer networking platform for finding project
collaborators and referral connections. The current implementation covers
production-style REST APIs, JWT authentication, PostgreSQL persistence, Redis
feed caching, WebSocket chat, Docker validation, CI, and test coverage.

Current scope: backend Phases 1, 2, 3A, and CI/build validation. AI matching,
OAuth, and frontend work are intentionally not included yet.

## Tech Stack

| Area | Technology |
|---|---|
| Backend API | Python, FastAPI, Pydantic v2 |
| Persistence | PostgreSQL 16, SQLAlchemy 2.x async ORM |
| Migrations | Alembic |
| Authentication | JWT access tokens, httpOnly refresh token cookie |
| Cache / Pub-Sub | Redis 7 |
| Realtime | FastAPI WebSocket |
| Testing | pytest, pytest-asyncio, pytest-cov, httpx |
| Quality | Ruff format/check |
| Infra | Docker Compose, backend Dockerfile, GitHub Actions |

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

    GHA[GitHub Actions] -->|ruff check / pytest / docker build| Docker
```

The API layer is intentionally thin: FastAPI endpoints validate input, resolve
dependencies, and call service functions. Business logic lives in `app/services`,
while SQLAlchemy models and Alembic migrations own persistence.

## Production Engineering Highlights

- JWT authentication uses short-lived access tokens and an httpOnly refresh
  token cookie.
- SQLAlchemy is configured with async sessions and PostgreSQL-backed models.
- Alembic migrations track every schema change for users, follows, posts, chat
  rooms, and chat messages.
- Redis caches personalized feed IDs and keeps feed reads fast after cache warmup.
- WebSocket chat authenticates the connection with a JWT query token and checks
  room membership before accepting the socket.
- Chat messages are persisted to PostgreSQL before broadcast, so delivery does
  not race ahead of durable storage.
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
../.venv/bin/uvicorn app.main:app --reload
```

API docs are available at `http://localhost:8000/docs`.

Run backend checks:

```bash
cd backend
../.venv/bin/ruff format app
../.venv/bin/ruff check app
../.venv/bin/python -m pytest --cov=app -v
```

If your local PostgreSQL volume only contains the default `devlink` database,
create the test database once:

```bash
docker exec devlink-starter-postgres-1 psql -U devlink -d devlink -c "CREATE DATABASE devlink_test;"
```

Apply migrations:

```bash
cd backend
../.venv/bin/alembic upgrade head
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
| `OPENAI_API_KEY` | Future | Reserved for AI matching work |

## Docker Commands

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
docker compose ps
```

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

The Phase 3A backend branch currently validates with:

```text
31 passed
85% coverage
```

Coverage includes auth, users, follows, posts/feed, chat room APIs, chat service
message persistence, message history pagination, and WebSocket authorization.

Use the same local validation commands before opening or merging a pull request:

```bash
cd backend
../.venv/bin/ruff format app
../.venv/bin/ruff check app
../.venv/bin/python -m pytest --cov=app -v
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

## Deployment

The backend includes a Dockerfile used by CI build validation:

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
