# company/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .models import ClientProfile
from .forms import ClientProfileForm


@login_required
def client_profile_edit(request):
    profile = ClientProfile.get_solo()

    if request.method == "POST":
        form = ClientProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Client profile updated.")
            return redirect("company:client_profile")
        messages.error(request, "Please correct the errors below.")
    else:
        form = ClientProfileForm(instance=profile)

    return render(request, "company/client_profile_form.html", {
        "title": "Client Profile",
        "form": form,
    })
