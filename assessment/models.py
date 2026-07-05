from django.db import models
from django.contrib.auth.models import User

RIASEC_TYPES = [
    ("R", "Realistic"),
    ("I", "Investigative"),
    ("A", "Artistic"),
    ("S", "Social"),
    ("E", "Enterprising"),
    ("C", "Conventional"),
]

RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

FIXED_SKILLS = [
    "Programming",
    "Data Analysis",
    "Statistics",
    "Writing",
    "Communication",
    "Design",
    "Project Management",
    "Problem Solving",
    "Research",
    "Teamwork",
    "Marketing",
    "Financial Literacy",
]


class RIASECQuestion(models.Model):
    text = models.TextField()
    riasec_type = models.CharField(max_length=1, choices=RIASEC_TYPES)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"[{self.riasec_type}] {self.text[:60]}"


class UserResponse(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="assessment_response")
    submitted_at = models.DateTimeField(auto_now=True)
    free_text_skills = models.TextField(blank=True)

    def __str__(self):
        return f"Response for {self.user.username} ({self.submitted_at:%Y-%m-%d})"


class RIASECAnswer(models.Model):
    response = models.ForeignKey(UserResponse, on_delete=models.CASCADE, related_name="riasec_answers")
    question = models.ForeignKey(RIASECQuestion, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)

    class Meta:
        unique_together = ("response", "question")

    def __str__(self):
        return f"{self.response.user.username} — Q{self.question.id}: {self.rating}"


class SkillRating(models.Model):
    response = models.ForeignKey(UserResponse, on_delete=models.CASCADE, related_name="skill_ratings")
    skill_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)

    class Meta:
        unique_together = ("response", "skill_name")

    def __str__(self):
        return f"{self.response.user.username} — {self.skill_name}: {self.rating}"
