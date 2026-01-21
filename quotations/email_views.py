# quotations/email_views.py
from __future__ import annotations

import base64
from io import BytesIO
from decimal import Decimal

import msal
import requests

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import get_template
from django.template import Context, Template
from django.utils.html import strip_tags

from xhtml2pdf import pisa

from company.models import ClientProfile
from .models import Quotation
from email_templates.models import EmailTemplate


# =========================
# PDF helpers (same logic as your views.py)
# =========================
def _pdf_link_callback(uri, rel):
    import os

    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        return path

    if uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
        return path

    if os.path.isfile(uri):
        return uri

    return uri


def _build_quote_pdf_bytes(quote: Quotation) -> bytes:
    client = ClientProfile.get_solo()

    subtotal = Decimal("0.00")
    for li in quote.items.all():
        subtotal += Decimal(li.line_total)

    gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    total = (subtotal + gst).quantize(Decimal("0.01"))

    template = get_template("quotations/quotation_print_pdf.html")
    html = template.render(
        {
            "item": quote,
            "client": client,
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "gst": gst,
            "total": total,
        }
    )

    result = BytesIO()
    pdf = pisa.CreatePDF(
        src=BytesIO(html.encode("utf-8")),
        dest=result,
        link_callback=_pdf_link_callback,
        encoding="utf-8",
    )

    if pdf.err:
        raise RuntimeError(
            "PDF generation error. Check quotation_print_pdf.html for unsupported HTML/CSS."
        )

    return result.getvalue()


# =========================
# Template rendering helpers
# =========================
def _render_template_text(text: str, ctx: dict) -> str:
    """
    Render Django-template-style placeholders stored in DB fields.
    Example: "Quote {{ quotation.number }}" -> "Quote Q-00001"
    """
    if not text:
        return ""
    try:
        return Template(text).render(Context(ctx)).strip()
    except Exception:
        return text.strip()


def _parse_emails(csv_text: str) -> list[str]:
    if not csv_text:
        return []
    parts = [p.strip() for p in csv_text.split(",")]
    return [p for p in parts if p]


def _email_list_to_graph_recipients(emails: list[str]) -> list[dict]:
    return [{"emailAddress": {"address": e}} for e in emails]


def _get_active_email_template(template_type: str) -> EmailTemplate | None:
    """
    Prefer the most recently updated active template of that type.
    """
    return (
        EmailTemplate.objects.filter(is_active=True, template_type=template_type)
        .order_by("-updated_at", "-id")
        .first()
    )


# =========================
# MSAL token cache helpers (Option A)
# =========================
SESSION_CACHE_KEY = "msal_token_cache"
SESSION_ACCOUNT_ID_KEY = "msal_home_account_id"
SESSION_FLOW_KEY = "msal_auth_flow"
SESSION_QUOTE_PK_KEY = "ms_quote_pk"


def _load_cache(request) -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    data = request.session.get(SESSION_CACHE_KEY)
    if data:
        cache.deserialize(data)
    return cache


def _save_cache(request, cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        request.session[SESSION_CACHE_KEY] = cache.serialize()


def _msal_app(cache: msal.SerializableTokenCache) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=settings.MS_CLIENT_ID,
        client_credential=settings.MS_CLIENT_SECRET,
        authority=settings.MS_AUTHORITY,
        token_cache=cache,
    )


def _get_account(app: msal.ConfidentialClientApplication, request):
    accounts = app.get_accounts()
    if not accounts:
        return None

    preferred_home_id = request.session.get(SESSION_ACCOUNT_ID_KEY)
    if preferred_home_id:
        for a in accounts:
            if a.get("home_account_id") == preferred_home_id:
                return a

    return accounts[0]


def _get_access_token_silent(request) -> str | None:
    cache = _load_cache(request)
    app = _msal_app(cache)
    account = _get_account(app, request)

    if not account:
        return None

    result = app.acquire_token_silent(
        scopes=settings.MS_GRAPH_SCOPES,
        account=account,
    )

    _save_cache(request, cache)

    if result and "access_token" in result:
        return result["access_token"]

    return None


# =========================
# Microsoft login + callback
# =========================
def microsoft_login(request, pk: int):
    request.session[SESSION_QUOTE_PK_KEY] = pk

    cache = _load_cache(request)
    app = _msal_app(cache)

    flow = app.initiate_auth_code_flow(
        scopes=settings.MS_GRAPH_SCOPES,
        redirect_uri=settings.MS_REDIRECT_URI,
    )

    request.session[SESSION_FLOW_KEY] = flow
    _save_cache(request, cache)

    return redirect(flow["auth_uri"])


