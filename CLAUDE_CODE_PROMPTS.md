# Claude Code Prompt Cards
# Copy and paste each block into Claude Code at the start of each phase.
# Always start a fresh session per phase to avoid context bloat.

# ─────────────────────────────────────────
# BEFORE ANY PHASE — run once
# ─────────────────────────────────────────
Read CODEX_PROMPT.md fully before doing anything.
Keep CODEX_PROMPT.md open as your specification throughout.
After completing each task, run tests and confirm they pass before proceeding.
Never skip writing tests — tests are part of the deliverable.

# ─────────────────────────────────────────
# PHASE 1 — Auth + User profiles
# ─────────────────────────────────────────
Read CODEX_PROMPT.md.

Implement Phase 1 in order:
1. Task 1-A: create requirements.txt, config.py, security.py, db/session.py
2. Task 1-B: User model, Pydantic schemas, auth endpoints, user endpoints, deps.py
3. Task 1-C: configure Alembic, generate and apply the users migration
4. Task 1-D: write tests in tests/api/test_auth.py and test_users.py

Rules:
- Use async SQLAlchemy everywhere (no sync session)
- Refresh token goes in httpOnly cookie, NOT in response body
- All endpoints must have response_model
- Run `pytest -v` after Task 1-D and fix until all tests pass
- Run `ruff check app` and fix all lint errors

Done when: `pytest --cov=app --cov-report=term-missing` shows ≥70% for auth + users modules.

# ─────────────────────────────────────────
# PHASE 2 — Follow system + Feed + Redis
# ─────────────────────────────────────────
Read CODEX_PROMPT.md. Phase 1 is complete.

Implement Phase 2:
1. Task 2-A: Follow model + Alembic migration
2. Task 2-B: follow/unfollow/list endpoints
3. Task 2-C: Redis feed service (LPUSH/LTRIM, 10-min TTL, cache miss fallback)
4. Task 2-D: Post model + endpoints + feed endpoint

Write tests:
- tests/api/test_follows.py: follow, unfollow, list followers, prevent self-follow
- tests/api/test_posts.py: create, read, delete, feed populates after follow

Run `pytest --cov=app -v` and fix until green.

# ─────────────────────────────────────────
# PHASE 3 — WebSocket Chat + AI Matching
# ─────────────────────────────────────────
Read CODEX_PROMPT.md. Phases 1-2 are complete.

Implement Phase 3:
1. Task 3-A: ConnectionManager, chat rooms model + migration, WS endpoint
   - Use Redis pub/sub so multiple backend replicas share state
   - Persist each message to DB before broadcasting
   - Authenticate via ?token= query param (decode JWT, 403 if invalid)
2. Task 3-B: ai_service.py with extract_skills(), get_skill_embedding(), match_users()
   - Mock OpenAI in tests using unittest.mock.patch
   - Cache match results in Redis for 1 hour

Write tests:
- tests/api/test_chat.py: create room, WS connect + send + receive (use httpx WS client)
- tests/services/test_ai_service.py: skill extraction with mocked OpenAI, cosine similarity

Run `pytest --cov=app -v` and fix until green.

# ─────────────────────────────────────────
# PHASE 4 — Docker, CI, Coverage polish
# ─────────────────────────────────────────
Read CODEX_PROMPT.md. Phases 1-3 are complete.

Implement Phase 4:
1. Task 4-A: Dockerfile for backend, docker-compose.yml (already scaffolded — verify and fill gaps)
2. Task 4-B: .github/workflows/ci.yml (already scaffolded — verify it matches current code)
3. Task 4-C: tests/conftest.py with all fixtures listed in CODEX_PROMPT.md
4. Task 4-D: add missing tests until `pytest --cov=app --cov-fail-under=70` passes

Also:
- Add ruff.toml with line-length=100 and select=["E","F","I"]
- Add .gitignore covering .env, __pycache__, .pytest_cache, .coverage, *.pyc
- Verify .env.example has every variable used in config.py
- Verify README.md endpoint table matches actual routes

Done when: `docker compose up --build` starts all services, health endpoint returns 200,
and GitHub Actions workflow file is valid YAML.

# ─────────────────────────────────────────
# PHASE 5 — React Frontend
# ─────────────────────────────────────────
Read CODEX_PROMPT.md. Backend phases 1-4 are complete.

Implement Phase 5:
1. Task 5-A: Vite + React + TypeScript + React Query + Tailwind setup
2. Task 5-B: src/lib/apiClient.ts with axios interceptors for token refresh
3. Task 5-C: pages — /login, /register, /feed, /profile/:username, /matches, /chat
4. Task 5-D: custom hooks — useAuth, useFollow, useWebSocket, useSkillMatch

Design guidelines:
- Clean, dark-leaning developer aesthetic (GitHub-inspired)
- Skill tags as colored badges
- Loading states with React Query (isLoading skeleton, not spinners)
- useWebSocket must reconnect with exponential backoff (max 5 retries)
- /matches page shows similarity score as a percentage bar under each card
- Mobile responsive (Tailwind sm/md breakpoints)

Run `npm run build` with zero TypeScript errors before finishing.
