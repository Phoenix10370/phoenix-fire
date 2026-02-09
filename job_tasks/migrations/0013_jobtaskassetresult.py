from django.db import migrations, models
import django.db.models.deletion


def backfill_results(apps, schema_editor):
    JobTaskAssetLink = apps.get_model("job_tasks", "JobTaskAssetLink")
    JobTaskAssetResult = apps.get_model("job_tasks", "JobTaskAssetResult")

    for link in JobTaskAssetLink.objects.exclude(result=""):
        job_id = link.last_updated_job_id or link.job_task_id
        if not job_id:
            continue
        JobTaskAssetResult.objects.update_or_create(
            job_task_id=job_id,
            property_asset_id=link.property_asset_id,
            defaults={"result": link.result or ""},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("job_tasks", "0012_jobtaskassetlink_last_updated_job"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobTaskAssetResult",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("result", models.CharField(blank=True, choices=[("pass", "Pass"), ("fail", "Fail"), ("access", "Access"), ("no_access", "No Access")], default="", max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job_task",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="asset_results", to="job_tasks.jobtask"),
                ),
                (
                    "property_asset",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="job_task_results", to="properties.propertyasset"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="jobtaskassetresult",
            constraint=models.UniqueConstraint(fields=("job_task", "property_asset"), name="uq_jobtask_asset_result"),
        ),
        migrations.RunPython(backfill_results, migrations.RunPython.noop),
    ]
