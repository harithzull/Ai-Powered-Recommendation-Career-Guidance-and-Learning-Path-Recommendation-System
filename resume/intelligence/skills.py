"""Collect text mentions and record whether their context supports the suggestion."""
import re

from recommender.normalization import normalize_label

from .matching import LINK_OR_EMAIL, MATCH_PRIORITY
from .schema import MAX_OCCURRENCES, MAX_SKILLS, Suggestion

CLAUSE_BREAK = re.compile(r'[;!?]+|(?<=\w)\.(?=\s|$)|\b(?:but|however|tetapi)\b', re.IGNORECASE)
NEGATED = re.compile(r"\b(?:no (?:direct |prior )?(?:hands-on )?experience (?:with|in|using|of)|"
                     r"never (?:used|worked with|learned)|not (?:familiar with|proficient in|used|experienced in)|"
                     r"unfamiliar with|without (?:experience (?:in|with) |using )?|didn't (?:use|learn)|"
                     r"do not (?:know|use)|lack(?:ing)? (?:experience (?:in|with) )?|"
                     r"tiada pengalaman (?:dalam|dengan)|tidak (?:menggunakan|mahir)|no|not)\b", re.IGNORECASE)
UNCERTAIN = re.compile(r'\b(?:currently learning|learning|beginner in|exposure to|familiarizing with|'
                       r'introduction to|introductory|basic exposure to|coursework in|sedang belajar)\b', re.IGNORECASE)
DESIRED = re.compile(r'\b(?:seek(?:ing)?(?: a| an| to)?|aspir(?:ing|e to)|wish to|interested in learning|'
                     r'want to learn|would like to|job requirements?|job description|'
                     r'candidate must|ideal candidate|must (?:have|know|use)|requirements include|'
                     r'(?:will be|required to) (?:use|learn)|looking to learn|ingin belajar)\b', re.IGNORECASE)
CUE = re.compile(r'\b(?:using|used|built with|developed with|written in|worked with|proficient in|'
                 r'skilled in|experienced in|experience with|expertise in|familiar with|'
                 r'technologies|tech stack|tools|kemahiran|menggunakan)\b\s*:?\s*', re.IGNORECASE)
ACTION = re.compile(r'^\W*(?:i\s+)?(?:built|developed|designed|implemented|led|managed|conducted|'
                    r'performed|prepared|maintained|deployed|created|analy[sz]ed|coordinated|'
                    r'supported|automated|processed|provided|worked|reviewed|used|'
                    r'membangunkan|menyediakan|mengurus)\b', re.IGNORECASE)
ITEM_BREAK = re.compile(r'[,;|•·]|\s+/\s+|\s+\band\b\s+', re.IGNORECASE)
LIST_DELIMITER = re.compile(r'[,;|•·]|\s+/\s+')
ITEM = re.compile(r'[\w.#/+&-]+(?:\s+[\w.#/+&-]+){0,6}\Z')
TOOL_NAME = re.compile(r'[A-Z][\w.+#-]{1,39}\Z')
STOP_ITEM = re.compile(r'\b(?:want|seeking|experience|never|none|n/a|etc|currently|'
                       r'using|learn|learning|with|used|for|a|an|the|have|good|strong|knowledge of)\b', re.IGNORECASE)
TECH_LABEL = re.compile(r'\b(?:technologies|tech stack|tools)\s*:', re.IGNORECASE)
SELF_REPORT = re.compile(r'^(?:experience with|experienced in|proficient in|skilled in|familiar with)\b', re.IGNORECASE)
PROJECT_ROLE = re.compile(r'^\W*(?:role|contributions?)\s*:', re.IGNORECASE)


def _clauses(value):
    start = 0
    for boundary in CLAUSE_BREAK.finditer(value):
        yield start, value[start:boundary.start()]
        start = boundary.end()
    yield start, value[start:]


def _support(clause, start, section):
    prefix = clause[:start]
    if section == 'excluded' or NEGATED.search(prefix) or DESIRED.search(prefix):
        return 'unsupported'
    if UNCERTAIN.search(prefix):
        return 'ambiguous'
    return 'explicit'


