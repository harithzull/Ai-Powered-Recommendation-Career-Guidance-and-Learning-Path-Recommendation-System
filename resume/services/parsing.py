"""Untrusted parsing: imported only in the bounded worker (tests use synthetic bytes)."""
import io
import posixpath
import re
import stat
import unicodedata
import zipfile

from defusedxml import ElementTree

from resume.constants import (
    MAX_COMPRESSION_RATIO, MAX_ENTRY_BYTES, MAX_FILE_BYTES, MAX_PAGES,
    MAX_PDF_STREAM_BYTES, MAX_TEXT_CHARS, MAX_UNCOMPRESSED_BYTES, MAX_ZIP_ENTRIES,
)


class Rejected(Exception):
    def __init__(self, code):
        self.code = code


def normalize_text(text):
    if len(text) > MAX_TEXT_CHARS:
        raise Rejected('text_limit')
    text = unicodedata.normalize('NFC', text.replace('\r\n', '\n').replace('\r', '\n'))
    text = ''.join(c for c in text if c in '\n\t' or not unicodedata.category(c).startswith('C'))
    lines = [re.sub(r'[^\S\n]+', ' ', line).strip() for line in text.split('\n')]
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
    if len(result) > MAX_TEXT_CHARS:
        raise Rejected('text_limit')
    return result


def pdf_text(data):
    from pypdf import PdfReader
    if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-1024:]:
        raise Rejected('invalid_pdf')
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        raise Rejected('encrypted_pdf')
    count = len(reader.pages)
    if count == 0:
        raise Rejected('invalid_pdf')
    if count > MAX_PAGES:
        raise Rejected('too_many_pages')
    # Traverse reachable objects without executing actions or opening resources.
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
    forbidden = {'/JS', '/JavaScript', '/OpenAction', '/AA', '/EmbeddedFiles', '/EmbeddedFile', '/EF', '/RichMedia',
                 '/XFA', '/Launch', '/SubmitForm', '/ImportData', '/GoToR', '/URI', '/Filespec'}
    visited = set()
    stack = [reader.trailer]
    objects = 0
    while stack:
        node = stack.pop()
        if isinstance(node, IndirectObject):
            key = (node.idnum, node.generation)
            if key in visited:
                continue
            visited.add(key)
            node = node.get_object()
        objects += 1
        if objects > 100_000:
            raise Rejected('resource_limit')
        if isinstance(node, DictionaryObject):
            if forbidden.intersection(node.keys()) or any(str(node.get(key, '')) in forbidden | {'/Screen', '/Movie', '/Sound', '/FileAttachment', '/3D'} for key in ('/S', '/Type', '/Subtype')):
                raise Rejected('active_content')
            # Do not decode streams while walking dictionaries.
            stack.extend(node.values())
        elif isinstance(node, ArrayObject):
            stack.extend(node)
    chunks, total = [], 0
    for page in reader.pages:
        content = page.get_contents()
        if content and len(content.get_data()) > MAX_PDF_STREAM_BYTES:
            raise Rejected('resource_limit')
        text = page.extract_text() or ''
        total += len(text)+2
        if total > MAX_TEXT_CHARS:
            raise Rejected('text_limit')
        chunks.append(text)
    return '\n\n'.join(chunks)


WORD = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DOC_CONTENT = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'


