from django.conf import settings


def google_maps(request):
    """
    Expose GOOGLE_MAPS_API_KEY to templates.

    Used by the Property form to load Google Places Autocomplete.
    """
    return {
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
    }
