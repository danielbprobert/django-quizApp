import os
from pathlib import Path
from dotenv import load_dotenv

# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def getenv_bool(name: str, default: str = "False") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")

# Secrets & environment
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")  # override in .env
DEBUG = getenv_bool("DJANGO_DEBUG", "True")  # True locally, False on prod

ALLOWED_HOSTS = [h for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h] or ["127.0.0.1", "localhost"]
# IMPORTANT: when DEBUG=False, set this to your public IP or domain in .env

# CSRF (schemes must be present, e.g. https://example.com)
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

ADMIN_URL = os.getenv("DJANGO_ADMIN_URL", "admin/")

# --------------------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    'django.contrib.humanize',
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Realtime (no Redis; in-memory only)
    "channels",

    # Custom Apps
    "quiz",
]

# --------------------------------------------------------------------------------------
# Middleware / URLs / Templates
# --------------------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"], 
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------------------
# Channels (InMemory only — suitable for single-process dev / tiny prod)
# NOTE: Do NOT run multiple workers if you want pub/sub to work without Redis.
# --------------------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

# --------------------------------------------------------------------------------------
# Database (SQLite for both dev & play prod)
# --------------------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------------------
# I18N / TZ
# --------------------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------------------
# Static / Media
# --------------------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"      
STATICFILES_DIRS = [BASE_DIR / "static"]     

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------------------
# Security (tighten automatically when DEBUG=False)
# --------------------------------------------------------------------------------------
if not DEBUG:
    # Cookies
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"

    # HTTPS enforcement
    SECURE_SSL_REDIRECT = True

    # Hardening headers
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    REFERRER_POLICY = "same-origin"

    # Once you confirm HTTPS is solid, consider HSTS (be sure before enabling):
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --------------------------------------------------------------------------------------
# Logging (quiet but helpful in prod)
# --------------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO" if not DEBUG else "DEBUG"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}