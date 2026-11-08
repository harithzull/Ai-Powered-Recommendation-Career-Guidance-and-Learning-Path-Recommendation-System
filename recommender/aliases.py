"""Exact reviewed aliases supplement canonical lookup; they do not change scoring."""
from .models import ReviewStatus, Skill, SkillAlias
from .normalization import normalize_label


def resolve_skill_name(value):
    key = normalize_label(value)
    matches = [skill for skill in Skill.objects.all() if normalize_label(skill.name) == key]
    if len(matches) == 1:
        return {"skill": matches[0], "match": "canonical"}
    if matches:
        return None  # Existing ambiguous canonical names require manual resolution.
    alias = SkillAlias.objects.select_related("skill").filter(
        normalized_name=key, kind=SkillAlias.Kind.EXACT, review_status=ReviewStatus.REVIEWED,
    ).first()
    return {"skill": alias.skill, "match": "exact_alias"} if alias else None


def search_skill_names(query, limit=10):
    """Return canonical names for suggestions. No past user choices are rewritten."""
    aliases = SkillAlias.objects.filter(kind=SkillAlias.Kind.EXACT, review_status=ReviewStatus.REVIEWED)
    exact = list(aliases.filter(normalized_name=normalize_label(query)).values_list("skill__name", flat=True))
    direct = list(Skill.objects.filter(name__icontains=query).order_by("name").values_list("name", flat=True)[:limit])
    partial = list(aliases.filter(normalized_name__contains=normalize_label(query))
                   .order_by("skill__name").values_list("skill__name", flat=True)[:limit])
    return list(dict.fromkeys([*exact, *direct, *partial]))[:limit]