def _items(clause, offset):
    start = 0
    for match in ITEM_BREAK.finditer(clause):
        yield from _item(clause[start:match.start()], offset + start)
        start = match.end()
    yield from _item(clause[start:], offset + start)


def _item(raw, offset):
    value = raw.strip(' \t-–—•*()')
    if (1 < len(value) <= 80 and ITEM.fullmatch(value) and not STOP_ITEM.search(value)
            and not LINK_OR_EMAIL.search(value) and any(letter.isalpha() for letter in value)):
        start = offset + raw.index(value)
        yield start, start + len(value)


def _unknown_spans(clause, section, cue, occupied):
    if NEGATED.search(clause) or UNCERTAIN.search(clause) or DESIRED.search(clause):
        return
    if section == 'skills' and not cue and not ACTION.match(clause):
        yield from _items(clause, 0)
    elif cue:
        tail = clause[cue.end():]
        if (occupied or LIST_DELIMITER.search(tail) or TECH_LABEL.search(cue[0])
                or SELF_REPORT.match(cue[0]) or TOOL_NAME.fullmatch(tail.strip())):
            yield from _items(tail, cue.end())


def _candidate_spans(line, section, catalog):
    for offset, clause in _clauses(line.text):
        cue = CUE.search(clause)
        claims_skill = section in ('skills', 'excluded') or bool(cue or ACTION.match(clause))
        if not claims_skill and not (NEGATED.search(clause) or UNCERTAIN.search(clause) or DESIRED.search(clause)):
            continue
        occupied = []
        for start, end, mapping in catalog.matches(clause):
            support = _support(clause, start, section)
            if not claims_skill and support == 'explicit':
                continue
            occupied.append((start, end))
            yield offset + start, offset + end, support, mapping
        if section == 'excluded':
            continue
        for start, end in _unknown_spans(clause, section, cue, occupied):
            if not any(start < right and end > left for left, right in occupied):
                yield offset + start, offset + end, _support(clause, start, section), ([], 'unmatched', None)


def extract_skills(sections, catalog, check_budget):
    rows = {}
    line_skills = {}
    for section, lines in sections:
        for line in lines:
            check_budget()
            for start, end, support, (ids, method, alias_id) in _candidate_spans(line, section.kind, catalog):
                value = line.text[start:end]
                normalized = normalize_label(value)
                if support == 'unsupported':
                    ids, method, alias_id = [], 'excluded_context', None
                elif method in ('ambiguous', 'unverified_alias'):
                    support = 'ambiguous'
                matched = method in MATCH_PRIORITY
                key = (ids[0] if matched else normalized, support, matched)
                evidence = line.evidence(section.kind, start, end, method=method, alias_id=alias_id)
                if key not in rows and len(rows) >= MAX_SKILLS:
                    continue
                row, previous_ids, previous_alias_id = rows.setdefault(
                    key, (Suggestion('skill', value, normalized, [], method, support), ids, alias_id))
                if matched and MATCH_PRIORITY[method] < MATCH_PRIORITY[row.method]:
                    row.method = method
                    row.value, row.normalized = value, normalized
                    rows[key] = row, ids, alias_id
                if len(row.evidence) < MAX_OCCURRENCES:
                    row.evidence.append(evidence)
                if support == 'explicit':
                    line_skills.setdefault(line.start, {})[key] = value

    check_budget()
    catalog.snapshots({pk for _, ids, _ in rows.values() for pk in ids})
    proof = catalog.alias_provenance({alias_id for _, _, alias_id in rows.values() if alias_id is not None})
    for row, ids, alias_id in rows.values():
        snapshots = catalog.snapshots(ids)
        if row.method in MATCH_PRIORITY and len(snapshots) == 1:
            row.canonical = dict(snapshots[0], **proof.get(alias_id, {}))
            if row.method == 'reviewed_variation':
                row.canonical['reviewed_variation'] = row.value
        elif snapshots:
            row.alternatives = snapshots
    return [row for row, _, _ in rows.values()], line_skills
