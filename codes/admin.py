from django.contrib import admin

from .models import Code, DefectCode


@admin.register(Code)
class CodeAdmin(admin.ModelAdmin):
    list_display = ("code", "fire_safety_measure", "visits_per_year")
    readonly_fields = ("code",)
    search_fields = ("code", "fire_safety_measure")
    ordering = ("code",)


@admin.register(DefectCode)
class DefectCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description")
