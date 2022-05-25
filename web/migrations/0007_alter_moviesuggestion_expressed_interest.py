# Generated by Django 4.0.4 on 2022-05-25 19:59

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('web', '0006_alter_moviesuggestion_expressed_interest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='moviesuggestion',
            name='expressed_interest',
            field=models.ManyToManyField(blank=True, to=settings.AUTH_USER_MODEL),
        ),
    ]
