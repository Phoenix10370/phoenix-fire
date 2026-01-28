from django.utils import timezone
from customers.models import Customer
from qbo.models import QBOObjectMap
from qbo.qbo_sync.query_api import qbo_query_all


def pull_customers_from_qbo():
    """
    Pull ALL customers from QBO and upsert QBOObjectMap records.
    Creates local Customer records if they don't exist yet.
    """
    qbo_customers, _ = qbo_query_all(
        "select Id, DisplayName, Active, MetaData.SyncToken from Customer",
        page_size=100,
    )

    created = 0
    updated = 0

    for qc in qbo_customers:
        qbo_id = qc["Id"]
        name = qc.get("DisplayName", "").strip()
        active = qc.get("Active", True)
        sync_token = qc.get("MetaData", {}).get("SyncToken", "")

        # 1) Get or create local Customer
        customer, _ = Customer.objects.get_or_create(
            name=name,
            defaults={"active": active},
        )

        # 2) Create or update mapping
        obj, is_created = QBOObjectMap.objects.update_or_create(
            entity_type="Customer",
            qbo_id=qbo_id,
            defaults={
                "local_app": "customers",
                "local_model": "Customer",
                "local_pk": str(customer.pk),
                "qbo_sync_token": sync_token,
                "last_pulled_at": timezone.now(),
                "last_error": "",
            },
        )

        if is_created:
            created += 1
        else:
            updated += 1

    return {
        "total": len(qbo_customers),
        "created": created,
        "updated": updated,
    }
