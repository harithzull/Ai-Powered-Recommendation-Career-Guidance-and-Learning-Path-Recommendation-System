from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from careercoach.security import rate_limited, serialized_user_work
from .models import AssessmentSession, QuestionBank
from .scoring import AssessmentError
from .services import abandon_session, comparable, finalize_session, save_answer, start_session, validate_bank, SessionConflict

DIMENSION_INFO = {
    "R": ("Realistic", "Practical making, repairing, equipment and outdoor activities."),
    "I": ("Investigative", "Exploring questions through research, analysis and experiments."),
    "A": ("Artistic", "Expressing ideas through writing, design, art or performance."),
    "S": ("Social", "Helping, teaching, mentoring and supporting other people."),
    "E": ("Enterprising", "Persuading, negotiating and directing initiatives toward a goal."),
    "C": ("Conventional", "Organizing information, keeping records and following structured procedures."),
}
SCALE = [(1, "Strongly dislike"), (2, "Dislike"), (3, "Neutral"), (4, "Enjoy"), (5, "Strongly enjoy")]


def _start_context(user):
    bank = QuestionBank.objects.filter(status="active").first()
    error = None
    try:
        if bank is None:
            raise AssessmentError("The assessment is temporarily unavailable. Please try again later.")
        validate_bank(bank)
    except AssessmentError as exc:
        error = str(exc)
    return {"bank": bank, "bank_error": error, "dimensions": DIMENSION_INFO.items(),
            "open_session": AssessmentSession.objects.filter(user=user, status="in_progress").first()}


def begin(request):
    try:
        session = start_session(request.user, request.POST.get("mode", "quick"))
    except AssessmentError as exc:
        return render(request, "assessment/start.html", {**_start_context(request.user), "error": str(exc)},
                      status=409 if isinstance(exc, SessionConflict) else 400)
    return redirect("assessment:session", session_id=session.pk)


