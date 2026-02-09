# job_tasks/services.py
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import JobServiceType, JobTask, JobTaskItem
from routines.models import ServiceRoutine, ServiceRoutineItem
from properties.models import PropertyAsset
from codes.models import AssetCode


# --------------------
# Helpers
# --------------------

def _safe_decimal(val, default="0.00") -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default)


def _get_routine_item_code(item: ServiceRoutineItem) -> str:
    if item.efsm_code:
        return item.efsm_code.code
    return ""


def _get_routine_item_description(item: ServiceRoutineItem) -> str:
    if item.custom_description:
        return item.custom_description
    if item.efsm_code:
        return getattr(item.efsm_code, "fire_safety_measure", "") or ""
    return ""


def _resolve_job_service_type(routine: ServiceRoutine) -> JobServiceType | None:
    """
    FINAL SOURCE OF TRUTH for JobTask.service_type

    Priority:
    1) Explicit routine.service_type FK (if present)
    2) Map routine.routine_type → JobServiceType
    """

    # 1️⃣ Explicit FK on routine (best case)
    st = getattr(routine, "service_type", None)
    if isinstance(st, JobServiceType):
        return st

    # 2️⃣ Fallback: map routine_type
    routine_type = (routine.routine_type or "").lower()

    MAP = {
        "annual": "Annual Inspection",
        "biannual": "Bi-Annual Inspection",
        "monthly": "Monthly Inspection",
        "quarterly": "Quarterly Invoicing",
    }

    name = MAP.get(routine_type)
    if not name:
        return None

    service_type, _ = JobServiceType.objects.get_or_create(
        name=name,
        defaults={"is_active": True},
    )
    return service_type


def _routine_type_key(routine: ServiceRoutine) -> str:
    return (routine.routine_type or "").lower()


def _asset_is_included_for_routine_type(routine_type: str, frequency: int) -> bool:
    if routine_type == "annual":
        return True
    if routine_type == "biannual":
        return frequency > 2
    if routine_type == "monthly":
        return frequency > 3
    return False


def _autolink_property_assets(job_task: JobTask, routine: ServiceRoutine) -> None:
    site = routine.site
    if not site:
        return

    routine_type = _routine_type_key(routine)
    if routine_type == "quarterly":
        return

    assetcode_ct = ContentType.objects.get_for_model(AssetCode)

    assets = PropertyAsset.objects.filter(
        property_id=site.pk,
        asset_code_content_type_id=assetcode_ct.id,
    )

    if not assets.exists():
        return

    codes = {
        ac.id: ac
        for ac in AssetCode.objects.filter(
            id__in=assets.values_list("asset_code_object_id", flat=True)
        )
    }

    to_link = []
    for pa in assets:
        ac = codes.get(pa.asset_code_object_id)
        if not ac:
            continue

        freq = int(ac.frequency or 1)
        if _asset_is_included_for_routine_type(routine_type, freq):
            to_link.append(pa)

    if to_link:
        job_task.property_assets.add(*to_link)


# --------------------
# Main entry
# --------------------

@transaction.atomic
def create_job_task_from_routine(routine: ServiceRoutine) -> JobTask:
    title = routine.name or f"Service Routine #{routine.pk}"

    job_task = JobTask.objects.create(
        title=title,
        site=routine.site,
        customer=getattr(routine.site, "customer", None),
        service_routine=routine,
        service_date=None,
        status="open",
        service_technician=None,
        service_type=_resolve_job_service_type(routine),
    )

    # Copy routine items
    for idx, rit in enumerate(routine.items.all().order_by("position", "id"), start=1):
        JobTaskItem.objects.create(
            job_task=job_task,
            sort_order=idx,
            code=_get_routine_item_code(rit),
            description=_get_routine_item_description(rit),
            quantity=_safe_decimal(rit.quantity),
            unit_price=_safe_decimal(rit.unit_price),
        )

    _autolink_property_assets(job_task, routine)
    return job_task
