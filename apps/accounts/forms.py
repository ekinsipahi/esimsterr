from django import forms
from django.contrib.auth import authenticate, password_validation

from .models import User


class SignupForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    marketing_opt_in = forms.BooleanField(required=False, initial=True)
    # Optional, and never a reason to reject a registration: a mistyped code
    # must cost somebody a bonus, not an account. Validated after the user
    # exists, where it can be reported without losing the form.
    referral_code = forms.CharField(required=False, max_length=16)

    def clean_referral_code(self):
        return (self.cleaned_data.get("referral_code") or "").strip().upper()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Sign in instead.")
        return email

    def clean_password(self):
        pw = self.cleaned_data["password"]
        password_validation.validate_password(pw)
        return pw


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        email = (data.get("email") or "").strip().lower()
        pw = data.get("password") or ""
        if email and pw:
            user = authenticate(self.request, username=email, password=pw)
            if user is None:
                existing = User.objects.filter(email__iexact=email).first()
                if existing and not existing.has_usable_password():
                    raise forms.ValidationError(
                        "This account was created with Google. Use the Google button to sign in."
                    )
                raise forms.ValidationError("Incorrect email or password.")
            if not user.is_active:
                raise forms.ValidationError("This account is disabled.")
            self.user = user
        return data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["display_name", "marketing_opt_in"]


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput, required=False)
    new_password = forms.CharField(widget=forms.PasswordInput, min_length=8)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if self.user.has_usable_password():
            if not self.user.check_password(data.get("current_password") or ""):
                raise forms.ValidationError("Current password is incorrect.")
        password_validation.validate_password(data.get("new_password") or "", self.user)
        return data
