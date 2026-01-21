from django.db import migrations, transaction


def backfill_site_ids(apps, schema_editor):
    Property = apps.get_model("properties", "Property")

    PREFIX = "PTY"
    PAD = 5

    with transaction.atomic():
        max_num = 0

        for p in Property.objects.exclude(site_id="").filter(site_id__startswith=PREFIX):
            try:
                num = int(p.site_id[len(PREFIX):])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass

        for p in Property.objects.filter(site_id="").order_by("id"):
            max_num += 1
            p.site_id = f"{PREFIX}{max_num:0{PAD}d}"
            p.save(update_fields=["site_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0007_auto_20260112_0838"),
    ]

    operations = [
        migrations.RunPython(backfill_site_ids, migrations.RunPython.noop),
    ]
