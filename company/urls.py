# company/urls.py
from django.urls import path
from .views import client_profile_edit

app_name = "company"

urlpatterns = [
    path("client/", client_profile_edit, name="client_profile"),
]
