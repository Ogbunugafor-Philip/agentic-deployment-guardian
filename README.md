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

## Phase 5 — AI root-cause analysis + remediation decision

As soon as Phase 4 parsing finishes (`log_status=retrieved`), the Celery task
chains a second task, `analyze_incident` — no manual step:

1. A **LangChain agent** ([app/ai_agent.py](app/ai_agent.py)) sends the
   `failed_step` + `parsed_summary` to **Cerebras** (`gpt-oss-120b`) with a
   structured prompt asking it to identify the exact failure point, explain in
   plain English why it failed, and suggest the most likely fix.
2. The plain-English diagnosis is stored in the `root_cause` column.
3. A **decision matrix** ([app/decision.py](app/decision.py)) classifies the
   incident as `AUTO_ROLLBACK`, `SERVICE_RESTART`, or `HUMAN_ESCALATION` (based
   on the failed step + root cause, with the model's severity as a tiebreaker
   and a safe `HUMAN_ESCALATION` default) and stores it in `remediation_action`.

`GET /incidents/{id}` includes `root_cause`, `remediation_action`, `ai_status`,
and `analyzed_at`. **`CEREBRAS_API_KEY` is never logged or stored.**

### Secret setup

Add a repository secret **`CEREBRAS_API_KEY`** under GitHub → Settings → Secrets
and variables → Actions. The deploy pipeline writes it into `.env` on every
deploy.

### Verifying the full Phase 5 flow

After deploying (with `CEREBRAS_API_KEY` set), trigger a failure as in Phase 4
(the **Failure Drill** workflow, or a signed webhook with a real failed job id),
then:
```bash
curl http://<VPS_HOST>:8101/incidents/<id>
docker compose logs --tail=40 worker   # "AI analysis for incident #N: remediation=..."
```
Within a few seconds of `log_status=retrieved` you should see `ai_status=analyzed`,
a clear plain-English `root_cause`, and a `remediation_action` of one of the three
levels.

## Phase 6 — Autonomous remediation engine

The moment Phase 5 sets `remediation_action`, the Celery task chains
`remediate_incident` automatically (no manual step). It dispatches one of three
paths and then confirms recovery:

- **AUTO_ROLLBACK** ([app/rollback.py](app/rollback.py)) — finds the last
  successful deploy commit via the GitHub API and reverts `main` to it (a new
  commit that triggers a deploy). **Default: dry-run** (records the planned
  revert without pushing). Set repo Variable `REMEDIATION_ROLLBACK_ENABLED=true`
  to perform the real revert (needs a write-scoped `GH_PAT`). A loop guard
  refuses to roll back when `main` is already a guardian rollback.
- **SERVICE_RESTART** ([app/restart.py](app/restart.py)) — SSHes to the VPS
  (`VPS_SSH_KEY`, base64 in `.env`) and runs `docker compose restart app`.
  **Default: live** (master switch `REMEDIATION_ENABLED`).
- **HUMAN_ESCALATION** ([app/remediation.py](app/remediation.py)) — flags the
  incident, stores a clear `escalation_reason`, and a structured
  `escalation_summary` (JSON) for the reporting phase.

**Confirmation checks (6.4):** after AUTO_ROLLBACK and SERVICE_RESTART the engine
polls `HEALTH_CHECK_URL` (default `http://app:8100/health`) until healthy or a
5-minute timeout, then writes `remediation_status` (`RECOVERED`,
`FAILED_RECOVERY`, or `ESCALATED`) and `remediated_at`. All credentials
(SSH key, tokens) are kept out of logs and the database.

### Verifying each path independently

The native automatic flow picks the path from the AI classification. To exercise
each path directly, seed an already-analyzed incident with a chosen action and
let the engine run (the script runs inside the worker container):

```bash
# on the VPS, in the project dir
docker exec -e ACTION=HUMAN_ESCALATION -i guardian-worker python3 - < scripts/seed_remediation.py
docker exec -e ACTION=SERVICE_RESTART  -i guardian-worker python3 - < scripts/seed_remediation.py
docker exec -e ACTION=AUTO_ROLLBACK    -i guardian-worker python3 - < scripts/seed_remediation.py

# then inspect the printed incident id
curl http://<VPS_HOST>:8101/incidents/<id>
docker compose logs --tail=40 worker     # "Remediation for incident #N: action=... status=..."
```

Expect: HUMAN_ESCALATION → `remediation_status=ESCALATED` with `escalation_reason`
+ `escalation_summary`; SERVICE_RESTART → app restarted and `RECOVERED`;
AUTO_ROLLBACK → dry-run detail naming the last-good commit and `RECOVERED` (health
still OK). The end-to-end automatic chain is verified by the **Failure Drill**
workflow, which flows webhook → logs → AI → remediation.

## Phase 8 — Deployment history & pattern recognition

When an incident finishes its full cycle (after the report step), the worker:

1. Writes a one-row summary into **`deployment_history`** — a separate long-term
   record (the live `incidents` table keeps full detail). Idempotent per incident.
2. Runs **pattern recognition** ([app/patterns.py](app/patterns.py)): groups
   history by failed step + exit code, and when the same failure has occurred
   **2+ times** records it in **`failure_patterns`** (`pattern_label`,
   `failed_step`, `occurrence_count`, `first_seen`, `last_seen`, `suggested_fix`)
   with a human label (e.g. "Recurring test failure", "Repeated env/config
   failure", "Repeated service crash").

**Feedback loop (8.3):** before analysing a new incident, the worker looks up a
matching pattern and, if found, injects it into the Cerebras prompt — *"This
failure matches a known pattern: [label]. It has occurred [N] times before.
Previous suggested fix: [fix]"* — so diagnoses get faster and more consistent as
history accumulates.

`GET /patterns` lists all identified failure patterns. All of this is automatic.
