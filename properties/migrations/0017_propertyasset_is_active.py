from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0016_propertyasset_main_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyasset",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
