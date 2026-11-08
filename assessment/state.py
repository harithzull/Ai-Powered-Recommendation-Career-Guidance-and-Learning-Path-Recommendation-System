"""Invalidate derived user data in the same transaction as its source changes."""
from recommender.models import CachedRecommendation

from .models import UserResponse


def is_complete(user):
    return UserResponse.objects.filter(user=user, completed_at__isnull=False).exists()


def invalidate_derived(user):
    """Refresh recommendations while preserving user-authored roadmap progress/history."""
    CachedRecommendation.objects.filter(user=user).delete()
