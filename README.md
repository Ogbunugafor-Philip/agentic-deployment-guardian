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

The receiver also accepts genuine GitHub repository webhooks signed with the same
secret — it parses the `workflow_run`, `workflow_job`, and the Actions-sender
payload shapes. (A native repo webhook subscribed to *Workflow jobs* / *Workflow
runs* delivers events for **all** conclusions, including successes; the
Actions-based `notify-guardian` sender fires on **failure only**. Scope or remove
the native webhook if you want failures only.)

The receiver `POST /webhook/github`:
- validates the signature against `GITHUB_WEBHOOK_SECRET` (rejects with 401 if
  missing/invalid);
- returns `200` immediately and records the incident in a background task, so
  GitHub never times out;
- writes a row to the `incidents` table in PostgreSQL (created automatically on
  startup) and logs the event — the raw secret is never logged.

`GET /incidents` lists the most recent recorded incidents.

### Secret setup

Add a repository secret **`WEBHOOK_SECRET`** (any long random string) under
GitHub → Settings → Secrets and variables → Actions. (GitHub reserves the
`GITHUB_` prefix for secret names, so the repo secret is named `WEBHOOK_SECRET`;
the workflows expose it to the app as the `GITHUB_WEBHOOK_SECRET` env var.) The
deploy pipeline writes it into `.env` on the VPS, and the notify workflow uses it
to sign outgoing events — both sides share the one secret. `.env` is gitignored.

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

## Phase 4 — Log retrieval and parsing engine

When a **failure** incident is recorded, the webhook receiver enqueues a Celery
task (`process_incident_logs`) on the Redis broker — no manual triggering. A
dedicated `guardian-worker` container runs the task:

1. **Pull** the failed job's raw logs from the GitHub REST API
   (`GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs`) using `GH_PAT`. The
   job id comes from the incident row (best sourced from `workflow_job` events,
   whose `id` is the real job id).
2. **Parse** them ([app/log_parser.py](app/log_parser.py)): strip per-line
   timestamps and ANSI codes, collapse repeated blank lines, find the failed
   step and exit code, and extract the most relevant error/exception/failure
   lines into a clean summary.
3. **Store** against the incident in PostgreSQL: `raw_log` (gzip-compressed),
   `parsed_summary`, `failed_step`, `exit_code`, `log_status`, and
   `log_retrieved_at`.

`GET /incidents/{id}` returns the parsed summary, failed step, exit code, log
status, and a decompressed log excerpt. **`GH_PAT` is never logged or stored in
any column.**

### Secret setup

Add a repository secret **`GH_PAT`** (a GitHub Personal Access Token) under
GitHub → Settings → Secrets and variables → Actions. It needs read access to
Actions logs for this repo: a classic token with the `repo` scope, or a
fine-grained token with **Actions: Read** + **Contents: Read**. The deploy
pipeline writes it into `.env` on every deploy.

### Verifying log retrieval

1. Add the `GH_PAT` secret, then push (or re-run the deploy) so the pipeline
   writes it and starts the `guardian-worker` container.
2. Actions → **Failure Drill** → **Run workflow**. The job fails on purpose; the
   native repo webhook delivers a `workflow_job` failure, which becomes an
   incident and triggers automatic log retrieval.
3. Inspect the result:
   ```bash
   curl http://<VPS_HOST>:8101/incidents            # find the new incident id + log_status
   curl http://<VPS_HOST>:8101/incidents/<id>       # parsed_summary, failed_step, exit_code, excerpt
   docker compose logs --tail=30 worker             # "Stored logs for incident #N ..."
   ```
   You should see `log_status=retrieved`, a `failed_step`, `exit_code=1`, and the
   extracted failure lines (e.g. the AssertionError) in `parsed_summary`.
