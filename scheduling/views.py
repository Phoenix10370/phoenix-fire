# C:\PhoenixFire\scheduling\views.py  (FULL FILE REPLACEMENT)

import json
from datetime import datetime, timedelta, time as dtime

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.views.decorators.http import require_GET, require_POST

from job_tasks.models import JobTask, JobServiceType

User = get_user_model()


def _jobtask_title(jt: JobTask) -> str:
    bits = [jt.title]
    if jt.site_id and getattr(jt.site, "full_address", None):
        bits.append(jt.site.full_address)
    return " • ".join([b for b in bits if b])


def _color_for_service_type(service_type_name: str | None) -> str:
    if not service_type_name:
        return "#4b5563"
    name = str(service_type_name).strip().lower()
    if name == "annual inspection":
        return "#ff0000"
    if name in {"bi annual inspection", "bi-annual inspection"}:
        return "#99ffff"
    if name == "monthly inspection":
        return "#6699ff"
    if name == "quartley invoice" or name == "quarterly invoice":
        return "#ff99ff"
    return "#4b5563"


def _fmt_time_dot(t: dtime | None) -> str:
    if not t:
        return ""
    hour = t.hour % 12
    hour = 12 if hour == 0 else hour
    ampm = "am" if t.hour < 12 else "pm"
    return f"{hour}.{t.minute:02d}{ampm}"


def _service_time_display(start_t: dtime | None, finish_t: dtime | None) -> str:
    if start_t and finish_t:
        return f"{_fmt_time_dot(start_t)}-{_fmt_time_dot(finish_t)}"
    if start_t and not finish_t:
        return f"{_fmt_time_dot(start_t)}-"
    if finish_t and not start_t:
        return f"-{_fmt_time_dot(finish_t)}"
    return ""


def _combine_date_time_naive(d, t: dtime | None):
    """
    Build a *naive* datetime so FullCalendar treats it as local time.
    """
    if not d:
        return None
    if not t:
        t = dtime(8, 0)
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second)


def _derive_end_naive(start_dt: datetime, finish_time: dtime | None):
    if not start_dt:
        return None
    if finish_time:
        return datetime(
            start_dt.year,
            start_dt.month,
            start_dt.day,
            finish_time.hour,
            finish_time.minute,
            finish_time.second,
        )
    return start_dt + timedelta(minutes=60)


def _naive_iso(dt: datetime) -> str:
    # timezone-free ISO
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_calendar_dt(value):
    """
    Accept ISO strings from FullCalendar.
    - If value is naive, interpret it in local timezone
    - If value is aware (has offset/Z), convert to local timezone
    """
    if not value or not isinstance(value, str):
        return None
    dt = parse_datetime(value)
    if not dt:
        return None

    tz = timezone.get_current_timezone()

    if timezone.is_naive(dt):
        # interpret as local time
        dt = timezone.make_aware(dt, tz)
    else:
        # convert to local time
        dt = dt.astimezone(tz)

    return dt


def _time_for_storage(dt):
    """
    Store as naive time (TimeField).
    """
    if not dt:
        return None
    return dt.timetz().replace(tzinfo=None, second=0, microsecond=0)


@login_required
def scheduling_view(request):
    service_types = JobServiceType.objects.filter(is_active=True).order_by("name")
    technicians = User.objects.filter(is_active=True).order_by("username")
    return render(
        request,
        "scheduling/scheduling.html",
        {"service_types": service_types, "technicians": technicians},
    )


