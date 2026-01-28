from django.contrib import admin

from .models import JobTask, JobTaskItem, JobServiceType


@admin.register(JobServiceType)
class JobServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


class JobTaskItemInline(admin.TabularInline):
    model = JobTaskItem
    extra = 0


@admin.register(JobTask)
class JobTaskAdmin(admin.ModelAdmin):
    inlines = [JobTaskItemInline]

    list_display = (
        "id",
        "title",
        "status",
        "site",
        "customer",
        "service_date",
        "service_type",
        "service_technician",
        "created_at",
    )

    list_filter = ("status", "service_type", "service_date")

    # ✅ keep this anyway (useful for admin search box)
    search_fields = ("title", "description")
