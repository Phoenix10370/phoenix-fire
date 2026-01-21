# email_templates/urls.py
from django.urls import path

from .views import (
    EmailTemplateListView,
    EmailTemplateCreateView,
    EmailTemplateUpdateView,
    EmailTemplateDeleteView,
)

app_name = "email_templates"

urlpatterns = [
    path("", EmailTemplateListView.as_view(), name="list"),
    path("new/", EmailTemplateCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", EmailTemplateUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", EmailTemplateDeleteView.as_view(), name="delete"),
]
