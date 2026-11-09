MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 30
MAX_TEXT_CHARS = 200_000
MAX_ZIP_ENTRIES = 200
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_PDF_STREAM_BYTES = 8 * 1024 * 1024
WORKER_MEMORY_BYTES = 256 * 1024 * 1024
WORKER_CPU_SECONDS = 5
WORKER_WALL_SECONDS = 10

ERRORS = {
    'empty_file': 'Choose a non-empty PDF or DOCX file.',
    'file_too_large': 'The maximum file size is 5 MB.',
    'unsupported_type': 'Only PDF and DOCX resumes are supported. Legacy DOC files are not accepted.',
    'invalid_signature': 'The file contents do not match the selected file type.',
    'invalid_pdf': 'This PDF is damaged or unsupported. Export a new PDF and try again.',
    'encrypted_pdf': 'Password-protected or encrypted PDFs are not supported.',
    'active_content': 'Documents containing active content, attachments or external resources are not supported.',
    'too_many_pages': 'The PDF exceeds the 30-page limit.',
    'invalid_docx': 'This DOCX is damaged or unsupported. Save a new DOCX and try again.',
    'unsafe_archive': 'The DOCX archive contains unsafe or unsupported entries.',
    'archive_limit': 'The DOCX archive exceeds safe extraction limits.',
    'text_limit': 'The document exceeds the safe text extraction limit.',
    'resource_limit': 'This document exceeds safe processing limits. Export a simpler document and try again.',
    'processing_timeout': 'Processing took too long. Export a simpler document and try again.',
    'extraction_failed': 'Text could not be extracted. Try exporting a simpler document.',
    'worker_unavailable': 'Resume processing is temporarily unavailable. Please try again later.',
    'storage_unavailable': 'Private storage is temporarily unavailable. Please try again later.',
    'interrupted': 'Processing was interrupted. Delete this entry and upload again.',
}
