# qbo/qbo_sync/query_api.py
from __future__ import annotations

from typing import Any, Dict
import requests
from django.apps import apps
from django.utils import timezone

from qbo.services import refresh_tokens


def _get_connection():
    Conn = apps.get_model("qbo", "QBOConnection")
    conn = Conn.objects.first()
    if not conn:
        raise RuntimeError("No QBOConnection found. Connect first at /qbo/connect/")
    return conn


def _base_url(conn) -> str:
    # Adjust this if your model uses a different field name than "environment".
    # Common values: "sandbox" or "production"
    env = (getattr(conn, "environment", "") or "sandbox").lower()

    if env.startswith("prod"):
        host = "https://quickbooks.api.intuit.com"
    else:
        host = "https://sandbox-quickbooks.api.intuit.com"

    if not getattr(conn, "realm_id", None):
        raise RuntimeError("QBOConnection.realm_id is empty. Reconnect and store realm_id.")
    return f"{host}/v3/company/{conn.realm_id}"


def _ensure_fresh_access_token(conn):
    """
    Very simple logic:
    - if expires_at exists and is in the past (or almost), refresh
    - save new tokens back to DB
    """
    expires_at = getattr(conn, "expires_at", None)
    if expires_at:
        # refresh 60 seconds early to avoid edge timing
        if expires_at <= timezone.now() + timezone.timedelta(seconds=60):
            if not conn.refresh_token:
                raise RuntimeError("No refresh_token stored. Reconnect via /qbo/connect/")
            data = refresh_tokens(conn.refresh_token)
            conn.access_token = data["access_token"]
            conn.refresh_token = data.get("refresh_token", conn.refresh_token)
            if data.get("expires_at"):
                conn.expires_at = data["expires_at"]
            conn.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])
    else:
        # If you don't store expires_at, you can still rely on middleware/other code.
        # But for this simple command, we won't auto-refresh without expires_at.
        pass


def qbo_query(query: str, minorversion: int = 75) -> Dict[str, Any]:
    """
    Calls:
      GET /query?query=...
    Returns JSON dict.
    """
    conn = _get_connection()
    _ensure_fresh_access_token(conn)

    url = f"{_base_url(conn)}/query"
    headers = {
        "Authorization": f"Bearer {conn.access_token}",
        "Accept": "application/json",
    }
    params = {"query": query, "minorversion": str(minorversion)}

    resp = requests.get(url, headers=headers, params=params, timeout=30)

    # If token expired and expires_at wasn't set/accurate, you'll see 401 here.
    # We'll raise a clean error with the response text.
    if resp.status_code >= 400:
        raise RuntimeError(f"QBO Query failed: {resp.status_code} {resp.text}")

    return resp.json()

def qbo_query_all(base_query: str, page_size: int = 100, minorversion: int = 75):
    """
    Runs a QBO SQL query in pages using STARTPOSITION / MAXRESULTS.
    Returns: (all_items, last_raw_response)
    """
    all_rows = []
    start = 1
    last_data = None

    while True:
        paged_query = f"{base_query} STARTPOSITION {start} MAXRESULTS {page_size}"
        data = qbo_query(paged_query, minorversion=minorversion)
        last_data = data

        qr = data.get("QueryResponse", {})
        # QBO returns the list under the entity name key, e.g. "Customer", "Item"
        # We detect it by excluding known metadata keys.
        entity_keys = [k for k in qr.keys() if k not in ("startPosition", "maxResults", "totalCount")]
        rows = []
        if entity_keys:
            rows = qr.get(entity_keys[0], []) or []

        all_rows.extend(rows)

        # Stop when we got less than a full page
        if len(rows) < page_size:
            break

        start += page_size

    return all_rows, last_data
