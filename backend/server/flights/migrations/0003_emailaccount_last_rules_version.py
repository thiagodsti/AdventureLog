from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flights', '0002_fix_flight_statuses'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailaccount',
            name='last_rules_version',
            field=models.CharField(
                blank=True, default='',
                help_text='Tracks which RULES_VERSION was last used for syncing',
                max_length=20,
            ),
        ),
    ]
