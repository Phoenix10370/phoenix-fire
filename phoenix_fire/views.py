from datetime import timedelta

from django.utils import timezone
from django.shortcuts import render

from customers.models import Customer
from properties.models import Property
from quotations.models import Quotation
from routines.models import ServiceRoutine


def dashboard(request):
    # Simple “recent” window (last 30 days)
    since = timezone.now() - timedelta(days=30)

    # ---- Property validation counts ----
    properties_total = Property.objects.count()
    properties_not_validated = Property.objects.filter(
        coords_validated=False
    ).count()

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

    context = {
        "customers_total": Customer.objects.count(),
        "customers_recent": Customer.objects.filter(created_at__gte=since).count()
        if hasattr(Customer, "created_at") else None,

        "properties_total": properties_total,
        "properties_recent": Property.objects.filter(created_at__gte=since).count()
        if hasattr(Property, "created_at") else None,

        # ✅ NEW
        "properties_not_validated": properties_not_validated,

        "quotations_total": Quotation.objects.count(),
        "quotations_recent": Quotation.objects.filter(created_at__gte=since).count(),

        "routines_total": ServiceRoutine.objects.count(),
        "routines_recent": ServiceRoutine.objects.filter(created_at__gte=since).count(),

        # Map
        "map_properties": map_properties,
    }

    return render(request, "dashboard.html", context)
