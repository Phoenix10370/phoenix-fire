from django.urls import path

from .views import (
    PropertyCreateView,
    PropertyDeleteView,
    PropertyDetailView,
    PropertyListView,
    PropertyUpdateView,
    PropertyQuotationsView,
    PropertyRoutinesView,
)

app_name = "properties"

urlpatterns = [
    path("", PropertyListView.as_view(), name="list"),
    path("new/", PropertyCreateView.as_view(), name="create"),

    path("<int:pk>/", PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/quotations/", PropertyQuotationsView.as_view(), name="quotations"),
    path("<int:pk>/routines/", PropertyRoutinesView.as_view(), name="routines"),

    path("<int:pk>/edit/", PropertyUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", PropertyDeleteView.as_view(), name="delete"),
]
