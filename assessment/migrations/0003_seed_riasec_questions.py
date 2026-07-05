from django.db import migrations

# Expanded RIASEC item bank — 7 questions per type (42 total).
# Orders 1–12 are the original seed items (kept intact); 13–42 are new.
# Each item targets a distinct facet of its type so an adaptive selector
# has genuine variety to choose from rather than near-duplicate wording.
QUESTIONS = [
    # ----- Realistic (R) -----
    (1,  "R", "I enjoy working with tools, machines, or building things that physically work."),
    (2,  "R", "I'd rather fix or assemble something concrete than discuss abstract ideas."),
    (13, "R", "I like jobs that let me work with my hands or operate equipment."),
    (14, "R", "I enjoy being outdoors or moving around rather than sitting at a desk all day."),
    (15, "R", "I feel satisfied when I can see a real, finished result from my work."),
    (16, "R", "I'm comfortable troubleshooting how a device or system physically works."),
    (17, "R", "I'd choose practical, hands-on tasks over theoretical discussion."),

    # ----- Investigative (I) -----
    (3,  "I", "I like solving complex problems by analyzing data or researching how things work."),
    (4,  "I", "I enjoy digging into the 'why' behind a problem before acting."),
    (18, "I", "I like running experiments or testing ideas to see what actually holds up."),
    (19, "I", "I enjoy learning new theories or concepts even without an immediate use for them."),
    (20, "I", "I'd rather investigate a question deeply than make a quick decision."),
    (21, "I", "I'm drawn to fields like science, maths, or technology where logic leads."),
    (22, "I", "I enjoy spotting patterns in information that others might miss."),

    # ----- Artistic (A) -----
    (5,  "A", "I enjoy creating original designs, visuals, content, or other creative work."),
    (6,  "A", "I prefer open-ended tasks where I can express my own ideas over following fixed rules."),
    (23, "A", "I like imagining new ideas and bringing them to life in my own style."),
    (24, "A", "I value originality and self-expression more than following a set process."),
    (25, "A", "I enjoy writing, music, art, or other creative outlets in my free time."),
    (26, "A", "I get bored by repetitive work that leaves no room for creativity."),
    (27, "A", "I notice and care about how things look, sound, or feel aesthetically."),

    # ----- Social (S) -----
    (7,  "S", "I find it rewarding to help, teach, or support other people."),
    (8,  "S", "I'd rather work closely with people than work alone on technical tasks."),
    (28, "S", "I enjoy explaining things to others until they understand."),
    (29, "S", "People often come to me for advice or support."),
    (30, "S", "I feel motivated when my work clearly improves someone's life."),
    (31, "S", "I'm good at sensing how others feel and responding to it."),
    (32, "S", "I'd enjoy a job centred on coaching, counselling, or caring for people."),

    # ----- Enterprising (E) -----
    (9,  "E", "I enjoy leading projects, pitching ideas, or persuading others."),
    (10, "E", "I'm drawn to roles where I can influence decisions and drive results."),
    (33, "E", "I'm comfortable taking charge and making decisions for a group."),
    (34, "E", "I enjoy competing and aiming to win or come out ahead."),
    (35, "E", "I like the idea of starting a business or running my own venture."),
    (36, "E", "I'm energised by setting ambitious goals and pushing to reach them."),
    (37, "E", "I enjoy negotiating, selling, or convincing people to come on board."),

    # ----- Conventional (C) -----
    (11, "C", "I like organizing information, following clear procedures, and keeping things accurate."),
    (12, "C", "I prefer well-defined tasks with clear rules over ambiguous, open-ended ones."),
    (38, "C", "I'm good at keeping records, files, or data neat and well-ordered."),
    (39, "C", "I feel comfortable when I know exactly what's expected of me."),
    (40, "C", "I pay close attention to detail and notice small errors."),
    (41, "C", "I enjoy working with numbers, schedules, or structured systems."),
    (42, "C", "I prefer a stable, predictable routine over constant change."),
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
        ("assessment", "0002_seed_riasec_questions"),
    ]

    operations = [
        migrations.RunPython(seed_questions, unseed_questions),
    ]
