from __future__ import annotations

from datetime import datetime, timezone, timedelta

import requests
from django.core.management.base import BaseCommand
from django.conf import settings

from qbo.models import QBOConnection
from customers.models import Customer


def _api_base_url() -> str:
    env = (getattr(settings, "QBO_ENVIRONMENT", "sandbox") or "sandbox").lower().strip()
    return "https://quickbooks.api.intuit.com" if env == "production" else "https://sandbox-quickbooks.api.intuit.com"


def _token_url() -> str:
    return "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def _get_connection() -> QBOConnection:
    conn = QBOConnection.objects.order_by("-updated_at").first()
    if not conn:
        raise RuntimeError("No QBOConnection found. Connect first at /qbo/connect/")
    return conn


def _refresh_if_needed(conn: QBOConnection) -> QBOConnection:
    now = datetime.now(timezone.utc)
    if conn.expires_at and conn.expires_at > now + timedelta(seconds=60):
        return conn

    if not settings.QBO_CLIENT_ID or not settings.QBO_CLIENT_SECRET:
        raise RuntimeError("Missing QBO_CLIENT_ID / QBO_CLIENT_SECRET in settings")

    if not conn.refresh_token:
        raise RuntimeError("No refresh_token stored. Reconnect at /qbo/connect/")

    data = {"grant_type": "refresh_token", "refresh_token": conn.refresh_token}

    r = requests.post(
        _token_url(),
        data=data,
        auth=(settings.QBO_CLIENT_ID, settings.QBO_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    conn.access_token = payload.get("access_token", "")
    conn.refresh_token = payload.get("refresh_token", conn.refresh_token)

    expires_in = int(payload.get("expires_in", 3600))
    conn.expires_at = now + timedelta(seconds=expires_in)

    conn.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])
    return conn


def _qbo_error_details(resp: requests.Response) -> str:
    try:
        return resp.text
    except Exception:
        return "<no response body>"


def sync_customers() -> dict:
    conn = _get_connection()
    conn = _refresh_if_needed(conn)

    # ✅ Minimal query that QBO reliably accepts
    # (QBO query language does NOT allow every nested field like BillAddr in a SELECT)
    query = "select Id, DisplayName, Active, PrimaryEmailAddr, PrimaryPhone from Customer maxresults 1000"

    url = f"{_api_base_url()}/v3/company/{conn.realm_id}/query"
    headers = {"Authorization": f"Bearer {conn.access_token}", "Accept": "application/json"}

    r = requests.get(url, headers=headers, params={"query": query, "minorversion": "75"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"QBO query failed ({r.status_code}): {_qbo_error_details(r)}")

    data = r.json()
    rows = (data.get("QueryResponse") or {}).get("Customer") or []

    created = 0
    updated = 0
    skipped_inactive = 0

    for c in rows:
        active = bool(c.get("Active", True))
        if not active:
            skipped_inactive += 1
            continue

        qbo_id = str(c.get("Id") or "").strip()
        name = (c.get("DisplayName") or "").strip() or f"QBO Customer {qbo_id}"
        if not qbo_id:
            continue

        email = ""
        pe = c.get("PrimaryEmailAddr")
        if isinstance(pe, dict):
            email = (pe.get("Address") or "").strip()

        phone = ""
        pp = c.get("PrimaryPhone")
        if isinstance(pp, dict):
            phone = (pp.get("FreeFormNumber") or "").strip()

        obj = Customer.objects.filter(accounting_id=qbo_id).first()
        if obj is None:
            obj = Customer(accounting_id=qbo_id, customer_name=name)
            created += 1
        else:
            updated += 1

        obj.customer_name = name
        obj.is_active = True

        if email:
            obj.billing_email = email
        if phone:
            obj.customer_main_phone = phone

        obj.save()

    return {
        "realm_id": conn.realm_id,
        "fetched": len(rows),
        "created": created,
        "updated": updated,
        "skipped_inactive": skipped_inactive,
    }


class Command(BaseCommand):
    help = "Sync active customers from QuickBooks Online into customers.Customer"

    def handle(self, *args, **options):
        result = sync_customers()
        self.stdout.write(self.style.SUCCESS("QBO customer sync complete"))
        for k, v in result.items():
            self.stdout.write(f"{k}: {v}")
