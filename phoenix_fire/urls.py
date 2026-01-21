from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views import dashboard


def healthcheck(request):
    return dashboard(request)


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", healthcheck, name="dashboard"),
    path("dashboard/", dashboard, name="dashboard"),

    path("codes/", include("codes.urls")),
    path("customers/", include("customers.urls")),
    path("properties/", include("properties.urls")),
    path("quotations/", include("quotations.urls")),
    path("routines/", include("routines.urls")),
    path("company/", include("company.urls")),
    path("email-templates/", include("email_templates.urls")),
]

# ✅ IMPORTANT: Render needs Django to serve /media/ unless using S3/Cloudinary
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
