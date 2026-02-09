from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("properties", "0015_property_coords_validated_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyasset",
            name="main_image",
            field=models.ImageField(blank=True, null=True, upload_to="properties/assets/"),
        ),
    ]
