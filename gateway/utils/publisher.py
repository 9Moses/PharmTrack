"""
utils/publisher.py — Gateway Service
Publishes domain events to RabbitMQ exchanges.

Exchange topology:
  pharmtrack.auth      (fanout) — auth events
  pharmtrack.delivery  (topic)  — delivery.* events
  pharmtrack.medicine  (topic)  — medicine.* events

NOTE: pika is imported lazily (inside functions, not at module level) to avoid
the socket.getfqdn() reverse-DNS call pika makes at import time. In containers
without a fast DNS resolver this blocks for ~30 seconds and prevents gunicorn
workers from starting, causing readiness probes to fail.
"""
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_connection():
    import pika  # lazy import — avoids 30s DNS hang at module load time
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300
    return pika.BlockingConnection(params)


def publish_event(exchange: str, routing_key: str, payload: dict) -> None:
    """
    Publish a JSON event to the given exchange with the given routing key.
    Uses a short-lived connection per publish (suitable for Django views).
    For high-throughput, replace with a connection pool or Celery broker.
    """
    import pika  # lazy import — avoids 30s DNS hang at module load time
    try:
        connection = _get_connection()
        channel = connection.channel()

        exchange_type = "fanout" if exchange.endswith(".auth") else "topic"
        channel.exchange_declare(exchange=exchange, exchange_type=exchange_type, durable=True)

        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(payload, default=str),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                content_type="application/json",
            ),
        )
        connection.close()
        logger.info("Published event '%s' to exchange '%s'", routing_key, exchange)
    except Exception as exc:
        logger.error("Failed to publish event '%s': %s", routing_key, exc)
        raise
