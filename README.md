# 🛡️ Agentic Deployment Guardian

**Built by Philip Osita Ogbunugafor**

An autonomous AIOps system that detects, diagnoses, and resolves GitHub Actions
pipeline failures on its own — then emails you a plain-English report. No human
needs to be awake.

---

## 📖 What Is This Project?

Imagine you push code to GitHub. Something breaks. Normally you get one email —
"your deployment failed" — and then **you** have to wake up, open your laptop,
read hundreds of lines of logs, find the cause, fix it, and redeploy. At 2am.

**The Agentic Deployment Guardian does all of that for you.**

The moment a pipeline fails, it:

1. **Detects** the failure automatically (GitHub webhook)
2. **Downloads** the full error logs from GitHub
3. **Reads and understands** them using AI (Cerebras `gpt-oss-120b`)
4. **Decides** what to do — restart, roll back, or escalate to a human
5. **Takes the action** on its own
6. **Confirms recovery** by polling the health endpoint
7. **Emails you** a professional report of what happened and what it did
8. **Learns** from every incident so future diagnoses get faster

All in seconds — before you even pick up your phone.

---

## 🚨 The Problems It Solves

- ❌ GitHub gives no intelligent diagnosis when a pipeline fails
- ❌ Engineers waste hours reading raw logs to find the root cause
- ❌ Fixing failures depends on a human being awake and available
- ❌ There is no automatic rollback when a deployment breaks
- ❌ After every incident, someone must manually write up what happened

This project fixes **every one** of those.

---

## 🧠 How It Works — End to End

```
1.  Developer pushes code to GitHub
2.  GitHub Actions runs the deploy pipeline
3.  A job fails
4.  GitHub fires a webhook → Guardian (/webhook/github on :8101)
5.  Guardian verifies the signature (HMAC) and records the incident
6.  A Celery worker pulls the failed job's raw logs from the GitHub API
7.  The log parser strips timestamps/ANSI/noise and finds the failure
8.  The logs are sent to Cerebras AI (with any known matching pattern)
9.  Cerebras returns a plain-English root cause + suggested fix
10. A decision matrix classifies the remediation:
        → AUTO_ROLLBACK     (revert main to the last good commit)
        → SERVICE_RESTART   (SSH in and restart the crashed container)
        → HUMAN_ESCALATION  (needs a person — flag it clearly)
11. Guardian executes the action automatically
12. Guardian polls http://app:8100/health until recovered (or 5-min timeout)
13. Guardian emails a professional HTML report via Gmail
14. Guardian writes a summary row to deployment_history
15. Pattern recognition runs — recurring failures get labelled and fed
    back into the AI prompt so the next diagnosis is faster and sharper
```

Every step is automatic. There are no manual triggers anywhere in the chain.

---

## 🧩 Glossary (for non-experts)

| Term | Plain meaning |
|------|---------------|
| **Webhook** | An automatic HTTP "alert" GitHub sends when an event happens |
| **CI/CD pipeline** | The automated steps that build and deploy your code |
| **Container** | A lightweight, isolated box that runs one service |
| **Celery worker** | A background process that does slow work off the main app |
| **Remediation** | The fix the system applies (restart / rollback / escalate) |
| **Rollback** | Going back to the last version that worked |
| **JWT** | A signed token that proves you're allowed to call the API |
| **HMAC signature** | A cryptographic stamp proving a webhook really came from GitHub |

---

## 🛠️ Technology Stack

