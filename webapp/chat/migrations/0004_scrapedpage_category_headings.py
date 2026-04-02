from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0003_scrapedpage"),
    ]

    operations = [
        migrations.AddField(
            model_name="scrapedpage",
            name="category",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="scrapedpage",
            name="headings",
            field=models.TextField(blank=True),
        ),
    ]
