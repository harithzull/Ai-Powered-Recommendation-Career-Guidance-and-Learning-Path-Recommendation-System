from django.db import migrations, models


def mark_completed(apps, schema_editor):
    Response = apps.get_model("assessment", "UserResponse")
    Response.objects.filter(riasec_answers__isnull=False, skill_ratings__isnull=False).update(
        completed_at=models.F("submitted_at"),
    )


class Migration(migrations.Migration):
    dependencies = [("assessment", "0004_diversify_riasec_questions")]
    operations = [
        migrations.AddField(model_name="userresponse", name="completed_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(mark_completed, migrations.RunPython.noop),
    ]
