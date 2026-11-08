from django.contrib.auth.models import User
from django.db import models

from recommender.models import Career


class SavedRoadmap(models.Model):
    """
    Persisted LLM-generated roadmap for a user+career pair.

    Generated once on first visit and reused on every reload so the content
    stays stable. Assessment and recommendation changes preserve the saved
    plan and learning progress; regeneration is a separate explicit action.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_roadmaps")
    career = models.ForeignKey(Career, on_delete=models.CASCADE, related_name="saved_roadmaps")
    title = models.CharField(max_length=200)
    overview = models.TextField(blank=True)
    steps_json = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "career")

    def __str__(self):
        return f"Roadmap({self.user.username} → {self.career.title})"


class RoadmapProgress(models.Model):
    """Tracks which roadmap steps a user has marked complete for a given career."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="roadmap_progress")
    career = models.ForeignKey(Career, on_delete=models.CASCADE, related_name="roadmap_progress")
    step_index = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("user", "career", "step_index")

    def __str__(self):
        return f"{self.user.username} | {self.career.title} | step {self.step_index}"
