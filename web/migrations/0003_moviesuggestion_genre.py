# Generated by Django 4.0.4 on 2022-05-25 18:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0002_moviesuggestion_suggested_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='moviesuggestion',
            name='genre',
            field=models.TextField(blank=True, null=True),
        ),
    ]
