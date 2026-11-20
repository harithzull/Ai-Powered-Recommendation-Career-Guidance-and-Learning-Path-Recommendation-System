"""Conservative local rules for structured entries."""
import re

from recommender.normalization import normalize_label

from .schema import MAX_STRUCTURED_PER_SECTION, MAX_VALUE_CHARS, Suggestion
from .sections import Line
from .skills import ACTION, DESIRED, NEGATED, PROJECT_ROLE, TECH_LABEL

BULLET = re.compile(r'^(?:[-–—•*]\s+|\d{1,2}[.)]\s+)')
YEAR = r'(?:19|20)\d{2}'
MONTH = (r'(?:Jan(?:uary|uari)?|Feb(?:ruary|ruari)?|Mar(?:ch)?|Mac|Apr(?:il)?|May|Mei|'
         r'Jun(?:e)?|Jul(?:y|ai)?|Aug(?:ust)?|Ogos|Sep(?:t(?:ember)?)?|Oct(?:ober)?|'
         r'Okt(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Dis(?:ember)?)')
DATE = rf'(?:{MONTH}\.?\s+{YEAR}|(?:0?[1-9]|1[0-2])[/.-]{YEAR}|{YEAR}[-/](?:0[1-9]|1[0-2])|{YEAR})'
DATE_RANGE = re.compile(rf'(?<!\w)(?P<start>{DATE})\s*(?:[-–—]|\bto\b|\bhingga\b)\s*'
                        rf'(?P<end>present|current|now|kini|sekarang|{DATE})(?!\w)', re.IGNORECASE)
DATE_VALUE = re.compile(rf'(?<!\w){DATE}(?!\w)', re.IGNORECASE)
CURRENT_WORK = {'present', 'current', 'now', 'kini', 'sekarang'}
QUALIFICATION = re.compile(
    r'^(?:\d{1,2}[.)]\s+)?(?:bachelor(?:[’\']s)?|master(?:[’\']s)?|doctor(?:ate)?|'
    r'ph\.?d\.?|b\.?sc\.?|m\.?sc\.?|b\.?eng\.?|m\.?eng\.?|mba|degree|'
    r'advanced diploma|diploma|foundation|matriculation|matrikulasi|'
    r'ijazah sarjana muda|ijazah sarjana|sarjana muda|sijil tinggi persekolahan malaysia|'
    r'spm|stpm|sijil pelajaran malaysia|a-levels?|certificate)(?=\W|$)', re.IGNORECASE)
FIELD = re.compile(r'\b(?:in|of|dalam)\s+(.+?)(?=\s*[(;]|\s+(?:with honours|expected|graduated|currently|'
                   r'completed|pursuing|tamat)\b|$)', re.IGNORECASE)
INSTITUTION = re.compile(r'\b(?:university|universities|universiti|polytechnic|politeknik|college|kolej|'
                         r'institute|institut|academy|akademi|school|sekolah)\b', re.IGNORECASE)
EDU_CURRENT = re.compile(r'\b(?:currently (?:studying|enrolled)|pursuing|in progress|sedang (?:belajar|mengikuti))\b', re.IGNORECASE)
EDU_COMPLETED = re.compile(r'\b(?:graduated|completed|conferred|tamat pengajian|lulus)\b', re.IGNORECASE)
EDU_EXPECTED = re.compile(r'\b(?:expected|anticipated|dijangka)\b', re.IGNORECASE)
ROLE = re.compile(r'\b(?:intern(?:ship)?|trainee|engineer|developer|analyst|assistant|associate|'
                  r'manager|officer|coordinator|executive|technician|designer|clerk|cashier|'
                  r'tutor|consultant|administrator|accountant|teacher|specialist|supervisor|'
                  r'industrial training|pelatih|pembantu|pegawai|jurutera|juruteknik|'
                  r'pereka|pengurus|penganalisis|pembangun)\b', re.IGNORECASE)
WORK_TYPE = re.compile(r'\b(?:intern(?:ship)?|industrial training|latihan industri|pelatih|'
                       r'part[- ]time|full[- ]time|contract|kontrak|sambilan|sepenuh masa)\b', re.IGNORECASE)
WORK_CURRENT = re.compile(r'\b(?:currently employed|currently working|sedang bekerja)\b', re.IGNORECASE)
TRAILING_WORK_TYPE = re.compile(r'\s*\(([^()]*)\)$')
ORGANIZATION = re.compile(r'^(?:company|employer|organization|organisation|syarikat|majikan)\s*:\s*|'
                          r'\b(?:sdn\.?\s*bhd\.?|berhad|enterprise|ltd\.?|inc\.?|plc|llc)\b', re.IGNORECASE)
