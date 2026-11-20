"""Private analysis history and owner-scoped review writes."""
import hashlib
from dataclasses import asdict

from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from resume import models
from resume.intelligence import schema
from resume.intelligence.pipeline import DeterministicExtractor, UnsupportedText, validate_text


class StaleAnalysis(Exception):
    pass


class RevisionLimit(Exception):
    pass


class InvalidReview(Exception):
    pass


@sensitive_variables()
def source_checksums(document):
    if document.status != models.ResumeDocument.Status.COMPLETED:
        raise UnsupportedText
    validate_text(document.extracted_text)
    return document.checksum, hashlib.sha256(document.extracted_text.encode('utf-8')).hexdigest()


def source_matches(analysis, document):
    try:
        return source_checksums(document) == (analysis.source_checksum, analysis.text_checksum)
    except UnsupportedText:
        return False


@sensitive_variables()
def analyze(owner, document_id, *, rerun=False, expected_latest=None):
    """Call under the existing user work lease. Publish a full snapshot atomically."""
    documents = models.ResumeDocument.objects.filter(owner=owner)
    document = documents.get(pk=document_id)
    checksums = source_checksums(document)
    latest = document.analyses.only('id', 'revision', 'source_checksum', 'text_checksum',
                                    'extractor_version').first()
    current_id = latest.pk if latest else None
    if rerun:
        if not latest or expected_latest != current_id:
            raise StaleAnalysis
    elif latest and latest.extractor_version == schema.EXTRACTOR_VERSION and (
            latest.source_checksum, latest.text_checksum) == checksums:
        return latest
    if latest and latest.revision >= schema.MAX_REVISIONS:
        raise RevisionLimit

    result = DeterministicExtractor().extract(document.extracted_text)
    with transaction.atomic():
        locked = documents.select_for_update().get(pk=document_id)
        if source_checksums(locked) != checksums or locked.analyses.values_list('pk', flat=True).first() != current_id:
            raise StaleAnalysis
        analysis = models.ResumeAnalysis.objects.create(
            document=locked, revision=latest.revision + 1 if latest else 1,
            source_checksum=checksums[0], text_checksum=checksums[1], extractor_version=schema.EXTRACTOR_VERSION,
            sections=[asdict(section) for section in result.sections], notices=list(result.notices),
        )
        models.ResumeSuggestion.objects.bulk_create([
            models.ResumeSuggestion(
                analysis=analysis, position=position, category=row.category, value=row.value,
                normalized_value=row.normalized, method=row.method, support=row.support, fields=row.fields,
                evidence=[asdict(span) for span in row.evidence], canonical_skill_id=row.canonical.get('id'),
                canonical_snapshot=row.canonical, alternatives=row.alternatives,
            )
            for position, row in enumerate(result.suggestions)
        ])
    return analysis


@transaction.atomic
@sensitive_variables()
def review(owner, document_id, analysis_id, suggestion_id, *, decision, expected_version, correction=None):
    document = models.ResumeDocument.objects.select_for_update().get(pk=document_id, owner=owner)
    suggestion = models.ResumeSuggestion.objects.select_for_update().select_related('analysis').get(
        pk=suggestion_id, analysis_id=analysis_id, analysis__document=document,
    )
    if not source_matches(suggestion.analysis, document) or suggestion.review_version != expected_version:
        raise StaleAnalysis
    states = models.ResumeSuggestion.ReviewState
    if decision not in (states.CONFIRMED, states.REJECTED, states.CORRECTED):
        raise InvalidReview
    if (decision == states.CONFIRMED and not suggestion.can_confirm) or (decision == states.CORRECTED and not correction):
        raise InvalidReview
    values = correction if decision == states.CORRECTED else {}
    updated = models.ResumeSuggestion.objects.filter(pk=suggestion.pk, review_version=expected_version).update(
        review_state=decision, review_version=expected_version + 1, reviewed_at=timezone.now(),
        correction=values, corrected_skill_id=values.get('canonical', {}).get('id'),
    )
    if not updated:
        raise StaleAnalysis
