"""Evaluate the checked-in synthetic fixtures against an isolated Phase 2A catalog."""
import os
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch


def measure(fixtures, extractor, normalize):
    results = dict(
        fixtures=len(fixtures), expected_skills=0, predicted_skills=0, exact_skills=0,
        expected_mappings=0, predicted_mappings=0, correct_mappings=0,
        expected_sections=0, detected_sections=0, expected_entities=0, detected_entities=0,
    )
    false_positives, false_negatives, mapping_errors = [], [], []
    entity_misses, entity_extras, runtimes = [], [], []
    statuses = Counter()
    skill_support = Counter()
    for fixture in fixtures:
        start = perf_counter()
        extracted = extractor.extract(fixture.text)
        runtimes.append((perf_counter() - start) * 1000)
        expected = {normalize(mention): catalog for mention, catalog in fixture.skills.items()}
        predicted = {}
        for row in extracted.suggestions:
            if row.category != 'skill':
                continue
            statuses[row.method] += 1
            skill_support[row.support] += 1
            if row.support == 'explicit':
                for evidence in row.evidence:
                    predicted[normalize(evidence.excerpt)] = row.canonical.get('name')
        mapped = {key: name for key, name in predicted.items() if name}
        observed_sections = Counter(section.kind for section in extracted.sections)
        result_sections = sum((Counter(fixture.sections) & observed_sections).values())
        expected_entities = {(kind, normalize(value)) for kind, value in fixture.entities}
        predicted_entities = {(row.category, normalize(row.value)) for row in extracted.suggestions
                              if row.category != 'skill'}
        results['expected_skills'] += len(expected)
        results['predicted_skills'] += len(predicted)
        results['exact_skills'] += len(expected.keys() & predicted.keys())
        results['expected_mappings'] += sum(name is not None for name in expected.values())
        results['predicted_mappings'] += len(mapped)
        results['correct_mappings'] += sum(expected.get(key) == name for key, name in mapped.items())
        results['expected_sections'] += len(fixture.sections)
        results['detected_sections'] += result_sections
        results['expected_entities'] += len(expected_entities)
        results['detected_entities'] += len(expected_entities & predicted_entities)
        false_positives.extend((fixture.id, key) for key in sorted(predicted.keys() - expected.keys()))
        false_negatives.extend((fixture.id, key) for key in sorted(expected.keys() - predicted.keys()))
        mapping_errors.extend((fixture.id, key, name) for key, name in mapped.items() if expected.get(key) != name)
        entity_misses.extend((fixture.id, row) for row in sorted(expected_entities - predicted_entities))
        entity_extras.extend((fixture.id, row) for row in sorted(predicted_entities - expected_entities))
    return {
        **results,
        'skill_precision': results['exact_skills'] / results['predicted_skills'],
        'skill_recall': results['exact_skills'] / results['expected_skills'],
        'mapping_precision': results['correct_mappings'] / results['predicted_mappings'],
        'mapping_recall': results['correct_mappings'] / results['expected_mappings'],
        'section_coverage': results['detected_sections'] / results['expected_sections'],
        'skill_methods': dict(statuses),
        'unmatched_suggestions': statuses['unmatched'],
        'ambiguous_mapping_suggestions': statuses['ambiguous'] + statuses['unverified_alias'],
        'skill_evidence_needing_clarification': skill_support['ambiguous'],
        'runtime_ms': {'median': round(median(runtimes), 2), 'max': round(max(runtimes), 2)},
        'false_positive_skills': false_positives,
        'false_negative_skills': false_negatives,
        'incorrect_mappings': mapping_errors,
        'structured_entry_misses': entity_misses,
        'extra_structured_entries': entity_extras,
    }


def main():
    import io
    import json

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'careercoach.test_settings'
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from recommender.models import Skill, SkillAlias
    from recommender.normalization import normalize_label
    from resume.intelligence.evaluation_fixtures import FIXTURES
    from resume.intelligence.pipeline import DeterministicExtractor

    if connection.vendor != 'sqlite' or connection.settings_dict['NAME'] != ':memory:':
        raise RuntimeError('Evaluation requires an isolated in-memory SQLite database.')
    output = io.StringIO()
    with patch('socket.socket.connect', side_effect=AssertionError('Network access is forbidden')):
        call_command('migrate', verbosity=0, interactive=False)
        call_command('import_data', data_dir=root / 'data', stdout=output)
        call_command('seed_career_enrichment', stdout=output)
        results = measure(FIXTURES, DeterministicExtractor(), normalize_label)
    print(json.dumps({'catalog_skills': Skill.objects.count(), 'catalog_aliases': SkillAlias.objects.count(),
                      **results}, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
