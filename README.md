# Agentic Deployment Guardian

This system autonomously detects, diagnoses, and resolves GitHub Actions pipeline failures.

## Architecture (Phase 2)

All services run in Docker via Docker Compose on the VPS and are deployed
automatically through GitHub Actions on every push to `main`.

| Service    | Container        | Host port            | Notes                                  |
|------------|------------------|----------------------|----------------------------------------|
| FastAPI    | `guardian-app`   | `8100`               | Application API (`/`, `/health`)       |
| Nginx      | `guardian-nginx` | `8101`               | Reverse proxy → `app:8100`             |
| PostgreSQL | `guardian-db`    | `127.0.0.1:5433`     | Guardian's own instance (localhost only) |
| Redis      | `guardian-redis` | `127.0.0.1:6380`     | Guardian's own instance (localhost only) |

PostgreSQL and Redis host ports are bound to `127.0.0.1` so they are not exposed
to the public internet; the app reaches them over the internal compose network
(`db:5432`, `redis:6379`). To allow external access, change the bindings in
`docker-compose.yml` and set strong credentials via `.env`.

## Configuration

Copy `.env.example` to `.env` on the server to override the defaults baked into
`docker-compose.yml` (notably the PostgreSQL password). `.env` is gitignored.

## Deployment

Pushes to `main` trigger `.github/workflows/deploy.yml`, which SSHes into the VPS,
pulls the latest code, runs `docker compose up -d --build`, and health-checks
both FastAPI (`:8100/health`) and the Nginx proxy (`:8101/health`).

```bash
# Manual local run (for development)
docker compose up -d --build
curl http://localhost:8101/health
```
