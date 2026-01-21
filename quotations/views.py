# quotations/views.py
from decimal import Decimal
from io import BytesIO
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView, DetailView, ListView

from xhtml2pdf import pisa

from codes.models import Code
from properties.models import Property
from company.models import ClientProfile

from .forms import QuotationForm, QuotationItemFormSet
from .models import Quotation


def _pdf_link_callback(uri, rel):
    if uri.startswith(settings.MEDIA_URL):
        return os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    if uri.startswith(settings.STATIC_URL):
        return os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    if os.path.isfile(uri):
        return uri
    return uri


class QuotationListView(ListView):
    model = Quotation
    template_name = "quotations/quotation_list.html"
    context_object_name = "items"

    def get_queryset(self):
        return (
            Quotation.objects.select_related("site", "site__customer")
            .prefetch_related("items", "items__efsm_code")
        )


class QuotationDetailView(DetailView):
    model = Quotation
    template_name = "quotations/quotation_detail.html"
    context_object_name = "item"

    def get_queryset(self):
        return (
            Quotation.objects.select_related("site", "site__customer")
            .prefetch_related("items", "items__efsm_code", "logs", "logs__actor")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        quote = self.object
        subtotal = Decimal("0.00")
        for li in quote.items.all():
            subtotal += Decimal(li.line_total)

        gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
        total = (subtotal + gst).quantize(Decimal("0.01"))

        ctx["subtotal"] = subtotal.quantize(Decimal("0.01"))
        ctx["gst"] = gst
        ctx["total"] = total
        return ctx


# =========================
# Accept (DATE ONLY) / Reject
# =========================
@login_required
def quotation_accept(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)

    if quote.status in ("accepted", "rejected"):
        messages.info(request, f"Quotation {quote.number} is already {quote.status}.")
        return redirect("quotations:detail", pk=quote.pk)

    if request.method == "POST":
        accepted_date_raw = (request.POST.get("accepted_date") or "").strip()
        accepted_by_name = (request.POST.get("accepted_by_name") or "").strip()
        work_order_number = (request.POST.get("work_order_number") or "").strip() or None

        accepted_date = parse_date(accepted_date_raw) if accepted_date_raw else timezone.localdate()
        if accepted_date is None:
            messages.error(request, "Accepted date is invalid.")
            return redirect("quotations:accept", pk=quote.pk)

        if not accepted_by_name:
            accepted_by_name = ((request.user.get_full_name() or "").strip() or request.user.username)

        # Save using your existing method (it currently sets accepted_at; you can still keep it for now)
        # But for date-only display, your template MUST use accepted_date_value and detail should use |date filter.
        quote.mark_accepted(request.user, work_order_number=work_order_number)

        # Store the chosen date into accepted_at at midnight (until you migrate to DateField)
        quote.accepted_at = timezone.make_aware(
            timezone.datetime.combine(accepted_date, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )

        # Optional: if you added accepted_by_name field in model, save it
        if hasattr(quote, "accepted_by_name"):
            quote.accepted_by_name = accepted_by_name

        quote.save()

        quote.log(
            "accepted",
            request.user,
            f"Accepted. Date={accepted_date.strftime('%Y-%m-%d')} "
            f"Accepted By={accepted_by_name} Work Order={work_order_number or '—'}",
        )

        messages.success(request, f"Quotation {quote.number} accepted.")
        return redirect("quotations:detail", pk=quote.pk)

    # ✅ GET: value MUST be YYYY-MM-DD for <input type="date">
    accepted_date_value = timezone.localdate().strftime("%Y-%m-%d")
    accepted_by_value = ((request.user.get_full_name() or "").strip() or request.user.username)

    # ✅ Per your requirement: always blank on open
    work_order_value = ""

    return render(
        request,
        "quotations/quotation_accept.html",
        {
            "item": quote,
            "accepted_date_value": accepted_date_value,   # ✅ MUST match template variable
            "accepted_by_value": accepted_by_value,
            "work_order_value": work_order_value,
            "cancel_url": reverse("quotations:detail", kwargs={"pk": quote.pk}),
        },
    )


@login_required
@require_POST
def quotation_reject(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)

    if quote.status in ("accepted", "rejected"):
        messages.info(request, f"Quotation {quote.number} is already {quote.status}.")
        return redirect("quotations:detail", pk=quote.pk)

    quote.mark_rejected(request.user)
    quote.save()
    quote.log("rejected", request.user, "Declined.")

    messages.success(request, f"Quotation {quote.number} declined.")
    return redirect("quotations:detail", pk=quote.pk)


def efsm_autocomplete(request):
    q = (request.GET.get("q") or "").strip()
    page = int(request.GET.get("page", 1))
    page_size = 25

    qs = Code.objects.all()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(fire_safety_measure__icontains=q))

    qs = qs.order_by("code")

    start = (page - 1) * page_size
    end = start + page_size + 1

    rows = list(qs.values("id", "code", "fire_safety_measure")[start:end])
    more = len(rows) > page_size
    rows = rows[:page_size]

    return JsonResponse(
        {
            "results": [
                {"id": r["id"], "text": f"{r['code']} - {r['fire_safety_measure']}"}
                for r in rows
            ],
            "more": more,
        }
    )


def quotation_create_for_property(request, property_id):
    prop = get_object_or_404(Property.objects.select_related("customer"), pk=property_id)
    quote = Quotation(site=prop)

    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quote)
        formset = QuotationItemFormSet(request.POST, instance=quote)

        if form.is_valid() and formset.is_valid():
            quote = form.save()
            formset.instance = quote
            formset.save()

            quote.log("created", request.user, "Quotation created.")
            messages.success(request, f"Quotation {quote.number} saved successfully.")
            return redirect("quotations:list")

        messages.error(request, "Quotation was NOT saved. Please fix the errors shown below.")

    else:
        form = QuotationForm(instance=quote)
        formset = QuotationItemFormSet(instance=quote)

    return render(
        request,
        "quotations/quotation_form.html",
        {
            "title": f"Create Quotation for {prop.site_id}",
            "property": prop,
            "form": form,
            "formset": formset,
            "cancel_url": reverse("properties:detail", kwargs={"pk": prop.pk}),
        },
    )


