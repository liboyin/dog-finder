"""Public creation and private, scanner-safe search lifecycle pages."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_safe

from . import services, tokens
from .forms import SearchForm


@require_http_methods(["GET", "POST"])
@never_cache
@sensitive_post_parameters()
def create(request: HttpRequest) -> HttpResponse:
    """Validate submissions without exposing subscriber status or private links."""
    if not settings.SEARCH_REGISTRATION_ENABLED:
        return render(
            request,
            "subscriptions/message.html",
            {"message": "Registration is not open yet."},
            status=503,
        )
    form = SearchForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        services.request_search(
            form.cleaned_data, request.META.get("REMOTE_ADDR", "unknown"), timezone.now()
        )
        return redirect("search-requested")
    return render(request, "subscriptions/create.html", {"form": form})


@require_safe
@never_cache
def requested(request: HttpRequest) -> HttpResponse:
    """Show the same receipt for accepted, suppressed, limited, and duplicate addresses."""
    return render(
        request,
        "subscriptions/message.html",
        {
            "message": "Check your inbox. If your request can be accepted, a confirmation email will arrive."
        },
    )


@require_http_methods(["GET", "POST"])
@never_cache
def confirm(request: HttpRequest, token: str) -> HttpResponse:
    """Display a confirmation on GET and activate only on a CSRF-protected POST."""
    search = tokens.resolve(token, "confirmation")
    if search is None:
        return render(
            request,
            "subscriptions/message.html",
            {"message": "This link is invalid or expired. Create a new search."},
            status=410,
        )
    message = ""
    if request.method == "POST":
        search, message = services.activate(search.pk, search.confirmation_version, timezone.now())
        if not message:
            return redirect("search-manage", token=tokens.issue(search, "management"))
    return render(request, "subscriptions/confirm.html", {"search": search, "message": message})


@require_safe
@never_cache
def manage(request: HttpRequest, token: str) -> HttpResponse:
    """Expose only one search and a masked email to its management credential."""
    search = tokens.resolve(token, "management")
    if search is None:
        return render(
            request,
            "subscriptions/message.html",
            {"message": "This link is unavailable."},
            status=410,
        )
    return render(
        request,
        "subscriptions/manage.html",
        {
            "search": search,
            "token": token,
            "masked_email": "***@" + search.subscriber.email.rsplit("@", 1)[1],
        },
    )


@require_http_methods(["GET", "POST"])
@never_cache
def cancel(request: HttpRequest, token: str) -> HttpResponse:
    """Require an explicit button press to cancel; scanner GETs have no effects."""
    search = tokens.resolve(token, "management")
    if search is None:
        return render(
            request,
            "subscriptions/message.html",
            {"message": "This link is unavailable."},
            status=410,
        )
    if request.method == "POST":
        services.cancel(search.pk, timezone.now())
        return redirect("search-manage", token=token)
    return render(request, "subscriptions/cancel.html", {"search": search})
