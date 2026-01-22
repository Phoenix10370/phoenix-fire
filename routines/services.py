from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction
from django.utils import timezone

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


# Quarterly EFSM mapping (SOURCE OF TRUTH)
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


def _safe_invoice_code(efsm_code_str: Optional[str], fallback_code: Optional[Code]) -> Optional[Code]:
    """
    Try to resolve requested EFSM code from Code table.
    If missing, fallback to first quotation EFSM code to avoid $0 invoice lines.
    """
    code_obj = None
    if efsm_code_str:
        code_obj = Code.objects.filter(code=efsm_code_str).first()
    if not code_obj:
        code_obj = fallback_code
    return code_obj


def _dedupe_items_by_routine_and_code(items: List[ServiceRoutineItem]) -> List[ServiceRoutineItem]:
    """
    Ensure we never try to insert duplicate (routine_id, efsm_code_id) pairs.
    If duplicates exist, we keep the first and merge quantities by summing.
    """
    deduped: Dict[tuple[int, int], ServiceRoutineItem] = {}
    for it in items:
        # routine / efsm_code are always set on these items
        key = (int(it.routine_id or it.routine.pk), int(it.efsm_code_id or it.efsm_code.pk))
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = it
        else:
            # Merge quantity; keep the first item's unit_price/source_quotation_item
            existing.quantity = (existing.quantity or 0) + (it.quantity or 0)
    return list(deduped.values())


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
    """
    Adds quotation EFSM items into routines.

    - If force_all_items=True: every quotation item is added to every target routine.
    - Else: respects visits_per_year scheduling rules against annual/biannual/monthlies.
    - price_multiplier:
        None -> keep original unit_price
        Decimal("0.00") -> set unit_price = 0
        Decimal("0.50") -> half etc
    """
    items: List[ServiceRoutineItem] = []

    for qi in q_items:
        v = getattr(qi.efsm_code, "visits_per_year", 1) or 1
        try:
            v_int = int(v)
        except Exception:
            v_int = 1

        if force_all_items:
            routine_targets = target_routines
        else:
            if v_int <= 1:
                routine_targets = [annual_r] if annual_r else []
            elif v_int == 2:
                routine_targets = [r for r in (annual_r, biannual_r) if r]
            else:
                routine_targets = [r for r in ([annual_r, biannual_r] + monthly_rs) if r]

        base_price = _money(qi.unit_price or 0)
        if price_multiplier is None:
            unit_price = base_price
        else:
            unit_price = (base_price * price_multiplier).quantize(Decimal("0.01"))

        for r in routine_targets:
            if not r:
                continue
            items.append(ServiceRoutineItem(
                routine=r,
                efsm_code=qi.efsm_code,
                quantity=qi.quantity or 0,
                unit_price=unit_price,
                source_quotation_item=qi,
            ))

    # Option A: upsert per (routine, efsm_code) so reruns are safe and UNIQUE never trips.
    # We also dedupe within this batch to avoid multiple upserts for same key.
    for it in _dedupe_items_by_routine_and_code(items):
        ServiceRoutineItem.objects.update_or_create(
            routine=it.routine,
            efsm_code=it.efsm_code,
            defaults={
                "quantity": it.quantity or 0,
                "unit_price": it.unit_price,
                "source_quotation_item": it.source_quotation_item,
            },
        )


def _add_invoice_line(
    *,
    routine: ServiceRoutine,
    amount: Decimal,
    efsm_code_obj: Optional[Code],
    note: str = "",
) -> None:
    """
    Adds a single invoice line into a routine (quantity=1) with the given amount.
    If efsm_code_obj is None, it will do nothing (safe).
    """
    amount = _money(amount)
    if not efsm_code_obj:
        return

    if note:
        routine.notes = ((routine.notes or "") + f"{note}\n").strip() + "\n"
        routine.save(update_fields=["notes"])

    # Option A: one invoice line per (routine, efsm_code). Safe on rerun.
    ServiceRoutineItem.objects.update_or_create(
        routine=routine,
        efsm_code=efsm_code_obj,
        defaults={
            "quantity": 1,
            "unit_price": amount,
            "source_quotation_item": None,
        },
    )


# --------------------
# Main routine creator
# --------------------

