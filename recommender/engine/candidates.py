from django.db.models import Prefetch

from recommender.models import Career, CareerSkill


def candidates():
    """All catalog careers, no inferred eligibility or demographic filtering."""
    return list(Career.objects.select_related('enrichment').prefetch_related(
        Prefetch('career_skills', queryset=CareerSkill.objects.select_related('skill').order_by('skill__name', 'pk'))
    ).order_by('title', 'pk'))
