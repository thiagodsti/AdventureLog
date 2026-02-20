"""
Data migration: mark past flights as 'completed' where status is still 'upcoming'.
Flights whose arrival_datetime has already passed should not show as upcoming.
"""
from django.db import migrations
from django.utils import timezone


def fix_flight_statuses(apps, schema_editor):
    Flight = apps.get_model('flights', 'Flight')
    now = timezone.now()
    updated = Flight.objects.filter(
        status='upcoming',
        arrival_datetime__lt=now,
    ).update(status='completed')
    if updated:
        print(f"  Updated {updated} past flight(s) to 'completed'.")


class Migration(migrations.Migration):

    dependencies = [
        ('flights', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(fix_flight_statuses, migrations.RunPython.noop),
    ]
