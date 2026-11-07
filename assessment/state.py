"""Invalidate derived user data in the same transaction as its source changes."""
from recommender.models import CachedRecommendation
from roadmap.models import RoadmapProgress, SavedRoadmap

from .models import UserResponse


def is_complete(user):
    return UserResponse.objects.filter(user=user, completed_at__isnull=False).exists()


def invalidate_derived(user):
    CachedRecommendation.objects.filter(user=user).delete()
    SavedRoadmap.objects.filter(user=user).delete()
    RoadmapProgress.objects.filter(user=user).delete()
