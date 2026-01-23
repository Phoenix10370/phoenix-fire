import csv
import io
import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ContactForm, CustomerForm, SiteForm, CustomerImportForm
from .models import Contact, Customer, Site


# ======================
# Customers CRUD
# ======================

class CustomerListView(ListView):
    model = Customer
    template_name = "customers/customer_list.html"
    context_object_name = "items"

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.GET.get("q") or "").strip()

        if q:
            qs = qs.filter(
                Q(customer_name__icontains=q)
                | Q(customer_address__icontains=q)
                | Q(customer_contact_name__icontains=q)
                | Q(billing_email__icontains=q)
                | Q(add_email__icontains=q)
                | Q(customer_main_phone__icontains=q)
                | Q(add_phone__icontains=q)
                | Q(company_code__icontains=q)
                | Q(accounting_id__icontains=q)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        return ctx


class CustomerDetailView(DetailView):
    model = Customer
    template_name = "customers/customer_detail.html"
    context_object_name = "item"


class CustomerCreateView(CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.object.pk})


class CustomerUpdateView(UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.object.pk})


class CustomerDeleteView(DeleteView):
    model = Customer
    template_name = "customers/customer_delete.html"
    success_url = reverse_lazy("customers:list")


# ======================
# Customers: Bulk Delete (NEW)
# ======================

class CustomerBulkDeleteView(View):
    """
    Deletes multiple customers selected on the Customer List page.
    Expects POST with ids=<pk> repeated (checkbox list).
    """
    def post(self, request):
        ids = request.POST.getlist("ids")

        if not ids:
            messages.warning(request, "No customers selected.")
            return redirect("customers:list")

        deleted_count, _ = Customer.objects.filter(pk__in=ids).delete()
        messages.success(request, f"Deleted {deleted_count} customer(s).")
        return redirect("customers:list")


# ======================
# CSV Import
# ======================

class CustomerImportView(View):
    template_name = "customers/customer_import.html"

    def get(self, request):
        form = CustomerImportForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = CustomerImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        uploaded = form.cleaned_data["file"]

        if not uploaded.name.lower().endswith(".csv"):
            form.add_error("file", "Please upload a .csv file.")
            return render(request, self.template_name, {"form": form})

        try:
            data = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            form.add_error("file", "Could not read file. Please save CSV as UTF-8.")
            return render(request, self.template_name, {"form": form})

        reader = csv.DictReader(io.StringIO(data))
        if not reader.fieldnames:
            form.add_error("file", "CSV file has no header row.")
            return render(request, self.template_name, {"form": form})

        def norm(s):
            return (s or "").strip().lower()

        header_map = {norm(h): h for h in reader.fieldnames}

        if "customer_name" not in header_map:
            form.add_error("file", "CSV must include a 'customer_name' column.")
            return render(request, self.template_name, {"form": form})

        rows = list(reader)
        if not rows:
            form.add_error("file", "CSV has no data rows.")
            return render(request, self.template_name, {"form": form})

        customer_type_map = {
            "strata": getattr(Customer, "TYPE_STRATA", "Strata"),
            "government": getattr(Customer, "TYPE_GOV", "Government"),
            "housing": getattr(Customer, "TYPE_HOUSING", "Housing"),
            "other": getattr(Customer, "TYPE_OTHER", "Other"),
        }

        billing_type_map = {
            "factored": getattr(Customer, "BILLING_FACTORED", "Factored"),
            "non factored": getattr(Customer, "BILLING_NON_FACTORED", "Non Factored"),
            "non-factored": getattr(Customer, "BILLING_NON_FACTORED", "Non Factored"),
            "non_factored": getattr(Customer, "BILLING_NON_FACTORED", "Non Factored"),
            "cash": getattr(Customer, "BILLING_CASH", "Cash"),
            "bartercard": getattr(Customer, "BILLING_BARTERCARD", "Bartercard"),
        }

        to_create = []
        errors = []

        for i, row in enumerate(rows, start=2):
            name = (row.get(header_map["customer_name"]) or "").strip()
            if not name:
                errors.append(f"Row {i}: customer_name is required.")
                continue

            ctype_raw = (row.get(header_map.get("customer_type", "")) or "").strip().lower()
            customer_type = customer_type_map.get(ctype_raw, customer_type_map["other"])

            btype_raw = (row.get(header_map.get("billing_type", "")) or "").strip().lower()
            billing_type = billing_type_map.get(btype_raw, billing_type_map.get("factored", "Factored"))

            is_active_raw = (row.get(header_map.get("is_active", "")) or "").strip().lower()
            is_active = True if not is_active_raw else is_active_raw in ["1", "true", "yes", "y", "active"]

            obj = Customer(
                customer_name=name,
                customer_type=customer_type,
                customer_address=(row.get(header_map.get("customer_address", "")) or "").strip(),
                customer_contact_name=(row.get(header_map.get("customer_contact_name", "")) or "").strip(),
                customer_main_phone=(row.get(header_map.get("customer_main_phone", "")) or "").strip(),
                billing_email=(row.get(header_map.get("billing_email", "")) or "").strip(),
                add_email=(row.get(header_map.get("add_email", "")) or "").strip(),
                add_phone=(row.get(header_map.get("add_phone", "")) or "").strip(),
                customer_abn_acn=(row.get(header_map.get("customer_abn_acn", "")) or "").strip(),
                notes=(row.get(header_map.get("notes", "")) or "").strip(),
                is_active=is_active,
                billing_type=billing_type,
            )

            # ✅ AUTO-GENERATE COMPANY CODE FOR IMPORT
            obj.company_code = uuid.uuid4().hex[:12].upper()

            try:
                obj.full_clean()
            except ValidationError as e:
                errors.append(f"Row {i}: {e}")
                continue

            to_create.append(obj)

        if errors:
            return render(request, self.template_name, {"form": form, "errors": errors})

        try:
            with transaction.atomic():
                Customer.objects.bulk_create(to_create)
        except Exception as e:
            return render(
                request,
                self.template_name,
                {"form": form, "errors": [f"Import failed: {e}"]},
            )

        messages.success(request, f"Imported {len(to_create)} customers successfully.")
        return redirect("customers:list")


