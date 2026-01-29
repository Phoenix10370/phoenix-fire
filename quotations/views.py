# quotations/views.py
from decimal import Decimal, InvalidOperation
from io import BytesIO
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.http import FileResponse, Http404
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
from .models import (
    Quotation,
    QuotationComment,
    QuotationCorrespondence,
)


# =========================
# PDF helpers
# =========================
def _pdf_link_callback(uri, rel):
    if uri.startswith(settings.MEDIA_URL):
        return os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    if uri.startswith(settings.STATIC_URL):
        return os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    if os.path.isfile(uri):
        return uri
    return uri


# =========================
# Calculator helpers
# =========================
def _to_int(val, default=0):
    try:
        if val is None or str(val).strip() == "":
            return int(default)
        return int(Decimal(str(val)))
    except Exception:
        return int(default)


def _to_dec(val, default="0.00"):
    try:
        if val is None or str(val).strip() == "":
            return Decimal(str(default)).quantize(Decimal("0.01"))
        return Decimal(str(val)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal(str(default)).quantize(Decimal("0.01"))


def _apply_calc_post_to_quote(quote: Quotation, post):
    quote.calc_men_annual = _to_int(post.get("men_annual"), 0)
    quote.calc_hours_annual = _to_dec(post.get("hours_annual"), "0.00")
    quote.calc_price_annual = _to_dec(post.get("price_annual"), "0.00")
    quote.calc_visits_annual = _to_int(post.get("visits_annual"), 1)

    quote.calc_men_half = _to_int(post.get("men_half"), 0)
    quote.calc_hours_half = _to_dec(post.get("hours_half"), "0.00")
    quote.calc_price_half = _to_dec(post.get("price_half"), "0.00")
    quote.calc_visits_half = _to_int(post.get("visits_half"), 1)

    quote.calc_men_month = _to_int(post.get("men_month"), 0)
    quote.calc_hours_month = _to_dec(post.get("hours_month"), "0.00")
    quote.calc_price_month = _to_dec(post.get("price_month"), "0.00")
    quote.calc_visits_month = _to_int(post.get("visits_month"), 12)

    quote.calc_afss_charge = _to_dec(post.get("afss_charge"), "0.00")


CALC_UPDATE_FIELDS = [
    "calc_men_annual", "calc_hours_annual", "calc_price_annual", "calc_visits_annual",
    "calc_men_half", "calc_hours_half", "calc_price_half", "calc_visits_half",
    "calc_men_month", "calc_hours_month", "calc_price_month", "calc_visits_month",
    "calc_afss_charge",
]


# =========================
# Formset diagnostics (NEW)
# =========================
def _formset_post_diagnostics(formset, post):
    """
    Identify which submitted form index is missing `id` even though Django expects one.
    This pinpoints the exact "bad row" when you see: {'id': ['This field is required.']}
    """
    prefix = formset.prefix
    try:
        total = int(post.get(f"{prefix}-TOTAL_FORMS", 0))
    except Exception:
        total = 0
    try:
        initial = int(post.get(f"{prefix}-INITIAL_FORMS", 0))
    except Exception:
        initial = 0

    bad = []

    # For indices < INITIAL_FORMS, Django expects a non-empty id
    for i in range(total):
        id_key = f"{prefix}-{i}-id"
        del_key = f"{prefix}-{i}-DELETE"
        efsm_key = f"{prefix}-{i}-efsm_code"
        qty_key = f"{prefix}-{i}-quantity"
        unit_key = f"{prefix}-{i}-unit_price"
        pos_key = f"{prefix}-{i}-position"

        id_val = (post.get(id_key) or "").strip()
        del_val = (post.get(del_key) or "").strip()
        efsm_val = (post.get(efsm_key) or "").strip()
        qty_val = (post.get(qty_key) or "").strip()
        unit_val = (post.get(unit_key) or "").strip()
        pos_val = (post.get(pos_key) or "").strip()

        if i < initial and id_val == "":
            bad.append({
                "index": i,
                "missing": id_key,
                "DELETE": del_val,
                "efsm_code": efsm_val,
                "quantity": qty_val,
                "unit_price": unit_val,
                "position": pos_val,
            })

    return {
        "prefix": prefix,
        "TOTAL_FORMS": total,
        "INITIAL_FORMS": initial,
        "missing_id_rows": bad,
    }


# =========================
# List / Detail
# =========================
class QuotationListView(ListView):
    model = Quotation
    template_name = "quotations/quotation_list.html"
    context_object_name = "items"

    def get_queryset(self):
        return (
            Quotation.objects
            .select_related("site", "site__customer")
            .prefetch_related("items", "items__efsm_code")
        )


class QuotationDetailView(DetailView):
    model = Quotation
    template_name = "quotations/quotation_detail.html"
    context_object_name = "item"

    def get_queryset(self):
        return (
            Quotation.objects
            .select_related("site", "site__customer")
            .prefetch_related(
                "items", "items__efsm_code",
                "logs", "logs__actor",
                "comments", "comments__created_by",
                "correspondence", "correspondence__uploaded_by",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        subtotal = sum(Decimal(li.line_total) for li in self.object.items.all())
        gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
        total = (subtotal + gst).quantize(Decimal("0.01"))

        ctx.update({
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "gst": gst,
            "total": total,
            "comments": self.object.comments.all(),
            "correspondence": self.object.correspondence.all(),
        })
        return ctx


# =========================
# Comments / Correspondence
# =========================
@login_required
@require_POST
def quotation_add_comment(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)
    text = (request.POST.get("comment") or "").strip()

    if not text:
        messages.error(request, "Comment cannot be blank.")
        return redirect("quotations:detail", pk=quote.pk)

    QuotationComment.objects.create(
        quotation=quote,
        comment=text,
        created_by=request.user if getattr(request.user, "is_authenticated", False) else None,
    )

    quote.log("modified", request.user, "Comment added.")
    messages.success(request, "Comment added.")
    return redirect("quotations:detail", pk=quote.pk)


@login_required
@require_POST
def quotation_upload_correspondence(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)

    f = request.FILES.get("document")
    if not f:
        messages.error(request, "Please choose a document to upload.")
        return redirect("quotations:detail", pk=quote.pk)

    QuotationCorrespondence.objects.create(
        quotation=quote,
        document=f,
        uploaded_by=request.user if getattr(request.user, "is_authenticated", False) else None,
        original_name=getattr(f, "name", "") or "",
    )

    quote.log("modified", request.user, f"Correspondence uploaded: {getattr(f, 'name', 'document')}")
    messages.success(request, "Document uploaded.")
    return redirect("quotations:detail", pk=quote.pk)


@login_required
def quotation_download_correspondence(request, pk, doc_id):
    quote = get_object_or_404(Quotation, pk=pk)
    doc = get_object_or_404(QuotationCorrespondence, pk=doc_id, quotation=quote)

    if not doc.document:
        raise Http404("File not found.")

    try:
        fh = doc.document.open("rb")
    except Exception:
        raise Http404("File not found.")

    filename = doc.original_name or os.path.basename(doc.document.name) or "document"
    return FileResponse(fh, as_attachment=True, filename=filename)


# =========================
# Accept / Reject
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
            accepted_by_name = (
                (request.user.get_full_name() or "").strip()
                or request.user.username
            )

        quote.mark_accepted(
            request.user,
            accepted_date=accepted_date,
            accepted_by_name=accepted_by_name,
            work_order_number=work_order_number,
        )
        quote.save()

        quote.log(
            "accepted",
            request.user,
            f"Accepted. Date={accepted_date} "
            f"Accepted By={accepted_by_name} "
            f"Work Order={work_order_number or '—'}",
        )

        messages.success(request, f"Quotation {quote.number} accepted.")
        return redirect("quotations:detail", pk=quote.pk)

    return render(
        request,
        "quotations/quotation_accept.html",
        {
            "item": quote,
            "accepted_date_value": timezone.localdate().strftime("%Y-%m-%d"),
            "accepted_by_value": (
                (request.user.get_full_name() or "").strip()
                or request.user.username
            ),
            "work_order_value": "",
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


# =========================
# Autocomplete
# =========================
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

    return JsonResponse({
        "results": [
            {"id": r["id"], "text": f"{r['code']} - {r['fire_safety_measure']}"}
            for r in rows
        ],
        "more": more,
    })


# =========================
# CREATE / UPDATE
# =========================
@login_required
def quotation_create_for_property(request, property_id):
    prop = get_object_or_404(Property.objects.select_related("customer"), pk=property_id)
    quote = Quotation(site=prop)

    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quote)
        formset = QuotationItemFormSet(request.POST, instance=quote)

        if form.is_valid() and formset.is_valid():
            quote = form.save(commit=False)

            if quote.status == "draft":
                quote.status = "created"

            quote.save()

            _apply_calc_post_to_quote(quote, request.POST)
            quote.save(update_fields=CALC_UPDATE_FIELDS)

            formset.instance = quote
            formset.save()

            quote.log("created", request.user, "Quotation created.")
            messages.success(request, f"Quotation {quote.number} saved successfully.")
            return redirect("quotations:list")

        # NEW: show which row is missing id (super helpful)
        diag = _formset_post_diagnostics(formset, request.POST)
        if diag["missing_id_rows"]:
            messages.error(
                request,
                "Formset POST diagnostics: "
                f"prefix={diag['prefix']} TOTAL_FORMS={diag['TOTAL_FORMS']} INITIAL_FORMS={diag['INITIAL_FORMS']} "
                f"missing_id_rows={diag['missing_id_rows']}"
            )

        _apply_calc_post_to_quote(quote, request.POST)
        messages.error(request, "Quotation was NOT saved. Please fix the errors below.")

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


@login_required
def quotation_update(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related("site"), pk=pk)

    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quote)
        formset = QuotationItemFormSet(
            request.POST,
            instance=quote,
            queryset=quote.items.order_by("position", "id"),
        )

        if form.is_valid() and formset.is_valid():
            quote = form.save(commit=False)

            if quote.status == "draft":
                quote.status = "created"

            quote.save()
            formset.save()

            _apply_calc_post_to_quote(quote, request.POST)
            quote.save(update_fields=CALC_UPDATE_FIELDS)

            quote.log("modified", request.user, "Quotation updated.")
            messages.success(request, f"Quotation {quote.number} updated successfully.")
            return redirect("quotations:list")

        # NEW: show which row is missing id (super helpful)
        diag = _formset_post_diagnostics(formset, request.POST)
        if diag["missing_id_rows"]:
            messages.error(
                request,
                "Formset POST diagnostics: "
                f"prefix={diag['prefix']} TOTAL_FORMS={diag['TOTAL_FORMS']} INITIAL_FORMS={diag['INITIAL_FORMS']} "
                f"missing_id_rows={diag['missing_id_rows']}"
            )

        _apply_calc_post_to_quote(quote, request.POST)
        messages.error(request, "Quotation was NOT updated. Please fix the errors below.")

    else:
        form = QuotationForm(instance=quote)
        formset = QuotationItemFormSet(
            instance=quote,
            queryset=quote.items.order_by("position", "id"),
        )

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


# =========================
# DELETE / PDF
# =========================
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
        Quotation.objects
        .select_related("site", "site__customer")
        .prefetch_related("items", "items__efsm_code"),
        pk=pk,
    )

    client = ClientProfile.get_solo()

    subtotal = sum(Decimal(li.line_total) for li in quote.items.all())
    gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    total = (subtotal + gst).quantize(Decimal("0.01"))

    template = get_template("quotations/quotation_print_pdf.html")
    html = template.render({
        "item": quote,
        "client": client,
        "subtotal": subtotal.quantize(Decimal("0.01")),
        "gst": gst,
        "total": total,
    })

    result = BytesIO()
    pdf = pisa.CreatePDF(
        src=BytesIO(html.encode("utf-8")),
        dest=result,
        link_callback=_pdf_link_callback,
        encoding="utf-8",
    )

    if pdf.err:
        return HttpResponse("PDF generation error.", status=500)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Quotation-{quote.number}.pdf"'
    return response
