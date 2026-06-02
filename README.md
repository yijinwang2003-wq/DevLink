# DevLink

DevLink is a backend-focused developer networking platform for finding project
collaborators and referral connections. The current implementation covers
production-style REST APIs, JWT authentication, PostgreSQL persistence, Redis
feed caching, WebSocket chat, Docker validation, CI, and test coverage.

Current scope: backend Phases 1, 2, 3A, and CI/build validation. AI matching,
OAuth, and frontend work are intentionally not included yet.

## Architecture Overview

```mermaid
flowchart LR
    Client[API Client / Browser] -->|REST JSON| API[FastAPI API Layer]
    Client -->|WebSocket token auth| WS[FastAPI WebSocket Endpoint]

    API --> Auth[Auth Service]
    API --> Users[User Service]
    API --> Follows[Follow Service]
    API --> Posts[Post Service]
    API --> Feed[Feed Service]
    API --> Chat[Chat Service]
    WS --> Chat

    Auth --> PG[(PostgreSQL 16)]
    Users --> PG
    Follows --> PG
    Posts --> PG
    Chat --> PG

    Feed --> Redis[(Redis 7)]
    Chat -. prepared pub/sub .-> Redis
```

The API layer is intentionally thin: FastAPI endpoints validate input, resolve
dependencies, and call service functions. Business logic lives in `app/services`,
while SQLAlchemy models and Alembic migrations own persistence.

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

## Testing

The Phase 3A backend branch currently validates with:

```text
31 passed
85% coverage
```

Coverage includes auth, users, follows, posts/feed, chat room APIs, chat service
message persistence, message history pagination, and WebSocket authorization.

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
