from pathlib import PurePosixPath
import unicodedata
from django import forms
from .constants import ERRORS, MAX_FILE_BYTES


class ResumeUploadForm(forms.Form):
    document = forms.FileField(allow_empty_file=False, widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.docx'}))
    consent = forms.BooleanField(label='I agree to private storage and offline text extraction. I can delete my resume at any time.')

    def clean_document(self):
        upload = self.cleaned_data['document']
        name = upload.name.replace('\\', '/').split('/')[-1]
        name = ''.join(c for c in name if not unicodedata.category(c).startswith('C'))[:180]
        suffix = PurePosixPath(name).suffix.lower()
        if suffix not in ('.pdf', '.docx'):
            raise forms.ValidationError(ERRORS['unsupported_type'])
        if upload.size > MAX_FILE_BYTES:
            raise forms.ValidationError(ERRORS['file_too_large'])
        data = upload.read(MAX_FILE_BYTES+1)
        if not data or len(data) > MAX_FILE_BYTES:
            raise forms.ValidationError(ERRORS['empty_file'] if not data else ERRORS['file_too_large'])
        if not data.startswith(b'%PDF-' if suffix == '.pdf' else b'PK\x03\x04'):
            raise forms.ValidationError(ERRORS['invalid_signature'])
        return {'name': name, 'type': suffix[1:], 'data': data}