| Tool | Role in this project |
|------|----------------------|
| **FastAPI** | Main app — webhook receiver + REST API |
| **PostgreSQL** | Database — incidents, history, patterns |
| **Redis** | Message broker between the app and the worker |
| **Celery** | Runs the diagnose → remediate → report chain in the background |
| **LangChain** | Framework connecting the app to the AI model |
| **Cerebras (`gpt-oss-120b`)** | The AI that reads logs and explains failures |
| **GitHub API** | Pulls raw logs from failed jobs; performs rollbacks |
| **GitHub Actions** | CI/CD — runs tests, then deploys on every push to `main` |
| **Docker + Compose** | Packages and runs all 5 services together |
| **Nginx** | Reverse proxy in front of the app (port 8101) |
| **Gmail SMTP** | Sends the incident report emails |
| **JWT (PyJWT)** | Auth on all management endpoints |
| **AES-256-GCM (cryptography)** | Encrypts raw logs at rest in the database |
| **pytest** | Test suite that must pass before any deploy |
| **Contabo VPS (Ubuntu 24.04)** | The server everything runs on |

---

## 🏗️ Project Structure

```
agentic-deployment-guardian/
├── .github/workflows/
│   ├── deploy.yml            # CI tests → deploy to VPS on every push to main
│   ├── notify-guardian.yml   # On a real failure, resolves the failed JOB id
│   │                         #   via the API and POSTs a signed webhook
│   └── failure-drill.yml     # Manual "fail on purpose" drill for verification
├── app/
│   ├── main.py               # FastAPI: webhook receiver + /token + API endpoints
│   ├── config.py             # All settings, loaded from environment (.env)
│   ├── db.py                 # SQLAlchemy engine + Redis client + health checks
│   ├── models.py             # Tables + all DB helpers
│   ├── celery_app.py         # Celery application (Redis broker)
│   ├── tasks.py              # The automatic chain: logs → AI → remediate → report
│   ├── github_webhook.py     # Signature verify + payload parse/sanitize
│   ├── github_api.py         # Pull job logs; rollback git operations
│   ├── log_parser.py         # Strip noise, extract failure, find step + exit code
│   ├── ai_agent.py           # LangChain + Cerebras root-cause analysis
│   ├── decision.py           # Decision matrix → remediation action
│   ├── rollback.py           # AUTO_ROLLBACK (dry-run or live revert)
│   ├── restart.py            # SERVICE_RESTART via SSH
│   ├── remediation.py        # HUMAN_ESCALATION + recovery health poll
│   ├── report.py             # Builds the HTML/text incident email
│   ├── email_sender.py       # Gmail SMTP delivery
│   ├── patterns.py           # Recurring-failure recognition
│   ├── crypto.py             # AES-256-GCM encryption at rest
│   ├── auth.py               # JWT auth (OAuth2 password flow)
│   └── ratelimit.py          # Redis rate limiter for the webhook
├── tests/                    # pytest unit + integration suite (CI-gated)
├── scripts/
│   ├── seed_failure.py       # Simulate a failure type through the AI chain
│   ├── seed_remediation.py   # Test each remediation path independently
│   ├── send_test_report.py   # Send a test incident email
│   └── send_test_webhook.sh  # Send a signed test webhook
├── nginx/default.conf        # Nginx reverse proxy (dynamic upstream resolution)
├── docker-compose.yml        # Defines all 5 containers
├── Dockerfile                # Builds the app/worker image
├── requirements.txt          # Python dependencies
├── .env.example              # Template of every environment variable
├── pytest.ini                # Test config
├── SECURITY.md               # Security audit + controls
└── README.md                 # This file
```

---

## 🔌 Port Assignments

The project uses dedicated ports to avoid clashing with anything else on the VPS:

| Service | Container port | Host port | Exposure |
|---------|----------------|-----------|----------|
| FastAPI app | 8100 | `0.0.0.0:8100` | public |
| Nginx reverse proxy | 8101 | `0.0.0.0:8101` | public |
| PostgreSQL | 5432 | `127.0.0.1:5433` | localhost only |
| Redis | 6379 | `127.0.0.1:6380` | localhost only |

PostgreSQL and Redis are bound to `127.0.0.1` so they are **never** exposed to
the internet.

---

## ✅ Prerequisites

- A Linux VPS (Ubuntu 22.04 or 24.04) with root SSH access
- A GitHub account + a repository for this project
- A **Cerebras** account → https://cloud.cerebras.ai (free API key)
- A **Gmail** account with **2-Step Verification** enabled (for an App Password)
- Git and VS Code on your local machine
- Basic comfort running terminal commands

