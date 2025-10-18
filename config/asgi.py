# config/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from django.conf import settings
from quiz.consumers import QuizConsumer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

# ✅ serve /static/* when DEBUG=True
if settings.DEBUG:
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter([
        path("ws/quiz/<int:quiz_id>/", QuizConsumer.as_asgi()),
    ]),
})
