from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone

from customers.models import Customer
from properties.models import Property
from quotations.models import Quotation
from routines.models import ServiceRoutine


def dashboard(request):
    """
    Dashboard view.

    Explicitly provides:
    - Summary counts (tiles)
    - Recent counts (last 30 days)
    - Validated property coordinates for map display

    This avoids relying on unknown context processors.
    """
    now = timezone.now()
    since_30_days = now - timedelta(days=30)

    # ---- Tile counts ----
    customers_total = Customer.objects.count()
    customers_recent = Customer.objects.filter(created_at__gte=since_30_days).count() \
        if hasattr(Customer, "created_at") else None

    properties_total = Property.objects.count()
    properties_recent = Property.objects.filter(created_at__gte=since_30_days).count() \
        if hasattr(Property, "created_at") else None

    quotations_total = Quotation.objects.count()
    quotations_recent = Quotation.objects.filter(created_at__gte=since_30_days).count() \
        if hasattr(Quotation, "created_at") else None

    routines_total = ServiceRoutine.objects.count()
    routines_recent = ServiceRoutine.objects.filter(created_at__gte=since_30_days).count() \
        if hasattr(ServiceRoutine, "created_at") else None

    # ---- Map properties (validated only) ----
    properties = (
        Property.objects
        .filter(
            coords_validated=True,
            latitude__isnull=False,
            longitude__isnull=False,
        )
        .only(
            "id",
            "building_name",
            "street",
            "city",
            "state",
            "post_code",
            "latitude",
            "longitude",
        )
        .order_by("building_name")
    )

    map_properties = [
        {
            "id": p.id,
            "name": p.building_name,
            "address": p.full_address,
            "lat": float(p.latitude),
            "lng": float(p.longitude),
            "url": f"/properties/{p.id}/",
        }
        for p in properties
    ]

    return render(
    request,
    "dashboard.html",
    {
        "map_properties": [{"debug": "THIS IS CORE.VIEWS.DASHBOARD"}],
    },
)

