from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError

from .knowledge_validation import (
    validate_localized_titles, validate_metadata, validate_occupation_uri,
    validate_riasec_profile, validate_skill_uri,
)
from .normalization import normalize_label


class SourceTaxonomy(models.TextChoices):
    ESCO = "esco", "ESCO-derived"
    CAREERCOACH = "careercoach", "CareerCoach curated"
    UNKNOWN = "unknown", "Unknown"


class ReviewStatus(models.TextChoices):
    NEEDS_REVIEW = "needs_review", "Needs review"
    REVIEWED = "reviewed", "Reviewed"


class SourceRecord(models.Model):
    source_taxonomy = models.CharField(max_length=20, choices=SourceTaxonomy, default=SourceTaxonomy.UNKNOWN)
    source_metadata = models.JSONField(default=dict, blank=True, validators=[validate_metadata])
    quality_status = models.CharField(max_length=20, choices=ReviewStatus, default=ReviewStatus.NEEDS_REVIEW)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        validate_metadata(self.source_metadata)


class Career(SourceRecord):
    esco_uri = models.URLField(max_length=500, null=True, blank=True, unique=True, validators=[validate_occupation_uri])
    source_title = models.CharField(max_length=255, blank=True)
    source_description = models.TextField(blank=True)
    title = models.CharField(max_length=255, unique=True)
    industry = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    description = models.TextField(blank=True)
    work_environment = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Skill(SourceRecord):
    esco_uri = models.URLField(max_length=500, null=True, blank=True, unique=True, validators=[validate_skill_uri])
    source_name = models.CharField(max_length=255, blank=True)
    source_description = models.TextField(blank=True)
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


class CareerSkill(SourceRecord):
    source_relation_type = models.CharField(max_length=50, blank=True,
        help_text="Verified original source relation, e.g. essential/optional; blank means unknown.")
    source_importance = models.PositiveSmallIntegerField(null=True, blank=True)
    source_proficiency = models.CharField(max_length=100, blank=True)
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


class CareerFamily(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CareerEnrichment(models.Model):
    career = models.OneToOneField(Career, on_delete=models.CASCADE, related_name="enrichment")
    family = models.ForeignKey(CareerFamily, on_delete=models.SET_NULL, null=True, blank=True, related_name="careers")
    specialization = models.CharField(max_length=150, blank=True)
    localized_titles = models.JSONField(default=dict, blank=True, validators=[validate_localized_titles])
    student_summary = models.TextField(blank=True)
    entry_level_suitable = models.BooleanField(null=True, blank=True)
    riasec_profile = models.JSONField(null=True, blank=True, validators=[validate_riasec_profile])
    review_status = models.CharField(max_length=20, choices=ReviewStatus, default=ReviewStatus.NEEDS_REVIEW)
    review_metadata = models.JSONField(default=dict, blank=True, validators=[validate_metadata])

    def clean(self):
        super().clean()
        validate_localized_titles(self.localized_titles)
        validate_metadata(self.review_metadata)
        validate_riasec_profile(self.riasec_profile)

    def __str__(self):
        return f"Enrichment: {self.career.title}"


class SkillAlias(models.Model):
    class Kind(models.TextChoices):
        EXACT = "exact", "Exact alias"
        RELATED = "related", "Related term (not an exact synonym)"

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="aliases")
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, unique=True, editable=False)
    kind = models.CharField(max_length=10, choices=Kind, default=Kind.EXACT)
    review_status = models.CharField(max_length=20, choices=ReviewStatus, default=ReviewStatus.NEEDS_REVIEW)
    review_metadata = models.JSONField(default=dict, blank=True, validators=[validate_metadata])

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(condition=~models.Q(normalized_name=""), name="skill_alias_key_not_empty")]

    def clean(self):
        validate_metadata(self.review_metadata)
        self.name = " ".join(self.name.split())
        self.normalized_name = normalize_label(self.name)
        if not self.normalized_name:
            raise ValidationError({"name": "An alias must not be empty."})
        # Equality collisions are deliberately rejected, even for the same concept:
        # canonical names already resolve without needing redundant aliases.
        if any(normalize_label(name) == self.normalized_name for name in Skill.objects.values_list("name", flat=True)):
            raise ValidationError({"name": "This name is already a canonical skill; do not merge concepts."})
        if self.review_status == ReviewStatus.REVIEWED and not self.review_metadata.get("evidence"):
            raise ValidationError({"review_metadata": "Reviewed aliases require evidence."})

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_label(self.name)
        self.full_clean()
        if kwargs.get("update_fields"):
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"name", "normalized_name"}
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} -> {self.skill.name} ({self.kind})"


class CachedRecommendation(models.Model):
    input_signature = models.CharField(max_length=64, blank=True, default="")
    user        = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cached_recommendations")
    results_json = models.TextField()
    computed_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CachedRecommendation({self.user.username}, {self.computed_at:%Y-%m-%d %H:%M})"
