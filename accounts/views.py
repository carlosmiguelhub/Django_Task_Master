from django.contrib.auth import login, logout
from django.shortcuts import render, redirect

from .forms import RegisterForm, LoginForm


def register_view(request):
    # if request.user.is_authenticated:
    #     return redirect("/app/dashboard/")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.save()

            login(request, user)
            return redirect("/app/dashboard/")
    else:
        form = RegisterForm()

    return render(request, "accounts/register_modern.html", {"form": form})


def login_view(request):
    # if request.user.is_authenticated:
    #     return redirect("/app/dashboard/")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            if not request.POST.get("remember_me"):
                request.session.set_expiry(0)
            return redirect("/app/dashboard/")
    else:
        form = LoginForm()

    return render(request, "accounts/login_modern.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("/")
