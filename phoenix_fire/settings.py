import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only")
DEBUG = os.environ.get("DEBUG", "1") == "1"

# Render: set env var RENDER=true
IS_RENDER = os.environ.get("RENDER", "").lower() == "true"

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,192.168.50.91,phoenix-fire-1.onrender.com"
).split(",")
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS if h.strip()]

LOGIN_URL = "/admin/login/"

# -----------------------------------------------------------------------------
# Applications
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "codes",
    "customers",
    "properties",
    "quotations",
    "company",
    "email_templates",
    "routines",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
            ],
        },
    },
]

# Add your company context processor
TEMPLATES[0]["OPTIONS"]["context_processors"] += [
    "company.context_processors.client_profile",
]

WSGI_APPLICATION = "phoenix_fire.wsgi.application"

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
# Render provides DATABASE_URL. Locally falls back to SQLite.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# -----------------------------------------------------------------------------
# Static files
# -----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Optional: WhiteNoise compressed storage
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# -----------------------------------------------------------------------------
# Media (uploads)
# -----------------------------------------------------------------------------
MEDIA_URL = "/media/"

from pathlib import Path
import os

MEDIA_URL = "/media/"

# If /var/data exists (Render disk mount), always use it.
# Works even if you didn't set RENDER=true.
if Path("/var/data").exists():
    MEDIA_ROOT = Path("/var/data/media")
else:
    MEDIA_ROOT = BASE_DIR / "media"


# -----------------------------------------------------------------------------
# Security tweaks for production
# -----------------------------------------------------------------------------
if IS_RENDER and not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# -----------------------------------------------------------------------------
# Email / Microsoft Graph
# -----------------------------------------------------------------------------
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "joe@phoenixfire.com.au")

MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")

MS_AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"

# MUST match Azure Redirect URI exactly
MS_REDIRECT_URI = os.environ.get(
    "MS_REDIRECT_URI",
    "http://localhost:8000/quotations/microsoft/callback/",
)

MS_GRAPH_SCOPES = ["User.Read", "Mail.Send"]
