import logging
from django.core.management.base import BaseCommand
from consumers.delivery_consumer import start_consumer

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Starts the RabbitMQ consumer for delivery events to adjust medicine stock."

    def handle(self, *args, **options):
        self.stdout.write("Starting Gateway Delivery Consumer...")
        try:
            start_consumer()
        except Exception as e:
            logger.exception("Failed to start gateway delivery consumer")
            self.stderr.write(f"Error: {e}")
