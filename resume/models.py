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
