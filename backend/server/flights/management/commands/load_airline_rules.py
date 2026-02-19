"""
Management command to load built-in airline parsing rules.
Run: python manage.py load_airline_rules
"""

from django.core.management.base import BaseCommand
from flights.models import AirlineRule
from flights.builtin_rules import BUILTIN_AIRLINE_RULES


class Command(BaseCommand):
    help = 'Load built-in airline parsing rules for LATAM, SAS, and Lufthansa'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete existing built-in rules before loading'
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted_count, _ = AirlineRule.objects.filter(is_builtin=True).delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted_count} existing built-in rules'))

        created = 0
        updated = 0
        for rule_data in BUILTIN_AIRLINE_RULES:
            obj, was_created = AirlineRule.objects.update_or_create(
                airline_code=rule_data['airline_code'],
                is_builtin=True,
                user=None,
                defaults=rule_data,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Airline rules loaded: {created} created, {updated} updated'
        ))
