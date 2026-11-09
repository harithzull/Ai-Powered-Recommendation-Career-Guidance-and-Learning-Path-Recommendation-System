"""Private exact-key storage. No public URL or user-supplied storage name."""
import re

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ResumeStorageError(Exception):
    def __init__(self):
        super().__init__('Private resume storage is unavailable')


class PrivateResumeStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_RESUME_ROOT, base_url=None,
                         file_permissions_mode=0o600, directory_permissions_mode=0o700)

    def get_available_name(self, name, max_length=None):
        if not re.fullmatch(r'[0-9a-f]{32}\.(pdf|docx)', name) or self.exists(name):
            raise ResumeStorageError()
        return name

    def url(self, name):
        raise NotImplementedError('Resume files have no public URL')


def private_storage():
    # Resolve on each call so test storage and future private backends can replace
    # the factory without putting local paths on model fields or migrations.
    return PrivateResumeStorage()


def remove_file(document):
    try:
        private_storage().delete(document.storage_key)
    except Exception:
        raise ResumeStorageError() from None
