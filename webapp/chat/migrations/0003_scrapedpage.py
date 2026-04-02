from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_chatsession_alter_chatmessage_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScrapedPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("url", models.URLField(unique=True)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("content", models.TextField()),
                ("fetched_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-fetched_at"],
            },
        ),
    ]
