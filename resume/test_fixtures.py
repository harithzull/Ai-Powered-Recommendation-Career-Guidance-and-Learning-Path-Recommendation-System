"""Synthetic in-memory fixtures only; no real student resumes."""
import io
from xml.sax.saxutils import escape
import zipfile


def pdf(text='Synthetic Resume', pages=1, encrypted=False, javascript=False):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, TextStringObject
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=500, height=700)
        if text is not None:
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            content = DecodedStreamObject()
            safe = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            content.set_data(('BT /F1 12 Tf 50 650 Td ('+safe+') Tj ET').encode('ascii'))
            page[NameObject('/Contents')] = content
    if encrypted:
        writer.encrypt('synthetic-password', algorithm='RC4-40')
    if javascript:
        writer.root_object[NameObject('/OpenAction')] = DictionaryObject({NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('app.alert("synthetic")')})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx(text='Synthetic Resume', extra=None, compression=zipfile.ZIP_STORED):
    entries = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+escape(text)+'</w:t></w:r></w:p><w:p><w:r><w:t>Python and SQL</w:t></w:r></w:p></w:body></w:document>',
    }
    entries.update(extra or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=compression) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()