def quotation_update(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related("site"), pk=pk)

    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quote)
        formset = QuotationItemFormSet(request.POST, instance=quote)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            quote.log("modified", request.user, "Quotation updated.")
            messages.success(request, f"Quotation {quote.number} updated successfully.")
            return redirect("quotations:list")

        messages.error(request, "Quotation was NOT updated. Please fix the errors shown below.")

    else:
        form = QuotationForm(instance=quote)
        formset = QuotationItemFormSet(instance=quote)

    return render(
        request,
        "quotations/quotation_form.html",
        {
            "title": f"Edit {quote.number}",
            "property": quote.site,
            "form": form,
            "formset": formset,
            "cancel_url": reverse("quotations:detail", kwargs={"pk": quote.pk}),
        },
    )


class QuotationDeleteView(DeleteView):
    model = Quotation
    template_name = "quotations/quotation_confirm_delete.html"
    success_url = reverse_lazy("quotations:list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f"Quotation {obj.number} deleted.")
        return super().delete(request, *args, **kwargs)


def quotation_print_pdf(request, pk):
    quote = get_object_or_404(
        Quotation.objects.select_related("site", "site__customer")
        .prefetch_related("items", "items__efsm_code"),
        pk=pk,
    )

    client = ClientProfile.get_solo()

    subtotal = Decimal("0.00")
    for li in quote.items.all():
        subtotal += Decimal(li.line_total)

    gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    total = (subtotal + gst).quantize(Decimal("0.01"))

    template = get_template("quotations/quotation_print_pdf.html")
    html = template.render(
        {
            "item": quote,
            "client": client,
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "gst": gst,
            "total": total,
        }
    )

    result = BytesIO()
    pdf = pisa.CreatePDF(
        src=BytesIO(html.encode("utf-8")),
        dest=result,
        link_callback=_pdf_link_callback,
        encoding="utf-8",
    )

    if pdf.err:
        return HttpResponse(
            "PDF generation error. Check quotation_print_pdf.html for unsupported HTML/CSS.",
            status=500,
        )

    filename = f"Quotation-{quote.number}.pdf"
    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
