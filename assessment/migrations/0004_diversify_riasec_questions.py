from django.db import migrations

# Rewrite pool items that were near-duplicates of another item of the same
# type, so adaptive deepening (several same-type questions in a row) doesn't
# feel repetitive. Each rewrite targets a distinct Holland-model facet.
REWRITES = {
    # Realistic — was ~duplicate of order 1 (tools/hands) and 2/17 (concrete vs abstract)
    13: "I'd enjoy working with plants, animals, or the natural environment.",
    17: "I like tasks that involve physical skill or coordination, like sports, driving, or crafting.",
    # Investigative — was ~duplicate of order 4 (dig into the why)
    20: "I enjoy puzzles, strategy games, or brain teasers that make me think hard.",
    # Artistic — was ~duplicate of order 6 (own ideas over fixed rules)
    24: "I'd enjoy performing, presenting creative work, or sharing things I create with an audience.",
    # Social — was ~duplicate of order 7 (helping/supporting people)
    30: "I work best in a team where people cooperate and support each other.",
    # Enterprising — 33 was ~duplicate of 10 (influence/decisions), 37 of 9 (pitch/persuade)
    33: "In group work, I naturally end up organising people and delegating tasks.",
    37: "I'm comfortable taking risks when there's a chance of a bigger reward.",
    # Conventional — 38 was ~duplicate of 11 (organizing/accuracy), 39 of 12 (well-defined tasks)
    38: "I like planning things out in advance rather than improvising as I go.",
    39: "I find it satisfying to complete forms, reports, or paperwork accurately.",
}

OLD_TEXTS = {
    13: "I like jobs that let me work with my hands or operate equipment.",
    17: "I'd choose practical, hands-on tasks over theoretical discussion.",
    20: "I'd rather investigate a question deeply than make a quick decision.",
    24: "I value originality and self-expression more than following a set process.",
    30: "I feel motivated when my work clearly improves someone's life.",
    33: "I'm comfortable taking charge and making decisions for a group.",
    37: "I enjoy negotiating, selling, or convincing people to come on board.",
    38: "I'm good at keeping records, files, or data neat and well-ordered.",
    39: "I feel comfortable when I know exactly what's expected of me.",
}


def apply_rewrites(apps, schema_editor):
    RIASECQuestion = apps.get_model("assessment", "RIASECQuestion")
    for order, text in REWRITES.items():
        RIASECQuestion.objects.filter(order=order).update(text=text)


def revert_rewrites(apps, schema_editor):
    RIASECQuestion = apps.get_model("assessment", "RIASECQuestion")
    for order, text in OLD_TEXTS.items():
        RIASECQuestion.objects.filter(order=order).update(text=text)


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0003_seed_riasec_questions"),
    ]

    operations = [
        migrations.RunPython(apply_rewrites, revert_rewrites),
    ]
