from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("job_tasks", "0011_jobtaskassetimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobtaskassetlink",
            name="last_updated_job",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="asset_link_updates", to="job_tasks.jobtask"),
        ),
    ]