def microsoft_callback(request):
    flow = request.session.get(SESSION_FLOW_KEY)
    if not flow:
        messages.error(request, "Microsoft login session expired. Please try again.")
        return redirect("quotations:list")

    cache = _load_cache(request)
    app = _msal_app(cache)

    try:
        result = app.acquire_token_by_auth_code_flow(flow, request.GET)
    except Exception as e:
        messages.error(request, f"Microsoft token exchange failed: {e}")
        return redirect("quotations:list")

    request.session.pop(SESSION_FLOW_KEY, None)

    if not result or "access_token" not in result:
        err = (result or {}).get("error") or ""
        desc = (result or {}).get("error_description") or ""
        messages.error(request, f"Microsoft login failed. {err} {desc}".strip())
        return redirect("quotations:list")

    _save_cache(request, cache)

    accounts = app.get_accounts()
    if accounts:
        request.session[SESSION_ACCOUNT_ID_KEY] = accounts[0].get("home_account_id", "")

    pk = request.session.get(SESSION_QUOTE_PK_KEY)
    if pk:
        messages.success(request, "Microsoft login successful. You can now send emails.")
        return redirect("quotations:detail", pk=pk)

    messages.success(request, "Microsoft login successful.")
    return redirect("quotations:list")


# =========================
# Send quotation email via Graph (uses saved EmailTemplate)
# =========================
def quotation_send_email(request, pk: int):
    quote = get_object_or_404(
        Quotation.objects.select_related("site", "site__customer").prefetch_related(
            "items", "items__efsm_code"
        ),
        pk=pk,
    )

    token = _get_access_token_silent(request)
    if not token:
        messages.info(request, "Please sign in to Microsoft to send email.")
        return redirect("quotations:microsoft_login", pk=pk)

    tmpl = _get_active_email_template("quotation")
    if not tmpl:
        messages.error(
            request,
            "No ACTIVE email template found for Template Type = Quotation.",
        )
        return redirect("quotations:detail", pk=pk)

    # ✅ Context for placeholders (THIS is what makes {{ company.trading_name }} work)
    ctx = {
        "quotation": quote,
        "property": quote.site,
        "customer": getattr(quote.site, "customer", None),
        "company": ClientProfile.get_solo(),
    }

    subject = _render_template_text(tmpl.subject, ctx) or f"Service Quotation - {quote.number}"

    body_rendered = _render_template_text(tmpl.body, ctx)
    body_text = strip_tags(body_rendered) if body_rendered else "Please find attached your Service Quotation PDF."

    to_raw = _render_template_text(tmpl.to or "", ctx)
    cc_raw = _render_template_text(tmpl.cc or "", ctx)

    to_list = _parse_emails(to_raw)
    cc_list = _parse_emails(cc_raw)

    if not to_list and quote.site and getattr(quote.site, "fire_coordinator_email", None):
        to_list = [quote.site.fire_coordinator_email]

    if not to_list:
        messages.error(
            request,
            "No recipient email found. Template 'To' is empty and Fire Coordinator Email is blank.",
        )
        return redirect("quotations:detail", pk=pk)

    try:
        pdf_bytes = _build_quote_pdf_bytes(quote)
    except Exception as e:
        messages.error(request, f"Could not generate PDF: {e}")
        return redirect("quotations:detail", pk=pk)

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": _email_list_to_graph_recipients(to_list),
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": f"Quotation-{quote.number}.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": pdf_b64,
                }
            ],
        },
        "saveToSentItems": True,
    }

    if cc_list:
        payload["message"]["ccRecipients"] = _email_list_to_graph_recipients(cc_list)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = requests.post(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if resp.status_code in (200, 202):
        if quote.status == "draft":
            quote.status = "sent"
            quote.save(update_fields=["status"])

        if hasattr(quote, "log"):
            quote.log(
                "sent",
                request.user,
                f"Email sent using template '{tmpl.name}'. To={', '.join(to_list)} CC={', '.join(cc_list) if cc_list else '—'}",
            )

        messages.success(request, f"Email sent to {', '.join(to_list)}.")
        return redirect("quotations:detail", pk=pk)

    if resp.status_code in (401, 403):
        request.session.pop(SESSION_CACHE_KEY, None)
        request.session.pop(SESSION_ACCOUNT_ID_KEY, None)
        messages.error(
            request,
            "Microsoft session expired or not permitted. Please sign in again.",
        )
        return redirect("quotations:microsoft_login", pk=pk)

    messages.error(request, f"Microsoft Graph error ({resp.status_code}): {resp.text}")
    return redirect("quotations:detail", pk=pk)
