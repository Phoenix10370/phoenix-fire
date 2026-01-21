from django.urls import path

from .views import (
    PropertyCreateView,
    PropertyDeleteView,
    PropertyDetailView,
    PropertyListView,
    PropertyUpdateView,
)

app_name = "properties"

urlpatterns = [
    path("", PropertyListView.as_view(), name="list"),
    path("new/", PropertyCreateView.as_view(), name="create"),
    path("<int:pk>/", PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", PropertyUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", PropertyDeleteView.as_view(), name="delete"),
]
