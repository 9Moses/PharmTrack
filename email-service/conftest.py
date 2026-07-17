"""
conftest.py — email-service test configuration.

This file is loaded by pytest BEFORE any test module is imported. It:
  1. Adds the project root to sys.path so `app.main` and `core.config`
     are importable (belt-and-suspenders alongside ENV PYTHONPATH=/app).
  2. Stubs out `pika` in sys.modules so that importing `email_consumer`
     never triggers a real RabbitMQ connection.  In Docker test containers
     there is no RabbitMQ, and pika's import-time socket initialisation
     (including reverse-DNS via socket.getfqdn) can hang for 30 s+.
"""
import os
import sys
from unittest.mock import MagicMock

# ── 1. sys.path ───────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 2. Stub pika before any app module is imported ────────────────────────────
_pika_stub = MagicMock(name="pika")
_pika_stub.URLParameters.return_value = MagicMock()
# Raise immediately so the consumer retry-loop doesn't spin in the background
_pika_stub.BlockingConnection.side_effect = RuntimeError(
    "pika stub: no RabbitMQ in test environment"
)
_exc_mod = MagicMock()
_exc_mod.AMQPConnectionError = RuntimeError   # consumer catches this to retry
_pika_stub.exceptions = _exc_mod

sys.modules.setdefault("pika", _pika_stub)
sys.modules.setdefault("pika.exceptions", _exc_mod)
