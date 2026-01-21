# company/context_processors.py
from .models import ClientProfile

def client_profile(request):
    try:
        return {"client_profile": ClientProfile.get_solo()}
    except Exception:
        return {"client_profile": None}
