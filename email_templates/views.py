# email_templates/views.py
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import EmailTemplateForm
from .models import EmailTemplate


class EmailTemplateListView(ListView):
    model = EmailTemplate
    template_name = "email_templates/emailtemplate_list.html"
    context_object_name = "items"

    def get_queryset(self):
        return EmailTemplate.objects.order_by("-updated_at")


class EmailTemplateCreateView(CreateView):
    model = EmailTemplate
    form_class = EmailTemplateForm
    template_name = "email_templates/emailtemplate_form.html"
    success_url = reverse_lazy("email_templates:list")

    def form_valid(self, form):
        messages.success(self.request, "Email template created.")
        return super().form_valid(form)


class EmailTemplateUpdateView(UpdateView):
    model = EmailTemplate
    form_class = EmailTemplateForm
    template_name = "email_templates/emailtemplate_form.html"
    success_url = reverse_lazy("email_templates:list")

    def form_valid(self, form):
        messages.success(self.request, "Email template updated.")
        return super().form_valid(form)


class EmailTemplateDeleteView(DeleteView):
    model = EmailTemplate
    template_name = "email_templates/emailtemplate_confirm_delete.html"
    success_url = reverse_lazy("email_templates:list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Email template deleted.")
        return super().delete(request, *args, **kwargs)