def safe_xml(data):
    return ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def docx_text(data):
    if not data.startswith(b'PK\x03\x04'):
        raise Rejected('invalid_docx')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES:
            raise Rejected('archive_limit')
        seen, total, parts = set(), 0, {}
        for entry in entries:
            name = entry.orig_filename  # Inspect before zipfile's platform normalization.
            lower = name.casefold()
            if (lower in seen or '\\' in name or ':' in name or '\x00' in name or name.startswith('/')
                    or '..' in name.split('/') or posixpath.normpath(name).rstrip('/') != name.rstrip('/')
                    or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise Rejected('unsafe_archive')
            seen.add(lower)
            total += entry.file_size
            if entry.file_size > MAX_ENTRY_BYTES or total > MAX_UNCOMPRESSED_BYTES or entry.file_size/max(entry.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise Rejected('archive_limit')
            if any(token in lower for token in ('vbaproject', 'macro', 'activex', 'embeddings/', 'oleobject', 'customui/')):
                raise Rejected('active_content')
            allowed = lower.endswith(('.xml', '.rels')) or lower.startswith('word/media/') and lower.endswith(('.png', '.jpg', '.jpeg', '.gif')) or entry.is_dir()
            if not allowed:
                raise Rejected('unsafe_archive')
            # Reading all entries checks actual CRC/decompression. Never unzip to disk.
            with archive.open(entry) as stream:
                value = stream.read(MAX_ENTRY_BYTES+1)
            if len(value) != entry.file_size:
                raise Rejected('archive_limit')
            if lower.startswith('word/media/') and value and not value.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')):
                raise Rejected('unsafe_archive')
            if lower.endswith(('.xml', '.rels')):
                parts[name] = safe_xml(value)
        if not {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'} <= set(parts):
            raise Rejected('invalid_docx')
        content = parts['[Content_Types].xml']
        if content.tag != '{http://schemas.openxmlformats.org/package/2006/content-types}Types':
            raise Rejected('invalid_docx')
        if not any(e.get('PartName') == '/word/document.xml' and e.get('ContentType') == DOC_CONTENT for e in content):
            raise Rejected('invalid_docx')
        root_rels = parts['_rels/.rels']
        if root_rels.tag != '{http://schemas.openxmlformats.org/package/2006/relationships}Relationships' or not any(
            e.get('Type') == 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'
            and e.get('Target') == 'word/document.xml' for e in root_rels):
            raise Rejected('invalid_docx')
        for root in parts.values():
            for element in root.iter():
                if any(token in value.casefold() for value in element.attrib.values() for token in ('macroenabled', 'vbaproject', 'activex', 'oleobject')):
                    raise Rejected('active_content')
                if element.tag.endswith('Relationship'):
                    target = element.get('Target', '')
                    if (element.get('TargetMode', '').casefold() == 'external' or ':' in target or '\\' in target
                            or target.startswith('/') or '..' in target.split('/')):
                        raise Rejected('active_content')
                if element.tag in {WORD+'object', WORD+'altChunk', WORD+'instrText', WORD+'fldSimple'}:
                    raise Rejected('active_content')
        if parts['word/document.xml'].tag != WORD+'document':
            raise Rejected('invalid_docx')
        chunks, length = [], 0
        # Preserve body/table paragraph order; include common headers/footers.
        names = ['word/document.xml'] + sorted(n for n in parts if re.fullmatch(r'word/(header|footer)\d+\.xml', n))
        for name in names:
            for paragraph in parts[name].iter(WORD+'p'):
                text = ''.join((node.text or '') if node.tag == WORD+'t' else '\t' if node.tag == WORD+'tab' else '\n' if node.tag in (WORD+'br', WORD+'cr') else '' for node in paragraph.iter())
                length += len(text)+2
                if length > MAX_TEXT_CHARS:
                    raise Rejected('text_limit')
                chunks.append(text)
        return '\n\n'.join(chunks)


def extract(data, file_type):
    if not data or len(data) > MAX_FILE_BYTES:
        raise Rejected('empty_file' if not data else 'file_too_large')
    try:
        text = normalize_text(pdf_text(data) if file_type == 'pdf' else docx_text(data))
    except Rejected:
        raise
    except MemoryError:
        raise Rejected('resource_limit') from None
    except Exception:
        raise Rejected('invalid_pdf' if file_type == 'pdf' else 'invalid_docx') from None
    return {'valid': True, 'status': 'completed' if text else 'no_extractable_text', 'text': text, 'error_code': ''}