ROLE_SEPARATOR = re.compile(r'\s+\b(?:at|di)\b\s+|\s+[-–—]\s+|\s*[|,]\s*', re.IGNORECASE)
DESCRIBE = re.compile(r'^\W*(?:description|responsibilities|about|penerangan)\s*:\s*', re.IGNORECASE)
PROJECT_URL = re.compile(r'https?://[^\s<>"\']{1,230}', re.IGNORECASE)
PROJECT_LINK = re.compile(r'^(?:project )?(?:url|link|repo(?:sitory)?)\s*:', re.IGNORECASE)
PROJECT_KIND = {
    'academic projects': 'academic', 'final year project': 'academic', 'final year projects': 'academic',
    'projek akademik': 'academic', 'projek tahun akhir': 'academic',
    'personal projects': 'personal', 'projek peribadi': 'personal',
}
MAX_FOLLOWING_LINES = 6


def _clean(text):
    return BULLET.sub('', text).strip(' \t|,;–—-')[:MAX_VALUE_CHARS]


def _date_fields(text, fields):
    if dates := DATE_RANGE.search(text):
        start, end = dates.group('start', 'end')
        fields.update(start_date=start, end_date=end)
        if end.casefold() in CURRENT_WORK:
            fields['current_employment'] = 'Explicitly current'
    elif date := DATE_VALUE.search(text):
        fields['stated_date'] = date[0]
    if WORK_CURRENT.search(text):
        fields['current_employment'] = 'Explicitly current'


def _make(category, value, method, support, fields, section, lines):
    return Suggestion(category, value, normalize_label(value)[:500], [
        line.evidence(section.kind) for line in lines
    ], method, support, fields)


def _education_status(evidence, fields):
    for marker, status, date_key in (
        (EDU_EXPECTED, 'Expected graduation', 'expected_graduation_date'),
        (EDU_CURRENT, 'Currently studying', None),
        (EDU_COMPLETED, 'Explicitly completed', 'graduation_date'),
    ):
        for line in evidence:
            match = marker.search(line.text)
            if match and not NEGATED.search(line.text[:match.start()]):
                fields['study_status'] = status
                dates = DATE_VALUE.findall(line.text)
                if date_key and len(dates) == 1:
                    fields[date_key] = dates[0]
                return


def education(section, lines):
    anchors = [index for index, line in enumerate(lines) if QUALIFICATION.match(_clean(line.text))]
    for index, following in zip(anchors, [*anchors[1:], len(lines)]):
        line = lines[index]
        raw = _clean(line.text)
        chunks = re.split(r'\s*[,;|]\s*|\s+[–—]\s+', raw)
        qualification = chunks[0]
        split = DATE_VALUE.search(qualification)
        if split:
            qualification = qualification[:split.start()].rstrip(' (-–—')
        qualification = re.split(r'\s+(?:graduated|completed|expected|currently|tamat)\b',
                                 qualification, maxsplit=1, flags=re.IGNORECASE)[0]
        qualification = qualification.rstrip(' (–—-')
        if not qualification:
            continue
        fields, evidence = {'qualification': qualification}, [line]
        if field := FIELD.search(qualification):
            fields['field_of_study'] = field[1].strip()
        if section.kind == 'education':
            for extra in lines[index + 1:min(following, index + 4)]:
                if (INSTITUTION.search(extra.text) or DATE_VALUE.search(extra.text)
                        or EDU_CURRENT.search(extra.text) or EDU_COMPLETED.search(extra.text)):
                    evidence.append(extra)
        combined = ' | '.join(item.text for item in evidence)
        for item in [*chunks[1:], *[item.text for item in evidence[1:]]]:
            candidate = _clean(DATE_VALUE.split(item, maxsplit=1)[0]).rstrip('(')
            if INSTITUTION.search(candidate) and not ACTION.match(candidate):
                fields['institution'] = candidate
                break
        _education_status(evidence, fields)
        if not ('graduation_date' in fields or 'expected_graduation_date' in fields):
            dates = list(dict.fromkeys(DATE_VALUE.findall(combined)))
            if len(dates) == 1:
                fields['stated_date'] = dates[0]
        support = 'inferred' if section.kind == 'unclassified' else 'explicit'
        yield _make('education', qualification, 'qualification_pattern', support, fields, section, evidence)


def _role_line(text):
    if ACTION.match(text) or DESIRED.search(text) or len(text) > 180 or not ROLE.search(text):
        return None
    if DATE_RANGE.search(text):
        text = DATE_RANGE.split(text, maxsplit=1)[0].rstrip(' (,|–—-')
    pieces = ROLE_SEPARATOR.split(text, maxsplit=2)
    title = pieces[0].strip()
    if not ROLE.search(title) or len(title.split()) > 12 or title.endswith(('.', '?', '!')):
        return None
    organization = pieces[1].strip() if len(pieces) > 1 else ''
    if DATE_VALUE.match(organization):
        organization = ''
    if (qualifier := TRAILING_WORK_TYPE.search(organization)) and WORK_TYPE.fullmatch(qualifier[1]):
        organization = organization[:qualifier.start()]
    return title, organization


def _mentions(lines, line_skills):
    return ', '.join(dict.fromkeys(value for line in lines
                                  for value in line_skills.get(line.start, {}).values()))[:MAX_VALUE_CHARS]


