# routines/services.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from django.db import transaction

from quotations.models import Quotation
from codes.models import Code
from .models import ServiceRoutine, ServiceRoutineItem


# --------------------
# Helpers
# --------------------

def _add_months(month: int, add: int) -> int:
    return ((int(month) - 1 + int(add)) % 12) + 1


def _month_cycle_excluding(start_month: int, excluded: set[int]) -> List[int]:
    out: List[int] = []
    for i in range(1, 13):
        m = _add_months(start_month, i)
        if m not in excluded:
            out.append(m)
    return out


def _money(v) -> Decimal:
    if v is None:
        v = 0
    if isinstance(v, Decimal):
        d = v
    else:
        d = Decimal(str(v))
    return d.quantize(Decimal("0.01"))


def _calc_section_total(men: int, hours: Decimal, price: Decimal, visits: int) -> Decimal:
    return (_money(men) * _money(hours) * _money(price) * _money(visits)).quantize(Decimal("0.01"))


def _quotation_items_subtotal(q_items) -> Decimal:
    total = Decimal("0.00")
    for qi in q_items:
        qty = qi.quantity or 0
        unit = _money(qi.unit_price or 0)
        total += (Decimal(qty) * unit)
    return total.quantize(Decimal("0.01"))


def _code_variants(code_str: str) -> List[str]:
    s = (code_str or "").strip()
    if not s:
        return []
    s_no_spaces = s.replace(" ", "")
    if "-" in s_no_spaces:
        left, right = s_no_spaces.split("-", 1)
        spaced = f"{left}- {right}"
        spaced2 = f"{left}-  {right}"
        spaced3 = f"{left} - {right}"
        return list(dict.fromkeys([s, s_no_spaces, spaced, spaced2, spaced3]))
    return list(dict.fromkeys([s, s_no_spaces]))


def _get_code_obj(code_str: Optional[str]) -> Optional[Code]:
    if not code_str:
        return None
    variants = _code_variants(code_str)
    if not variants:
        return None

    obj = Code.objects.filter(code__in=variants).first()
    if obj:
        return obj

    for v in variants:
        obj = Code.objects.filter(code__iexact=v).first()
        if obj:
            return obj
    return None


def _quarterly_marker_code_for_month(month_due: int) -> str:
    return f"EFSM-{100 + (int(month_due) - 1)}"


QUARTERLY_EFSM_CODES = {
    1:  ["EFSM-100", "EFSM-103", "EFSM-106", "EFSM-109"],
    2:  ["EFSM-101", "EFSM-104", "EFSM-107", "EFSM-110"],
    3:  ["EFSM-102", "EFSM-105", "EFSM-108", "EFSM-111"],
    4:  ["EFSM-103", "EFSM-106", "EFSM-109", "EFSM-112"],
    5:  ["EFSM-104", "EFSM-107", "EFSM-110", "EFSM-101"],
    6:  ["EFSM-105", "EFSM-108", "EFSM-111", "EFSM-102"],
    7:  ["EFSM-106", "EFSM-109", "EFSM-100", "EFSM-103"],
    8:  ["EFSM-107", "EFSM-110", "EFSM-101", "EFSM-104"],
    9:  ["EFSM-108", "EFSM-111", "EFSM-102", "EFSM-105"],
    10: ["EFSM-109", "EFSM-112", "EFSM-103", "EFSM-106"],
    11: ["EFSM-110", "EFSM-101", "EFSM-104", "EFSM-107"],
    12: ["EFSM-111", "EFSM-102", "EFSM-105", "EFSM-108"],
}


def _upsert_measure_line(*, routine: ServiceRoutine, qi, unit_price: Decimal) -> None:
    ServiceRoutineItem.objects.update_or_create(
        routine=routine,
        source_quotation_item=qi,
        defaults={
            "efsm_code": qi.efsm_code,
            "custom_description": "",
            "quantity": qi.quantity or 0,
            "unit_price": _money(unit_price),
        },
    )


def _prune_stale_measure_lines(*, quotation: Quotation, q_items) -> None:
    current_qi_ids = {qi.id for qi in q_items}
    ServiceRoutineItem.objects.filter(
        routine__quotation=quotation,
        source_quotation_item__isnull=False,
    ).exclude(source_quotation_item_id__in=current_qi_ids).delete()


