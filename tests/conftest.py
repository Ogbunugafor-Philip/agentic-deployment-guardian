"""Shared test setup: force deterministic env BEFORE any app module imports
settings, so tests are self-contained regardless of the CI/container env."""

import os

_TEST_ENV = {
    "DATABASE_URL": "postgresql+psycopg2://guardian:guardian@localhost:5432/guardian",
    "REDIS_URL": "redis://localhost:6379/0",
    "GITHUB_WEBHOOK_SECRET": "test-webhook-secret",
    "GH_PAT": "test-pat",
    "CEREBRAS_API_KEY": "test-cerebras-key",
    "GMAIL_APP_PASSWORD": "test-app-password",
    "GMAIL_FROM": "philiposita1041@gmail.com",
    "GMAIL_TO": "philiposita1041@gmail.com",
    "JWT_SECRET": "test-jwt-secret-0123456789",
    "API_USER": "guardian",
    "API_PASSWORD": "test-api-password",
    "GUARDIAN_ENC_KEY": "test-encryption-key-0123456789",
}

# Force (not setdefault) so CI-provided values can't change expected test inputs.
os.environ.update(_TEST_ENV)
