import base64
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from .models import QBOConnection


AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def qbo_api_base() -> str:
    # Intuit uses different base hosts for sandbox vs production
    if settings.QBO_ENVIRONMENT == "production":
        return "https://quickbooks.api.intuit.com"
    return "https://sandbox-quickbooks.api.intuit.com"


def build_authorize_url(request) -> str:
    state = secrets.token_urlsafe(24)
    request.session["qbo_oauth_state"] = state

    params = {
        "client_id": settings.QBO_CLIENT_ID,
        "response_type": "code",
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": settings.QBO_REDIRECT_URI,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _basic_auth_header() -> str:
    raw = f"{settings.QBO_CLIENT_ID}:{settings.QBO_CLIENT_SECRET}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("utf-8")


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    headers = {
        "Authorization": _basic_auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def refresh_tokens(refresh_token: str) -> dict:
    headers = {
        "Authorization": _basic_auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
    r.raise_for_status()
    return r.json()


def get_connection() -> QBOConnection:
    conn = QBOConnection.objects.order_by("-updated_at").first()
    if not conn:
        raise RuntimeError("No QBOConnection found. Visit /qbo/connect/ first.")
    return conn


def ensure_fresh_access_token(conn: QBOConnection) -> QBOConnection:
    # Refresh if expiring in the next 60 seconds
    if conn.expires_at and conn.expires_at > (timezone.now() + timedelta(seconds=60)):
        return conn

    token_data = refresh_tokens(conn.refresh_token)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", conn.refresh_token)
    expires_in = int(token_data.get("expires_in", 3600))

    conn.access_token = access_token
    conn.refresh_token = refresh_token
    conn.expires_at = timezone.now() + timedelta(seconds=expires_in)
    conn.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])
    return conn


def qbo_get(conn: QBOConnection, path: str, params: dict | None = None) -> dict:
    conn = ensure_fresh_access_token(conn)

    url = f"{qbo_api_base()}{path}"
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Accept": "application/json",
    }

    r = requests.get(url, headers=headers, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()
