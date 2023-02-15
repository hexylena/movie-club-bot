# Generated by Django 4.0.4 on 2023-02-15 18:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0018_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='antiinterest',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='buff',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='criticrating',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='event',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='interest',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='moviesuggestion',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='poll',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pollarbitrary',
            name='tennant_id',
            field=models.CharField(default="-627602564", max_length=64),
            preserve_default=False,
        ),
    ]