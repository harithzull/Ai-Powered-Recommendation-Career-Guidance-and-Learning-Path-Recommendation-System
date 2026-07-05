"""
LLM-powered roadmap generator (Groq) with rule-based fallback.
"""
import json
import logging
from dataclasses import dataclass

from django.conf import settings

from assessment.models import UserResponse
from recommender.matching import semantic_skill_match
from recommender.models import Career, CareerSkill

logger = logging.getLogger(__name__)

MAX_SKILL_STEPS = 8

PHASE_COLORS = {
    "Foundation":     ("var(--clay)",      "#fff4ee"),
    "Skill Building": ("var(--moss)",      "#f0f7f3"),
    "Practice":       ("#7b5ea7",          "#f5f0ff"),
    "Portfolio":      ("var(--moss-deep)", "#e8f4ed"),
    "Career Prep":    ("#b8860b",          "#fffbe6"),
}
DIFFICULTY_COLORS = {
    "Beginner":     ("var(--moss)",  "#f0f7f3"),
    "Intermediate": ("#7b5ea7",      "#f5f0ff"),
    "Advanced":     ("var(--clay)",  "#fff4ee"),
}


@dataclass
class RoadmapStep:
    index: int
    label: str
    phase: str = "Skill Building"
    title: str = ""
    description: str = ""
    estimated_time: str = ""
    difficulty: str = "Intermediate"
    deliverable: str = ""
    why_it_matters: str = ""
    search_keywords: str = ""
    is_skill_step: bool = True

    @property
    def phase_color(self) -> str:
        return PHASE_COLORS.get(self.phase, ("var(--moss)", "#f0f7f3"))[0]

    @property
    def phase_bg(self) -> str:
        return PHASE_COLORS.get(self.phase, ("var(--moss)", "#f0f7f3"))[1]

    @property
    def difficulty_color(self) -> str:
        return DIFFICULTY_COLORS.get(self.difficulty, ("var(--muted)", "#f5f5f5"))[0]

    @property
    def difficulty_bg(self) -> str:
        return DIFFICULTY_COLORS.get(self.difficulty, ("var(--muted)", "#f5f5f5"))[1]


def _user_skill_texts(response: UserResponse) -> list[str]:
    texts: list[str] = []
    for sr in response.skill_ratings.all():
        texts.extend([sr.skill_name] * sr.rating)
    for raw in response.free_text_skills.split(","):
        token = raw.strip()
        if token:
            texts.append(token)
    return texts


