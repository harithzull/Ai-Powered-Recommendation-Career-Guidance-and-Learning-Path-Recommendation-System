from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommender", "0003_alter_cachedrecommendation_id_alter_career_id_and_more")]
    operations = [migrations.AddField(
        model_name="cachedrecommendation", name="input_signature",
        field=models.CharField(blank=True, default="", max_length=64),
    )]
