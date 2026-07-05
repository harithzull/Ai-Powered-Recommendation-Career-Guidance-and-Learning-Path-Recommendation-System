from django.db import migrations

QUESTIONS = [
    # Realistic (R)
    (1, "R", "I enjoy working with tools, machines, or building things that physically work."),
    (2, "R", "I'd rather fix or assemble something concrete than discuss abstract ideas."),
    # Investigative (I)
    (3, "I", "I like solving complex problems by analyzing data or researching how things work."),
    (4, "I", "I enjoy digging into the 'why' behind a problem before acting."),
    # Artistic (A)
    (5, "A", "I enjoy creating original designs, visuals, content, or other creative work."),
    (6, "A", "I prefer open-ended tasks where I can express my own ideas over following fixed rules."),
    # Social (S)
    (7, "S", "I find it rewarding to help, teach, or support other people."),
    (8, "S", "I'd rather work closely with people than work alone on technical tasks."),
    # Enterprising (E)
    (9, "E", "I enjoy leading projects, pitching ideas, or persuading others."),
    (10, "E", "I'm drawn to roles where I can influence decisions and drive results."),
    # Conventional (C)
    (11, "C", "I like organizing information, following clear procedures, and keeping things accurate."),
    (12, "C", "I prefer well-defined tasks with clear rules over ambiguous, open-ended ones."),
]


def seed_questions(apps, schema_editor):
    RIASECQuestion = apps.get_model("assessment", "RIASECQuestion")
    for order, riasec_type, text in QUESTIONS:
        RIASECQuestion.objects.get_or_create(
            order=order,
            defaults={"riasec_type": riasec_type, "text": text},
        )


def unseed_questions(apps, schema_editor):
    RIASECQuestion = apps.get_model("assessment", "RIASECQuestion")
    RIASECQuestion.objects.filter(order__in=[q[0] for q in QUESTIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_questions, unseed_questions),
    ]
