from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.CreateModel(
        name="SecurityCounter",
        fields=[
            ("key", models.CharField(max_length=128, primary_key=True, serialize=False)),
            ("count", models.PositiveIntegerField(default=0)),
            ("expires_at", models.DateTimeField(db_index=True)),
        ],
    )]
