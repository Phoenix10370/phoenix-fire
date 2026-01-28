from __future__ import annotations

from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from qbo.models import QBOConnection


class QBOClientError(RuntimeError):
    pass


class QBOClient:
    """
    QBO client for sync jobs.
    - Reads latest QBOConnection from DB
    - Refreshes token when needed (uses requests HTTP Basic Auth, most reliable)
    - Provides query/get/post helpers
    """

    def __init__(self):
        self.conn = QBOConnection.objects.order_by("-updated_at").first()
        if not self.conn:
            raise QBOClientError("No QBOConnection found. Visit /qbo/connect/ first.")

        self.client_id = (getattr(settings, "QBO_CLIENT_ID", "") or "").strip()
        self.client_secret = (getattr(settings, "QBO_CLIENT_SECRET", "") or "").strip()
        self.env = (getattr(settings, "QBO_ENVIRONMENT", "sandbox") or "sandbox").strip().lower()

        if not self.client_id or not self.client_secret:
            raise QBOClientError("QBO_CLIENT_ID / QBO_CLIENT_SECRET missing or empty (env not loaded).")

    # -------------------------------------------------------------------------
    # URLs
    # -------------------------------------------------------------------------
    def _api_base_url(self) -> str:
        # Only affects API base URL (not the token URL)
        if self.env == "production":
            return "https://quickbooks.api.intuit.com"
        return "https://sandbox-quickbooks.api.intuit.com"

    def _token_url(self) -> str:
        return "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    # -------------------------------------------------------------------------
    # Token refresh
    # -------------------------------------------------------------------------
    def refresh_if_needed(self) -> None:
        # Refresh if expires within next 60 seconds, or expires_at missing
        if self.conn.expires_at and self.conn.expires_at > timezone.now() + timedelta(seconds=60):
            return

        if not self.conn.refresh_token:
            raise QBOClientError("No refresh_token stored. Reconnect via /qbo/connect/.")

        resp = requests.post(
            self._token_url(),
            auth=(self.client_id, self.client_secret),  # ✅ most reliable way
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.conn.refresh_token,
            },
            timeout=30,
        )

        if not resp.ok:
            # This is where you'll see: {"error":"invalid_client"} etc.
            raise QBOClientError(f"Token refresh failed ({resp.status_code}): {resp.text}")

        data = resp.json()

        self.conn.access_token = data["access_token"]
        # Intuit may rotate refresh tokens; keep old if not provided
        self.conn.refresh_token = data.get("refresh_token") or self.conn.refresh_token
        self.conn.expires_at = timezone.now() + timedelta(seconds=int(data.get("expires_in", 3600)))
        self.conn.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])

    # -------------------------------------------------------------------------
    # HTTP helpers
    # -------------------------------------------------------------------------
    def _bearer_headers(self, content_type: str) -> dict:
        return {
            "Authorization": f"Bearer {self.conn.access_token}",
            "Accept": "application/json",
            "Content-Type": content_type,
        }

    def query(self, sql: str, minorversion: str = "75") -> dict:
        """
        QBO Query endpoint: POST + application/text + UTF-8 bytes body.
        """
        self.refresh_if_needed()

        url = f"{self._api_base_url()}/v3/company/{self.conn.realm_id}/query"
        resp = requests.post(
            url,
            headers=self._bearer_headers("application/text"),
            params={"minorversion": minorversion},
            data=sql.encode("utf-8"),
            timeout=30,
        )

        if not resp.ok:
            raise QBOClientError(f"QBO QUERY FAILED ({resp.status_code}): {resp.text}")

        return resp.json()

    def get(self, endpoint: str, params: dict | None = None, minorversion: str = "75") -> dict:
        self.refresh_if_needed()

        url = f"{self._api_base_url()}/v3/company/{self.conn.realm_id}/{endpoint.lstrip('/')}"
        merged = dict(params or {})
        merged["minorversion"] = minorversion

        resp = requests.get(
            url,
            headers=self._bearer_headers("application/json"),
            params=merged,
            timeout=30,
        )

        if not resp.ok:
            raise QBOClientError(f"QBO GET FAILED ({resp.status_code}): {resp.text}")

        return resp.json()

    def post(self, endpoint: str, payload: dict, params: dict | None = None, minorversion: str = "75") -> dict:
        self.refresh_if_needed()

        url = f"{self._api_base_url()}/v3/company/{self.conn.realm_id}/{endpoint.lstrip('/')}"
        merged = dict(params or {})
        merged["minorversion"] = minorversion

        resp = requests.post(
            url,
            headers=self._bearer_headers("application/json"),
            params=merged,
            json=payload,
            timeout=30,
        )

        if not resp.ok:
            raise QBOClientError(f"QBO POST FAILED ({resp.status_code}): {resp.text}")

        return resp.json()