def experience(section, lines, line_skills):
    anchors = [(index, match) for index, line in enumerate(lines) if (match := _role_line(_clean(line.text)))]
    for (index, (title, organization)), (following, _) in zip(anchors, [*anchors[1:], (len(lines), None)]):
        line = lines[index]
        fields, evidence, description_lines = {'job_title': title}, [line], []
        if organization:
            fields['organization'] = organization
        _date_fields(line.text, fields)
        if work_type := WORK_TYPE.search(line.text):
            fields['employment_type'] = work_type[0]
        for item in lines[index + 1:min(following, index + MAX_FOLLOWING_LINES)]:
            value = _clean(item.text)
            if ACTION.match(item.text) or DESCRIBE.match(item.text):
                description_lines.append(item)
            elif ORGANIZATION.search(value) and 'organization' not in fields:
                fields['organization'] = value.split(':', 1)[1].strip() if ':' in value else value
            elif WORK_TYPE.fullmatch(value):
                fields.setdefault('employment_type', value)
            elif DATE_RANGE.fullmatch(value) or DATE_VALUE.fullmatch(value) or WORK_CURRENT.search(value):
                _date_fields(value, fields)
            elif TECH_LABEL.match(item.text):
                pass
            elif BULLET.match(item.text):
                description_lines.append(item)
            else:
                continue
            evidence.append(item)
        if description_lines:
            fields['description'] = ' '.join(_clean(item.text) for item in description_lines)[:MAX_VALUE_CHARS]
        if mentions := _mentions(evidence, line_skills):
            fields['technologies_or_skills'] = mentions
        support = 'explicit' if organization or len(fields) > 1 else 'ambiguous'
        yield _make('experience', title, 'work_entry_pattern', support, fields, section, evidence)


def _project_title(line, next_line):
    value = _clean(line.text)
    if (not value or ACTION.match(value) or QUALIFICATION.match(value) or _role_line(value)
            or PROJECT_LINK.match(value) or PROJECT_URL.match(value)
            or TECH_LABEL.match(value) or PROJECT_ROLE.match(value) or DESCRIBE.match(value)):
        return None
    prefix, sep, description = value.partition(':')
    if len(prefix.split()) > 12 or prefix.endswith(('.', '?', '!')) or PROJECT_URL.search(prefix):
        return None
    if sep and prefix.strip() and description.strip():
        return prefix.strip(), description.strip()
    if (next_line and (ACTION.match(next_line.text) or BULLET.match(next_line.text)
                       or TECH_LABEL.match(next_line.text) or PROJECT_ROLE.match(next_line.text)
                       or DESCRIBE.match(next_line.text) or PROJECT_URL.match(next_line.text))):
        return prefix, ''
    if prefix[:1].isupper() and len(prefix.split()) <= 6 and not re.search(r'\b(?:is|was|were|will|using)\b', prefix, re.I):
        return prefix, ''
    return None


def projects(section, lines, line_skills):
    anchors = []
    for index, line in enumerate(lines):
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if match := _project_title(line, next_line):
            anchors.append((index, match))
    for (index, (title, description)), (following, _) in zip(anchors, [*anchors[1:], (len(lines), None)]):
        fields, evidence = {'project_name': title}, [lines[index]]
        contributions = []
        if kind := PROJECT_KIND.get(normalize_label(section.label)):
            fields['project_type'] = kind
        for line in lines[index:min(following, index + MAX_FOLLOWING_LINES)]:
            if 'project_url' not in fields and (url := PROJECT_URL.search(line.text)):
                fields['project_url'] = url[0].rstrip('.,;)')
            if role := PROJECT_ROLE.match(line.text):
                fields['role_or_contributions'] = _clean(line.text[role.end():])
            elif ACTION.match(line.text):
                contributions.append(_clean(line.text))
            elif explicit := DESCRIBE.match(line.text):
                description = _clean(line.text[explicit.end():])
            elif line is not evidence[0] and not (TECH_LABEL.match(line.text) or PROJECT_URL.search(line.text)):
                continue
            if line is not evidence[0]:
                evidence.append(line)
        if contributions:
            fields.setdefault('role_or_contributions', ' '.join(contributions)[:MAX_VALUE_CHARS])
        if description:
            fields['description'] = description
        if mentions := _mentions(evidence, line_skills):
            fields['technologies'] = mentions
        support = 'explicit' if len(fields) > (2 if 'project_type' in fields else 1) else 'ambiguous'
        yield _make('project', title, 'project_entry_pattern', support, fields, section, evidence)


def structured_suggestions(sections, line_skills, check_budget):
    emitters = {'education': education, 'unclassified': education, 'experience': experience, 'projects': projects}
    counts = dict.fromkeys(('education', 'experience', 'project'), 0)
    for section, lines in sections:
        check_budget()
        if section.kind not in emitters:
            continue
        lines = [Line(line.text[:MAX_VALUE_CHARS], line.start) for line in lines]
        emitter = emitters[section.kind]
        entries = emitter(section, lines) if emitter is education else emitter(section, lines, line_skills)
        for entry in entries:
            check_budget()
            if counts[entry.category] >= MAX_STRUCTURED_PER_SECTION:
                break
            counts[entry.category] += 1
            yield entry
