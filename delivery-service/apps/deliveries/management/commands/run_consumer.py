"""
Delivery Service — RabbitMQ consumer management command.
Listens on pharmtrack.auth exchange for upstream events.
"""
import json
import logging
import pika
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


def handle_message(ch, method, properties, body):
    try:
        payload = json.loads(body)
        event = payload.get("event", "")
        logger.info("[Delivery Consumer] Received: %s", event)
        if event == "user.logged_in":
            logger.info("[Delivery Consumer] User logged in: %s", payload.get("email"))
        elif event == "medicine.created":
            logger.info("[Delivery Consumer] Medicine created: %s", payload.get("name"))
            from apps.medicines.models import Medicine
            from datetime import date
            
            # Use actual values from the gateway event payload
            Medicine.objects.update_or_create(
                id=payload.get("medicine_id"),
                defaults={
                    "name": payload.get("name", "Unknown"),
                    "quantity": payload.get("quantity", 0),
                    "batch": payload.get("batch", "N/A"),
                    "expiry_date": payload.get("expiry_date") or date(2099, 12, 31),
                    "price": payload.get("price", 0.00),
                }
            )
            
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.error("[Delivery Consumer] Error: %s", exc)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


class Command(BaseCommand):
    help = "Start RabbitMQ consumer for delivery service"

    def handle(self, *args, **options):
        self.stdout.write("[Delivery Consumer] Starting...")
        params = pika.URLParameters(settings.RABBITMQ_URL)
        params.heartbeat = 600
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        # Auth Events
        channel.exchange_declare(exchange="pharmtrack.auth", exchange_type="fanout", durable=True)
        channel.queue_declare(queue="delivery.auth.events", durable=True)
        channel.queue_bind(exchange="pharmtrack.auth", queue="delivery.auth.events")
        
        # Medicine Events
        channel.exchange_declare(exchange="pharmtrack.medicine", exchange_type="topic", durable=True)
        channel.queue_declare(queue="delivery.medicine.events", durable=True)
        channel.queue_bind(exchange="pharmtrack.medicine", queue="delivery.medicine.events", routing_key="medicine.#")
        
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue="delivery.auth.events", on_message_callback=handle_message)
        channel.basic_consume(queue="delivery.medicine.events", on_message_callback=handle_message)
        self.stdout.write("[Delivery Consumer] Waiting for messages...")
        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
            connection.close()
