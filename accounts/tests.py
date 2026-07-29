from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse


class PublicAuthLayoutTests(TestCase):
    def test_login_uses_theme_control_without_app_navbar(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="tm-nav"')
        self.assertContains(response, "tm-public-theme-control")
        self.assertContains(response, "tm-auth-page-login")
        self.assertContains(response, "tm-auth-brand")
        self.assertContains(response, reverse("accounts:password_reset"))
        self.assertContains(response, "data-auth-form")
        self.assertContains(response, "tm-auth-spinner")
        self.assertNotContains(response, "tm-auth-story")

    def test_register_uses_theme_control_without_app_navbar(self):
        response = self.client.get(reverse("accounts:register"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="tm-nav"')
        self.assertContains(response, "tm-public-theme-control")
        self.assertContains(response, "tm-auth-page-register")
        self.assertContains(response, "tm-auth-brand")
        self.assertContains(response, "data-auth-form")
        self.assertContains(response, "tm-auth-spinner")
        self.assertNotContains(response, "tm-auth-story")

    def test_password_reset_page_uses_public_auth_layout(self):
        response = self.client.get(reverse("accounts:password_reset"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="tm-nav"')
        self.assertContains(response, "tm-public-theme-control")
        self.assertContains(response, "Reset your password")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_password_reset_sends_secure_link_for_known_email(self):
        get_user_model().objects.create_user(
            username="reset-owner",
            email="owner@example.com",
            password="old-password-123",
        )

        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "owner@example.com"},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/auth/password-reset/", mail.outbox[0].body)
        self.assertNotIn("old-password-123", mail.outbox[0].body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_password_reset_does_not_reveal_unknown_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "missing@example.com"},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