def _build_prompt(user, career: Career, missing_names: list[str]) -> str:
    try:
        response = UserResponse.objects.prefetch_related("skill_ratings").get(user=user)
    except UserResponse.DoesNotExist:
        response = None

    profile = getattr(user, "profile", None)
    field_of_study   = getattr(profile, "field_of_study",   "Not set") if profile else "Not set"
    experience_level = getattr(profile, "experience_level", "Not set") if profile else "Not set"

    if response:
        rated = sorted(response.skill_ratings.all(), key=lambda s: -s.rating)
        user_skills_str = ", ".join(
            f"{s.skill_name} ({s.rating}/5)" for s in rated[:12]
        ) or "None rated"
    else:
        user_skills_str = "None rated"

    career_skills = (
        CareerSkill.objects
        .filter(career=career)
        .select_related("skill")
        .order_by("-importance", "skill__name")[:20]
    )
    career_skills_str = "\n".join(
        f"- {cs.skill.name} (importance: {cs.importance}, level: {cs.required_level}, core: {'yes' if cs.is_core else 'no'})"
        for cs in career_skills
    ) or "Not specified"

    missing_str = (
        ", ".join(missing_names)
        if missing_names
        else "None — user already covers core skills well"
    )

    if experience_level in ("No experience", "Internship"):
        difficulty_hint = "Prefer Beginner and Intermediate difficulty steps."
    elif experience_level == "3+ years":
        difficulty_hint = "Prefer Intermediate and Advanced difficulty steps."
    else:
        difficulty_hint = "Mix Beginner and Intermediate steps appropriately."

    return f"""You are a career roadmap generator for a career guidance web app.

Generate a personalized learning roadmap for the user based on:
- target career
- user's current profile
- user's rated skills
- missing core skills
- career skill requirements

The roadmap must NOT be generic. It should adapt to the user's existing skills, missing skills, experience level, and the career's required skill levels.

Target career: {career.title}

Career summary: {career.summary or career.description or "Not provided"}

Industry: {career.industry}

User profile:
- Field of study: {field_of_study}
- Experience level: {experience_level}

User rated skills: {user_skills_str}

Missing core skills for this career: {missing_str}

Career required skills:
{career_skills_str}

Generate a roadmap with 5 to 8 steps.

Each step must include:
- phase (must be exactly one of: Foundation, Skill Building, Practice, Portfolio, Career Prep)
- title
- description (max 60 words)
- estimated_time
- difficulty (must be exactly one of: Beginner, Intermediate, Advanced)
- deliverable
- why_it_matters (max 40 words)
- search_keywords: 2-4 words for a free-resource search (e.g. "Python data analysis", "SQL beginner tutorial"). Leave empty string "" for Portfolio and Career Prep steps.

Rules:
1. If the user already has strong skill coverage, focus more on portfolio projects and job preparation.
2. If the user has many missing skills, start with fundamentals before projects.
3. Do not say "learn X" only. Make each step practical and action-based.
4. Use the missing skills to decide the roadmap sequence.
5. The final steps must include a Portfolio step and a Career Prep step.
6. Keep the language clear, student-friendly, and realistic.
7. Do not recommend paid resources unless specifically asked.
8. {difficulty_hint}
9. If missing_skills is empty, focus the roadmap on portfolio depth, specialisation, and career preparation.
10. Return only valid JSON — no markdown fences, no extra text before or after.

JSON format:
{{
  "roadmap_title": "...",
  "overview": "...",
  "steps": [
    {{
      "phase": "...",
      "title": "...",
      "description": "...",
      "estimated_time": "...",
      "difficulty": "Beginner | Intermediate | Advanced",
      "deliverable": "...",
      "why_it_matters": "...",
      "search_keywords": "..."
    }}
  ]
}}"""


def _call_groq(prompt: str) -> dict | None:
    api_key = getattr(settings, "GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1800,
            temperature=0.5,
        )
        raw = completion.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning("Groq roadmap generation failed: %s", e)
        return None


def _steps_from_llm(data: dict) -> list[RoadmapStep]:
    steps = []
    valid_phases = set(PHASE_COLORS)
    valid_diff   = set(DIFFICULTY_COLORS)
    for i, s in enumerate(data.get("steps", [])):
        phase = s.get("phase", "Skill Building")
        if phase not in valid_phases:
            phase = "Skill Building"
        diff = s.get("difficulty", "Intermediate")
        if diff not in valid_diff:
            diff = "Intermediate"
        title = s.get("title", f"Step {i + 1}")
        steps.append(RoadmapStep(
            index           = i,
            label           = title,
            phase           = phase,
            title           = title,
            description     = s.get("description", ""),
            estimated_time  = s.get("estimated_time", ""),
            difficulty      = diff,
            deliverable     = s.get("deliverable", ""),
            why_it_matters  = s.get("why_it_matters", ""),
            search_keywords = s.get("search_keywords", ""),
            is_skill_step   = phase not in ("Portfolio", "Career Prep"),
        ))
    return steps


