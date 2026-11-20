"""Bounded phrase lookup over the existing catalog. No fuzzy or network lookup."""
import re

from recommender.models import ReviewStatus, Skill, SkillAlias
from recommender.normalization import normalize_label

from .schema import MAX_CATALOG_ROWS

TOKEN = re.compile(r'https?://data\.europa\.eu/esco/skill/[0-9a-f-]{36}(?![\w/-])'
                   r'|(?<!\w)\.[A-Za-z][\w]*(?:\.[\w]+)*'
                   r"|(?<![\w+#])[\w]+(?:\.[\w]+)*(?:\+\+|#)?(?![\w+#])|[()/&’']", re.IGNORECASE)
LINK_OR_EMAIL = re.compile(r'(?:https?://|www\.)[^\s<>,;]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', re.IGNORECASE)
DASHES = '-\u2010\u2011\u2012\u2013\u2014'
GAP = re.compile(r'[\s' + re.escape(DASHES) + r']*')
DASH_TRANSLATION = str.maketrans({dash: ' ' for dash in DASHES})
MAX_TERMS = 24
MAX_ALTERNATIVES = 5
MAX_REVIEWED_VARIATIONS = 8
MATCH_PRIORITY = {'exact_match': 0, 'verified_alias': 1, 'reviewed_variation': 2}


class CatalogLimit(Exception):
    pass


def skill_snapshot(skill):
    metadata = skill.source_metadata if isinstance(skill.source_metadata, dict) else {}
    provenance = {key: metadata[key][:240] for key in ('dataset', 'dataset_version', 'source_version',
                                                      'source_file', 'version', 'file', 'file_sha256',
                                                      'record_hash', 'verification')
                  if isinstance(metadata.get(key), str)}
    if type(metadata.get('line')) is int:
        provenance['line'] = metadata['line']
    return {
        'id': skill.pk, 'name': skill.name, 'esco_uri': skill.esco_uri,
        'taxonomy': skill.source_taxonomy, 'quality_status': skill.quality_status,
        'source_name': skill.source_name,
        'source': provenance,
    }


def _words(value):
    tokens = tuple(TOKEN.finditer(value))
    if not tokens or len(tokens) > MAX_TERMS or tokens[0].start() or tokens[-1].end() != len(value):
        return ()
    if not all(GAP.fullmatch(value[left.end():right.start()]) for left, right in zip(tokens, tokens[1:])):
        return ()
    return tuple(normalize_label(token[0]) for token in tokens)


def _compact_variation(value):
    return normalize_label(value.translate(DASH_TRANSLATION))


