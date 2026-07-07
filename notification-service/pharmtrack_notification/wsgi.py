import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pharmtrack_notification.settings")
application = get_wsgi_application()
