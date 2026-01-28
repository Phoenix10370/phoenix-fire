from django.db import transaction
from django.utils import timezone

from .models import JobTask, JobTaskItem, JobServiceType


@transaction.atomic
def create_job_task_from_routine(routine, user=None) -> JobTask:
    """
    Creates a JobTask from a ServiceRoutine and snapshots Routine Items into JobTaskItem.
    """
    prop = getattr(routine, "site", None)  # routines use routine.site for property
    cust = getattr(prop, "customer", None) if prop else None

    routine_type_display = ""
    try:
        routine_type_display = routine.get_routine_type_display()
    except Exception:
        routine_type_display = ""

    service_type = None
    if routine_type_display:
        service_type, _ = JobServiceType.objects.get_or_create(name=routine_type_display)

    job_task = JobTask.objects.create(
        site=prop,  # ✅ IMPORTANT: JobTask uses site, not property
        customer=cust,
        service_routine=routine,
        title=getattr(routine, "name", None) or f"Job Task from Routine #{routine.pk}",
        description=getattr(routine, "notes", "") or "",
        status="open",
        service_date=timezone.now().date(),
        service_type=service_type,
        service_technician=user if getattr(user, "pk", None) else None,
    )

    items_manager = getattr(routine, "items", None)
    items = list(items_manager.all()) if items_manager is not None else []

    for idx, it in enumerate(items, start=1):
        code = ""
        desc = ""

        if hasattr(it, "display_code"):
            code = it.display_code or ""
        elif hasattr(it, "efsm_code") and it.efsm_code:
            code = getattr(it.efsm_code, "code", "") or ""

        if hasattr(it, "display_description"):
            desc = it.display_description or ""
        else:
            desc = getattr(it, "custom_description", "") or ""

        JobTaskItem.objects.create(
            job_task=job_task,
            code=code,
            description=desc,
            quantity=getattr(it, "quantity", 0) or 0,
            unit_price=getattr(it, "unit_price", 0) or 0,
            sort_order=idx,
        )

    return job_task
