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

    context = {
        "customers_total": Customer.objects.count(),
        "customers_recent": Customer.objects.filter(created_at__gte=since).count()
        if hasattr(Customer, "created_at") else None,

        "properties_total": Property.objects.count(),
        "properties_recent": Property.objects.filter(created_at__gte=since).count()
        if hasattr(Property, "created_at") else None,

        "quotations_total": Quotation.objects.count(),
        "quotations_recent": Quotation.objects.filter(created_at__gte=since).count(),

        "routines_total": ServiceRoutine.objects.count(),
        "routines_recent": ServiceRoutine.objects.filter(created_at__gte=since).count(),
    }

    return render(request, "dashboard.html", context)
