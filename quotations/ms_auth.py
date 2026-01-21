import msal
from django.conf import settings


def _build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        client_id=settings.MS_CLIENT_ID,
        authority=settings.MS_AUTHORITY,
        client_credential=settings.MS_CLIENT_SECRET,
        token_cache=cache,
    )


def build_auth_url(request):
    app = _build_msal_app()

    flow = app.initiate_auth_code_flow(
        scopes=settings.MS_GRAPH_SCOPES,
        redirect_uri=settings.MS_REDIRECT_URI,
    )

    request.session["msal_flow"] = flow
    return flow["auth_uri"]


def acquire_token_by_auth_code_flow(request, query_params):
    flow = request.session.get("msal_flow")
    if not flow:
        return None

    app = _build_msal_app()
    result = app.acquire_token_by_auth_code_flow(flow, query_params)

    # result contains access_token, expires_in, id_token_claims, etc.
    return result
