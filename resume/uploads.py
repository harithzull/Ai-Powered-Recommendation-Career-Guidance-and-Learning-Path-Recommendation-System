"""Bound actual multipart bytes in memory; never spool resume PII to shared temp."""
from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload
from .constants import MAX_FILE_BYTES


class BoundedMemoryUploadHandler(MemoryFileUploadHandler):
    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.activated = True

    def new_file(self, *args, **kwargs):
        self.received = 0
        super().new_file(*args, **kwargs)

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > MAX_FILE_BYTES:
            self.request.resume_upload_too_large = True
            self.file.close()
            raise StopUpload(connection_reset=True)
        return super().receive_data_chunk(raw_data, start)
