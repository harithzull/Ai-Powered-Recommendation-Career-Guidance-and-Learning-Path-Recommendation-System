"""Private HTML endpoints for local resume analysis and user review."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import Http404, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_POST

from careercoach.security import rate_limited, serialized_user_work

from .intelligence.forms import AnalyzeForm, CorrectionForm, FIELDS, ReviewForm
from .intelligence.pipeline import AnalysisUnavailable, UnsupportedText
from .intelligence.schema import EXTRACTOR_VERSION
from .models import ResumeAnalysis, ResumeDocument, ResumeSuggestion
from .services.intelligence import InvalidReview, RevisionLimit, StaleAnalysis, analyze, review, source_matches
from .constants import MAX_TEXT_CHARS


def _error(request, message, status):
    return render(request, 'resume/error.html', {'message': message}, status=status)


def _private(view):
    @sensitive_post_parameters()
    @wraps(view)
    @sensitive_variables()
    def wrapped(request, *args, **kwargs):
        try:
            response = view(request, *args, **kwargs)
        except (Http404, ResumeDocument.DoesNotExist, ResumeAnalysis.DoesNotExist, ResumeSuggestion.DoesNotExist):
            response = HttpResponseNotFound('Resume analysis unavailable.')
        except (AnalysisUnavailable, DatabaseError):
            response = _error(request, 'Resume analysis is temporarily unavailable. Please try again later.', 503)
        return response
    return wrapped


@sensitive_variables()
def _document(request, pk):
    return get_object_or_404(ResumeDocument, pk=pk, owner=request.user)


def _analysis_url(analysis):
    return redirect('resume:analysis_detail', pk=analysis.document_id, analysis_id=analysis.pk)


def _render_suggestions(analysis):
    grouped = {}
    if analysis:
        for item in analysis.suggestions.all():
            labels = FIELDS.get(item.category, {})
            grouped.setdefault(item.get_category_display(), []).append({
                'item': item,
                'fields': [(labels.get(key, key), value) for key, value in item.fields.items()],
                'corrections': [(labels.get(key, key), value)
                                for key, value in item.correction.get('fields', {}).items()],
            })
    return grouped


@_private
@login_required
@require_GET
@sensitive_variables()
def overview(request, pk, analysis_id=None):
    document = _document(request, pk)
    history = list(document.analyses.only('id', 'revision', 'extractor_version', 'created_at'))
    latest = history[0] if history else None
    analysis = (get_object_or_404(document.analyses, pk=analysis_id) if analysis_id
                else document.analyses.first())
    return render(request, 'resume/analysis.html', {
        'document': document, 'analysis': analysis, 'history': history, 'latest': latest,
        'stale': bool(analysis and not source_matches(analysis, document)),
        'ready': (document.status == ResumeDocument.Status.COMPLETED
                  and 0 < len(document.extracted_text) <= MAX_TEXT_CHARS and bool(document.extracted_text.strip())),
        'new_extractor': bool(latest and latest.extractor_version != EXTRACTOR_VERSION),
        'groups': _render_suggestions(analysis),
    })


@transaction.non_atomic_requests
@_private
@login_required
@require_POST
@rate_limited('resume-analysis', 'RESUME_ANALYSES_PER_DAY', 86400, by_user=True)
@serialized_user_work
@sensitive_variables()
def run(request, pk):
    form = AnalyzeForm(request.POST)
    if not form.is_valid():
        return _error(request, 'Reload the analysis and submit the form again.', 400)
    try:
        analysis = analyze(request.user, pk, rerun=form.cleaned_data['rerun'],
                           expected_latest=form.cleaned_data['latest'])
    except UnsupportedText:
        return _error(request, 'Analysis requires a resume with successfully extracted text within the size limit.', 422)
    except StaleAnalysis:
        return _error(request, 'This analysis changed. Reload the resume and try again.', 409)
    except RevisionLimit:
        return _error(request, 'This resume reached the analysis history limit.', 409)
    return _analysis_url(analysis)


@sensitive_variables()
def _suggestion(request, pk, analysis_id, suggestion_id):
    return get_object_or_404(
        ResumeSuggestion.objects.select_related('analysis__document'),
        pk=suggestion_id, analysis_id=analysis_id, analysis__document_id=pk,
        analysis__document__owner=request.user,
    )


@sensitive_variables()
def _correction_page(request, suggestion, form, status=200):
    return render(request, 'resume/analysis_correct.html', {'suggestion': suggestion, 'form': form}, status=status)


@_private
@login_required
@require_GET
@sensitive_variables()
def correct(request, pk, analysis_id, suggestion_id):
    suggestion = _suggestion(request, pk, analysis_id, suggestion_id)
    if not source_matches(suggestion.analysis, suggestion.analysis.document):
        return _error(request, 'This historical analysis is read-only because the source changed.', 409)
    return _correction_page(request, suggestion, CorrectionForm(suggestion))


@transaction.non_atomic_requests
@_private
@login_required
@require_POST
@rate_limited('resume-review', 'RESUME_REVIEWS_PER_MINUTE', 60, by_user=True)
@serialized_user_work
@sensitive_variables()
def save_review(request, pk, analysis_id, suggestion_id):
    suggestion = _suggestion(request, pk, analysis_id, suggestion_id)
    correcting = request.POST.get('decision') == ResumeSuggestion.ReviewState.CORRECTED
    form = CorrectionForm(suggestion, request.POST) if correcting else ReviewForm(request.POST)
    if not form.is_valid():
        if correcting:
            return _correction_page(request, suggestion, form, 400)
        return _error(request, 'Review action is invalid. Reload the analysis and try again.', 400)
    values = form.cleaned_data
    try:
        review(request.user, pk, analysis_id, suggestion_id, decision=values['decision'],
               expected_version=values['review_version'], correction=values.get('correction'))
    except StaleAnalysis:
        return _error(request, 'The source or review changed. Reload the analysis and try again.', 409)
    except InvalidReview:
        return _error(request, 'Correct this suggestion before confirming it.', 400)
    return _analysis_url(suggestion.analysis)
