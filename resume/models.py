import uuid

from django.conf import settings
from django.db import models


class ResumeDocument(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        NO_TEXT = 'no_extractable_text', 'No extractable text'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resume_documents')
    original_filename = models.CharField(max_length=180)
    file_type = models.CharField(max_length=4, choices=[('pdf', 'PDF'), ('docx', 'DOCX')])
    file_size = models.PositiveIntegerField()
    storage_identifier = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    file_retained = models.BooleanField(default=False)
    checksum = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=Status, default=Status.PENDING)
    extracted_text = models.TextField(blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    extraction_completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at', '-pk']
        indexes = [models.Index(fields=['owner', '-uploaded_at'], name='resume_owner_uploaded')]

    @property
    def storage_key(self):
        return f'{self.storage_identifier.hex}.{self.file_type}'

class ResumeAnalysis(models.Model):
    """A completed, private snapshot. Ownership follows the source document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(ResumeDocument, on_delete=models.CASCADE, related_name='analyses')
    revision = models.PositiveSmallIntegerField()
    source_checksum = models.CharField(max_length=64)
    text_checksum = models.CharField(max_length=64)
    extractor_version = models.CharField(max_length=40)
    sections = models.JSONField(default=list)
    notices = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-revision']
        constraints = [
            models.UniqueConstraint(fields=['document', 'revision'], name='resume_unique_analysis_revision'),
            models.CheckConstraint(condition=models.Q(revision__gte=1), name='resume_valid_analysis_revision'),
        ]


class ResumeSuggestion(models.Model):
    class Category(models.TextChoices):
        SKILL = 'skill', 'Skill'
        EDUCATION = 'education', 'Education'
        EXPERIENCE = 'experience', 'Work experience'
        PROJECT = 'project', 'Project'

    class Support(models.TextChoices):
        EXPLICIT = 'explicit', 'Explicitly stated'
        INFERRED = 'inferred', 'Structure inferred from text'
        AMBIGUOUS = 'ambiguous', 'Needs clarification'
        UNSUPPORTED = 'unsupported', 'Context does not support possession'

    class ReviewState(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        REJECTED = 'rejected', 'Rejected'
        CORRECTED = 'corrected', 'Corrected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(ResumeAnalysis, on_delete=models.CASCADE, related_name='suggestions')
    position = models.PositiveSmallIntegerField()
    category = models.CharField(max_length=12, choices=Category)
    value = models.CharField(max_length=500)
    normalized_value = models.CharField(max_length=500)
    method = models.CharField(max_length=32)
    support = models.CharField(max_length=12, choices=Support)
    fields = models.JSONField(default=dict, blank=True)
    evidence = models.JSONField(default=list)
    canonical_skill = models.ForeignKey('recommender.Skill', null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name='+')
    canonical_snapshot = models.JSONField(default=dict, blank=True)
    alternatives = models.JSONField(default=list, blank=True)
    review_state = models.CharField(max_length=10, choices=ReviewState, default=ReviewState.PENDING)
    review_version = models.PositiveIntegerField(default=0)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    correction = models.JSONField(default=dict, blank=True)
    corrected_skill = models.ForeignKey('recommender.Skill', null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name='+')

    class Meta:
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['analysis', 'position'], name='resume_unique_suggestion_position'),
            models.CheckConstraint(condition=models.Q(category__in=['skill', 'education', 'experience', 'project']),
                                   name='resume_valid_suggestion_category'),
            models.CheckConstraint(condition=models.Q(support__in=['explicit', 'inferred', 'ambiguous', 'unsupported']),
                                   name='resume_valid_suggestion_support'),
            models.CheckConstraint(condition=models.Q(review_state__in=['pending', 'confirmed', 'rejected', 'corrected']),
                                   name='resume_valid_review_state'),
        ]

    @property
    def can_confirm(self):
        if self.support == self.Support.UNSUPPORTED:
            return False
        if self.category == self.Category.SKILL:
            return self.method not in ('ambiguous', 'unverified_alias')
        return True