@login_required
@require_http_methods(["GET", "POST"])
@rate_limited("interest-start", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
def start(request):
    if request.method == "POST":
        return begin(request)
    return render(request, "assessment/start.html", _start_context(request.user))


def _number(value):
    # Decimal strings only; JSON booleans, floats, signs and huge numbers are not IDs.
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 12:
        raise AssessmentError("Invalid form data. Reload this page and try again.")
    return int(value)


@login_required
@require_http_methods(["GET", "POST"])
@rate_limited("interest-answer", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
def session_page(request, session_id):
    session = get_object_or_404(AssessmentSession.objects.select_related("bank"), pk=session_id, user=request.user)
    if session.status == "completed":
        if request.method == "POST":
            return render(request, "assessment/notice.html", {"error": "Completed assessments cannot be changed. Start a retake."}, status=409)
        return redirect("assessment:result", session_id=session.pk)
    if session.status != "in_progress":
        return render(request, "assessment/notice.html", {"error": "This assessment was abandoned. Start a new session."}, status=409)
    error, status = None, 200
    if request.method == "POST":
        try:
            # Prevent duplicate scalar form fields being silently accepted.
            if any(len(request.POST.getlist(key)) != 1 for key in ["position", "item_id", "revision", "action"]):
                raise AssessmentError("Invalid form data.")
            if len(request.POST.getlist("rating")) > 1:
                raise AssessmentError("Choose one response for this question.")
            position = _number(request.POST.get("position"))
            action = request.POST.get("action")
            value = request.POST.get("rating")
            session = save_answer(request.user, session.pk, position=position, item_id=_number(request.POST.get("item_id")),
                                  rating=None if value is None else _number(value), revision=_number(request.POST.get("revision")), action=action)
            if action == "save":
                messages.success(request, "Answer saved. You can resume this assessment later.")
                return redirect("assessment:start")
            if action == "next" and position == session.items.count() - 1:
                return redirect("assessment:review", session_id=session.pk)
            return redirect("assessment:session", session_id=session.pk)
        except AssessmentError as exc:
            error, status = str(exc), 409 if isinstance(exc, SessionConflict) else 400
            session.refresh_from_db()
    try:
        position = _number(request.GET["q"]) - 1 if "q" in request.GET else session.current_position
    except AssessmentError:
        return HttpResponseBadRequest("Invalid question position.")
    selected = get_object_or_404(session.items, position=position)
    answered = session.items.filter(rating__isnull=False).count()
    return render(request, "assessment/session.html", {"session": session, "selected": selected, "scale": SCALE,
                  "question_number": position + 1, "total": session.items.count(), "answered": answered,
                  "error": error}, status=status)


@login_required
@require_http_methods(["GET", "POST"])
@rate_limited("interest-finalize", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
def review(request, session_id):
    session = get_object_or_404(AssessmentSession.objects.select_related("bank"), pk=session_id, user=request.user)
    error, status = None, 200
    if request.method == "POST":
        try:
            if len(request.POST.getlist("revision")) != 1:
                raise AssessmentError("Invalid form revision.")
            session = finalize_session(request.user, session.pk, revision=_number(request.POST.get("revision")))
            return redirect("assessment:result", session_id=session.pk)
        except AssessmentError as exc:
            error, status = str(exc), 409 if isinstance(exc, SessionConflict) else 400
            session.refresh_from_db()
    elif session.status == "completed":
        return redirect("assessment:result", session_id=session.pk)
    if session.status == "abandoned":
        return render(request, "assessment/notice.html", {"error": "This assessment is closed."}, status=409)
    items = list(session.items.all())
    scale = dict(SCALE)
    rows = [{"item": item, "number": i + 1, "label": scale.get(item.rating, "Not answered")} for i, item in enumerate(items)]
    return render(request, "assessment/review.html", {"session": session, "rows": rows,
                  "missing": sum(item.rating is None for item in items), "error": error}, status=status)


@login_required
@require_POST
@rate_limited("interest-abandon", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
def abandon(request, session_id):
    try:
        abandon_session(request.user, session_id, revision=_number(request.POST.get("revision")))
    except AssessmentError as exc:
        return render(request, "assessment/notice.html", {"error": str(exc)}, status=409)
    return redirect("assessment:start")


def _result_rows(session):
    return [{"letter": letter, "name": name, "description": description,
             "score": session.result.get("scores", {}).get(letter), "count": session.result.get("counts", {}).get(letter, 0)}
            for letter, (name, description) in DIMENSION_INFO.items()]


@login_required
@require_GET
def result(request, session_id):
    session = get_object_or_404(AssessmentSession.objects.select_related("bank"), pk=session_id, user=request.user, status="completed")
    rows = _result_rows(session)
    top = session.result.get("holland_code", "")
    return render(request, "assessment/result.html", {"session": session, "rows": rows,
                  "top_rows": [next(row for row in rows if row["letter"] == letter) for letter in top],
                  "legacy": session.mode == "legacy"})


@login_required
@require_GET
def history(request):
    sessions = AssessmentSession.objects.filter(user=request.user).select_related("bank")
    page = Paginator(sessions, 20).get_page(request.GET.get("page"))
    comparison, warning = None, None
    if request.GET.get("first") and request.GET.get("second"):
        try:
            first_id, second_id = UUID(request.GET["first"]), UUID(request.GET["second"])
        except ValueError:
            return HttpResponseBadRequest("Invalid assessment identifiers.")
        first = get_object_or_404(sessions, pk=first_id, status="completed")
        second = get_object_or_404(sessions, pk=second_id, status="completed")
        if comparable(first, second):
            comparison = {"first": first, "second": second, "rows": [
                {"name": DIMENSION_INFO[t][0], "first": first.result["scores"][t], "second": second.result["scores"][t]}
                for t in DIMENSION_INFO]}
        else:
            warning = "These sessions use different modes, banks, item sets, or scoring methods. Their scores should not be presented as a direct trend; legacy scores also used agreement wording and a different scale."
    return render(request, "assessment/history.html", {"page": page, "comparison": comparison, "comparison_warning": warning})
