# properties/utils.py

from __future__ import annotations

from .models import Property


def build_property_tab_counts(prop: Property) -> dict[str, int]:
    if not prop:
        return {
            "job_tasks": 0,
            "quotations": 0,
            "routines": 0,
            "assets": 0,
        }

    return {
        "job_tasks": prop.job_tasks.count(),
        "quotations": prop.quotations.count(),
        "routines": prop.service_routines.count(),
        "assets": prop.site_assets.count(),
    }
