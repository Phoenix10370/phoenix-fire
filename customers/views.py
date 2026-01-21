from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ContactForm, CustomerForm, SiteForm
from .models import Contact, Customer, Site


# ======================
# Customers CRUD
# ======================

class CustomerListView(ListView):
    model = Customer
    template_name = "customers/customer_list.html"
    context_object_name = "items"


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
