from datetime import timedelta
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch, Mock
import uuid
import zipfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .checks import private_resume_storage
from .constants import MAX_FILE_BYTES
from .models import ResumeDocument
from .services.documents import accept_document, ResumeRejected
from .services.extraction import extract_text
from .services.parsing import normalize_text, Rejected
from .storage import PrivateResumeStorage, ResumeStorageError
from .test_fixtures import pdf, docx


class ParserTests(SimpleTestCase):
    def test_real_subprocess_pdf_and_deterministic_text(self):
        data = pdf('Synthetic PDF Resume')
        first = extract_text(data, 'pdf')
        self.assertEqual(first['status'], 'completed')
        self.assertEqual(first['text'], 'Synthetic PDF Resume')
        self.assertEqual(first, extract_text(data, 'pdf'))

    def test_real_subprocess_docx_paragraphs(self):
        result = extract_text(docx(), 'docx')
        self.assertEqual(result['text'], 'Synthetic Resume\n\nPython and SQL')
        self.assertEqual(result['status'], 'completed')

    def test_encrypted_pdf_is_rejected(self):
        self.assertEqual(extract_text(pdf(encrypted=True), 'pdf')['error_code'], 'encrypted_pdf')

    def test_image_only_pdf_has_no_extractable_text(self):
        result = extract_text(pdf(text=None), 'pdf')
        self.assertTrue(result['valid'])
        self.assertEqual(result['status'], 'no_extractable_text')

    def test_excessive_pdf_pages(self):
        self.assertEqual(extract_text(pdf(pages=31), 'pdf')['error_code'], 'too_many_pages')

    def test_malformed_pdf_and_docx(self):
        for data, kind, code in [(b'%PDF-not-a-document', 'pdf', 'invalid_pdf'), (b'PK\x03\x04not-a-zip', 'docx', 'invalid_docx')]:
            self.assertEqual(extract_text(data, kind)['error_code'], code)

    def test_pdf_javascript_is_rejected(self):
        self.assertEqual(extract_text(pdf(javascript=True), 'pdf')['error_code'], 'active_content')

    def test_docx_macros_activex_and_embedded_payloads(self):
        for path in ('word/vbaProject.bin', 'word/activeX/control.xml', 'word/embeddings/evil.exe'):
            self.assertEqual(extract_text(docx(extra={path: b'MZpayload'}), 'docx')['error_code'], 'active_content')

    def test_docx_external_relationship(self):
        data = docx(extra={'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Target="https://example.invalid/"/></Relationships>'})
        self.assertEqual(extract_text(data, 'docx')['error_code'], 'active_content')

    def test_docx_traversal_absolute_and_backslash_entries(self):
        for name in ('../escape.xml', '/escape.xml', 'word\\escape.xml', 'C:/escape.xml'):
            data = docx(extra={name: '<a/>'})
            if '\\' in name:
                # zipfile normalizes writer names on Windows. Craft both ZIP
                # headers explicitly so this is genuinely an unsafe wire entry.
                data = data.replace(name.replace('\\', '/').encode(), name.encode())
            self.assertEqual(extract_text(data, 'docx')['error_code'], 'unsafe_archive')

    def test_docx_xml_entities_do_not_read_files(self):
        xml = '<!DOCTYPE a [<!ENTITY x SYSTEM "file:///never-read-private-file">]><a>&x;</a>'
        self.assertEqual(extract_text(docx(extra={'word/document.xml': xml}), 'docx')['error_code'], 'invalid_docx')

    def test_docx_archive_entry_count_ratio_and_size(self):
        data = docx(extra={f'word/test{i}.xml': '<a/>' for i in range(201)})
        self.assertEqual(extract_text(data, 'docx')['error_code'], 'archive_limit')

    def test_total_archive_size_and_crc_corruption(self):
        from .services.parsing import docx_text
        with patch('resume.services.parsing.MAX_UNCOMPRESSED_BYTES', 100), self.assertRaises(Rejected):
            docx_text(docx())
        # Corrupt stored document bytes without updating the ZIP's recorded CRC.
        data = docx().replace(b'Synthetic Resume', b'Corrupted Resume')
        self.assertEqual(extract_text(data, 'docx')['error_code'], 'invalid_docx')
        data = docx(extra={'word/bomb.xml': '<a>'+'A'*500_000+'</a>'}, compression=zipfile.ZIP_DEFLATED)
        self.assertEqual(extract_text(data, 'docx')['error_code'], 'archive_limit')
        data = docx(extra={'word/oversized.xml': '<a>'+'X'*(9*1024*1024)+'</a>'}, compression=zipfile.ZIP_DEFLATED)
        self.assertEqual(extract_text(data, 'docx')['error_code'], 'archive_limit')

    def test_docx_symlinks_and_disguised_executable_images(self):
        self.assertEqual(extract_text(docx(extra={'word/media/image.png': b'MZpayload'}), 'docx')['error_code'], 'unsafe_archive')
        data = io.BytesIO(docx())
        with zipfile.ZipFile(data, 'a') as archive:
            entry = zipfile.ZipInfo('word/link.xml')
            entry.create_system = 3
            entry.external_attr = (0o120777 << 16)
            archive.writestr(entry, 'elsewhere')
        self.assertEqual(extract_text(data.getvalue(), 'docx')['error_code'], 'unsafe_archive')

    def test_excessive_pdf_and_docx_text(self):
        for data, kind in ((pdf('X'*200_001), 'pdf'), (docx('X'*200_001), 'docx')):
            self.assertEqual(extract_text(data, kind)['error_code'], 'text_limit')

    def test_normalization_preserves_paragraphs_unicode_and_removes_controls(self):
        self.assertEqual(normalize_text('  Resume\t name\r\n\r\n\r\nCafe\u0301\x00  '), 'Resume name\n\nCafé')
        with self.assertRaises(Rejected):
            normalize_text('X'*200_001)
        with self.assertRaises(Rejected):
            normalize_text('\u0344'*150_000)  # NFC can expand some characters.

    def test_timeout_kills_worker_without_leaking_details(self):
        process = Mock()
        process.communicate.side_effect = [subprocess.TimeoutExpired('private-content', 10), (b'', None)]
        process.poll.return_value = None
        with patch('resume.services.extraction.subprocess.Popen', return_value=process), patch('resume.services.extraction.windows_job', return_value=lambda: None):
            result = extract_text(b'%PDF-test', 'pdf')
        self.assertEqual(result['error_code'], 'processing_timeout')
        process.kill.assert_called_once()

    def test_isolation_failure_never_sends_document_to_worker(self):
        process = Mock()
        process.poll.return_value = None
        with patch('resume.services.extraction.subprocess.Popen', return_value=process), patch('resume.services.extraction.windows_job', side_effect=OSError('private path')):
            self.assertEqual(extract_text(b'%PDF-test', 'pdf')['error_code'], 'worker_unavailable')
        process.kill.assert_called_once()
        process.communicate.assert_called_once_with()

    def test_no_network_or_llm_even_with_external_document_links(self):
        with patch('socket.create_connection', side_effect=AssertionError()), patch('groq.Groq', side_effect=AssertionError()):
            self.assertEqual(extract_text(pdf(), 'pdf')['status'], 'completed')
            self.assertFalse(extract_text(docx(extra={'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Target="https://example.invalid/"/></Relationships>'}), 'docx')['valid'])


class ResumeViewsTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(PRIVATE_RESUME_ROOT=Path(self.temp.name)/'private')
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user('resume_owner')
        self.other = User.objects.create_user('other_owner')
        self.client.force_login(self.user)

    def upload(self, data=None, name='resume.pdf', **kwargs):
        return self.client.post('/resumes/upload/', {'document': SimpleUploadedFile(name, pdf() if data is None else data, content_type='application/octet-stream'), 'consent': 'on', **kwargs})

    def create(self):
        self.assertEqual(self.upload().status_code, 302)
        return ResumeDocument.objects.get()

    def test_pdf_upload_metadata_and_private_download(self):
        data = pdf()
        self.assertEqual(self.upload(data).status_code, 302)
        document = ResumeDocument.objects.get()
        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.checksum, hashlib.sha256(data).hexdigest())
        self.assertEqual(document.file_size, len(data))
        self.assertEqual(document.extracted_text, 'Synthetic Resume')
        self.assertEqual(document.status, 'completed')
        self.assertTrue(document.file_retained)
        self.assertEqual(document.original_filename, 'resume.pdf')
        response = self.client.get(f'/resumes/{document.pk}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(b''.join(response.streaming_content), data)
        response.close()

    def test_docx_upload_and_escaped_private_text(self):
        self.assertEqual(self.upload(docx('<script>private text</script>'), 'resume.docx').status_code, 302)
        document = ResumeDocument.objects.get()
        response = self.client.get(f'/resumes/{document.pk}/')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>private text</script>')
        self.assertNotContains(response, 'cdn.jsdelivr.net')
        self.assertNotContains(response, 'fonts.googleapis.com')
        self.assertIn("connect-src 'self'", response['Content-Security-Policy'])

    def test_no_text_pdf_record_and_message(self):
        self.assertEqual(self.upload(pdf(text=None)).status_code, 302)
        document = ResumeDocument.objects.get()
        self.assertEqual(document.status, 'no_extractable_text')
        self.assertContains(self.client.get(f'/resumes/{document.pk}/'), 'No extractable text was found')

    def test_empty_oversized_wrong_extensions_spoofed_signatures(self):
        for data, name in ((b'', 'x.pdf'), (b'x', 'x.doc'), (b'x', 'x.exe'), (b'not pdf', 'x.pdf'), (pdf(), 'x.docx')):
            self.assertEqual(self.upload(data, name).status_code, 400)
        self.assertEqual(self.upload(b'%PDF-'+b'x'*MAX_FILE_BYTES).status_code, 413)
        self.assertFalse(ResumeDocument.objects.exists())

    def test_invalid_structure_leaves_no_file_or_record(self):
        self.assertEqual(self.upload(b'%PDF-damaged').status_code, 400)
        self.assertFalse(ResumeDocument.objects.exists())
        root = Path(self.temp.name)/'private'
        self.assertFalse(root.exists() and list(root.iterdir()))

    def test_consent_required(self):
        self.assertEqual(self.upload(consent='').status_code, 400)
        self.assertFalse(ResumeDocument.objects.exists())

    def test_anonymous_routes_require_login(self):
        self.client.logout()
        for path in ('/resumes/', '/resumes/upload/', f'/resumes/{uuid.uuid4()}/', f'/resumes/{uuid.uuid4()}/download/'):
            self.assertEqual(self.client.get(path).status_code, 302)

    def test_csrf_enforced_for_upload_and_delete(self):
        document = self.create()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/resumes/upload/', {'consent': 'on'}).status_code, 403)
        self.assertEqual(client.post(f'/resumes/{document.pk}/delete/').status_code, 403)
        self.assertTrue(ResumeDocument.objects.filter(pk=document.pk).exists())

    def test_cross_user_metadata_download_delete_and_lists(self):
        document = self.create()
        self.client.force_login(self.other)
        for suffix in ('', 'download/', 'delete-confirmation/'):
            self.assertEqual(self.client.get(f'/resumes/{document.pk}/{suffix}').status_code, 404)
        self.assertEqual(self.client.post(f'/resumes/{document.pk}/delete/').status_code, 404)
        self.assertNotContains(self.client.get('/resumes/'), 'resume.pdf')

    def test_delete_is_post_only_and_removes_text_and_file(self):
        document = self.create()
        path = Path(self.temp.name)/'private'/document.storage_key
        self.assertTrue(path.exists())
        self.assertEqual(self.client.get(f'/resumes/{document.pk}/delete/').status_code, 405)
        self.assertTrue(path.exists())
        self.assertEqual(self.client.post(f'/resumes/{document.pk}/delete/').status_code, 302)
        self.assertFalse(path.exists())
        self.assertFalse(ResumeDocument.objects.exists())

    def test_owner_account_cascade_deletes_file(self):
        document = self.create()
        path = Path(self.temp.name)/'private'/document.storage_key
        self.user.delete()
        self.assertFalse(path.exists())
        self.assertFalse(ResumeDocument.objects.exists())

    def test_download_missing_file_is_generic_404(self):
        document = self.create()
        (Path(self.temp.name)/'private'/document.storage_key).unlink()
        self.assertEqual(self.client.get(f'/resumes/{document.pk}/download/').status_code, 404)

    def test_storage_failure_is_generic_and_tracked(self):
        with patch('resume.services.documents.private_storage') as store:
            store.return_value.save.side_effect = OSError('secret-resume-content private-path')
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'secret-resume-content', status_code=503)
        self.assertEqual(ResumeDocument.objects.get().status, 'failed')

    def test_storage_delete_failure_retains_record_and_text_for_retry(self):
        document = self.create()
        with patch('resume.storage.private_storage') as store:
            store.return_value.delete.side_effect = OSError('private-path')
            self.assertEqual(self.client.post(f'/resumes/{document.pk}/delete/').status_code, 503)
        document.refresh_from_db()
        self.assertEqual(document.extracted_text, 'Synthetic Resume')
        self.assertTrue((Path(self.temp.name)/'private'/document.storage_key).exists())

    def test_db_failure_after_file_write_cleans_file_and_keeps_reservation(self):
        original = ResumeDocument.save
        def fail_completed(instance, *args, **kwargs):
            if instance.status == 'completed':
                raise DatabaseError('private SQL data')
            return original(instance, *args, **kwargs)
        with patch.object(ResumeDocument, 'save', fail_completed):
            self.assertEqual(self.upload().status_code, 503)
        document = ResumeDocument.objects.get()
        self.assertEqual(document.status, 'failed')
        self.assertEqual(document.extracted_text, '')
        self.assertFalse((Path(self.temp.name)/'private'/document.storage_key).exists())

    def test_db_failure_during_delete_retains_row_with_no_download(self):
        document = self.create()
        with patch('django.db.models.sql.DeleteQuery.delete_batch', side_effect=DatabaseError('private SQL')):
            self.assertEqual(self.client.post(f'/resumes/{document.pk}/delete/').status_code, 503)
        document.refresh_from_db()
        self.assertFalse(document.file_retained)
        self.assertFalse((Path(self.temp.name)/'private'/document.storage_key).exists())
        self.assertEqual(self.client.post(f'/resumes/{document.pk}/delete/').status_code, 302)

    def test_partial_storage_write_and_cleanup_failure_stays_tracked(self):
        real_store = PrivateResumeStorage()
        def partial(name, content):
            real_store.save(name, content)
            raise OSError('private disk failure')
        fake = Mock()
        fake.save.side_effect = partial
        with patch('resume.services.documents.private_storage', return_value=fake), patch('resume.storage.private_storage') as cleanup:
            cleanup.return_value.delete.side_effect = OSError('cleanup failed')
            self.assertEqual(self.upload().status_code, 503)
        document = ResumeDocument.objects.get()
        path = Path(self.temp.name)/'private'/document.storage_key
        self.assertTrue(path.exists())
        self.assertEqual(document.status, 'failed')
        self.assertEqual(self.client.get(f'/resumes/{document.pk}/download/').status_code, 404)
        self.assertEqual(self.client.post(f'/resumes/{document.pk}/delete/').status_code, 302)
        self.assertFalse(path.exists())

    def test_initial_db_failure_writes_no_files(self):
        with patch('resume.services.documents.ResumeDocument.objects.create', side_effect=DatabaseError('private SQL')):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'private SQL', status_code=503)
        self.assertFalse((Path(self.temp.name)/'private').exists())

    def test_original_name_is_display_only_and_never_a_storage_path(self):
        self.assertEqual(self.upload(name='..\\..\\sensitive.pdf').status_code, 302)
        document = ResumeDocument.objects.get()
        self.assertEqual(document.original_filename, 'sensitive.pdf')
        self.assertNotIn('sensitive', document.storage_key)
        self.assertNotContains(self.client.get(f'/resumes/{document.pk}/'), str(document.storage_identifier))

    def test_invalid_public_storage_config_and_no_inline_routes(self):
        document = self.create()
        self.assertEqual(self.client.get('/private_storage/resumes/'+document.storage_key).status_code, 404)
        self.assertEqual(self.client.get('/static/'+document.storage_key).status_code, 404)

    def test_worker_failure_does_not_store_original(self):
        with patch('resume.services.documents.extract_text', return_value={'valid': False, 'status': 'failed', 'text': '', 'error_code': 'processing_timeout'}):
            self.assertEqual(self.upload().status_code, 400)
        self.assertFalse(ResumeDocument.objects.exists())

    def test_stale_upload_cleanup_does_not_remove_completed_docs(self):
        document = self.create()
        stale = ResumeDocument.objects.create(owner=self.user, original_filename='stale.pdf', file_type='pdf', file_size=1, checksum='0'*64)
        ResumeDocument.objects.filter(pk=stale.pk).update(updated_at=timezone.now()-timedelta(hours=1))
        call_command('cleanup_resume_uploads', stdout=io.StringIO())
        stale.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(stale.error_code, 'interrupted')
        self.assertEqual(document.status, 'completed')

    @override_settings(RESUME_UPLOADS_PER_DAY=1)
    def test_upload_rate_limit(self):
        self.assertEqual(self.upload().status_code, 302)
        self.assertEqual(self.upload().status_code, 429)

    @override_settings(RESUME_MAX_DOCUMENTS=1)
    def test_document_quota(self):
        self.create()
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(ResumeDocument.objects.count(), 1)

    def test_private_storage_has_no_url_and_rejects_traversal(self):
        storage = PrivateResumeStorage()
        with self.assertRaises(NotImplementedError):
            storage.url('resume.pdf')
        with self.assertRaises(ResumeStorageError):
            storage.get_available_name('../escape.pdf')
        self.assertEqual(self.client.get('/media/anything.pdf').status_code, 404)

    def test_storage_settings_reject_public_roots(self):
        with override_settings(STATIC_ROOT=self.temp.name, PRIVATE_RESUME_ROOT=Path(self.temp.name)/'private'):
            self.assertEqual(private_resume_storage(None)[0].id, 'resume.E001')
