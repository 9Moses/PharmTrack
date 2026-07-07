"""
app/consumers/email_consumer.py — Email Service
Subscribes to RabbitMQ events and dispatches templated emails.

Bindings:
  pharmtrack.auth (fanout)      → otp.requested
  pharmtrack.delivery (topic)   → delivery.assigned, delivery.completed, delivery.cancelled
"""
import asyncio
import json
import logging
import threading
from datetime import datetime

import pika

from core.config import settings
from app.services.email_sender import send_email
from app.services.template_renderer import render_template

logger = logging.getLogger(__name__)


# ─── Email dispatch functions ────────────────────────────────

async def _send_otp_email(payload: dict):
    year = datetime.utcnow().year
    html = render_template("otp_email.html", {
        "name": payload.get("name", "User"),
        "otp": payload.get("otp"),
        "year": year,
    })
    await send_email(
        to=payload["email"],
        subject="Your PharmTrack Login OTP",
        text_body=f"Your OTP is: {payload.get('otp')}. It expires in 5 minutes.",
        html_body=html,
    )


async def _send_delivery_assigned_email(payload: dict):
    year = datetime.utcnow().year
    html = render_template("delivery_assigned.html", {
        "customer_name": payload.get("customer_name", "Customer"),
        "delivery_id": payload.get("delivery_id", ""),
        "from_location": payload.get("from_location", ""),
        "destination": payload.get("destination", ""),
        "driver_name": payload.get("driver_name", ""),
        "total_amount": payload.get("total_amount", "0.00"),
        "qr_code": payload.get("qr_code", ""),
        "year": year,
    })
    customer_email = payload.get("customer_email")
    if customer_email:
        await send_email(
            to=customer_email,
            subject="PharmTrack — Your Delivery Has Been Assigned",
            text_body=f"Your delivery from {payload.get('from_location')} to {payload.get('destination')} has been assigned.",
            html_body=html,
        )


async def _send_delivery_completed_email(payload: dict):
    year = datetime.utcnow().year
    html = render_template("delivery_completed.html", {
        "customer_name": payload.get("customer_name", "Customer"),
        "delivery_id": payload.get("delivery_id", ""),
        "destination": payload.get("destination", ""),
        "year": year,
    })
    customer_email = payload.get("customer_email")
    if customer_email:
        await send_email(
            to=customer_email,
            subject="PharmTrack — Delivery Completed ✅",
            text_body=f"Your delivery to {payload.get('destination')} has been completed.",
            html_body=html,
        )


async def _send_delivery_cancelled_email(payload: dict):
    customer_email = payload.get("customer_email")
    reason = payload.get("cancellation_reason", "No reason provided")
    if customer_email:
        await send_email(
            to=customer_email,
            subject="PharmTrack — Delivery Cancelled",
            text_body=f"Your delivery has been cancelled. Reason: {reason}.",
        )


# ─── Event router ─────────────────────────────────────────────

EVENT_HANDLERS = {
    "otp.requested": _send_otp_email,
    "delivery.assigned": _send_delivery_assigned_email,
    "delivery.completed": _send_delivery_completed_email,
    "delivery.cancelled": _send_delivery_cancelled_email,
}


def _run_async(coro):
    """Run an async coroutine from a sync pika callback thread."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def on_message(ch, method, properties, body):
    try:
        payload = json.loads(body)
        event = payload.get("event", "")
        handler = EVENT_HANDLERS.get(event)
        if handler:
            logger.info("[Email Consumer] Handling event: %s", event)
            _run_async(handler(payload))
        else:
            logger.debug("[Email Consumer] No handler for event: %s", event)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.error("[Email Consumer] Error processing '%s': %s", body[:100], exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_consumer():
    """
    Blocking consumer — called in a background thread from FastAPI lifespan.
    Will retry connecting to RabbitMQ continuously if it fails.
    """
    import time
    from pika.exceptions import AMQPConnectionError
    
    params = pika.URLParameters(settings.rabbitmq_url)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300

    while True:
        try:
            logger.info("[Email Consumer] Attempting to connect to RabbitMQ...")
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            # ── Declare exchanges ──
            channel.exchange_declare(exchange="pharmtrack.auth", exchange_type="fanout", durable=True)
            channel.exchange_declare(exchange="pharmtrack.delivery", exchange_type="topic", durable=True)

            # ── Auth queue (OTP) ──
            channel.queue_declare(queue="email.auth.events", durable=True)
            channel.queue_bind(exchange="pharmtrack.auth", queue="email.auth.events")

            # ── Delivery queue ──
            channel.queue_declare(queue="email.delivery.events", durable=True)
            for key in ["delivery.assigned", "delivery.completed", "delivery.cancelled"]:
                channel.queue_bind(
                    exchange="pharmtrack.delivery",
                    queue="email.delivery.events",
                    routing_key=key,
                )

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue="email.auth.events", on_message_callback=on_message)
            channel.basic_consume(queue="email.delivery.events", on_message_callback=on_message)

            logger.info("[Email Consumer] Waiting for events...")
            channel.start_consuming()

        except AMQPConnectionError as exc:
            logger.error("[Email Consumer] Connection failed, retrying in 5s: %s", exc)
            time.sleep(5)
        except Exception as exc:
            logger.error("[Email Consumer] Consumer crashed, retrying in 5s: %s", exc)
            time.sleep(5)


def start_consumer_thread() -> threading.Thread:
    """Start the consumer in a daemon thread."""
    t = threading.Thread(target=start_consumer, daemon=True, name="email-rabbitmq-consumer")
    t.start()
    logger.info("[Email Consumer] Background thread started.")
    return t