@login_required
@require_GET
def events_feed(request):
    """
    Calendar events from JobTask.service_date + start/finish_time.
    Optional filter: ?technician=<id> and ?date=YYYY-MM-DD
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    tech_id = (request.GET.get("technician") or "").strip()
    date_str = (request.GET.get("date") or "").strip()

    if not start or not end:
        return HttpResponseBadRequest("Missing start/end")

    start_dt = _parse_calendar_dt(start)
    end_dt = _parse_calendar_dt(end)
    if not start_dt or not end_dt:
        return HttpResponseBadRequest("Invalid start/end")

    start_date = start_dt.date()
    end_date = end_dt.date()

    filter_date = parse_date(date_str) if date_str else None
    if filter_date:
        start_date = filter_date
        end_date = filter_date

    qs = (
        JobTask.objects.select_related("service_type", "site", "service_technician")
        .filter(service_date__isnull=False)
        .filter(service_date__gte=start_date, service_date__lte=end_date)
    )

    if tech_id and tech_id.isdigit():
        qs = qs.filter(service_technician_id=int(tech_id))

    events = []
    for jt in qs:
        sdt = _combine_date_time_naive(jt.service_date, jt.start_time)
        edt = _derive_end_naive(sdt, jt.finish_time) if sdt else None
        if not sdt or not edt:
            continue
        if edt <= sdt:
            edt = sdt + timedelta(minutes=60)

        color = _color_for_service_type(str(jt.service_type) if jt.service_type_id else "")

        events.append(
            {
                "id": jt.id,
                "title": _jobtask_title(jt),
                "start": _naive_iso(sdt),
                "end": _naive_iso(edt),
                "allDay": False,
                "backgroundColor": color,
                "borderColor": color,
                "extendedProps": {
                    "job_task_id": jt.id,
                    "service_type_id": jt.service_type_id,
                    "service_type": str(jt.service_type) if jt.service_type_id else "",
                    "status": jt.status,
                    "technician_id": jt.service_technician_id,
                    "technician": str(jt.service_technician) if jt.service_technician_id else "",
                    "site_address": jt.site.full_address if jt.site_id and getattr(jt.site, "full_address", None) else "",
                    "event_color": color,
                },
            }
        )

    return JsonResponse(events, safe=False)


@login_required
@require_GET
def unallocated_feed(request):
    service_type = (request.GET.get("service_type") or "").strip()
    date_str = (request.GET.get("date") or "").strip()
    filter_date = parse_date(date_str) if date_str else None

    qs = (
        JobTask.objects.select_related("service_type", "site", "service_technician")
        .filter(service_date__isnull=True)
        .order_by("-created_at")
    )

    if filter_date:
        qs = qs.filter(created_at__date=filter_date)

    if service_type:
        if service_type.isdigit():
            qs = qs.filter(service_type_id=int(service_type))
        else:
            qs = qs.filter(service_type__name__icontains=service_type)

    qs = qs[:300]

    items = []
    for jt in qs:
        duration_minutes = 60
        if jt.start_time and jt.finish_time:
            delta = (
                datetime.combine(datetime.today(), jt.finish_time)
                - datetime.combine(datetime.today(), jt.start_time)
            )
            duration_minutes = max(15, int(delta.total_seconds() / 60))

        items.append(
            {
                "job_task_id": jt.id,
                "title": _jobtask_title(jt),
                "service_type": str(jt.service_type) if jt.service_type_id else "",
                "durationMinutes": duration_minutes,
                "technician_id": jt.service_technician_id,
                "technician_name": str(jt.service_technician) if jt.service_technician_id else "Unassigned",
            }
        )

    return JsonResponse(items, safe=False)


def _update_jobtask_schedule(job_task_id: int, start_dt, end_dt):
    """
    CRITICAL FIX:
    Use QuerySet.update() to bypass the save path that is wiping finish_time.
    """
    if not start_dt:
        raise ValueError("Missing start_dt")

    if not end_dt:
        end_dt = start_dt + timedelta(minutes=60)

    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(minutes=60)

    service_date = start_dt.date()
    start_t = _time_for_storage(start_dt)
    finish_t = _time_for_storage(end_dt)
    service_time = _service_time_display(start_t, finish_t)

    JobTask.objects.filter(pk=job_task_id).update(
        service_date=service_date,
        start_time=start_t,
        finish_time=finish_t,
        service_time=service_time,
    )


@login_required
@require_POST
def schedule_jobtask(request, pk: int):
    """
    Drop from Unallocated onto calendar.
    Body: { start: "...", end: "...", allDay?: bool }
    """
    get_object_or_404(JobTask, pk=pk)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    start_raw = payload.get("start")
    end_raw = payload.get("end")
    all_day = bool(payload.get("allDay", False))

    start_dt = _parse_calendar_dt(start_raw)
    end_dt = _parse_calendar_dt(end_raw)

    if not start_dt:
        return HttpResponseBadRequest("Missing/invalid start")

    if all_day:
        start_dt = start_dt.replace(hour=8, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(minutes=60)

    # If end missing, default +60
    if not end_dt:
        end_dt = start_dt + timedelta(minutes=60)

    _update_jobtask_schedule(pk, start_dt, end_dt)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def update_jobtask_times(request, pk: int):
    """
    Move/resize existing scheduled event.
    Body: { start: "...", end: "...", allDay?: bool }
    """
    get_object_or_404(JobTask, pk=pk)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    start_raw = payload.get("start")
    end_raw = payload.get("end")
    all_day = bool(payload.get("allDay", False))

    start_dt = _parse_calendar_dt(start_raw)
    end_dt = _parse_calendar_dt(end_raw)

    if not start_dt:
        return HttpResponseBadRequest("Missing/invalid start")

    if all_day:
        start_dt = start_dt.replace(hour=8, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(minutes=60)

    if not end_dt:
        end_dt = start_dt + timedelta(minutes=60)

    _update_jobtask_schedule(pk, start_dt, end_dt)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def unschedule_jobtask(request, pk: int):
    """
    Drop from calendar back into Unallocated.
    Clears service_date/start/finish/service_time.
    Uses update() to bypass save path.
    """
    get_object_or_404(JobTask, pk=pk)

    JobTask.objects.filter(pk=pk).update(
        service_date=None,
        start_time=None,
        finish_time=None,
        service_time="",
    )

    return JsonResponse({"ok": True})
