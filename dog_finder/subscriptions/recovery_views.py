"""Public recovery request and private address-wide dashboard pages."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_safe

from . import recovery, tokens
from .forms import RecoveryForm


@require_http_methods(["GET", "POST"])
@never_cache
@sensitive_post_parameters()
def request_recovery(request: HttpRequest) -> HttpResponse:
    """Offer the same public receipt for all syntactically valid addresses."""
    if not settings.SEARCH_REGISTRATION_ENABLED:
        return render(
            request,
            "subscriptions/message.html",
            {"message": "Recovery is not open yet."},
            status=503,
        )
    form = RecoveryForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        recovery.request_recovery(
            form.cleaned_data["email"], request.META.get("REMOTE_ADDR", "unknown"), timezone.now()
        )
        return redirect("recovery-requested")
    return render(request, "subscriptions/recovery_request.html", {"form": form})


@require_safe
@never_cache
def requested(request: HttpRequest) -> HttpResponse:
    """Keep subscriber existence, suppression, and rate-limit outcomes private."""
    return render(
        request,
        "subscriptions/message.html",
        {"message": "Check your inbox. If recovery is available, an email will arrive."},
    )


@require_http_methods(["GET", "POST"])
@never_cache
def confirm(request: HttpRequest, token: str) -> HttpResponse:
    """Require an explicit protected action before consuming a recovery link."""
    subscriber = (
        recovery.consume(token, replace_links=request.POST.get("replace_links") == "yes")
        if request.method == "POST"
        else recovery.resolve(token, "recovery")
    )
    if subscriber is None:
        return render(
            request,
            "subscriptions/message.html",
            {
                "message": "This recovery link is unavailable. Request a new link from Find my alerts."
            },
            status=410,
        )
    if request.method == "POST":
        return redirect("address-manage", token=recovery.issue(subscriber, "address"))
    return render(request, "subscriptions/recovery_confirm.html")


@require_safe
@never_cache
def manage(request: HttpRequest, token: str) -> HttpResponse:
    """Expose only this address's active searches and renewable expired searches."""
    subscriber = recovery.resolve(token, "address")
    if subscriber is None:
        return render(
            request,
            "subscriptions/message.html",
            {"message": "This link is unavailable."},
            status=410,
        )
    now = timezone.now()
    entries = [
        {
            "search": search,
            "token": tokens.issue(search, "management"),
            "expired": search.expires_at <= now,
        }
        for search in recovery.available(subscriber, now)
    ]
    return render(
        request,
        "subscriptions/address_manage.html",
        {
            "entries": entries,
            "masked_email": "***@" + subscriber.email.rsplit("@", 1)[1],
        },
    )
