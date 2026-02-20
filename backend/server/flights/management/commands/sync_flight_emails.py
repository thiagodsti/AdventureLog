"""
Management command to sync all active email accounts for flight emails.
Designed to be called periodically (e.g. every 10 minutes) by run_periodic_sync.py.
"""

import logging
from django.core.management.base import BaseCommand

from flights.models import EmailAccount
from flights.parsers import sync_email_account

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync all active email accounts to scan for new flight emails'

    def handle(self, *args, **options):
        accounts = EmailAccount.objects.filter(is_active=True)
        total = accounts.count()
        if total == 0:
            self.stdout.write('No active email accounts to sync.')
            return

        self.stdout.write(f'Syncing {total} active email account(s)...')
        total_flights = 0
        total_errors = 0

        for account in accounts:
            try:
                self.stdout.write(f'  Syncing {account.name} ({account.email_address})...')
                summary = sync_email_account(account)
                flights_created = summary.get('flights_created', 0)
                errors = summary.get('errors', [])
                total_flights += flights_created
                total_errors += len(errors)
                if flights_created:
                    self.stdout.write(f'    -> {flights_created} new flight(s) found')
                if errors:
                    for err in errors:
                        self.stderr.write(f'    -> Error: {err}')
            except Exception as e:
                total_errors += 1
                logger.error('Failed to sync account %s: %s', account.id, e)
                self.stderr.write(f'    -> Failed: {e}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Sync complete: {total_flights} new flight(s), {total_errors} error(s)'
            )
        )
