from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

from .views import dashboard


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", dashboard, name="dashboard"),
    path("dashboard/", dashboard, name="dashboard_alt"),

    path("codes/", include("codes.urls")),
    path("customers/", include("customers.urls")),
    path("properties/", include("properties.urls")),
    path("quotations/", include("quotations.urls")),
    path("routines/", include("routines.urls")),
    path("company/", include("company.urls")),
    path("email-templates/", include("email_templates.urls")),
]

# ✅ Serve uploaded media (logos) in local dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