---

## 🚀 Full Setup — Follow These Steps Exactly

> The whole system is **pipeline-managed**: you never edit files on the server.
> You push to `main`, GitHub Actions runs the tests, and if they pass it deploys
> to the VPS automatically. Below, each "phase" adds one capability.

### Phase 1 — Server + pipeline

**1. Log into the VPS and create the project user**
```bash
ssh root@YOUR_VPS_IP
adduser guardian
usermod -aG sudo guardian
usermod -aG docker guardian      # lets the deploy run Docker without sudo
```

**2. Install Docker + tools**
```bash
apt update && apt upgrade -y
apt install -y git curl ufw docker.io docker-compose-plugin
systemctl enable --now docker    # so containers come back on reboot
```

**3. Open only the public app ports**
```bash
ufw allow 22 && ufw allow 8100 && ufw allow 8101 && ufw --force enable
```

**4. Create the deploy SSH key (used by GitHub Actions to log into the VPS)**
```bash
su - guardian
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
cat ~/.ssh/id_ed25519        # copy the PRIVATE key for the VPS_SSH_KEY secret
```

**5. Create the project directory and point it at your GitHub repo**
```bash
mkdir -p /home/guardian/agentic-deployment-guardian
cd /home/guardian/agentic-deployment-guardian
git init && git branch -m main
git config --global --add safe.directory /home/guardian/agentic-deployment-guardian
git remote add origin https://github.com/YOURNAME/agentic-deployment-guardian.git
```

**6. Add the core GitHub secrets** (repo → Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|-------|
| `VPS_HOST` | your VPS IP |
| `VPS_USER` | `guardian` |
| `VPS_SSH_KEY` | the **private** key printed above (entire block) |

Push the code from your local machine and watch the **Actions** tab go green.

### Phases 2–8 — add capabilities by adding secrets

Each capability is unlocked simply by adding its secret and pushing. The
pipeline writes every secret into a `.env` file on the VPS (mode `600`) on each
deploy — you never create `.env` by hand.

| Phase | Capability | Secret you add |
|-------|-----------|----------------|
| 2 | Dockerized app + Postgres + Redis + Nginx | `POSTGRES_PASSWORD` |
| 3 | Webhook receiver (signature-verified) | `WEBHOOK_SECRET` (see note ⚠️) |
| 4 | Pull + parse failed-job logs | `GH_PAT` |
| 5 | Cerebras AI root-cause analysis | `CEREBRAS_API_KEY` |
| 6 | Autonomous remediation | *(reuses `VPS_SSH_KEY`, `GH_PAT`)* |
| 7 | Gmail incident reports | `GMAIL_APP_PASSWORD` |
| 8 | History + pattern recognition | *(none)* |

> ⚠️ **Important naming note:** GitHub does **not** allow repository secret names
> that start with `GITHUB_`. So the webhook secret is stored as **`WEBHOOK_SECRET`**,
> and the pipeline exposes it to the app as the `GITHUB_WEBHOOK_SECRET` env var.

**How to get each secret:**

- **`WEBHOOK_SECRET`** — run `openssl rand -hex 32`. Use the same value when you
  add the repository webhook (GitHub → Settings → Webhooks → Add webhook):
  - Payload URL: `http://YOUR_VPS_IP:8101/webhook/github`
  - Content type: `application/json`
  - Secret: the value above
  - Events: **Workflow jobs**
- **`GH_PAT`** — GitHub → Developer settings → Personal access tokens (classic),
  scope **`repo`**. *(For live rollback it also needs **Contents: Write** + **Workflows**.)*
- **`CEREBRAS_API_KEY`** — https://cloud.cerebras.ai → API Keys (must have access
  to `gpt-oss-120b`).
- **`GMAIL_APP_PASSWORD`** — https://myaccount.google.com/apppasswords (needs
  2-Step Verification). 16-character password.

### Phase 9 — security hardening + production

