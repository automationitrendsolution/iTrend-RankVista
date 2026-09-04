"""Authentication and user-administration forms.
All validation lives here so views stay thin and never trust the client."""

from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import Role, User

INPUT_CLASS = "rv-input"


class LoginForm(forms.Form):
    """Email/username plus password, with an optional persistent session."""

    identifier = forms.CharField(
        label="Email or username",
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "you@company.com",
                "autocomplete": "username",
                "autofocus": "autofocus",
                "spellcheck": "false",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": INPUT_CLASS,
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )
    remember_me = forms.BooleanField(label="Keep me signed in", required=False, initial=True)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user: User | None = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        identifier = (cleaned.get("identifier") or "").strip()
        password = cleaned.get("password") or ""
        if not identifier or not password:
            return cleaned

        email = identifier.lower()
        if "@" not in identifier:
            match = User.objects.filter(username__iexact=identifier).values_list("email", flat=True)
            email = match[0] if match else identifier.lower()

        user = authenticate(self.request, username=email, password=password)
        if user is None:
            raise ValidationError("Incorrect email or password. Please try again.", code="invalid")
        if not user.is_active or user.is_deleted:
            raise ValidationError(
                "This account has been deactivated. Contact your administrator.", code="inactive"
            )
        self.user = user
        return cleaned


class UserCreateForm(forms.ModelForm):
    """Create a platform user with a validated initial password."""

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["email", "username", "full_name", "role", "is_active"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS, "placeholder": "user@company.com"}),
            "username": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "jdoe"}),
            "full_name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Jane Doe"}),
            "role": forms.Select(attrs={"class": "rv-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "rv-check"}),
        }

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserUpdateForm(forms.ModelForm):
    """Edit an existing user without ever touching the password hash."""

    class Meta:
        model = User
        fields = ["email", "username", "full_name", "role", "is_active"]
        widgets = UserCreateForm.Meta.widgets

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This username is already taken.")
        return username


class PasswordResetForm(forms.Form):
    """Administrator-initiated password reset for another account."""

    password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            try:
                validate_password(p1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class ProfileForm(forms.ModelForm):
    """Self-service profile fields. Role and status are deliberately excluded."""

    class Meta:
        model = User
        fields = ["full_name", "username"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "username": forms.TextInput(attrs={"class": INPUT_CLASS}),
        }

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This username is already taken.")
        return username


class ChangePasswordForm(forms.Form):
    """Self-service password change requiring the current password."""

    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "current-password"})
    )
    password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS, "autocomplete": "new-password"}),
    )

    def __init__(self, user: User, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self) -> str:
        value = self.cleaned_data["current_password"]
        if not self.user.check_password(value):
            raise ValidationError("Your current password is incorrect.")
        return value

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        elif p1:
            try:
                validate_password(p1, user=self.user)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


ROLE_CHOICES = Role.choices
