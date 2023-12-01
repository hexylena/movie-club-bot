# Generated by Django 4.2.1 on 2023-12-01 12:00

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0002_moviesuggestion_imdb_update"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tennant_id", models.CharField(max_length=64)),
                ("name", models.TextField()),
            ],
        ),
    ]
