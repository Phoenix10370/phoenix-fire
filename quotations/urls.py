# quotations/urls.py
from django.urls import path
from . import views
from . import email_views

app_name = "quotations"

urlpatterns = [
    path("from-property/<int:property_id>/", views.quotation_create_for_property, name="create_for_property"),

    path("", views.QuotationListView.as_view(), name="list"),
    path("<int:pk>/", views.QuotationDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.quotation_update, name="update"),
    path("<int:pk>/delete/", views.QuotationDeleteView.as_view(), name="delete"),

    path("<int:pk>/accept/", views.quotation_accept, name="accept"),
    path("<int:pk>/reject/", views.quotation_reject, name="reject"),

    path("<int:pk>/print/pdf/", views.quotation_print_pdf, name="print_pdf"),

    path("<int:pk>/send-email/", email_views.quotation_send_email, name="send_email"),
    path("<int:pk>/microsoft/login/", email_views.microsoft_login, name="microsoft_login"),
    path("microsoft/callback/", email_views.microsoft_callback, name="microsoft_callback"),

    path("autocomplete/efsm/", views.efsm_autocomplete, name="efsm-autocomplete"),
]
