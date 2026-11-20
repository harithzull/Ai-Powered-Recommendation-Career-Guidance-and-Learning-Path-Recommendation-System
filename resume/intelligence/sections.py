"""Recognize complete headings or exact labels followed by an inline colon."""
import re
from dataclasses import dataclass

from recommender.normalization import normalize_label

from .schema import MAX_LINE_CHARS, Evidence, Section


HEADINGS = {
    'skills': ('skills', 'technical skills', 'skills and competencies', 'technical competencies',
               'core skills', 'key skills', 'computer skills', 'soft skills', 'skill set',
               'kemahiran', 'kemahiran teknikal', 'kemahiran insaniah', 'kemahiran komputer'),
    'education': ('education', 'education and training', 'academic background',
                  'academic qualifications', 'education background', 'qualifications',
                  'pendidikan', 'kelayakan akademik', 'latar belakang pendidikan'),
    'experience': ('experience', 'work experience', 'employment history', 'work history',
                   'professional experience', 'internship experience', 'internship', 'industrial training',
                   'pengalaman kerja', 'pengalaman', 'latihan industri', 'pengalaman latihan industri'),
    'projects': ('projects', 'project experience', 'personal projects', 'academic projects', 'selected projects',
                 'final year project', 'final year projects', 'projek', 'projek akademik',
                 'projek tahun akhir', 'projek peribadi'),
    'certifications': ('certifications', 'certificates', 'licenses and certifications',
                       'pensijilan', 'sijil'),
    'summary': ('summary', 'professional summary', 'profile', 'personal profile', 'about me',
                'ringkasan', 'profil diri'),
    'excluded': ('career objective', 'career objectives', 'objective', 'objectives', 'desired role',
                 'target role', 'job description', 'job requirements', 'requirements',
                 'references', 'reference', 'referees', 'objektif kerjaya', 'rujukan'),
    'other': ('languages', 'awards', 'volunteering', 'interests', 'hobbies', 'contact',
              'additional information', 'bahasa', 'minat', 'aktiviti kokurikulum'),
}
SECTION_KEYS = {label: kind for kind, labels in HEADINGS.items() for label in labels}


@dataclass(frozen=True)
class Line:
    text: str
    start: int

    def evidence(self, section, start=0, end=None, *, method='', alias_id=None):
        end = len(self.text) if end is None else end
        context = self.text[max(0, start - 90):min(len(self.text), end + 50)] if method else ''
        return Evidence(self.start + start, self.start + end, self.text[start:end], section, context, method, alias_id)


def _heading(value):
    prefix, separator, _ = value.replace('：', ':', 1).partition(':')
    label = prefix.strip(' \t#*_=–—•-')
    kind = SECTION_KEYS.get(normalize_label(label.replace('&', 'and')))
    return (kind, label, len(prefix) + len(separator)) if kind else None


def split_sections(text):
    sections = []
    lines = []
    kind, label, offset, begin = 'unclassified', '', 0, 0
    for raw in text.splitlines(keepends=True):
        line = raw.strip()
        start = offset + len(raw) - len(raw.lstrip())
        if line and (heading := _heading(line)):
            if lines or label:
                sections.append((Section(kind, label, begin, offset), lines))
            kind, label, consumed = heading
            begin, lines = offset, []
            remainder = line[consumed:]
            start += consumed + len(remainder) - len(remainder.lstrip())
            line = remainder.strip()
        if line:
            lines.append(Line(line, start))
        offset += len(raw)
    if lines or label:
        sections.append((Section(kind, label, begin, len(text)), lines))
    return sections


def bounded_lines(sections):
    return [(section, [line for line in lines if len(line.text) <= MAX_LINE_CHARS])
            for section, lines in sections]
