# job_tasks/services.py
from decimal import Decimal

from django.db import transaction

from .models import JobTask, JobTaskItem, JobServiceType
from routines.models import ServiceRoutine, ServiceRoutineItem


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

        # ✅ must be blank and unscheduled
        service_date=None,
        status="open",

        # ✅ no tech auto assignment
        service_technician=None,

        # ✅ copy service type if possible
        service_type=service_type,
    )

    items_rel = getattr(routine, "items", None)
    if not items_rel:
        return job_task

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

    return job_task
