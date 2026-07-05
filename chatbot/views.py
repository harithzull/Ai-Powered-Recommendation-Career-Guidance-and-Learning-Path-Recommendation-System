import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from assessment.models import UserResponse
from recommender.recommendations import get_recommendations
from recommender.scoring import riasec_profile

_SESSION_KEY = "chatbot_history"
_MAX_HISTORY = 20   # 10 exchanges (user + assistant pairs)
_MAX_MSG_LEN = 1000


def _build_system_prompt(user) -> str:
    lines = [
        "You are CareerCoach AI, a friendly and concise career guidance assistant embedded in the CareerCoach app.",
        "Help the user understand their career recommendations, skill gaps, and learning roadmap.",
        "Reference their specific data when relevant. Keep answers short and practical.",
        "If asked something completely unrelated to careers or this app, gently redirect.",
        "",
        "== USER PROFILE ==",
    ]

    try:
        profile = user.profile
        lines.append(f"Field of study: {profile.field_of_study or 'Not set'}")
        lines.append(f"Experience level: {profile.experience_level or 'Not set'}")
    except AttributeError:
        lines.append("Profile: not completed yet")

    try:
        response = UserResponse.objects.prefetch_related(
            "riasec_answers__question", "skill_ratings"
        ).get(user=user)

        # RIASEC profile
        scores = riasec_profile(response)
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        riasec_str = ", ".join(f"{t}={v:.0%}" for t, v in sorted_scores)
        lines.append(f"RIASEC interest profile (highest first): {riasec_str}")

        # Top rated skills
        top_skills = sorted(response.skill_ratings.all(), key=lambda s: -s.rating)[:10]
        if top_skills:
            skill_str = ", ".join(f"{s.skill_name} ({s.rating}/5)" for s in top_skills)
            lines.append(f"User's top skills: {skill_str}")
        else:
            lines.append("Skills: none rated yet")

        # Top career recommendations
        recs = get_recommendations(user, top_n=3)
        if recs:
            lines.append("")
            lines.append("== TOP CAREER RECOMMENDATIONS ==")
            for i, rec in enumerate(recs, 1):
                lines.append(
                    f"{i}. {rec['career'].title} — {rec['final_score']}% overall match "
                    f"(Interest {rec['interest_pct']}%, Skill {rec['skill_pct']}%, Background {rec['background_pct']}%)"
                )
                if rec["missing_skills"]:
                    missing = ", ".join(rec["missing_skills"][:6])
                    lines.append(f"   Core skills to develop: {missing}")
                else:
                    lines.append("   Core skills: all covered")
        else:
            lines.append("Recommendations: not yet generated (assessment may be incomplete)")

    except UserResponse.DoesNotExist:
        lines.append("Assessment: not completed yet")

    return "\n".join(lines)


@login_required
def chat_page(request):
    history = request.session.get(_SESSION_KEY, [])
    return render(request, "chatbot/chat.html", {"history": history})


@login_required
@require_POST
def send_message(request):
    try:
        body = json.loads(request.body)
        user_message = str(body.get("message", "")).strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid request body."}, status=400)

    if not user_message:
        return JsonResponse({"error": "Message cannot be empty."}, status=400)

    if len(user_message) > _MAX_MSG_LEN:
        return JsonResponse({"error": f"Message too long (max {_MAX_MSG_LEN} characters)."}, status=400)

    api_key = getattr(settings, "GROQ_API_KEY", "").strip()
    if not api_key:
        return JsonResponse({
            "error": "Chatbot is not configured. Add your GROQ_API_KEY to settings.py."
        }, status=503)

    history = request.session.get(_SESSION_KEY, [])
    system_prompt = _build_system_prompt(request.user)

    messages = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": user_message}]
    )

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=600,
            temperature=0.7,
        )
        reply = completion.choices[0].message.content.strip()
    except Exception as e:
        return JsonResponse({"error": f"AI service error: {e}"}, status=502)

    history.append({"role": "user",      "content": user_message})
    history.append({"role": "assistant", "content": reply})
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    request.session[_SESSION_KEY] = history

    return JsonResponse({"reply": reply})


@login_required
def clear_chat(request):
    request.session.pop(_SESSION_KEY, None)
    return JsonResponse({"ok": True})
