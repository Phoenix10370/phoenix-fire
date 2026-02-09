import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# Load environment variables from .env
# Priority (first found wins):
#   1) BASE_DIR / "qbo_integration" / ".env"
#   2) BASE_DIR / ".env"
# -----------------------------------------------------------------------------
DOTENV_1 = BASE_DIR / "qbo_integration" / ".env"
DOTENV_2 = BASE_DIR / ".env"

if DOTENV_1.exists():
    load_dotenv(DOTENV_1)
elif DOTENV_2.exists():
    load_dotenv(DOTENV_2)

# =============================================================================
# Core
# =============================================================================
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only")

DEBUG = os.environ.get("DEBUG", "1") == "1"

IS_RENDER = os.environ.get("RENDER", "").lower() == "true" or Path("/var/data").exists()

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,192.168.50.91,phoenix-fire-1.onrender.com",
).split(",")
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS if h.strip()]

LOGIN_URL = "/admin/login/"

# =============================================================================
# Applications
# =============================================================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # project apps
    "codes",
    "customers",
    "properties",
    "quotations",
    "company",
    "email_templates",
    "routines",
    "qbo",
    "job_tasks.apps.JobTasksConfig",
    "core",
    "scheduling",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    # 🔁 QBO automatic token refresh
    "qbo.middleware.QBOTokenRefreshMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "phoenix_fire.urls"

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
                "company.context_processors.client_profile",

                # ✅ Google Maps API key (for address autocomplete)
                "core.context_processors.google_maps",
            ],
        },
    },
]

WSGI_APPLICATION = "phoenix_fire.wsgi.application"

# =============================================================================
# Database
# =============================================================================
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# =============================================================================
# Static files
# =============================================================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# =============================================================================
# Media (uploads)
# =============================================================================
MEDIA_URL = "/media/"

if Path("/var/data").exists():
    MEDIA_ROOT = Path("/var/data/media")
else:
    MEDIA_ROOT = BASE_DIR / "media"

# =============================================================================
# Storage (Django 4.2+)
# =============================================================================
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# =============================================================================
# Security (production)
# =============================================================================
if IS_RENDER and not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# =============================================================================
# Google Maps / Places API
# =============================================================================
# Used for address autocomplete on Property forms
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()

# =============================================================================
# QuickBooks Online (QBO)
# =============================================================================
QBO_CLIENT_ID = os.environ.get("QBO_CLIENT_ID", "").strip()
QBO_CLIENT_SECRET = os.environ.get("QBO_CLIENT_SECRET", "").strip()

# "sandbox" or "production"
QBO_ENVIRONMENT = os.environ.get("QBO_ENVIRONMENT", "sandbox").strip().lower() or "sandbox"

QBO_REDIRECT_URI = os.environ.get(
    "QBO_REDIRECT_URI",
    "http://localhost:8000/qbo/callback/",
).strip()

# =============================================================================
# Email / Microsoft Graph
# =============================================================================
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "joe@phoenixfire.com.au")

MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")

MS_AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"

MS_REDIRECT_URI = os.environ.get(
    "MS_REDIRECT_URI",
    "http://localhost:8000/quotations/microsoft/callback/",
)

MS_GRAPH_SCOPES = ["User.Read", "Mail.Send"]

# =============================================================================
# Logging
# =============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
