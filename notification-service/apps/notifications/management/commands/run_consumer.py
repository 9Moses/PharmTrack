from django.core.management.base import BaseCommand
from consumers.event_consumer import start_consumer

class Command(BaseCommand):
    help = "Start RabbitMQ consumer for notification service"

    def handle(self, *args, **options):
        self.stdout.write("[Notification Consumer] Starting event consumer...")
        start_consumer()
