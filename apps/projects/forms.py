"""Project create/edit validation. All rules run server-side."""

from __future__ import annotations

import re

from django import forms

from apps.common.constants import MARKETPLACES

ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
INPUT_CLASS = "rv-input"


class ProjectForm(forms.Form):
    """Fields backing the create and edit project dialogs."""

    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "e.g. Snow Cover Keyword Analysis"}
        ),
    )
    marketplace = forms.ChoiceField(
        choices=[(code, f"{meta['label']}") for code, meta in MARKETPLACES.items()],
        widget=forms.Select(attrs={"class": "rv-select"}),
    )
    primary_asin = forms.CharField(
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "B0CF1NXT25",
                "spellcheck": "false",
                "maxlength": "10",
            }
        ),
    )
    image_url = forms.URLField(
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(
            attrs={"class": INPUT_CLASS, "placeholder": "https://images.example.com/product.jpg"}
        ),
    )
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASS, "placeholder": "Comma-separated labels"}
        ),
    )

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if len(name) < 3:
            raise forms.ValidationError("Project name must be at least 3 characters.")
        return name

    def clean_primary_asin(self) -> str:
        asin = self.cleaned_data["primary_asin"].strip().upper()
        if not ASIN_PATTERN.match(asin):
            raise forms.ValidationError("An ASIN is exactly 10 letters or digits.")
        return asin

    def clean_tags(self) -> list[str]:
        raw = self.cleaned_data.get("tags") or ""
        return [tag.strip() for tag in raw.split(",") if tag.strip()][:10]

    def to_document(self) -> dict[str, object]:
        """Shape validated input into the project document written to Mongo."""
        data = self.cleaned_data
        return {
            "name": data["name"],
            "marketplace": data["marketplace"],
            "primary_asin": data["primary_asin"],
            "image_url": data.get("image_url") or "",
            "tags": data.get("tags") or [],
        }
