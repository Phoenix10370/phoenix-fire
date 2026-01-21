import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only")
DEBUG = True

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,192.168.50.91"
).split(",")



LOGIN_URL = "/admin/login/"



STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

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

WSGI_APPLICATION = "phoenix_fire.wsgi.application"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# LOCAL = SQLite (easy)
# ONLINE (Render) = Postgres (when DB_HOST exists)
if os.environ.get("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME"),
            "USER": os.environ.get("DB_USER"),
            "PASSWORD": os.environ.get("DB_PASSWORD"),
            "HOST": os.environ.get("DB_HOST"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
 import dj_database_url

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=True,
    )
}


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

TEMPLATES[0]["OPTIONS"]["context_processors"] += [
    "company.context_processors.client_profile",
]

# =========================
# Email sending choice
# =========================
# If you're using Microsoft Graph (Option C), you DO NOT need SMTP here.
# Keep DEFAULT_FROM_EMAIL only for display purposes inside templates/logs.

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "joe@phoenixfire.com.au")

# =========================
# Microsoft Graph (Delegated) - Option C
# =========================
# Microsoft Graph (Delegated login)

# =========================
# Microsoft Graph (Delegated) - Option C
# =========================
# IMPORTANT:
# - MS_TENANT_ID = Directory (tenant) ID
# - MS_CLIENT_ID = Application (client) ID

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "joe@phoenixfire.com.au")

MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "377b68ca-5483-4948-82be-8fcacc7536b9")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "bd12e908-173c-4991-a3da-d8ff5334ae82")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")

MS_AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"

# MUST match Azure Redirect URI exactly
MS_REDIRECT_URI = os.environ.get(
    "MS_REDIRECT_URI",
    "http://localhost:8000/quotations/microsoft/callback/",
)

MS_GRAPH_SCOPES = ["User.Read", "Mail.Send"]


