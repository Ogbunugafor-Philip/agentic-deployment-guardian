# Security Audit — Agentic Deployment Guardian (Phase 9)

Final hardening review of the autonomous deployment guardian.

## Controls in place

| Area | Control |
|------|---------|
| **Endpoint auth** | JWT (HS256, OAuth2 password flow via `/token`) required on all management/read endpoints (`/`, `/incidents`, `/incidents/{id}`, `/patterns`). `/health` is intentionally public. |
| **Webhook auth** | `/webhook/github` is authenticated by HMAC-SHA256 (`X-Hub-Signature-256`) against `GITHUB_WEBHOOK_SECRET`, verified in constant time. JWT is not used here because GitHub cannot send one. |
| **Encryption at rest** | Raw job logs are AES-256-GCM encrypted (`app/crypto.py`) before storage in PostgreSQL; per-record random nonce; key derived from `GUARDIAN_ENC_KEY`. |
| **Secret storage** | All credentials (GH_PAT, Cerebras key, Gmail app password, SSH key, JWT/enc keys) live in `.env` (mode 600) only — never written to the database. Verified clean by audit in every phase. |
| **Rate limiting** | Fixed-window Redis limiter on `/webhook/github` (default 60 req/IP/min → HTTP 429), honouring `X-Forwarded-For` from nginx. |
| **Input validation** | Webhook bodies are signature-checked, size-capped (`max_webhook_bytes`, default 2 MB → HTTP 413), JSON-validated; extracted fields are length-bounded, control-char stripped, and `conclusion` is constrained to a known vocabulary. |
| **Secrets in pipeline** | Written to `.env` by the GitHub Actions deploy from repo secrets; the SSH key is base64 single-lined; `JWT_SECRET`/`GUARDIAN_ENC_KEY`/`API_PASSWORD` are auto-generated once and preserved across deploys. Secrets are never echoed to logs (verified). |
| **Tests gate deploy** | A CI `test` job (pytest, 44 tests) must pass before the `deploy` job runs (`needs: test`). |
| **Network exposure** | Only FastAPI (8100) and nginx (8101) are public; PostgreSQL (5433) and Redis (6380) bind to `127.0.0.1` only. |
| **Auto-recovery** | All containers `restart: unless-stopped`; Docker enabled on boot. |
| **Autonomous push safety** | AUTO_ROLLBACK has a loop guard (won't roll back a commit that is itself a guardian rollback). |

## Residual risks / recommendations

1. **Live rollback requires a write-scoped `GH_PAT`.** With live rollback enabled, an AUTO_ROLLBACK pushes a revert to `main`. If `GH_PAT` is read-only the push fails safe (recorded `FAILED_RECOVERY`, no change). Use a fine-grained token scoped to this repo with **Contents: Write + Workflows** and nothing more.
2. **Single shared API user.** Management auth is one operator account (`API_USER`/`API_PASSWORD`). Adequate for a single-operator guardian; add per-user accounts if the audience grows.
3. **JWT secret rotation invalidates live tokens.** Tokens are short-lived (60 min) so impact is minimal.
4. **`GUARDIAN_ENC_KEY` must be backed up.** If it is lost, previously-encrypted raw logs become unreadable. It is preserved across deploys; back up `.env`.
5. **Gmail app password** grants send access to the mailbox. Scope is limited to SMTP send; rotate periodically.
6. **VPS is shared** with other tenants. The guardian only manages its own compose project and assigned ports; SSH restart targets only `app`.

## Verified clean
No secret (SSH key, GH_PAT, Cerebras key, Gmail password) appears in any container log or database column across all phases.
