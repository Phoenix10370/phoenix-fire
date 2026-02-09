from django.contrib import admin
from .models import Technician

@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'email']