def _add_measures_to_routines(
    *,
    q_items,
    target_routines: List[ServiceRoutine],
    price_multiplier: Optional[Decimal],
    force_all_items: bool,
    annual_r: Optional[ServiceRoutine],
    biannual_r: Optional[ServiceRoutine],
    monthly_rs: List[ServiceRoutine],
) -> None:
    target_ids = {r.id for r in target_routines if r}

    for qi in q_items:
        code = getattr(qi, "efsm_code", None)
        v = getattr(code, "visits_per_year", 1) if code else 1
        v = v or 1

        try:
            v_int = int(v)
        except Exception:
            v_int = 1

        if force_all_items:
            routine_targets = [r for r in target_routines if r]
        else:
            if v_int <= 1:
                routine_targets = [annual_r] if annual_r else []
            elif v_int == 2:
                routine_targets = [r for r in (annual_r, biannual_r) if r]
            else:
                routine_targets = [r for r in ([annual_r, biannual_r] + monthly_rs) if r]

            routine_targets = [r for r in routine_targets if r and r.id in target_ids]

        base_price = _money(qi.unit_price or 0)
        unit_price = (
            base_price
            if price_multiplier is None
            else (base_price * price_multiplier).quantize(Decimal("0.01"))
        )

        for r in routine_targets:
            _upsert_measure_line(routine=r, qi=qi, unit_price=unit_price)


def _ensure_quarterly_marker_with_value(*, routine: ServiceRoutine, amount: Decimal) -> None:
    code_str = _quarterly_marker_code_for_month(routine.month_due)
    code_obj = _get_code_obj(code_str)
    if not code_obj:
        return

    ServiceRoutineItem.objects.update_or_create(
        routine=routine,
        efsm_code=code_obj,
        source_quotation_item=None,
        defaults={
            "custom_description": "",
            "quantity": 1,
            "unit_price": _money(amount),
        },
    )


def _clear_non_marker_values_for_routine(*, routine: ServiceRoutine) -> None:
    ServiceRoutineItem.objects.filter(
        routine=routine,
        source_quotation_item__isnull=False,
    ).update(unit_price=Decimal("0.00"))


