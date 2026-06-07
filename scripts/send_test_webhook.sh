#!/usr/bin/env bash
#
# Send a correctly-signed test failure webhook to the Guardian receiver.
#
# Usage:
#   GITHUB_WEBHOOK_SECRET=<secret> ./scripts/send_test_webhook.sh [URL]
#
# URL defaults to the local Nginx proxy on the VPS. From elsewhere, pass the
# public endpoint, e.g.:
#   GITHUB_WEBHOOK_SECRET=<secret> ./scripts/send_test_webhook.sh http://<VPS_HOST>:8101/webhook/github
#
# Requires: bash, curl, openssl.
set -euo pipefail

URL="${1:-http://localhost:8101/webhook/github}"
: "${GITHUB_WEBHOOK_SECRET:?Set GITHUB_WEBHOOK_SECRET to the shared webhook secret}"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
job_id="test-$(date +%s)"

# Single-line JSON, no trailing newline — the exact bytes we sign and send.
payload="{\"job_id\":\"${job_id}\",\"workflow\":\"Manual Test\",\"repository\":{\"owner\":\"Ogbunugafor-Philip\",\"name\":\"agentic-deployment-guardian\"},\"commit_sha\":\"deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\",\"branch\":\"main\",\"conclusion\":\"failure\",\"html_url\":\"https://github.com/Ogbunugafor-Philip/agentic-deployment-guardian\",\"timestamp\":\"${ts}\",\"event\":\"workflow_run\"}"

sig="sha256=$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$GITHUB_WEBHOOK_SECRET" -r | cut -d' ' -f1)"

echo "POST ${URL} (job_id=${job_id})"
curl -sS -m 15 -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: workflow_run" \
  -H "X-Hub-Signature-256: ${sig}" \
  --data-binary "$payload" \
  -w "\nHTTP %{http_code}\n"
