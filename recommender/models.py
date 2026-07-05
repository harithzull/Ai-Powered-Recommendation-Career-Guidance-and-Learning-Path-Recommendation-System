from django.contrib.auth.models import User
from django.db import models


class Career(models.Model):
    title = models.CharField(max_length=255, unique=True)
    industry = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    description = models.TextField(blank=True)
    work_environment = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Skill(models.Model):
    CATEGORY_CHOICES = [
        ("skill/competence", "Skill / Competence"),
        ("knowledge", "Knowledge"),
        ("", "Unspecified"),
    ]

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, blank=True, choices=CATEGORY_CHOICES)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CareerSkill(models.Model):
    LEVEL_CHOICES = [
        ("basic", "Basic"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    career = models.ForeignKey(Career, on_delete=models.CASCADE, related_name="career_skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="career_skills")
    skill_type = models.CharField(max_length=50, blank=True)
    required_level = models.CharField(max_length=50, blank=True, choices=LEVEL_CHOICES)
    importance = models.PositiveSmallIntegerField(default=0)
    is_core = models.BooleanField(default=False)

    class Meta:
        unique_together = ("career", "skill")
        ordering = ["-importance", "skill__name"]

    def __str__(self):
        return f"{self.career} — {self.skill} (importance {self.importance})"


class CachedRecommendation(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cached_recommendations")
    results_json = models.TextField()
    computed_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CachedRecommendation({self.user.username}, {self.computed_at:%Y-%m-%d %H:%M})"
