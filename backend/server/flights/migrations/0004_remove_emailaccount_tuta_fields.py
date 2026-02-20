from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flights', '0003_emailaccount_last_rules_version'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='emailaccount',
            name='tuta_user',
        ),
        migrations.RemoveField(
            model_name='emailaccount',
            name='tuta_password',
        ),
        migrations.AlterField(
            model_name='emailaccount',
            name='provider',
            field=models.CharField(
                choices=[
                    ('gmail', 'Gmail (IMAP/OAuth)'),
                    ('outlook', 'Outlook (IMAP)'),
                    ('imap', 'Generic IMAP'),
                ],
                default='imap',
                max_length=20,
            ),
        ),
    ]
