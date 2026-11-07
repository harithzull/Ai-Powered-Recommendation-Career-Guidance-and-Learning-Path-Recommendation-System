from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import SecurityCounter, UserProfile
from careercoach.security import WorkInProgress, consume, user_work_lock
from careercoach.test_utils import UserDataTestCase
from recommender.models import CachedRecommendation
from roadmap.models import RoadmapProgress, SavedRoadmap


class AuthenticationTests(TestCase):
    def registration(self, **changes):
        data = {"username": "newstudent", "email": "new@example.com",
                "password1": "Secure-pass-837!", "password2": "Secure-pass-837!"}
        data.update(changes)
        return self.client.post("/accounts/register/", data)

    def test_registration_hashes_password_and_logs_in(self):
        response = self.registration()
        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        user = User.objects.get(username="newstudent")
        self.assertTrue(user.check_password("Secure-pass-837!"))
        self.assertNotEqual(user.password, "Secure-pass-837!")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_invalid_registration_does_not_create_user_or_redisplay_password(self):
        response = self.registration(password2="different")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())
        self.assertNotContains(response, "Secure-pass-837!")

    def test_duplicate_username_and_bad_email_are_rejected(self):
        User.objects.create_user("newstudent")
        response = self.registration(email="invalid")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_rejected(self):
        self.registration(password1="12345678", password2="12345678")
        self.assertFalse(User.objects.exists())

    def test_login_failure_success_and_post_logout(self):
        User.objects.create_user("student", password="Secure-pass-837!")
        self.assertEqual(self.client.post("/accounts/login/", {"username": "student", "password": "wrong"}).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post("/accounts/login/", {"username": "student", "password": "Secure-pass-837!"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_private_routes_require_authentication(self):
        for url in ["/dashboard/", "/accounts/profile/", "/assessment/background/", "/assessment/interests/",
                    "/assessment/skills/", "/assessment/skill-search/", "/recommendations/", "/roadmap/1/", "/chat/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertIn("/accounts/login/", self.client.get(url).url)
        for url in ["/chat/message/", "/chat/clear/", "/assessment/interests/next/", "/assessment/retake/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 302)

    @override_settings(LOGIN_ATTEMPTS_PER_MINUTE=2)
    def test_login_limit_ignores_forged_forwarded_ip(self):
        for _ in range(2):
            self.client.post("/accounts/login/", {"username": "missing", "password": "wrong"})
        response = self.client.post("/accounts/login/", {}, HTTP_X_FORWARDED_FOR="198.51.100.2")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    @override_settings(REGISTER_ATTEMPTS_PER_HOUR=1)
    def test_registration_limit(self):
        self.registration(password2="wrong")
        self.assertEqual(self.registration().status_code, 429)
        self.assertFalse(User.objects.exists())

    def test_login_registration_csrf_and_untrusted_origin(self):
        client = Client(enforce_csrf_checks=True)
        for path in ["/accounts/login/", "/accounts/register/"]:
            with self.subTest(path=path):
                self.assertEqual(client.post(path, {}).status_code, 403)
                client.get(path)
                token = client.cookies["csrftoken"].value
                self.assertEqual(client.post(path, {}, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.example").status_code, 403)

    def test_logout_requires_csrf_and_valid_token_succeeds(self):
        user = User.objects.create_user("student", password="Secure-pass-837!")
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.post("/accounts/logout/").status_code, 403)
        self.assertIn("_auth_user_id", client.session)
        client.get("/accounts/profile/")
        response = client.post("/accounts/logout/", {}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)


class ProfileTests(UserDataTestCase):
    def test_profile_changes_are_user_scoped_and_invalidate_derived_data(self):
        for user in [self.user, self.other]:
            CachedRecommendation.objects.create(user=user, results_json="[]")
            SavedRoadmap.objects.create(user=user, career=self.career, title="Plan", steps_json="[]")
            RoadmapProgress.objects.create(user=user, career=self.career, step_index=0)
        response = self.client.post("/accounts/profile/", {
            "field_of_study": "Business", "experience_level": "Internship", "user": self.other.pk,
            "next": "https://evil.example",
        })
        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        self.assertEqual(UserProfile.objects.get(user=self.user).field_of_study, "Business")
        self.assertEqual(UserProfile.objects.get(user=self.other).field_of_study, "Computing/IT")
        for model in [CachedRecommendation, SavedRoadmap, RoadmapProgress]:
            self.assertFalse(model.objects.filter(user=self.user).exists())
            self.assertTrue(model.objects.filter(user=self.other).exists())

    def test_profile_choice_validation_preserves_previous_values(self):
        response = self.client.post("/accounts/profile/", {"field_of_study": "bad", "experience_level": "bad"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserProfile.objects.get(user=self.user).field_of_study, "Computing/IT")

    def test_same_host_next_redirect_is_preserved(self):
        response = self.client.post("/accounts/profile/", {
            "field_of_study": "Business", "experience_level": "Internship", "next": "/chat/",
        })
        self.assertRedirects(response, "/chat/", fetch_redirect_response=False)


class SecurityCounterTests(UserDataTestCase):
    def test_fixed_window_limit_expires(self):
        now = timezone.now()
        with patch("careercoach.security.timezone.now", return_value=now):
            self.assertTrue(consume("test", "identity", 1, 60))
            self.assertFalse(consume("test", "identity", 1, 60))
        with patch("careercoach.security.timezone.now", return_value=now + timedelta(seconds=61)):
            self.assertTrue(consume("test", "identity", 1, 60))

    def test_work_lock_blocks_duplicates_and_releases_on_failure(self):
        with self.assertRaises(RuntimeError):
            with user_work_lock(self.user):
                with self.assertRaises(WorkInProgress):
                    with user_work_lock(self.user):
                        self.fail("Second request acquired lock")
                raise RuntimeError("test failure")
        with user_work_lock(self.user):
            pass

    def test_expired_lock_can_be_reclaimed(self):
        now = timezone.now()
        with user_work_lock(self.user):
            with patch("careercoach.security.timezone.now", return_value=now + timedelta(minutes=6)):
                with user_work_lock(self.user):
                    pass

    def test_counter_database_error_fails_closed(self):
        from django.db import OperationalError
        with patch("careercoach.security.SecurityCounter.objects.get_or_create", side_effect=OperationalError):
            self.assertFalse(consume("test", "identity", 1, 60))

    def test_cleanup_only_deletes_expired_counters(self):
        SecurityCounter.objects.create(key="expired", expires_at=timezone.now() - timedelta(seconds=1))
        SecurityCounter.objects.create(key="active", expires_at=timezone.now() + timedelta(hours=1))
        call_command("cleanup_security_counters", stdout=StringIO())
        self.assertFalse(SecurityCounter.objects.filter(pk="expired").exists())
        self.assertTrue(SecurityCounter.objects.filter(pk="active").exists())
