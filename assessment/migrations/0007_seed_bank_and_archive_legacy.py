from collections import Counter
from django.db import migrations

BANK_VERSION = 'careercoach-riasec-2026.1'
ITEMS = [('R', 'Mechanical repair', 'Repair a simple mechanical object.'),
 ('R', 'Practical assembly', 'Assemble an object by following a diagram.'),
 ('R', 'Outdoor plant care', 'Grow and care for plants outdoors.'),
 ('R', 'Hands-on making', 'Use hand tools to shape a piece of material.'),
 ('R', 'Practical measurement', 'Take measurements for a small building project.'),
 ('R', 'Equipment setup', 'Set up equipment for a practical task.'),
 ('I', 'Causal analysis', 'Compare information to work out why an event happened.'),
 ('I', 'Experimental inquiry', 'Plan a small experiment to test an idea.'),
 ('I', 'Quantitative patterns', 'Look for patterns in a set of numbers.'),
 ('I', 'Scientific inquiry', 'Investigate how a natural process works.'),
 ('I', 'Researching explanations', 'Research different explanations for an unanswered question.'),
 ('I', 'Logical reasoning', 'Develop a step-by-step solution to a logic puzzle.'),
 ('A', 'Visual expression', 'Create an original illustration.'),
 ('A', 'Creative writing', 'Write a short fictional story.'),
 ('A', 'Musical expression', 'Perform a piece of music.'),
 ('A', 'Communication design', 'Develop a visual concept for a poster.'),
 ('A', 'Movement expression', 'Experiment with movements for a dance.'),
 ('A', 'Three-dimensional expression', 'Shape a sculpture from clay or another material.'),
 ('S', 'Teaching', 'Explain an unfamiliar idea to someone who wants to learn.'),
 ('S', 'Supportive listening', 'Listen to a person who needs support with a difficulty.'),
 ('S', 'Coaching', 'Help someone practise a new skill.'),
 ('S', 'Mentoring', 'Guide a new student as they settle into a course.'),
 ('S', 'Practical helping', 'Help someone find services they need.'),
 ('S', 'Inclusive learning support', 'Adapt a learning activity for someone who needs extra support.'),
 ('E', 'Persuasion', 'Present a proposal to persuade a group to support it.'),
 ('E', 'Entrepreneurship', 'Plan how to turn a small business idea into a service.'),
 ('E', 'Negotiation', 'Negotiate an agreement between people with different goals.'),
 ('E', 'Project coordination', "Coordinate people's tasks to deliver a group project."),
 ('E', 'Initiative direction', 'Make decisions about the direction of a student initiative.'),
 ('E', 'Promotion', 'Promote an event to attract participants.'),
 ('C', 'Information organization', 'Sort information into a clear filing system.'),
 ('C', 'Checking accuracy', 'Check a list of figures for recording errors.'),
 ('C', 'Record keeping', "Keep records of a group's spending."),
 ('C', 'Following procedures', 'Follow a written procedure to process a form.'),
 ('C', 'Structured scheduling', 'Build a timetable that meets a set of requirements.'),
 ('C', 'Consistent data entry', 'Update a spreadsheet using a consistent format.')]


def seed_and_archive(apps, schema_editor):
    alias = schema_editor.connection.alias
    Bank = apps.get_model("assessment", "QuestionBank")
    Item = apps.get_model("assessment", "InterestItem")
    Session = apps.get_model("assessment", "AssessmentSession")
    Response = apps.get_model("assessment", "UserResponse")
    Answer = apps.get_model("assessment", "RIASECAnswer")
    Skill = apps.get_model("assessment", "SkillRating")
    bank, _ = Bank.objects.using(alias).get_or_create(version=BANK_VERSION, defaults={
        "status": "active", "notes": "Original activity-interest items; implementation content review only. Not empirically validated. Six core facets per dimension; first three are Quick core.",
    })
    number = Counter()
    for dimension, facet, text in ITEMS:
        number[dimension] += 1
        Item.objects.using(alias).get_or_create(bank=bank, code=f"{dimension}{number[dimension]:02d}", defaults={
            "dimension": dimension, "facet": facet, "purpose": "Explore enjoyment of " + facet.lower() + "; does not assess ability.",
            "text": text, "quick_core": number[dimension] <= 3, "status": "active",
        })
    for response in Response.objects.using(alias).iterator():
        if Session.objects.using(alias).filter(legacy_response_id=response.pk).exists():
            continue
        answers = list(Answer.objects.using(alias).filter(response_id=response.pk).select_related("question"))
        totals = dict.fromkeys("RIASEC", 0)
        counts = dict.fromkeys("RIASEC", 0)
        snapshots = []
        for answer in answers:
            dimension = answer.question.riasec_type
            totals[dimension] += answer.rating
            counts[dimension] += 1
            snapshots.append({"question_id": answer.question_id, "dimension": dimension,
                              "text_at_archival": answer.question.text, "rating": answer.rating})
        profile = {t: round((totals[t] / counts[t]) / 5, 4) if counts[t] else 0.0 for t in "RIASEC"}
        result = {}
        if response.completed_at is not None:
            result = {"scoring_version": "legacy-mean-div5-v1", "mode": "legacy", "bank_version": None,
                      "raw_totals": totals, "counts": counts,
                      "raw_averages": {t: totals[t] / counts[t] if counts[t] else None for t in "RIASEC"},
                      "scores": {t: round(profile[t] * 100, 2) for t in "RIASEC"},
                      "compatibility_profile": profile, "holland_code": "", "ties": [], "near_ties": []}
        session = Session.objects.using(alias).create(
            user_id=response.user_id, mode="legacy", legacy_response_id=response.pk,
            status="completed" if response.completed_at is not None else "abandoned",
            completed_at=response.completed_at, scoring_version="legacy-mean-div5-v1", result=result,
            context_snapshot={"legacy_answers": snapshots, "free_text_skills": response.free_text_skills,
                              "skills": list(Skill.objects.using(alias).filter(response_id=response.pk).values("skill_name", "rating")),
                              "original_submitted_at": response.submitted_at.isoformat(), "original_started_at": None,
                              "limitation": "Original bank/version/order and text at response time were not recorded; text is a snapshot at archival."},
        )
        Session.objects.using(alias).filter(pk=session.pk).update(started_at=response.submitted_at)


class Migration(migrations.Migration):
    dependencies = [("assessment", "0006_versioned_interest_sessions")]
    operations = [migrations.RunPython(seed_and_archive, migrations.RunPython.noop)]
