from django.urls import path
from .views_equipment_optional_fields import (
    EquipmentOptionalFieldListView,
    EquipmentOptionalFieldEditView,
)

app_name = "codes"

urlpatterns = [
    path("equipment-optional-fields/", EquipmentOptionalFieldListView.as_view(), name="eof_list"),
    path("equipment-optional-fields/<int:pk>/edit/", EquipmentOptionalFieldEditView.as_view(), name="eof_edit"),
]
