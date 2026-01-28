from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from customers.models import Customer
from qbo.models import QBOObjectMap
from qbo.qbo_sync.qbo_client import QBOClient, QBOClientError




@dataclass
class CustomerSyncResult:
    pulled_total: int = 0
    matched_local: int = 0
    linked_local_updated: int = 0
    pulled_unmatched: int = 0

    push_candidates: int = 0
    pushed_created: int = 0
    pushed_failed: int = 0


def _safe_getattr(obj, field_name: str):
    try:
        return getattr(obj, field_name)
    except Exception:
        return None

def _query_all_customers(client: QBOClient, *, max_results: int = 1000, page_size: int = 100):
    """
    Pull customers in pages using STARTPOSITION / MAXRESULTS.
    Returns a list of QBO Customer dicts.
    """
    all_rows = []
    start = 1

    # cap page_size to something reasonable
    page_size = max(1, min(int(page_size), 1000))
    max_results = max(1, int(max_results))

    while len(all_rows) < max_results:
        remaining = max_results - len(all_rows)
        this_page = min(page_size, remaining)

        sql = (
            "SELECT Id, DisplayName, Active, PrimaryEmailAddr, MetaData "
            f"FROM Customer STARTPOSITION {start} MAXRESULTS {this_page}"
        )
        data = client.query(sql)
        rows = (data.get("QueryResponse") or {}).get("Customer") or []

        all_rows.extend(rows)

        # stop if QBO returned fewer than requested (no more pages)
        if len(rows) < this_page:
            break

        start += this_page

    return all_rows


def pull_customers_from_qbo(*, dry_run: bool = False, max_results: int = 1000) -> CustomerSyncResult:
    """
    Pull QBO customers and link to local customers by:
      QBO Customer.DisplayName  -> local Customer.customer_name (case-insensitive)

    Updates:
      local Customer.accounting_id = QBO Customer.Id (if different)

    Also writes/updates QBOObjectMap rows for Customer entities.

    Does NOT create new local customers. (Safe for your existing DB.)
    """
    client = QBOClient()
    result = CustomerSyncResult()

    # ✅ pagination
    qbo_customers = _query_all_customers(client, max_results=max_results, page_size=100)
    result.pulled_total = len(qbo_customers)

    # Local lookup by customer_name (case-insensitive)
    local_map = {}
    for row in Customer.objects.all().values("id", "customer_name", "accounting_id"):
        name = (row.get("customer_name") or "").strip().lower()
        if name:
            local_map[name] = row

    now = timezone.now()

    for qc in qbo_customers:
        display = (qc.get("DisplayName") or "").strip()
        qbo_id = str(qc.get("Id") or "").strip()

        if not display or not qbo_id:
            continue

        # Pull SyncToken if present (useful later for updates)
        sync_token = ""
        md = qc.get("MetaData") or {}
        if isinstance(md, dict):
            sync_token = str(md.get("SyncToken") or "").strip()

        local_row = local_map.get(display.lower())

        if not local_row:
            result.pulled_unmatched += 1
            # Still store that we saw this QBO customer (unlinked)
            if not dry_run:
                QBOObjectMap.objects.update_or_create(
                    entity_type="Customer",
                    qbo_id=qbo_id,
                    defaults={
                        "local_app": "",
                        "local_model": "",
                        "local_pk": "",
                        "qbo_sync_token": sync_token,
                        "last_pulled_at": now,
                        "last_error": "",
                    },
                )
            continue

        result.matched_local += 1

        # Link local customer to QBO id (your existing logic)
        if (local_row.get("accounting_id") or "").strip() != qbo_id:
            if not dry_run:
                Customer.objects.filter(id=local_row["id"]).update(accounting_id=qbo_id)
            result.linked_local_updated += 1

        # ✅ write mapping (linked)
        if not dry_run:
            QBOObjectMap.objects.update_or_create(
                entity_type="Customer",
                qbo_id=qbo_id,
                defaults={
                    "local_app": "customers",
                    "local_model": "Customer",
                    "local_pk": str(local_row["id"]),
                    "qbo_sync_token": sync_token,
                    "last_pulled_at": now,
                    "last_error": "",
                },
            )

    return result


def push_customers_to_qbo(*, dry_run: bool = False, limit: int | None = None) -> CustomerSyncResult:
    """
    Push local customers that do NOT yet have accounting_id into QBO as new Customers.

    Uses:
      local Customer.customer_name -> QBO Customer.DisplayName

    Stores returned QBO Id into:
      local Customer.accounting_id

    Safe: does not modify other local fields.
    """
    client = QBOClient()
    result = CustomerSyncResult()

    QBOObjectMap.objects.update_or_create(
    entity_type="Customer",
    qbo_id=qbo_id,
    defaults={
        "local_app": "customers",
        "local_model": "Customer",
        "local_pk": str(cust.pk),
        "qbo_sync_token": "",
        "last_pushed_at": timezone.now(),
        "last_error": "",
    },
)

    qs = Customer.objects.filter(accounting_id__isnull=True) | Customer.objects.filter(accounting_id="")
    qs = qs.order_by("customer_name")
    if limit is not None:
        qs = qs[: int(limit)]

    to_push = list(qs)
    result.push_candidates = len(to_push)

    # Optional: if your Customer model has any of these, we’ll include it in QBO payload
    email_fields_to_try = ["email", "primary_email", "customer_email", "email_address", "billing_email"]

    for cust in to_push:
        display_name = (cust.customer_name or "").strip()
        if not display_name:
            continue

        payload = {"DisplayName": display_name}

        email_val = None
        for f in email_fields_to_try:
            v = _safe_getattr(cust, f)
            if isinstance(v, str) and v.strip():
                email_val = v.strip()
                break

        if email_val:
            payload["PrimaryEmailAddr"] = {"Address": email_val}

        if dry_run:
            continue

        try:
            created = client.post("customer", payload)
            qbo_customer = created.get("Customer") or {}
            qbo_id = str(qbo_customer.get("Id") or "").strip()

            if qbo_id:
                Customer.objects.filter(pk=cust.pk).update(accounting_id=qbo_id)
                result.pushed_created += 1
            else:
                result.pushed_failed += 1

        except QBOClientError:
            result.pushed_failed += 1

    return result


def sync_customers(*, pull: bool = True, push: bool = True, dry_run: bool = False, max_results: int = 1000) -> CustomerSyncResult:
    """
    Orchestrates:
      1) Pull (link existing QBO customers to local)
      2) Push (create QBO customers for local ones missing accounting_id)

    dry_run=True rolls back DB writes and skips QBO writes.
    """
    result = CustomerSyncResult()

    with transaction.atomic():
        if pull:
            r1 = pull_customers_from_qbo(dry_run=dry_run, max_results=max_results)
            result.pulled_total = r1.pulled_total
            result.matched_local = r1.matched_local
            result.linked_local_updated = r1.linked_local_updated
            result.pulled_unmatched = r1.pulled_unmatched

        if push:
            r2 = push_customers_to_qbo(dry_run=dry_run)
            result.push_candidates = r2.push_candidates
            result.pushed_created = r2.pushed_created
            result.pushed_failed = r2.pushed_failed

        if dry_run:
            transaction.set_rollback(True)

    return result

# NOTE:
# QBO Jobs (Customers with ParentRef) are intentionally not linked yet.
# Waiting on local Job/Property model design.