def _fallback_steps(career: Career, missing_names: list[str]) -> list[RoadmapStep]:
    steps: list[RoadmapStep] = []
    idx = 0

    steps.append(RoadmapStep(
        index=idx, label=f"Research the {career.title} role",
        phase="Foundation", title=f"Research the {career.title} role",
        description=f"Read job descriptions, identify industry expectations, and map out what the {career.title} role involves day-to-day.",
        estimated_time="1 week", difficulty="Beginner",
        deliverable="A written summary of the role's key responsibilities and requirements.",
        why_it_matters="Understanding the role deeply helps you prioritise what to learn first.",
        search_keywords=f"{career.title} career overview",
        is_skill_step=False,
    ))
    idx += 1

    for skill_name in missing_names[:MAX_SKILL_STEPS]:
        steps.append(RoadmapStep(
            index=idx, label=f"Build {skill_name}",
            phase="Skill Building", title=f"Build {skill_name}",
            description=f"Study and practise {skill_name} through free online resources, tutorials, and hands-on exercises.",
            estimated_time="1–2 weeks", difficulty="Intermediate",
            deliverable=f"A small project or exercise demonstrating {skill_name}.",
            why_it_matters=f"{skill_name} is a core requirement for {career.title} roles.",
            search_keywords=f"{skill_name} tutorial",
            is_skill_step=True,
        ))
        idx += 1

    steps.append(RoadmapStep(
        index=idx, label="Build a portfolio project",
        phase="Portfolio", title="Build a portfolio project",
        description=f"Create a project that showcases your {career.title} skills end-to-end. Publish it on GitHub.",
        estimated_time="2–3 weeks", difficulty="Intermediate",
        deliverable="A GitHub repository with a working project and clear README.",
        why_it_matters="Employers want evidence of applied skills, not just certificates.",
        search_keywords="",
        is_skill_step=False,
    ))
    idx += 1

    steps.append(RoadmapStep(
        index=idx, label="Prepare your application",
        phase="Career Prep", title="Prepare your application",
        description=f"Update your CV and LinkedIn. Write a tailored cover letter. Practise interview questions for {career.title} roles.",
        estimated_time="1 week", difficulty="Beginner",
        deliverable="An updated CV, LinkedIn profile, and a list of 10 interview Q&A pairs.",
        why_it_matters="Strong preparation dramatically increases your chance of landing interviews.",
        search_keywords="",
        is_skill_step=False,
    ))

    return steps


# ── Persistence: generate once, reuse on reload ─────────────────────────────

_STEP_FIELDS = (
    "index", "label", "phase", "title", "description", "estimated_time",
    "difficulty", "deliverable", "why_it_matters", "search_keywords",
    "is_skill_step",
)


def _steps_to_json(steps: list[RoadmapStep]) -> str:
    return json.dumps([{f: getattr(s, f) for f in _STEP_FIELDS} for s in steps])


def _steps_from_json(data: str) -> list[RoadmapStep]:
    return [RoadmapStep(**{f: row[f] for f in _STEP_FIELDS if f in row})
            for row in json.loads(data)]


def get_or_create_roadmap(user, career: Career) -> tuple[list[RoadmapStep], str, str]:
    """
    Return the user's saved roadmap for this career, generating and saving it
    on first visit. Reloads never re-hit the LLM; the saved rows are deleted
    when the user redoes the assessment, which triggers regeneration here.
    """
    from roadmap.models import SavedRoadmap

    try:
        saved = SavedRoadmap.objects.get(user=user, career=career)
        return _steps_from_json(saved.steps_json), saved.title, saved.overview
    except SavedRoadmap.DoesNotExist:
        pass
    except (json.JSONDecodeError, TypeError, ValueError):
        # Corrupt row — drop it and regenerate below.
        SavedRoadmap.objects.filter(user=user, career=career).delete()

    steps, title, overview = generate_roadmap(user, career)
    if steps:
        SavedRoadmap.objects.update_or_create(
            user=user, career=career,
            defaults={
                "title":      title,
                "overview":   overview,
                "steps_json": _steps_to_json(steps),
            },
        )
    return steps, title, overview


def generate_roadmap(user, career: Career) -> tuple[list[RoadmapStep], str, str]:
    """
    Returns (steps, roadmap_title, overview).
    Falls back to rule-based steps if Groq is unavailable or fails.
    """
    try:
        response = UserResponse.objects.prefetch_related("skill_ratings").get(user=user)
    except UserResponse.DoesNotExist:
        return [], career.title, ""

    skill_texts = _user_skill_texts(response)
    _, missing_names = semantic_skill_match(skill_texts, career)

    prompt = _build_prompt(user, career, missing_names)
    data   = _call_groq(prompt)

    if data and data.get("steps"):
        steps = _steps_from_llm(data)
        return steps, data.get("roadmap_title", career.title), data.get("overview", "")

    steps = _fallback_steps(career, missing_names)
    return steps, f"Roadmap: {career.title}", ""