class Catalog:
    def __init__(self, check_budget):
        self._check_budget = check_budget
        self._root = {}
        self._snapshots = {}
        skills = Skill.objects.order_by('pk').values_list(
            'pk', 'name', 'esco_uri', 'quality_status', 'source_metadata__resume_variations')
        size = 0
        for size, (pk, name, uri, quality, variations) in enumerate(skills[:MAX_CATALOG_ROWS + 1].iterator(), 1):
            check_budget()
            if size > MAX_CATALOG_ROWS:
                raise CatalogLimit
            self._add(name, pk, 'exact_match')
            if quality == ReviewStatus.REVIEWED and isinstance(variations, list):
                for record in variations[:MAX_REVIEWED_VARIATIONS]:
                    self._add_reviewed_variation(pk, name, record)
            if uri:
                self._add(uri, pk, 'exact_match')
                self._add(uri.rsplit('/', 1)[-1], pk, 'exact_match')
        aliases = SkillAlias.objects.order_by('pk').values_list(
            'pk', 'name', 'skill_id', 'kind', 'review_status', 'review_metadata__evidence')
        remaining = MAX_CATALOG_ROWS - size
        for index, (alias_id, name, pk, kind, status, proof) in enumerate(aliases[:remaining + 1].iterator(), 1):
            check_budget()
            if index > remaining:
                raise CatalogLimit
            reviewed = kind == SkillAlias.Kind.EXACT and status == ReviewStatus.REVIEWED and bool(proof)
            self._add(name, pk, 'verified_alias' if reviewed else 'unverified_alias', alias_id=alias_id)

    def _add_reviewed_variation(self, pk, canonical, record):
        if not isinstance(record, dict) or not isinstance(record.get('label'), str) or not record.get('evidence'):
            return
        label = record['label'][:256]
        if len(label) <= 255 and _compact_variation(label) == _compact_variation(canonical):
            self._add(label, pk, 'reviewed_variation')

    def _add(self, label, pk, method, *, alias_id=None):
        label = label.strip()
        words = _words(label)
        if not words or (len(label) <= 2 and label.isalpha() and not label.isupper()):
            return
        node = self._root
        for word in words:
            node = node.setdefault(word, {})
        node.setdefault(None, []).append((label, pk, method, alias_id))

    def matches(self, value):
        """Yield non-overlapping longest matches. Sentence and URL boundaries stay intact."""
        tokens = list(TOKEN.finditer(value))
        masked = set()
        token_index = 0
        for link in LINK_OR_EMAIL.finditer(value):
            if TOKEN.fullmatch(link[0].rstrip('.!?)]}')) and '/esco/skill/' in link[0].lower():
                continue
            while token_index < len(tokens) and tokens[token_index].start() < link.end():
                if tokens[token_index].end() > link.start():
                    masked.add(token_index)
                token_index += 1
        start = 0
        while start < len(tokens):
            self._check_budget()
            node, best = self._root, None
            for end in range(start, min(len(tokens), start + MAX_TERMS)):
                token = tokens[end]
                if end in masked or (end > start and not GAP.fullmatch(value[tokens[end - 1].end():token.start()])):
                    break
                node = node.get(normalize_label(token[0]))
                if node is None:
                    break
                if None in node:
                    begin, finish = tokens[start].start(), token.end()
                    matched = self._resolve(value[begin:finish], node[None])
                    if matched:
                        best = end, begin, finish, matched
            if best:
                end, begin, finish, matched = best
                yield begin, finish, matched
                start = end + 1
            else:
                start += 1

    def _resolve(self, value, candidates):
        # Exact identities take precedence. A punctuation variant that maps to
        # several catalog identities stays ambiguous even if only one is reviewed.
        exact, aliases, reviewed, unverified = {}, {}, {}, {}
        variant_identities = set()
        groups = {'exact_match': exact, 'verified_alias': aliases, 'reviewed_variation': reviewed,
                  'unverified_alias': unverified}
        key, variant_key = normalize_label(value), _compact_variation(value)
        if len(value) > 500 or len(key) > 500:
            return None
        for label, skill_id, method, alias_id in candidates:
            self._check_budget()
            if len(label) <= 2 and label.isalpha() and label != value:
                continue
            if normalize_label(label) == key:
                groups[method][skill_id] = alias_id
            elif method == 'exact_match' and _compact_variation(label) == variant_key:
                variant_identities.add(skill_id)
        if exact:
            return sorted(exact)[:MAX_ALTERNATIVES], 'exact_match' if len(exact) == 1 else 'ambiguous', None
        if aliases:
            return sorted(aliases)[:MAX_ALTERNATIVES], 'verified_alias' if len(aliases) == 1 else 'ambiguous', next(iter(aliases.values()))
        if reviewed:
            identities = variant_identities | reviewed.keys()
            return sorted(identities)[:MAX_ALTERNATIVES], 'reviewed_variation' if len(identities) == 1 else 'ambiguous', None
        if unverified:
            return sorted(unverified)[:MAX_ALTERNATIVES], 'unverified_alias', None
        return None

    def snapshots(self, ids):
        missing = set(ids) - self._snapshots.keys()
        if missing:
            self._snapshots.update((skill.pk, skill_snapshot(skill)) for skill in Skill.objects.filter(pk__in=missing)
                                   .only('pk', 'name', 'esco_uri', 'source_name', 'source_taxonomy',
                                         'quality_status', 'source_metadata').order_by())
        return [self._snapshots[pk] for pk in ids if pk in self._snapshots]

    @staticmethod
    def alias_provenance(alias_ids):
        aliases = SkillAlias.objects.filter(pk__in=alias_ids, kind=SkillAlias.Kind.EXACT,
                                            review_status=ReviewStatus.REVIEWED).order_by()
        return {alias.pk: {'alias_id': alias.pk, 'alias': alias.name,
                           'alias_review_status': alias.review_status}
                for alias in aliases}
