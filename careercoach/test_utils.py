from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserProfile
from assessment.models import RIASECAnswer, RIASECQuestion, SkillRating, UserResponse
from recommender.models import Career


class UserDataTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("student", "student@example.com", "Secure-pass-837!")
        cls.other = User.objects.create_user("other", "other@example.com", "Secure-pass-837!")
        cls.career = Career.objects.create(title="Software developer", industry="Technology", summary="Build software")
        cls.questions = [RIASECQuestion.objects.filter(riasec_type=t).first() for t in "RIASEC"]
        for user in [cls.user, cls.other]:
            UserProfile.objects.create(user=user, field_of_study="Computing/IT", experience_level="No experience")
            response = UserResponse.objects.create(user=user, completed_at=timezone.now())
            RIASECAnswer.objects.bulk_create([
                RIASECAnswer(response=response, question=q, rating=4) for q in cls.questions
            ])
            SkillRating.objects.create(response=response, skill_name="Programming", rating=3)

    def setUp(self):
        self.client.force_login(self.user)

    def answers(self):
        return [{"id": q.pk, "rating": 4} for q in self.questions]
