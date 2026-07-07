"""
consumers/event_consumer.py — Notification Service
Subscribes to:
  - pharmtrack.delivery (topic) → delivery.* routing keys
  - pharmtrack.auth (fanout)    → user.logged_in

Handled events:
  delivery.assigned, delivery.scanned, delivery.status_changed,
  delivery.completed, delivery.cancelled, delivery.customer_confirmed

For each event, creates a Notification record in Postgres.
"""
import json
import logging
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmtrack_notification.settings")
django.setup()

import pika
from django.conf import settings
from apps.notifications.models import Notification, NotificationType

logger = logging.getLogger(__name__)

# ─── Event handlers ────────────────────────────────────────────

EVENT_MAP = {
    "delivery.assigned": {
        "type": NotificationType.DELIVERY_ASSIGNED,
        "title": "New Delivery Assigned",
        "message": lambda p: (
            f"Delivery from {p.get('from_location')} to {p.get('destination')} "
            f"has been assigned to driver {p.get('driver_name', 'N/A')}."
        ),
    },
    "delivery.scanned": {
        "type": NotificationType.DELIVERY_SCANNED,
        "title": "Delivery Scanned at Warehouse",
        "message": lambda p: (
            f"Delivery {p.get('delivery_id')} has been scanned at the warehouse "
            f"and is now in transit to {p.get('customer_name', 'the customer')}."
        ),
    },
    "delivery.status_changed": {
        "type": NotificationType.DELIVERY_STATUS_CHANGED,
        "title": "Delivery Status Updated",
        "message": lambda p: (
            f"Delivery status changed from {p.get('old_status')} to {p.get('new_status')}."
        ),
    },
    "delivery.completed": {
        "type": NotificationType.DELIVERY_COMPLETED,
        "title": "Delivery Completed",
        "message": lambda p: (
            f"Delivery to {p.get('destination')} has been completed successfully."
        ),
    },
    "delivery.cancelled": {
        "type": NotificationType.DELIVERY_CANCELLED,
        "title": "Delivery Cancelled",
        "message": lambda p: (
            f"Delivery cancelled. Reason: {p.get('cancellation_reason', 'No reason provided')}."
        ),
    },
    "delivery.customer_confirmed": {
        "type": NotificationType.DELIVERY_COMPLETED,
        "title": "Delivery Confirmed by Customer",
        "message": lambda p: (
            f"Delivery to {p.get('destination')} was confirmed by customer {p.get('customer_name', 'N/A')}. "
            f"Delivery is now marked as complete."
        ),
    },
    "user.logged_in": {
        "type": NotificationType.USER_LOGIN,
        "title": "New Login",
        "message": lambda p: f"A new login was detected for {p.get('email')}.",
    },
}


def process_event(payload: dict) -> None:
    event = payload.get("event", "")
    config = EVENT_MAP.get(event)

    if not config:
        logger.debug("[Notification Consumer] Unknown event: %s", event)
        return

    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("[Notification Consumer] No user_id in event: %s", event)
        return

    Notification.objects.create(
        user_id=user_id,
        notification_type=config["type"],
        title=config["title"],
        message=config["message"](payload),
        metadata=payload,
    )
    logger.info("[Notification Consumer] Created notification [%s] for user %s", event, user_id)


def on_message(ch, method, properties, body):
    try:
        payload = json.loads(body)
        process_event(payload)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.error("[Notification Consumer] Error: %s", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_consumer():
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # ── Delivery exchange (topic) ──
    channel.exchange_declare(exchange="pharmtrack.delivery", exchange_type="topic", durable=True)
    channel.queue_declare(queue="notification.delivery.events", durable=True)
    channel.queue_bind(
        exchange="pharmtrack.delivery",
        queue="notification.delivery.events",
        routing_key="delivery.*",
    )

    # ── Auth exchange (fanout) ──
    channel.exchange_declare(exchange="pharmtrack.auth", exchange_type="fanout", durable=True)
    channel.queue_declare(queue="notification.auth.events", durable=True)
    channel.queue_bind(exchange="pharmtrack.auth", queue="notification.auth.events")

    # Consume both queues
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="notification.delivery.events", on_message_callback=on_message)
    channel.basic_consume(queue="notification.auth.events", on_message_callback=on_message)

    logger.info("[Notification Consumer] Waiting for events...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()
