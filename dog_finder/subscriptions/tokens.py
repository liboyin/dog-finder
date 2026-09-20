"""Purpose-scoped signed credentials with revocation versions stored on searches."""

from django.core import signing
from django.core.exceptions import ValidationError

from .models import Search


def issue(search: Search, purpose: str) -> str:
    """Create a confirmation or management credential without including personal data."""
    version = getattr(search, f"{purpose}_version")
    return signing.dumps({"id": str(search.pk), "version": str(version)}, salt=f"search.{purpose}")


def resolve(token: str, purpose: str) -> Search | None:
    """Resolve valid scoped credentials; treat malformed, revoked, and deleted alike."""
    try:
        data = signing.loads(
            token,
            salt=f"search.{purpose}",
            max_age=7 * 86400 if purpose == "confirmation" else None,
        )
        return (
            Search.objects.select_related("subscriber")
            .filter(pk=data["id"], **{f"{purpose}_version": data["version"]})
            .first()
        )
    except (signing.BadSignature, KeyError, TypeError, ValidationError):
        return None
