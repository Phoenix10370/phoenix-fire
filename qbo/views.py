import base64
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_GET

from customers.models import Customer
from .models import QBOConnection


# ----------------------------
# Helpers
# ----------------------------
def _qbo_base_url() -> str:
    env = (getattr(settings, "QBO_ENVIRONMENT", "sandbox") or "sandbox").lower().strip()
    return "https://sandbox-quickbooks.api.intuit.com" if env == "sandbox" else "https://quickbooks.api.intuit.com"


def _qbo_auth_url() -> str:
    # Intuit uses the same AppCenter URL for sandbox + prod
    return "https://appcenter.intuit.com/app/connect/oauth2"


def _qbo_token_url() -> str:
    return "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def _get_connection() -> QBOConnection:
    conn = QBOConnection.objects.order_by("-updated_at").first()
    if not conn:
        raise RuntimeError("QBO is not connected. Visit /qbo/connect/ first.")
    return conn


def _auth_header_basic(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"Basic {b64}"


def _qbo_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _refresh_if_needed(conn: QBOConnection) -> QBOConnection:
    # Refresh if token expires within next 60 seconds
    if conn.expires_at and conn.expires_at > timezone.now() + timedelta(seconds=60):
        return conn

    client_id = (getattr(settings, "QBO_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "QBO_CLIENT_SECRET", "") or "").strip()

    if not client_id or not client_secret:
        raise RuntimeError("Missing QBO_CLIENT_ID / QBO_CLIENT_SECRET in settings (env not loaded).")

    if not conn.refresh_token:
        raise RuntimeError("No refresh_token stored. Reconnect via /qbo/connect/")

    resp = requests.post(
        _qbo_token_url(),
        headers={
            "Authorization": _auth_header_basic(client_id, client_secret),
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
        # make the error readable
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    conn.access_token = data["access_token"]
    conn.refresh_token = data.get("refresh_token") or conn.refresh_token
    conn.expires_at = timezone.now() + timedelta(seconds=int(data.get("expires_in", 3600)))
    conn.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])
    return conn


def _qbo_get(conn: QBOConnection, url: str, params: dict | None = None) -> dict:
    conn = _refresh_if_needed(conn)
    r = requests.get(url, headers=_qbo_headers(conn.access_token), params=params or {}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"QBO GET failed ({r.status_code}): {r.text}")
    return r.json()


def _qbo_post(conn: QBOConnection, url: str, payload: dict, params: dict | None = None) -> dict:
    conn = _refresh_if_needed(conn)
    r = requests.post(url, headers=_qbo_headers(conn.access_token), params=params or {}, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"QBO POST failed ({r.status_code}): {r.text}")
    return r.json()


def _mask(s: str, keep: int = 6) -> str:
    s = s or ""
    if len(s) <= keep * 2:
        return "*" * len(s)
    return f"{s[:keep]}...{s[-keep:]}"


# ----------------------------
# DEBUG: confirm what Django is using (browser-visible)
# ----------------------------
@require_GET
def qbo_debug(request):
    client_id = (getattr(settings, "QBO_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "QBO_CLIENT_SECRET", "") or "").strip()
    redirect_uri = (getattr(settings, "QBO_REDIRECT_URI", "") or "").strip()
    env = (getattr(settings, "QBO_ENVIRONMENT", "sandbox") or "sandbox").strip()

    state = "DEBUGSTATE"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    auth_url = f"{_qbo_auth_url()}?{urlencode(params)}"

    return HttpResponse(
        "QBO DEBUG\n"
        f"ENV: {env}\n"
        f"CLIENT_ID: {client_id}\n"
        f"CLIENT_SECRET: {_mask(client_secret)} (len={len(client_secret)})\n"
        f"REDIRECT_URI: {redirect_uri}\n"
        f"\nAUTH_URL (what /qbo/connect/ will redirect to):\n{auth_url}\n",
        content_type="text/plain",
    )


# ----------------------------
# OAuth
# ----------------------------
@require_GET
def qbo_connect(request):
    client_id = (getattr(settings, "QBO_CLIENT_ID", "") or "").strip()
    redirect_uri = (getattr(settings, "QBO_REDIRECT_URI", "") or "").strip()

    if not client_id:
        return HttpResponse("QBO_CLIENT_ID is empty. Fix .env and restart Django.", status=500)
    if not redirect_uri:
        return HttpResponse("QBO_REDIRECT_URI is empty. Fix settings and restart Django.", status=500)

    state = secrets.token_urlsafe(24)
    request.session["qbo_oauth_state"] = state

    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    auth_url = f"{_qbo_auth_url()}?{urlencode(params)}"

    # server-side log
    print("QBO CONNECT redirecting to:", auth_url)

    return redirect(auth_url)


@require_GET
def qbo_callback(request):
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    state = request.GET.get("state")
    expected_state = request.session.get("qbo_oauth_state")

    if expected_state and state != expected_state:
        return HttpResponse("Invalid OAuth state", status=400)

    if not code or not realm_id:
        return HttpResponse("Missing code or realmId", status=400)

    client_id = (getattr(settings, "QBO_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "QBO_CLIENT_SECRET", "") or "").strip()
    redirect_uri = (getattr(settings, "QBO_REDIRECT_URI", "") or "").strip()

    if not client_id or not client_secret:
        return HttpResponse("Missing QBO_CLIENT_ID / QBO_CLIENT_SECRET in Django settings.", status=500)

    resp = requests.post(
        _qbo_token_url(),
        headers={
            "Authorization": _auth_header_basic(client_id, client_secret),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        # show Intuit error body
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")

    data = resp.json()

    conn, _ = QBOConnection.objects.get_or_create(realm_id=str(realm_id))
    conn.access_token = data["access_token"]
    conn.refresh_token = data.get("refresh_token") or conn.refresh_token
    conn.expires_at = timezone.now() + timedelta(seconds=int(data.get("expires_in", 3600)))
    conn.save()

    return HttpResponse(
        "✅ Connected to QuickBooks\n\n"
        f"realmId: {realm_id}\n\n"
        "Next endpoints:\n"
        "- /qbo/companyinfo/\n"
        "- /qbo/customers/\n"
        "- /qbo/items/\n"
        "- /qbo/accounts/\n"
        "- /qbo/invoice/create-test/\n",
        content_type="text/plain",
    )


# ----------------------------
# QBO endpoints
# ----------------------------
@require_GET
def qbo_companyinfo(request):
    conn = _get_connection()
    base = _qbo_base_url()
    url = f"{base}/v3/company/{conn.realm_id}/companyinfo/{conn.realm_id}"
    data = _qbo_get(conn, url, params={"minorversion": "75"})
    return JsonResponse(data)


@require_GET
def qbo_customers(request):
    conn = _get_connection()
    base = _qbo_base_url()
    # IMPORTANT: BillAddr is not selectable in all QBO schemas; keep this minimal/reliable.
    query = "select Id, DisplayName, Active, PrimaryEmailAddr, PrimaryPhone from Customer maxresults 100"
    url = f"{base}/v3/company/{conn.realm_id}/query"
    data = _qbo_get(conn, url, params={"query": query, "minorversion": "75"})
    return JsonResponse(data)


@require_GET
def qbo_sync_customers(request):
    """
    Pull customers from QBO and upsert into local Customer using accounting_id = QBO Id.
    """
    conn = _get_connection()
    base = _qbo_base_url()
    query = "select Id, DisplayName, Active, PrimaryEmailAddr, PrimaryPhone from Customer maxresults 1000"
    url = f"{base}/v3/company/{conn.realm_id}/query"
    data = _qbo_get(conn, url, params={"query": query, "minorversion": "75"})
    rows = (data.get("QueryResponse") or {}).get("Customer") or []

    created = updated = skipped_inactive = 0

    for c in rows:
        if c.get("Active") is False:
            skipped_inactive += 1
            continue

        qbo_id = str(c.get("Id") or "").strip()
        name = (c.get("DisplayName") or "").strip()
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
        if not obj:
            obj = Customer(accounting_id=qbo_id, customer_name=name or f"QBO Customer {qbo_id}")
            created += 1
        else:
            updated += 1

        if name:
            obj.customer_name = name
        obj.is_active = True

        # these fields exist in your earlier sync script; keep them guarded
        if email and hasattr(obj, "billing_email"):
            obj.billing_email = email
        if phone and hasattr(obj, "customer_main_phone"):
            obj.customer_main_phone = phone

        obj.save()

    return HttpResponse(
        "QBO customer sync complete\n"
        f"realm_id: {conn.realm_id}\n"
        f"fetched: {len(rows)}\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        f"skipped_inactive: {skipped_inactive}\n",
        content_type="text/plain",
    )


@require_GET
def qbo_items(request):
    conn = _get_connection()
    base = _qbo_base_url()
    query = "select Id, Name, Type, Active from Item maxresults 200"
    url = f"{base}/v3/company/{conn.realm_id}/query"
    data = _qbo_get(conn, url, params={"query": query, "minorversion": "75"})
    return JsonResponse(data)


@require_GET
def qbo_accounts(request):
    conn = _get_connection()
    base = _qbo_base_url()
    query = "select Id, Name, AccountType, AccountSubType, Active from Account maxresults 200"
    url = f"{base}/v3/company/{conn.realm_id}/query"
    data = _qbo_get(conn, url, params={"query": query, "minorversion": "75"})
    return JsonResponse(data)


@require_GET
def qbo_create_test_invoice(request):
    conn = _get_connection()
    base = _qbo_base_url()

    cust = Customer.objects.exclude(accounting_id__isnull=True).exclude(accounting_id="").order_by("customer_name").first()
    if not cust:
        return HttpResponse("No local Customer with accounting_id found. Sync customers first.", status=400)

    items_query = "select Id, Name, Type, Active from Item where Active = true maxresults 200"
    items_url = f"{base}/v3/company/{conn.realm_id}/query"
    items_data = _qbo_get(conn, items_url, params={"query": items_query, "minorversion": "75"})
    items = (items_data.get("QueryResponse") or {}).get("Item") or []

    service_item = None
    for it in items:
        if it.get("Active") is True and (it.get("Type") or "").lower() in {"service", "noninventory", "othercharge"}:
            service_item = it
            break

    if not service_item:
        return HttpResponse("No suitable active Item found in QBO. Create a Service item first.", status=400)

    payload = {
        "CustomerRef": {"value": str(cust.accounting_id)},
        "Line": [
            {
                "Amount": 10.00,
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": str(service_item["Id"]), "name": service_item.get("Name", "")},
                    "Qty": 1,
                    "UnitPrice": 10.00,
                },
                "Description": "Test invoice from PhoenixFire",
            }
        ],
    }

    create_url = f"{base}/v3/company/{conn.realm_id}/invoice"
    created = _qbo_post(conn, create_url, payload, params={"minorversion": "75"})
    return JsonResponse(created)