# ======================
# CSV Template Download
# ======================

class CustomerImportTemplateView(View):
    def get(self, request):
        headers = [
            "customer_name",
            "customer_type",
            "customer_address",
            "customer_contact_name",
            "customer_main_phone",
            "billing_email",
            "add_email",
            "add_phone",
            "customer_abn_acn",
            "billing_type",
            "is_active",
            "notes",
        ]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="customers_import_template.csv"'

        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerow([
            "ACME Corp",
            "Strata",
            "123 Sample St",
            "John Smith",
            "0412345678",
            "billing@acme.com",
            "",
            "",
            "12 345 678 901",
            "Factored",
            "true",
            "Imported via CSV",
        ])

        return response


# ======================
# Sites (nested)
# ======================

class SiteCreateView(CreateView):
    model = Site
    form_class = SiteForm
    template_name = "customers/site_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs["customer_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.customer = self.customer
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.customer.pk})


class SiteUpdateView(UpdateView):
    model = Site
    form_class = SiteForm
    template_name = "customers/site_form.html"
    pk_url_kwarg = "site_pk"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs["customer_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Site.objects.filter(customer=self.customer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.customer.pk})


class SiteDeleteView(DeleteView):
    model = Site
    template_name = "customers/site_delete.html"
    pk_url_kwarg = "site_pk"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs["customer_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Site.objects.filter(customer=self.customer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.customer.pk})


# ======================
# Contacts (nested)
# ======================

class ContactCreateView(CreateView):
    model = Contact
    form_class = ContactForm
    template_name = "customers/contact_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs["customer_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.customer = self.customer
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.customer.pk})


class ContactUpdateView(UpdateView):
    model = Contact
    form_class = ContactForm
    template_name = "customers/contact_form.html"
    pk_url_kwarg = "contact_pk"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs["customer_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Contact.objects.filter(customer=self.customer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.customer.pk})


class ContactDeleteView(DeleteView):
    model = Contact
    template_name = "customers/contact_delete.html"
    pk_url_kwarg = "contact_pk"

    def dispatch(self, request, *args, **kwargs):
        self.customer = get_object_or_404(Customer, pk=kwargs["customer_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Contact.objects.filter(customer=self.customer)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["customer"] = self.customer
        return ctx

    def get_success_url(self):
        return reverse_lazy("customers:detail", kwargs={"pk": self.customer.pk})