No new GitHub secrets are required. On deploy the pipeline **auto-generates and
preserves** three more values in `.env` (so they never appear in your repo):

| Auto-generated in `.env` | Purpose |
|--------------------------|---------|
| `JWT_SECRET` | signs the API access tokens |
| `API_PASSWORD` | the password for the `guardian` API user |
| `GUARDIAN_ENC_KEY` | AES-256 key that encrypts raw logs at rest |

> 🔐 **Back up the VPS `.env`.** If `GUARDIAN_ENC_KEY` is lost, previously
> encrypted logs can't be read. It is preserved across deploys automatically.

**Enabling live rollback (optional, powerful):** by default `AUTO_ROLLBACK` runs
in **dry-run** (it identifies the last good commit and records the plan, but does
not push). To let it actually revert `main`, set a repository **Variable**
`REMEDIATION_ROLLBACK_ENABLED=true` (Settings → Secrets and variables → Actions →
Variables) **and** give `GH_PAT` write scope. If the token is read-only the
revert simply fails safe (recorded `FAILED_RECOVERY`, nothing pushed).

---

## 🔑 All GitHub Secrets (complete list)

| Secret | What it is | Where to get it |
|--------|------------|-----------------|
| `VPS_HOST` | VPS IP address | Your VPS dashboard |
| `VPS_USER` | `guardian` | fixed value |
| `VPS_SSH_KEY` | private SSH key | `cat ~/.ssh/id_ed25519` on the VPS |
| `POSTGRES_PASSWORD` | database password | choose a strong one |
| `WEBHOOK_SECRET` | webhook signing secret | `openssl rand -hex 32` |
| `GH_PAT` | GitHub Personal Access Token | GitHub → Developer settings |
| `CEREBRAS_API_KEY` | Cerebras AI key | https://cloud.cerebras.ai |
| `GMAIL_APP_PASSWORD` | Gmail App Password | https://myaccount.google.com/apppasswords |

*(`JWT_SECRET`, `API_PASSWORD`, `GUARDIAN_ENC_KEY` are generated by the pipeline,
not added by you.)*

---

## 🔐 Using the Secured API

Every endpoint except `/health` and `/webhook/github` requires a JWT.

```bash
# 1) Get the API password (on the VPS)
sudo -u guardian grep '^API_PASSWORD=' /home/guardian/agentic-deployment-guardian/.env

# 2) Exchange it for a token
curl -X POST http://YOUR_VPS_IP:8101/token \
  -d "username=guardian&password=THE_API_PASSWORD"
# → {"access_token":"<JWT>","token_type":"bearer"}

# 3) Call protected endpoints with the token
TOKEN=<JWT>
curl http://YOUR_VPS_IP:8101/incidents      -H "Authorization: Bearer $TOKEN"
curl http://YOUR_VPS_IP:8101/incidents/1    -H "Authorization: Bearer $TOKEN"
curl http://YOUR_VPS_IP:8101/patterns       -H "Authorization: Bearer $TOKEN"
```

### API endpoints

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/health` | none | Liveness + Postgres/Redis checks |
| POST | `/token` | credentials | Get a JWT |
| POST | `/webhook/github` | HMAC signature | Receive failure events |
| GET | `/` | JWT | Service info |
| GET | `/incidents` | JWT | Recent incidents |
| GET | `/incidents/{id}` | JWT | One incident (incl. decrypted log excerpt) |
| GET | `/patterns` | JWT | Recurring failure patterns |

---

## 🗄️ Database Tables

| Table | What it stores |
|-------|----------------|
| `incidents` | Every incident in full detail: parsed logs, AES-256-encrypted raw log, AI root cause, remediation action + status, escalation, report status |
| `deployment_history` | One long-term summary row per completed incident |
| `failure_patterns` | Recurring failure types, labelled, with occurrence counts |

---

## 🔍 Verify Everything Works

```bash
# On the VPS:
docker ps --filter "name=guardian-"           # all 5 containers Up
curl http://localhost:8101/health              # {"status":"healthy",...}
docker compose logs worker --tail=30           # the chain in action
```

**Simulate a real failure end-to-end (recommended):**
1. GitHub → **Actions → Failure Drill → Run workflow** (a job that fails on purpose)
2. Watch the worker: `docker compose logs worker -f`
3. Check your Gmail inbox for the `[Guardian] Incident #N …` report
4. Inspect it: `curl :8101/incidents/<id> -H "Authorization: Bearer $TOKEN"`

