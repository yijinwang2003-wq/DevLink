# DevLink

A developer networking platform for finding project collaborators and referrals.
Built as a portfolio project demonstrating production-grade SWE skills.

## Architecture

```
Client (React + TypeScript)
        │  REST + WebSocket
        ▼
API Gateway (FastAPI + JWT middleware)
   ├── Auth service     — OAuth2 / JWT / refresh tokens
   ├── User service     — profiles, skills, search
   ├── Follow service   — social graph
   ├── Post service     — activity feed (Redis cache)
   ├── Chat service     — WebSocket rooms (Redis pub/sub)
   └── AI service       — resume parsing, skill matching (OpenAI)
        │
   PostgreSQL 16    Redis 7
```

## Quickstart

```bash
cp .env.example .env        # fill in SECRET_KEY and OPENAI_API_KEY
docker compose up --build   # starts postgres, redis, backend, frontend
```

Backend API docs: http://localhost:8000/docs
Frontend: http://localhost:5173

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | ✅ | `redis://host:6379/0` |
| `SECRET_KEY` | ✅ | 32-char hex — `openssl rand -hex 32` |
| `OPENAI_API_KEY` | Phase 3+ | OpenAI key for AI matching features |
| `VITE_API_URL` | Frontend | Backend URL seen by browser |

## API endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access token + refresh cookie |
| POST | `/api/v1/auth/refresh` | Rotate access token |
| POST | `/api/v1/auth/logout` | Clear refresh cookie |

### Users
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/users/me` | Current user profile |
| PUT | `/api/v1/users/me` | Update profile / skills |
| GET | `/api/v1/users/{username}` | Public profile |
| GET | `/api/v1/users/?skill=python` | Search users by skill |

### Social
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/users/{username}/follow` | Follow user |
| DELETE | `/api/v1/users/{username}/follow` | Unfollow |
| GET | `/api/v1/users/{username}/followers` | Follower list |
| GET | `/api/v1/feed/` | Personalized feed (Redis cached) |

### Chat
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/chat/rooms/` | User's chat rooms |
| POST | `/api/v1/chat/rooms/` | Create / get DM room |
| WS | `/ws/chat/{room_id}?token=jwt` | WebSocket connection |

### AI
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/ai/extract-skills` | Parse resume text → skills |
| GET | `/api/v1/ai/matches` | Top 10 matched developers |

## Development

```bash
# Run tests
cd backend && pytest --cov=app -v

# Apply migrations
alembic upgrade head

# Create new migration after model changes
alembic revision --autogenerate -m "describe change"

# Lint
ruff check app && ruff format app
```

## CI/CD

GitHub Actions runs on every push to `main` and every PR:
1. **Lint** — ruff check + format
2. **Test** — pytest with PostgreSQL + Redis services, fails if coverage < 70%
3. **Build** — docker build validation
