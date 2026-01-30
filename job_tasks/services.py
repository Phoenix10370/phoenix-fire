# job_tasks/services.py
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import JobServiceType, JobTask, JobTaskItem
from routines.models import ServiceRoutine, ServiceRoutineItem
from properties.models import PropertyAsset
from codes.models import AssetCode


def _safe_decimal(val, default="0.00") -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default)


def _get_routine_item_code(item: ServiceRoutineItem) -> str:
    efsm = getattr(item, "efsm_code", None)
    if efsm is not None:
        code = getattr(efsm, "code", None)
        if code:
            return str(code).strip()
        return str(efsm).strip()
    return str(getattr(item, "code", "") or "").strip()


def _get_routine_item_description(item: ServiceRoutineItem) -> str:
    desc = getattr(item, "description", None)
    if desc:
        return str(desc).strip()

    desc = getattr(item, "custom_description", None)
    if desc:
        return str(desc).strip()

    efsm = getattr(item, "efsm_code", None)
    if efsm is not None:
        efsm_desc = getattr(efsm, "description", None)
        if efsm_desc:
            return str(efsm_desc).strip()
        return str(efsm).strip()

    return ""


def _routine_service_type_or_none(routine: ServiceRoutine):
    """
    Best-effort: copy service_type from routine if that field exists.
    """
    st = getattr(routine, "service_type", None)
    if st:
        return st

    st_id = getattr(routine, "service_type_id", None)
    if st_id:
        try:
            return JobServiceType.objects.get(pk=st_id)
        except JobServiceType.DoesNotExist:
            return None

    return None


def _routine_type_key(routine: ServiceRoutine) -> str:
    """
    ServiceRoutine.routine_type values in your model:
      - annual
      - biannual   (Half Yearly)
      - monthly
      - quarterly
    """
    return (getattr(routine, "routine_type", "") or "").strip().lower()


def _asset_is_included_for_routine_type(routine_type: str, frequency: int) -> bool:
    """
    Your rules based on AssetCode.frequency (times per year):
      - Annual: include all assets
      - Half Yearly (biannual): include assets with frequency > 2 (exclude 1 and 2)
      - Monthly: include assets with frequency > 3
      - Quarterly: include none
    """
    if routine_type == "annual":
        return True
    if routine_type == "biannual":
        return frequency > 2
    if routine_type == "monthly":
        return frequency > 3
    if routine_type == "quarterly":
        return False

    # Unknown routine type -> safest default (avoid sending too many assets)
    return False


def _autolink_property_assets(job_task: JobTask, routine: ServiceRoutine) -> None:
    """
    Link PropertyAssets to the new JobTask based on routine type and AssetCode.frequency.

    Notes:
      - Only considers PropertyAssets whose asset_code_content_type is codes.AssetCode
      - Does NOT create/delete assets; only creates M2M link rows
    """
    site = getattr(routine, "site", None)
    if not site:
        return

    routine_type = _routine_type_key(routine)

    # Explicitly none for quarterly
    if routine_type == "quarterly":
        return

    assetcode_ct = ContentType.objects.get_for_model(AssetCode)

    # Only property assets that point to AssetCode
    prop_assets = list(
        PropertyAsset.objects.filter(
            property_id=site.pk,
            asset_code_content_type_id=assetcode_ct.id,
        ).only("id", "asset_code_object_id")
    )
    if not prop_assets:
        return

    code_ids = [pa.asset_code_object_id for pa in prop_assets if pa.asset_code_object_id]
    if not code_ids:
        return

    codes_by_id = {
        ac.id: ac
        for ac in AssetCode.objects.filter(id__in=code_ids).only("id", "frequency")
    }

    to_link = []
    for pa in prop_assets:
        ac = codes_by_id.get(pa.asset_code_object_id)
        if not ac:
            continue

        try:
            freq_int = int(getattr(ac, "frequency", 1) or 1)
        except (TypeError, ValueError):
            freq_int = 1

        if _asset_is_included_for_routine_type(routine_type, freq_int):
            to_link.append(pa)

    if to_link:
        job_task.property_assets.add(*to_link)


@transaction.atomic
def create_job_task_from_routine(routine: ServiceRoutine) -> JobTask:
    routine_name = (getattr(routine, "name", "") or "").strip()
    title = routine_name or f"Service Routine #{routine.pk}"

    service_type = _routine_service_type_or_none(routine)

    job_task = JobTask.objects.create(
        title=title,
        site=getattr(routine, "site", None),
        customer=getattr(getattr(routine, "site", None), "customer", None),
        service_routine=routine,

        # must be blank and unscheduled
        service_date=None,
        status="open",

        # no tech auto assignment
        service_technician=None,

        # copy service type if possible
        service_type=service_type,
    )

    items_rel = getattr(routine, "items", None)
    if items_rel:
        routine_items = list(items_rel.all().order_by("id"))
        sort_order = 1
        for rit in routine_items:
            JobTaskItem.objects.create(
                job_task=job_task,
                sort_order=sort_order,
                code=_get_routine_item_code(rit),
                description=_get_routine_item_description(rit),
                quantity=_safe_decimal(getattr(rit, "quantity", 0), default="0"),
                unit_price=_safe_decimal(getattr(rit, "unit_price", 0), default="0"),
            )
            sort_order += 1

    # Auto-link Property Assets using frequency rules
    _autolink_property_assets(job_task=job_task, routine=routine)

    return job_task
