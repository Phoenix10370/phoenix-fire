from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("job_tasks", "0010_jobtaskassetlink_image_urls_jobtaskassetlink_result_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobTaskAssetImage",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="job_tasks/assets/")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="job_tasks.jobtaskassetlink",
                    ),
                ),
            ],
        ),
    ]
