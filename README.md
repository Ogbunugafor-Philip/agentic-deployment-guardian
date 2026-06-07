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

## Phase 3 — GitHub webhook integration

When the deploy pipeline fails, `.github/workflows/notify-guardian.yml` fires on
the `workflow_run` *failure* event, builds a JSON payload (job id, repository
owner/name, commit SHA, branch, conclusion, timestamp), signs it with
`GITHUB_WEBHOOK_SECRET` (HMAC-SHA256, `X-Hub-Signature-256` — GitHub's own
scheme), and POSTs it to the receiver.

The receiver `POST /webhook/github`:
- validates the signature against `GITHUB_WEBHOOK_SECRET` (rejects with 401 if
  missing/invalid);
- returns `200` immediately and records the incident in a background task, so
  GitHub never times out;
- writes a row to the `incidents` table in PostgreSQL (created automatically on
  startup) and logs the event — the raw secret is never logged.

`GET /incidents` lists the most recent recorded incidents.

### Secret setup

Add a repository secret **`GITHUB_WEBHOOK_SECRET`** (any long random string) under
GitHub → Settings → Secrets and variables → Actions. The deploy pipeline writes it
into `.env` on the VPS, and the notify workflow uses it to sign outgoing events —
both sides share the one secret. `.env` is gitignored.

### Testing the webhook

1. **Manual GitHub run (full external path):** Actions → *Notify Guardian on
   Failure* → **Run workflow**. It sends a signed synthetic failure event from a
   GitHub runner to `http://<VPS_HOST>:8101/webhook/github`.
2. **Direct signed request** (from the VPS or anywhere with the secret):
   ```bash
   GITHUB_WEBHOOK_SECRET=<secret> ./scripts/send_test_webhook.sh
   # or against the public endpoint:
   GITHUB_WEBHOOK_SECRET=<secret> ./scripts/send_test_webhook.sh http://<VPS_HOST>:8101/webhook/github
   ```
3. **Confirm it was recorded:**
   ```bash
   curl http://<VPS_HOST>:8101/incidents          # most recent incidents
   docker compose logs --tail=20 app              # "Incident #N recorded ..."
   ```
   A wrong/missing signature returns `401` and is **not** recorded — that is the
   expected, secure behaviour.
