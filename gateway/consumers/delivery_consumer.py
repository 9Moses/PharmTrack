"""
consumers/delivery_consumer.py — Gateway Service
Subscribes to:
  - pharmtrack.delivery (topic) → delivery.* routing keys

Listens for delivery assignment and cancellation to adjust medicine stock accordingly.
Uses SELECT ... FOR UPDATE to avoid race conditions.
"""
import json
import logging
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmtrack_gateway.settings")
django.setup()

import pika  # noqa: E402
from django.conf import settings  # noqa: E402
from django.db import transaction  # noqa: E402
from apps.medicines.models import Medicine  # noqa: E402
from utils.publisher import publish_event  # noqa: E402

logger = logging.getLogger(__name__)


def process_delivery_event(routing_key: str, payload: dict) -> None:
    event = payload.get("event", routing_key)
    items = payload.get("items", [])

    if event == "delivery.assigned":
        _deduct_stock(items)
    elif event == "delivery.cancelled":
        _restore_stock(items)
    else:
        logger.debug("[Delivery Consumer] Ignoring event: %s", event)


def _deduct_stock(items: list) -> None:
    for item in items:
        medicine_id = item.get("medicine_id")
        quantity = int(item.get("quantity", 0))
        if not medicine_id or quantity <= 0:
            continue

        try:
            with transaction.atomic():
                medicine = Medicine.objects.select_for_update().get(id=medicine_id)
                if medicine.quantity >= quantity:
                    medicine.quantity -= quantity
                    medicine.save(update_fields=["quantity", "updated_at"])
                    logger.info("[Delivery Consumer] Deducted %s from medicine %s", quantity, medicine_id)

                    # Publish event for stock update
                    publish_event("pharmtrack.medicine", "medicine.updated", {
                        "event": "medicine.updated",
                        "medicine_id": str(medicine.id),
                        "quantity": medicine.quantity,
                    })
                else:
                    logger.warning(
                        "[Delivery Consumer] Insufficient stock for %s. Requested: %s, Available: %s",
                        medicine_id, quantity, medicine.quantity
                    )
        except Medicine.DoesNotExist:
            logger.error("[Delivery Consumer] Medicine %s not found during deduction", medicine_id)
        except Exception as exc:
            logger.error("[Delivery Consumer] Error deducting stock for %s: %s", medicine_id, exc)


def _restore_stock(items: list) -> None:
    for item in items:
        medicine_id = item.get("medicine_id")
        quantity = int(item.get("quantity", 0))
        if not medicine_id or quantity <= 0:
            continue

        try:
            with transaction.atomic():
                medicine = Medicine.objects.select_for_update().get(id=medicine_id)
                medicine.quantity += quantity
                medicine.save(update_fields=["quantity", "updated_at"])
                logger.info("[Delivery Consumer] Restored %s to medicine %s", quantity, medicine_id)

                # Publish event for stock update
                publish_event("pharmtrack.medicine", "medicine.updated", {
                    "event": "medicine.updated",
                    "medicine_id": str(medicine.id),
                    "quantity": medicine.quantity,
                })
        except Medicine.DoesNotExist:
            logger.error("[Delivery Consumer] Medicine %s not found during restoration", medicine_id)
        except Exception as exc:
            logger.error("[Delivery Consumer] Error restoring stock for %s: %s", medicine_id, exc)


def on_message(ch, method, properties, body):
    try:
        payload = json.loads(body)
        process_delivery_event(method.routing_key, payload)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.error("[Delivery Consumer] Error processing message: %s", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_consumer():
    params = pika.URLParameters(settings.RABBITMQ_URL)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Delivery exchange (topic)
    channel.exchange_declare(exchange="pharmtrack.delivery", exchange_type="topic", durable=True)
    channel.queue_declare(queue="gateway.delivery.events", durable=True)
    channel.queue_bind(
        exchange="pharmtrack.delivery",
        queue="gateway.delivery.events",
        routing_key="delivery.*",
    )

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="gateway.delivery.events", on_message_callback=on_message)

    logger.info("[Delivery Consumer] Waiting for events...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()
