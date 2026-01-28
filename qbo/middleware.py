import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .models import QBOConnection

logger = logging.getLogger(__name__)


class QBOTokenRefreshMiddleware:
    """
    Auto-refresh QBO access token when it is near expiry.

    IMPORTANT:
    - Must NOT block /qbo/connect/, /qbo/callback/, /qbo/debug/
    - Must NOT raise if QBO isn't connected yet (first-time setup)
    """

    # Paths we must never interfere with
    SKIP_PREFIXES = (
        "/qbo/connect/",
        "/qbo/callback/",
        "/qbo/debug/",
        "/admin/",     # optional safety
        "/static/",    # optional safety
        "/media/",     # optional safety
    )

    # Only refresh on QBO endpoints (keeps it out of the rest of the app)
    QBO_PREFIX = "/qbo/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""

        # If it's not a QBO URL, do nothing
        if not path.startswith(self.QBO_PREFIX):
            return self.get_response(request)

        # If it's a skip URL, do nothing
        if any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)

        # Attempt refresh, but NEVER block request if not connected
        try:
            self._refresh_if_needed()
        except Exception as exc:
            # Do not break the entire site because QBO is down / not connected
            logger.warning("QBO token refresh skipped/failed: %s", exc)

        return self.get_response(request)

    def _refresh_if_needed(self) -> None:
        conn = QBOConnection.objects.order_by("-updated_at").first()
        if not conn:
            # Not connected yet (first time). Do nothing.
            return

        # If no expiry set or still valid for >60 seconds, no refresh needed
        if conn.expires_at and conn.expires_at > timezone.now() + timedelta(seconds=60):
            return

        client_id = (getattr(settings, "QBO_CLIENT_ID", "") or "").strip()
        client_secret = (getattr(settings, "QBO_CLIENT_SECRET", "") or "").strip()
        if not client_id or not client_secret:
            raise RuntimeError("Missing QBO_CLIENT_ID / QBO_CLIENT_SECRET in settings")

        if not conn.refresh_token:
            # Cannot refresh without refresh_token; user must reconnect
            raise RuntimeError("No refresh_token stored. Reconnect via /qbo/connect/")

        token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

        # Basic auth (requests will do correct Basic header)
        resp = requests.post(
            token_url,
            auth=(client_id, client_secret),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": conn.refresh_token,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")

        data = resp.json()

        conn.access_token = data["access_token"]
        conn.refresh_token = data.get("refresh_token") or conn.refresh_token
        conn.expires_at = timezone.now() + timedelta(seconds=int(data.get("expires_in", 3600)))
        conn.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])
