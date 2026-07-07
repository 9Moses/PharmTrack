"""
events/publisher.py — Delivery Service
Publishes delivery domain events consumed by notification-service & email-service.
"""
import json
import logging
import pika
from django.conf import settings

logger = logging.getLogger(__name__)

EXCHANGE = "pharmtrack.delivery"


def _get_channel():
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = 600
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    return conn, ch


def publish_delivery_event(routing_key: str, payload: dict) -> None:
    try:
        conn, ch = _get_channel()
        ch.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload, default=str),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                content_type="application/json",
            ),
        )
        conn.close()
        logger.info("[Delivery Publisher] Sent '%s'", routing_key)
    except Exception as exc:
        logger.error("[Delivery Publisher] Failed '%s': %s", routing_key, exc)
        raise
