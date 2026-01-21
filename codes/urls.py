# codes/urls.py
from django.urls import path

from .views import (
    # EFSM
    CodeCreateView,
    CodeDeleteView,
    CodeListView,
    CodeUpdateView,
    efsm_import,

    # Defects
    DefectCodeCreateView,
    DefectCodeDeleteView,
    DefectCodeListView,
    DefectCodeUpdateView,

    # Assets
    AssetCodeCreateView,
    AssetCodeDeleteView,
    AssetCodeListView,
    AssetCodeUpdateView,

    # AJAX
    asset_equipment_options,
)

from .dropdowns_views import (
    DropdownListListView,
    DropdownListCreateView,
    DropdownListUpdateView,
    DropdownListDeleteView,
    DropdownOptionListView,
    DropdownOptionCreateView,
    DropdownOptionUpdateView,
    DropdownOptionDeleteView,
)

app_name = "codes"

urlpatterns = [
    # =========================
    # EFSM Codes
    # =========================
    path("efsm/", CodeListView.as_view(), name="efsm_list"),
    path("efsm/import/", efsm_import, name="efsm_import"),
    path("efsm/new/", CodeCreateView.as_view(), name="efsm_create"),
    path("efsm/<int:pk>/edit/", CodeUpdateView.as_view(), name="efsm_update"),
    path("efsm/<int:pk>/delete/", CodeDeleteView.as_view(), name="efsm_delete"),

    # =========================
    # Defect Codes
    # =========================
    path("defects/", DefectCodeListView.as_view(), name="defect_list"),
    path("defects/new/", DefectCodeCreateView.as_view(), name="defect_create"),
    path("defects/<int:pk>/edit/", DefectCodeUpdateView.as_view(), name="defect_update"),
    path("defects/<int:pk>/delete/", DefectCodeDeleteView.as_view(), name="defect_delete"),

    # =========================
    # Asset Codes
    # =========================
    path("assets/", AssetCodeListView.as_view(), name="asset_list"),
    path("assets/new/", AssetCodeCreateView.as_view(), name="asset_create"),
    path("assets/<int:pk>/edit/", AssetCodeUpdateView.as_view(), name="asset_update"),
    path("assets/<int:pk>/delete/", AssetCodeDeleteView.as_view(), name="asset_delete"),

    # AJAX for dependent equipment dropdown
    path("assets/equipment-options/", asset_equipment_options, name="asset_equipment_options"),

    # =========================
    # Dropdown Settings
    # =========================
    path("settings/dropdowns/", DropdownListListView.as_view(), name="dropdown_list_list"),
    path("settings/dropdowns/new/", DropdownListCreateView.as_view(), name="dropdown_list_create"),
    path("settings/dropdowns/<int:pk>/edit/", DropdownListUpdateView.as_view(), name="dropdown_list_update"),
    path("settings/dropdowns/<int:pk>/delete/", DropdownListDeleteView.as_view(), name="dropdown_list_delete"),

    path("settings/dropdowns/<int:list_id>/options/", DropdownOptionListView.as_view(), name="dropdown_option_list"),
    path("settings/dropdowns/<int:list_id>/options/new/", DropdownOptionCreateView.as_view(), name="dropdown_option_create"),
    path("settings/dropdowns/options/<int:pk>/edit/", DropdownOptionUpdateView.as_view(), name="dropdown_option_update"),
    path("settings/dropdowns/options/<int:pk>/delete/", DropdownOptionDeleteView.as_view(), name="dropdown_option_delete"),
]
