import hashlib
from django.core.files.base import ContentFile
from django.db import transaction, DatabaseError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from resume.models import ResumeDocument
from resume.storage import private_storage, remove_file
from .extraction import extract_text


class ResumeRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@sensitive_variables()
def accept_document(user, upload):
    data = upload['data']
    # Committed reservation before parsing/storage: interrupted files remain
    # tracked by a randomized key even if later DB writes become unavailable.
    document = ResumeDocument.objects.create(owner=user, original_filename=upload['name'], file_type=upload['type'],
        file_size=len(data), checksum=hashlib.sha256(data).hexdigest())
    try:
        document.status = ResumeDocument.Status.PROCESSING
        document.save(update_fields=['status', 'updated_at'])
        result = extract_text(data, document.file_type)
        if not result['valid']:
            document.delete()
            raise ResumeRejected(result['error_code'])
        if result['status'] != 'failed':
            returned = private_storage().save(document.storage_key, ContentFile(data))
            if returned != document.storage_key:
                raise RuntimeError('Private backend must support exact keys')
            document.file_retained = True
        document.status, document.extracted_text, document.error_code = result['status'], result['text'], result['error_code']
        document.extraction_completed_at = timezone.now()
        document.save(update_fields=['file_retained', 'status', 'extracted_text', 'error_code', 'extraction_completed_at', 'updated_at'])
        return document
    except ResumeRejected:
        raise
    except Exception:
        try:
            remove_file(document)
        except Exception:
            pass
        ResumeDocument.objects.filter(pk=document.pk).update(status='failed', file_retained=False,
            extracted_text='', error_code='storage_unavailable', extraction_completed_at=timezone.now(), updated_at=timezone.now())
        raise ResumeRejected('storage_unavailable') from None


def delete_document(document):
    try:
        with transaction.atomic():
            ResumeDocument.objects.select_for_update().get(pk=document.pk, owner=document.owner).delete()
    except DatabaseError:
        # Filesystem deletion is not rollbackable. If SQL deletion rolled back,
        # retain the owner-visible row for retry and correct its download state.
        try:
            if not private_storage().exists(document.storage_key):
                ResumeDocument.objects.filter(pk=document.pk).update(file_retained=False)
        except Exception:
            pass
        raise DatabaseError('Resume deletion requires a retry') from None