**Test each remediation path independently (on the VPS):**
```bash
docker exec -e ACTION=HUMAN_ESCALATION -i guardian-worker python3 - < scripts/seed_remediation.py
docker exec -e ACTION=SERVICE_RESTART  -i guardian-worker python3 - < scripts/seed_remediation.py
docker exec -e ACTION=AUTO_ROLLBACK    -i guardian-worker python3 - < scripts/seed_remediation.py
```

**Run the test suite inside the container:**
```bash
docker exec guardian-app pytest -q
```

---

## 📬 Sample Incident Email

**Subject:** `[Guardian] Incident #5 — Write .env — ESCALATED`

> **What Happened** — An automated deployment for the agentic-deployment-guardian
> project failed while running the step "Write .env". The Guardian detected the
> problem automatically and began investigating.
>
> **Where It Happened** — Repository: Ogbunugafor-Philip/agentic-deployment-guardian
> · Branch: main · Commit: 76530fd2
>
> **Why It Failed** — The pipeline tried to write the environment file but a
> required secret was missing or empty. The deployment was stopped automatically
> to protect the live service.
>
> **What Was Done** — The Guardian escalated this incident for human review. No
> automated change was made because this type of failure needs a person to verify
> and correct the missing configuration.
>
> **Next Steps** — Check that all required GitHub secrets are present and valid,
> then re-run the deployment.

Color coding: 🟩 green = recovered · 🟧 orange = escalated · 🟥 red = recovery failed.

---

## 🧯 Troubleshooting

| Symptom | Likely cause & fix |
|--------|--------------------|
| Deploy fails: `… secret is not set` | A required GitHub secret is missing — add it, re-run. |
| `/incidents` returns 401 | That's correct — get a JWT from `/token` first. |
| `:8101` returns 502 right after a deploy | Nginx is re-resolving the app; it clears within ~10s (dynamic resolver). |
| AI step stuck / `ai_status` empty | Cerebras key invalid — test it: `curl https://api.cerebras.ai/v1/chat/completions -H "Authorization: Bearer $KEY" -d '{"model":"gpt-oss-120b","messages":[{"role":"user","content":"ping"}],"max_tokens":1}'`. Update `CEREBRAS_API_KEY` and redeploy. |
| Email not arriving | Check the Gmail **App Password** (not your login password) and that 2-Step Verification is on. |
| Rollback recorded `FAILED_RECOVERY` | `GH_PAT` lacks write scope — give it Contents:Write + Workflows, or keep dry-run. |
| Webhook returns 429 | Rate limit hit (60/min per IP) — expected protection. |

---

## 🔒 Security Model (summary)

- **JWT** on all management endpoints; `/health` open; webhook uses **HMAC**.
- **AES-256-GCM** encryption-at-rest for raw logs (`GUARDIAN_ENC_KEY`).
- **Secrets live in `.env` only** (mode 600) — never written to the database.
- **Rate limiting** + **body-size cap** + **input sanitisation** on the webhook.
- **Tests gate deploys** — a failing test blocks the deploy.
- **Postgres/Redis** bound to localhost; only 8100/8101 are public.
- Full details and residual risks in [SECURITY.md](SECURITY.md).

---

## 👤 Author

**Philip Osita Ogbunugafor** — built as a complete, production-grade AIOps system
spanning DevOps, backend engineering, AI integration, and security, implemented
incrementally across 9 phases on a live Linux VPS.

## 📄 License

Open source, available for learning and portfolio purposes.