@transaction.atomic
def create_service_routines_from_quotation(
    *,
    quotation: Quotation,
    annual_due_month: int,
    invoice_frequency: str,
    user=None,
) -> List[ServiceRoutine]:
    quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)

    q_items = list(quotation.items.select_related("efsm_code").all())
    if not q_items:
        return list(quotation.service_routines.all())

    annual_month = int(annual_due_month)
    biannual_month = _add_months(annual_month, 6)

    now = timezone.now()
    created_by = user if getattr(user, "is_authenticated", False) else None

    # Determine max visits_per_year (schedule rules)
    max_visits = 1
    for qi in q_items:
        v = getattr(qi.efsm_code, "visits_per_year", 1) or 1
        try:
            v_int = int(v)
        except Exception:
            v_int = 1
        if v_int > max_visits:
            max_visits = v_int

    # -----
    # Ensure base routines exist (idempotent)
    # -----
    annual_r, _ = ServiceRoutine.objects.update_or_create(
        quotation=quotation,
        routine_type="annual",
        month_due=annual_month,
        defaults={
            "name": "Annual Service Routine",
            "site": quotation.site,
            "notes": quotation.notes or "",
            "created_by": created_by,
            "work_order_number": quotation.work_order_number or "",
        },
    )

    biannual_r: Optional[ServiceRoutine] = None
    if max_visits >= 2:
        biannual_r, _ = ServiceRoutine.objects.update_or_create(
            quotation=quotation,
            routine_type="biannual",
            month_due=biannual_month,
            defaults={
                "name": "Bi-Annual Service Routine",
                "site": quotation.site,
                "notes": quotation.notes or "",
                "created_by": created_by,
                "work_order_number": quotation.work_order_number or "",
            },
        )

    monthly_rs: List[ServiceRoutine] = []
    monthly_months: List[int] = []
    if max_visits >= 3:
        excluded = {annual_month, biannual_month}
        monthly_months = _month_cycle_excluding(annual_month, excluded)
        for m in monthly_months:
            r, _ = ServiceRoutine.objects.update_or_create(
                quotation=quotation,
                routine_type="monthly",
                month_due=m,
                defaults={
                    "name": "Monthly Service Routine",
                    "site": quotation.site,
                    "notes": quotation.notes or "",
                    "created_by": created_by,
                    "work_order_number": quotation.work_order_number or "",
                },
            )
            monthly_rs.append(r)

    routines = list(quotation.service_routines.all())

    # fallback invoice EFSM code (never fail invoices)
    fallback_code = q_items[0].efsm_code if q_items else None

    # =========================
    # AS PER CALCULATOR (NEW RULES)
    # =========================
    if invoice_frequency == "calculator":
        # read saved calculator fields from quotation
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

        # define "has data" as computed total > 0
        has_annual = annual_total > 0
        has_half = half_total > 0
        has_month = month_total > 0

        # Always add measures to created routines at $0 (so visibility stays)
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=Decimal("0.00"),
            force_all_items=False,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )

        # Case 1: Annual only
        if has_annual and (not has_half) and (not has_month):
            _add_invoice_line(
                routine=annual_r,
                amount=(annual_total + afss),
                efsm_code_obj=fallback_code,
                note="Calculator invoice: Annual total (+ AFSS) applied to Annual routine.",
            )

        # Case 2: Annual + Half only
        elif has_annual and has_half and (not has_month):
            # Ensure biannual exists if calculator requires it
            if not biannual_r:
                biannual_r, _ = ServiceRoutine.objects.update_or_create(
                    quotation=quotation,
                    routine_type="biannual",
                    month_due=biannual_month,
                    defaults={
                        "name": "Bi-Annual Service Routine",
                        "site": quotation.site,
                        "notes": quotation.notes or "",
                        "created_by": created_by,
                        "work_order_number": quotation.work_order_number or "",
                    },
                )
                routines = list(quotation.service_routines.all())

            _add_invoice_line(
                routine=annual_r,
                amount=(annual_total + afss),
                efsm_code_obj=fallback_code,
                note="Calculator invoice: Annual total (+ AFSS) applied to Annual routine.",
            )
            _add_invoice_line(
                routine=biannual_r,
                amount=half_total,
                efsm_code_obj=fallback_code,
                note="Calculator invoice: Half-Yearly total applied to Bi-Annual routine.",
            )

        # Case 3: All sections => behave like QUARTERLY invoicing
        elif has_annual and has_half and has_month:
            total_value = (annual_total + half_total + month_total + afss).quantize(Decimal("0.01"))
            quarter_value = (total_value * Decimal("0.25")).quantize(Decimal("0.01"))
            quarter_codes = QUARTERLY_EFSM_CODES.get(annual_month, [])

            quarterly_routines: List[ServiceRoutine] = []
            for i in range(1, 5):
                m = _add_months(annual_month, (i - 1) * 3)
                r, _ = ServiceRoutine.objects.update_or_create(
                    quotation=quotation,
                    routine_type="quarterly",
                    month_due=m,
                    defaults={
                        "name": f"Quarterly Invoicing Period {i}",
                        "site": quotation.site,
                        "notes": "",
                        "created_by": created_by,
                        "work_order_number": quotation.work_order_number or "",
                    },
                )
                quarterly_routines.append(r)

            # show measures at $0 in quarterly routines too
            _add_measures_to_routines(
                q_items=q_items,
                target_routines=quarterly_routines,
                price_multiplier=Decimal("0.00"),
                force_all_items=True,
                annual_r=annual_r,
                biannual_r=biannual_r,
                monthly_rs=monthly_rs,
            )

            # ALWAYS add invoice lines with value
            for idx, r in enumerate(sorted(quarterly_routines, key=lambda x: x.month_due)):
                requested_code = quarter_codes[idx] if idx < len(quarter_codes) else None
                code_obj = _safe_invoice_code(requested_code, fallback_code)

                if requested_code and code_obj and getattr(code_obj, "code", "") != requested_code:
                    note = f"Invoice EFSM requested {requested_code} (not found). Used {code_obj.code}. Value={quarter_value}"
                elif requested_code:
                    note = f"Invoice EFSM: {requested_code}. Value={quarter_value}"
                else:
                    note = f"Invoice EFSM: (not specified). Value={quarter_value}"

                _add_invoice_line(
                    routine=r,
                    amount=quarter_value,
                    efsm_code_obj=code_obj,
                    note=note,
                )

        # Fallback: if calculator has nothing meaningful, just keep old behaviour (items normally)
        else:
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

    # =========================
    # NON-CALCULATOR MODES (keep your current behaviour)
    # =========================

    total_value = _quotation_items_subtotal(q_items)

    # Annual: annual priced 100%, others 0 (via scaled item prices)
    if invoice_frequency == "annual":
        _add_measures_to_routines(
            q_items=q_items,
            target_routines=routines,
            price_multiplier=None,
            force_all_items=False,
            annual_r=annual_r,
            biannual_r=biannual_r,
            monthly_rs=monthly_rs,
        )
        non_annual = [r for r in routines if not (r.routine_type == "annual" and r.month_due == annual_month)]
        if non_annual:
            _add_measures_to_routines(
                q_items=q_items,
                target_routines=non_annual,
                price_multiplier=Decimal("0.00"),
                force_all_items=False,
                annual_r=annual_r,
                biannual_r=biannual_r,
                monthly_rs=monthly_rs,
            )

    # Bi-Annual: 50/50 (force all items so totals are correct)
    elif invoice_frequency == "bi_annual":
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

        monthlies = [r for r in routines if r.routine_type == "monthly"]
        if monthlies:
            _add_measures_to_routines(
                q_items=q_items,
                target_routines=monthlies,
                price_multiplier=Decimal("0.00"),
                force_all_items=False,
                annual_r=annual_r,
                biannual_r=biannual_r,
                monthly_rs=monthly_rs,
            )

    # Monthly: total/12 each (force all items everywhere)
    elif invoice_frequency == "monthly":
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

    # Quarterly: normal routines $0, plus quarterly invoice routines with 25% each
    elif invoice_frequency == "quarterly":
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
        quarter_codes = QUARTERLY_EFSM_CODES.get(annual_month, [])

        quarterly_routines: List[ServiceRoutine] = []
        for i in range(1, 5):
            m = _add_months(annual_month, (i - 1) * 3)
            r, _ = ServiceRoutine.objects.update_or_create(
                quotation=quotation,
                routine_type="quarterly",
                month_due=m,
                defaults={
                    "name": f"Quarterly Invoicing Period {i}",
                    "site": quotation.site,
                    "notes": "",
                    "created_by": created_by,
                    "work_order_number": quotation.work_order_number or "",
                },
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

        for idx, r in enumerate(sorted(quarterly_routines, key=lambda x: x.month_due)):
            requested_code = quarter_codes[idx] if idx < len(quarter_codes) else None
            code_obj = _safe_invoice_code(requested_code, fallback_code)

            if requested_code and code_obj and getattr(code_obj, "code", "") != requested_code:
                note = f"Invoice EFSM requested {requested_code} (not found). Used {code_obj.code}. Value={quarter_value}"
            elif requested_code:
                note = f"Invoice EFSM: {requested_code}. Value={quarter_value}"
            else:
                note = f"Invoice EFSM: (not specified). Value={quarter_value}"

            _add_invoice_line(
                routine=r,
                amount=quarter_value,
                efsm_code_obj=code_obj,
                note=note,
            )

    else:
        # safe fallback
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


# --------------------
# Cascade month update
# --------------------

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
