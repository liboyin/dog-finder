"""Server-side criteria validation shared by the initial public form."""

from django import forms

from .models import Postcode

STATES = [(s, s) for s in ("ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA")]


class SearchForm(forms.Form):
    """Validate criteria without revealing anything about the supplied address."""

    email = forms.EmailField(max_length=254)
    postcode = forms.RegexField(r"^[0-9]{4}$", max_length=4, label="Home postcode")
    state = forms.ChoiceField(
        choices=[("", "Choose if your postcode spans states")] + STATES,
        required=False,
        label="State or territory (only needed for shared postcodes)",
    )
    interstate = forms.TypedChoiceField(
        choices=[("", "Choose one"), ("yes", "Yes"), ("no", "No")],
        coerce=lambda value: value == "yes",
        label="Include interstate adoption",
    )
    name = forms.RegexField(r"^[^\x00-\x1f\x7f]+$", max_length=100, strip=True, label="Search name")
    description = forms.CharField(
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="What you are looking for",
        help_text=(
            "AI will assess this description. Include the preferences that matter most. "
            "Example: A calm, low-shedding small adult dog for an apartment with a cat. "
            "Avoid names, contact details, and sensitive personal information."
        ),
    )

    def clean(self) -> dict:
        """Resolve only known postcode/state pairs, retaining ambiguity for the user."""
        cleaned = super().clean()
        code = cleaned.get("postcode")
        if code:
            states = list(Postcode.objects.filter(code=code).values_list("state", flat=True))
            if not states:
                self.add_error("postcode", "Enter a known Australian postcode.")
            elif cleaned.get("state"):
                if cleaned["state"] not in states:
                    self.add_error("state", "Choose a state belonging to that postcode.")
            elif len(states) == 1:
                cleaned["state"] = states[0]
            else:
                self.add_error("state", "This postcode spans states. Choose your home state.")
        return cleaned


class EditSearchForm(SearchForm):
    """Reuse criteria validation without allowing the owner address to change."""

    email = None
    edit_version = forms.UUIDField(widget=forms.HiddenInput)


class RecoveryForm(forms.Form):
    """Validate a recovery address without disclosing whether it has searches."""

    email = forms.EmailField(max_length=254)
