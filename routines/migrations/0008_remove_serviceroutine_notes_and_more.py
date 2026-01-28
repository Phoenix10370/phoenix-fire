from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "routines",
            "0007_remove_serviceroutineitem_uniq_service_routine_item_position",
        ),
    ]

    operations = [
        # ✅ Preserve existing data: rename notes -> quotation_notes
        migrations.RenameField(
            model_name="serviceroutine",
            old_name="notes",
            new_name="quotation_notes",
        ),

        # --- Manpower / hours fields ---
        migrations.AddField(
            model_name="serviceroutine",
            name="annual_men_req",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="annual_man_hours",
            field=models.DecimalField(
                max_digits=8, decimal_places=2, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="half_yearly_men_req",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="half_yearly_man_hours",
            field=models.DecimalField(
                max_digits=8, decimal_places=2, blank=True, null=True
            ),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="monthly_men_req",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="monthly_man_hours",
            field=models.DecimalField(
                max_digits=8, decimal_places=2, blank=True, null=True
            ),
        ),

        # --- Monthly notes (shared across routines) ---
        migrations.AddField(
            model_name="serviceroutine",
            name="monthly_run_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="monthly_week_notes",
            field=models.TextField(blank=True, default=""),
        ),

        # --- Additional notes ---
        migrations.AddField(
            model_name="serviceroutine",
            name="site_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="serviceroutine",
            name="technician_notes",
            field=models.TextField(blank=True, default=""),
        ),
    ]