def _safe_text(obj, *field_names: str) -> str:
    for f in field_names:
        v = getattr(obj, f, None)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _to_int_or_none(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    try:
        if isinstance(v, Decimal):
            return int(v)
        if isinstance(v, float):
            return int(v)
        s = str(v).strip()
        if not s:
            return None
        return int(Decimal(s))
    except Exception:
        return None


def _routine_defaults_from_quotation(*, quotation: Quotation, created_by, notes_for_quarterly: bool, service_type=None) -> dict:
    site = quotation.site

    quotation_notes = _safe_text(quotation, "notes", "quotation_notes", "routine_notes", "service_notes")
    site_notes = _safe_text(site, "site_notes", "notes", "access_notes")
    technician_notes = _safe_text(site, "technician_notes", "tech_notes", "notes")

    defaults = {
        "site": site,
        "created_by": created_by,
        "work_order_number": quotation.work_order_number or "",

        # ✅ persist the chosen service type onto each routine
        "service_type": service_type,

        "quotation_notes": quotation_notes,
        "site_notes": site_notes,
        "technician_notes": technician_notes,

        "annual_men_req": _to_int_or_none(getattr(quotation, "calc_men_annual", None)),
        "annual_man_hours": _to_int_or_none(getattr(quotation, "calc_hours_annual", None)),

        "half_yearly_men_req": _to_int_or_none(getattr(quotation, "calc_men_half", None)),
        "half_yearly_man_hours": _to_int_or_none(getattr(quotation, "calc_hours_half", None)),

        "monthly_men_req": _to_int_or_none(getattr(quotation, "calc_men_month", None)),
        "monthly_man_hours": _to_int_or_none(getattr(quotation, "calc_hours_month", None)),
    }

    if notes_for_quarterly:
        defaults["quotation_notes"] = ""

    return defaults


def preview_service_routines_from_quotation(*, quotation: Quotation, annual_due_month: int, invoice_frequency: str) -> list[dict]:
    annual_month = int(annual_due_month)
    biannual_month = _add_months(annual_month, 6)

    q_items = list(
        quotation.items.select_related("efsm_code").order_by("position", "id").all()
    )
    if not q_items:
        return []

    max_visits = 1
    for qi in q_items:
        code = getattr(qi, "efsm_code", None)
        v = getattr(code, "visits_per_year", 1) if code else 1
        v = v or 1
        try:
            max_visits = max(max_visits, int(v))
        except Exception:
            pass

    preview: list[dict] = []
    preview.append({"type": "Annual", "month": annual_month, "rule": "Always created"})

    if max_visits >= 2:
        preview.append({"type": "Bi-Annual", "month": biannual_month, "rule": "Created when any item has 2+ visits/year"})

    if max_visits >= 3:
        excluded = {annual_month, biannual_month}
        months = _month_cycle_excluding(annual_month, excluded)
        for m in months:
            preview.append({"type": "Monthly", "month": m, "rule": "Created when any item has 3+ visits/year"})

    if invoice_frequency == "quarterly":
        for i in range(4):
            m = _add_months(annual_month, i * 3)
            preview.append({"type": "Quarterly", "month": m, "rule": "Quarterly invoicing periods (4)"})

    invoice_frequency = (invoice_frequency or "").strip()
    if invoice_frequency == "annual":
        behaviour = "Invoice value goes to Annual routine only."
    elif invoice_frequency == "bi_annual":
        behaviour = "Invoice value split 50/50 across Annual + Bi-Annual."
    elif invoice_frequency == "monthly":
        behaviour = "Invoice value split evenly across all routines (1/12 each)."
    elif invoice_frequency == "quarterly":
        behaviour = "Quarterly routines carry the invoice values (marker lines). Other lines remain $0.00."
    elif invoice_frequency == "calculator":
        behaviour = "Calculator mode: invoice values based on calculator sections + AFSS."
    else:
        behaviour = "Invoice frequency uses default behaviour."

    for row in preview:
        row["invoice_behaviour"] = behaviour
        row["max_visits"] = max_visits

    return preview


@transaction.atomic
def create_service_routines_from_quotation(
    *,
    quotation: Quotation,
    annual_due_month: int,
    invoice_frequency: str,
    user=None,
    service_type=None,   # ✅ NEW
) -> List[ServiceRoutine]:
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)

    q_items = list(
        quotation.items.select_related("efsm_code").order_by("position", "id").all()
    )
    if not q_items:
        return list(quotation.service_routines.all())

    _prune_stale_measure_lines(quotation=quotation, q_items=q_items)

    annual_month = int(annual_due_month)
    biannual_month = _add_months(annual_month, 6)

    created_by = user if getattr(user, "is_authenticated", False) else None

    max_visits = 1
    for qi in q_items:
        v = getattr(qi.efsm_code, "visits_per_year", 1) or 1
        try:
            v_int = int(v)
        except Exception:
            v_int = 1
        if v_int > max_visits:
            max_visits = v_int

    base_defaults = _routine_defaults_from_quotation(
        quotation=quotation,
        created_by=created_by,
        notes_for_quarterly=False,
        service_type=service_type,  # ✅ set on base routines
    )

    annual_r, _ = ServiceRoutine.objects.update_or_create(
        quotation=quotation,
        routine_type="annual",
        month_due=annual_month,
        defaults={**base_defaults, "name": "Annual Service Routine"},
    )

    biannual_r: Optional[ServiceRoutine] = None
    if max_visits >= 2:
        biannual_r, _ = ServiceRoutine.objects.update_or_create(
            quotation=quotation,
            routine_type="biannual",
            month_due=biannual_month,
            defaults={**base_defaults, "name": "Bi-Annual Service Routine"},
        )

    monthly_rs: List[ServiceRoutine] = []
    if max_visits >= 3:
        excluded = {annual_month, biannual_month}
        monthly_months = _month_cycle_excluding(annual_month, excluded)
        for m in monthly_months:
            r, _ = ServiceRoutine.objects.update_or_create(
                quotation=quotation,
                routine_type="monthly",
                month_due=m,
                defaults={**base_defaults, "name": "Monthly Service Routine"},
            )
            monthly_rs.append(r)

    routines = list(quotation.service_routines.all())

    # ---- CALCULATOR MODE (unchanged except quarterly defaults also get service_type)
    if invoice_frequency == "calculator":
        annual_total = _calc_section_total(
            quotation.calc_men_annual,
            quotation.calc_hours_annual,
            quotation.calc_price_annual,
            quotation.calc_visits_annual,
        )
        half_total = _calc_section_total(
            quotation.calc_men_half,
            quotation.calc_hours_half,
            quotation.calc_price_half,
            quotation.calc_visits_half,
        )
        month_total = _calc_section_total(
            quotation.calc_men_month,
            quotation.calc_hours_month,
            quotation.calc_price_month,
            quotation.calc_visits_month,
        )
        afss = _money(getattr(quotation, "calc_afss_charge", Decimal("0.00")) or 0)

        has_annual = annual_total > 0
        has_half = half_total > 0
        has_month = month_total > 0

        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=Decimal("0.00"),
            force_all_items=False,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )

        if has_annual and has_half and has_month:
            total_value = (annual_total + half_total + month_total + afss).quantize(Decimal("0.01"))
            quarter_value = (total_value * Decimal("0.25")).quantize(Decimal("0.01"))

            quarterly_defaults = _routine_defaults_from_quotation(
                quotation=quotation,
                created_by=created_by,
                notes_for_quarterly=True,
                service_type=service_type,  # ✅
            )

            quarterly_routines: List[ServiceRoutine] = []
            for i in range(1, 5):
                m = _add_months(annual_month, (i - 1) * 3)
                r, _ = ServiceRoutine.objects.update_or_create(
                    quotation=quotation,
                    routine_type="quarterly",
                    month_due=m,
                    defaults={**quarterly_defaults, "name": f"Quarterly Invoicing Period {i}"},
                )
                quarterly_routines.append(r)

            _add_measures_to_routines(
                q_items=q_items,
                target_routines=quarterly_routines,
                price_multiplier=Decimal("0.00"),
                force_all_items=True,
                annual_r=annual_r,
                biannual_r=biannual_r,
                monthly_rs=monthly_rs,
            )

            for r in sorted(quarterly_routines, key=lambda x: x.month_due):
                _clear_non_marker_values_for_routine(routine=r)
                _ensure_quarterly_marker_with_value(routine=r, amount=quarter_value)

            return list(quotation.service_routines.all())

        return list(quotation.service_routines.all())

    # ---- NON-CALCULATOR MODES (unchanged)
    total_value = _quotation_items_subtotal(q_items)

    if invoice_frequency == "annual":
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=Decimal("0.00"),
            force_all_items=False,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=[annual_r],
            price_multiplier=None,
            force_all_items=True,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )
        return list(quotation.service_routines.all())

    if invoice_frequency == "bi_annual":
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=Decimal("0.00"),
            force_all_items=False,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )
        half = Decimal("0.50")
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=[annual_r],
            price_multiplier=half,
            force_all_items=True,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )
        if biannual_r:
            _add_measures_to_routines(
                q_items=q_items,
                target_routines=[biannual_r],
                price_multiplier=half,
                force_all_items=True,
                annual_r=annual_r,
                biannual_r=biannual_r,
                monthly_rs=monthly_rs,
            )
        return list(quotation.service_routines.all())

    if invoice_frequency == "monthly":
        twelfth = (Decimal("1.00") / Decimal("12.00"))
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=twelfth,
            force_all_items=True,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )
        return list(quotation.service_routines.all())

    if invoice_frequency == "quarterly":
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=Decimal("0.00"),
            force_all_items=False,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )

        quarter_value = (total_value * Decimal("0.25")).quantize(Decimal("0.01"))

        quarterly_defaults = _routine_defaults_from_quotation(
            quotation=quotation,
            created_by=created_by,
            notes_for_quarterly=True,
            service_type=service_type,  # ✅
        )

        quarterly_routines: List[ServiceRoutine] = []
        for i in range(1, 5):
            m = _add_months(annual_month, (i - 1) * 3)
            r, _ = ServiceRoutine.objects.update_or_create(
                quotation=quotation,
                routine_type="quarterly",
                month_due=m,
                defaults={**quarterly_defaults, "name": f"Quarterly Invoicing Period {i}"},
            )
            quarterly_routines.append(r)

        _add_measures_to_routines(
            q_items=q_items,
            target_routines=quarterly_routines,
            price_multiplier=Decimal("0.00"),
            force_all_items=True,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )

        for r in sorted(quarterly_routines, key=lambda x: x.month_due):
            _clear_non_marker_values_for_routine(routine=r)
            _ensure_quarterly_marker_with_value(routine=r, amount=quarter_value)

        return list(quotation.service_routines.all())

    _add_measures_to_routines(
        q_items=q_items,
        target_routines=routines,
        price_multiplier=None,
        force_all_items=False,
        annual_r=annual_r,
        biannual_r=biannual_r,
        monthly_rs=monthly_rs,
    )
    return list(quotation.service_routines.all())


@transaction.atomic
def cascade_update_routine_months_for_quotation(*, quotation: Quotation, new_annual_month: int, user=None) -> None:
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)

    routines = list(quotation.service_routines.all())
    if not routines:
        return

    annual = next((r for r in routines if r.routine_type == "annual"), None)
    biannual = next((r for r in routines if r.routine_type == "biannual"), None)
    monthlies = [r for r in routines if r.routine_type == "monthly"]

    new_annual_month = int(new_annual_month)
    new_biannual_month = _add_months(new_annual_month, 6)

    if annual and annual.month_due != new_annual_month:
        annual.month_due = new_annual_month
        annual.save(update_fields=["month_due"])

    if biannual and biannual.month_due != new_biannual_month:
        biannual.month_due = new_biannual_month
        biannual.save(update_fields=["month_due"])

    excluded = {new_annual_month, new_biannual_month}
    new_monthly_months = _month_cycle_excluding(new_annual_month, excluded)

    monthlies_sorted = sorted(monthlies, key=lambda r: r.month_due)
    for r, new_m in zip(monthlies_sorted, new_monthly_months):
        if r.month_due != new_m:
            r.month_due = new_m
            r.save(update_fields=["month_due"])
