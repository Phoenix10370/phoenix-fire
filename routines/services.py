from __future__ import annotations

from typing import Dict, List

from django.db import transaction
from django.utils import timezone

from quotations.models import Quotation
from .models import ServiceRoutine, ServiceRoutineItem


def _add_months(month: int, add: int) -> int:
    # month is 1..12
    return ((int(month) - 1 + int(add)) % 12) + 1


def _month_cycle_excluding(start_month: int, excluded: set[int]) -> List[int]:
    """
    Returns months in forward order starting AFTER start_month, wrapping around,
    excluding any in excluded.
    Example: start=1 (Jan), excluded={1,7} -> [2,3,4,5,6,8,9,10,11,12]
    """
    out: List[int] = []
    for i in range(1, 13):
        m = _add_months(start_month, i)
        if m not in excluded:
            out.append(m)
    return out


@transaction.atomic
def create_service_routines_from_quotation(*, quotation: Quotation, annual_due_month: int, user=None) -> List[ServiceRoutine]:
    """
    Creates ServiceRoutine records for a quotation based on max visits_per_year:
      - max <= 1: Annual only (month_due = annual_due_month)
      - max == 2: Annual (month_due=annual_due_month) + Bi-Annual (month_due=annual+6)
      - max >= 3: Annual + Bi-Annual + 10 Monthlies (all remaining months excluding those two)

    Also copies quotation items into routines:
      - visits_per_year == 1 -> Annual only
      - visits_per_year == 2 -> Annual + Bi-Annual
      - visits_per_year >= 3 -> Annual + Bi-Annual + all Monthlies
    """
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)

    # If already created, return existing
    existing = list(quotation.service_routines.all())
    if existing:
        return existing

    q_items = list(quotation.items.select_related("efsm_code").all())
    if not q_items:
        return []

    # Determine max visits_per_year
    max_visits = 1
    for qi in q_items:
        v = getattr(qi.efsm_code, "visits_per_year", 1) or 1
        try:
            v_int = int(v)
        except Exception:
            v_int = 1
        if v_int > max_visits:
            max_visits = v_int

    annual_month = int(annual_due_month)
    biannual_month = _add_months(annual_month, 6)

    now = timezone.now()
    created_by = user if getattr(user, "is_authenticated", False) else None

    routines_to_create: List[ServiceRoutine] = []

    # Always create Annual
    routines_to_create.append(ServiceRoutine(
        quotation=quotation,
        routine_type="annual",
        month_due=annual_month,
        name="Annual Service Routine",
        site=quotation.site,
        notes=quotation.notes or "",
        created_by=created_by,
        work_order_number=quotation.work_order_number or "",
        created_at=now,
    ))

    # Create Bi-Annual if needed
    if max_visits >= 2:
        routines_to_create.append(ServiceRoutine(
            quotation=quotation,
            routine_type="biannual",
            month_due=biannual_month,
            name="Bi-Annual Service Routine",
            site=quotation.site,
            notes=quotation.notes or "",
            created_by=created_by,
            work_order_number=quotation.work_order_number or "",
            created_at=now,
        ))

    # Create 10 Monthlies if needed (max_visits >= 3)
    monthly_months: List[int] = []
    if max_visits >= 3:
        excluded = {annual_month, biannual_month}
        monthly_months = _month_cycle_excluding(annual_month, excluded)  # 10 months
        for m in monthly_months:
            routines_to_create.append(ServiceRoutine(
                quotation=quotation,
                routine_type="monthly",
                month_due=m,
                name="Monthly Service Routine",
                site=quotation.site,
                notes=quotation.notes or "",
                created_by=created_by,
                work_order_number=quotation.work_order_number or "",
                created_at=now,
            ))

    ServiceRoutine.objects.bulk_create(routines_to_create)

    # Map routines by month for item copying
    routines = list(quotation.service_routines.all())
    routine_by_month: Dict[int, ServiceRoutine] = {r.month_due: r for r in routines}

    # Copy items into correct routines
    items_to_create: List[ServiceRoutineItem] = []

    for qi in q_items:
        v = getattr(qi.efsm_code, "visits_per_year", 1) or 1
        try:
            v_int = int(v)
        except Exception:
            v_int = 1

        if v_int <= 1:
            target_months = [annual_month]
        elif v_int == 2:
            target_months = [annual_month, biannual_month]
        else:
            target_months = [annual_month, biannual_month] + monthly_months

        for m in target_months:
            r = routine_by_month.get(m)
            if not r:
                continue
            items_to_create.append(ServiceRoutineItem(
                routine=r,
                efsm_code=qi.efsm_code,
                quantity=qi.quantity,
                unit_price=qi.unit_price,
                source_quotation_item=qi,
            ))

    ServiceRoutineItem.objects.bulk_create(items_to_create, ignore_conflicts=True)

    # Optional log
    try:
        quotation.log(
            action="status_changed",
            user=user,
            message=f"Service routines created. Annual due month set to {annual_month}.",
        )
    except Exception:
        pass

    return list(quotation.service_routines.all())


@transaction.atomic
def cascade_update_routine_months_for_quotation(*, quotation: Quotation, new_annual_month: int, user=None) -> None:
    """
    When user changes Annual month_due and confirms "Yes",
    update all related routines for the same quotation:
      - annual -> new_annual_month
      - biannual -> new_annual_month + 6
      - monthly -> remaining 10 months (excluding annual & biannual), in order after annual
    """
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)

    routines = list(quotation.service_routines.all())
    if not routines:
        return

    annual = next((r for r in routines if r.routine_type == "annual"), None)
    biannual = next((r for r in routines if r.routine_type == "biannual"), None)
    monthlies = [r for r in routines if r.routine_type == "monthly"]

    new_annual_month = int(new_annual_month)
    new_biannual_month = _add_months(new_annual_month, 6)

    # Update Annual
    if annual and annual.month_due != new_annual_month:
        annual.month_due = new_annual_month
        annual.save(update_fields=["month_due"])

    # Update Bi-Annual
    if biannual and biannual.month_due != new_biannual_month:
        biannual.month_due = new_biannual_month
        biannual.save(update_fields=["month_due"])

    # Update Monthlies
    excluded = {new_annual_month, new_biannual_month}
    new_monthly_months = _month_cycle_excluding(new_annual_month, excluded)  # 10 months

    # stable ordering: sort by current month_due, then assign in new sequence
    monthlies_sorted = sorted(monthlies, key=lambda r: r.month_due)

    for r, new_m in zip(monthlies_sorted, new_monthly_months):
        if r.month_due != new_m:
            r.month_due = new_m
            r.save(update_fields=["month_due"])

    # Optional log
    try:
        quotation.log(
            action="status_changed",
            user=user,
            message=f"Routine months updated: Annual={new_annual_month}, Bi-Annual={new_biannual_month}.",
        )
    except Exception:
        pass
