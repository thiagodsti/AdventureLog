"""
One-time management command to mark visited cities/regions for all
existing completed flights that have resolved airport objects with
linked WorldTravel cities.
"""

import logging

from django.core.management.base import BaseCommand

from flights.models import Flight

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Mark visited cities/regions from existing completed flights"

    def handle(self, *args, **options):
        from worldtravel.models import VisitedCity, VisitedRegion

        flights = (
            Flight.objects.filter(status='completed')
            .exclude(arrival_airport_obj__isnull=True)
            .select_related(
                'arrival_airport_obj__worldtravel_city__region',
                'departure_airport_obj__worldtravel_city__region',
            )
        )

        cities_created = 0
        regions_created = 0

        for flight in flights:
            for airport_obj in (flight.departure_airport_obj, flight.arrival_airport_obj):
                if not airport_obj or not airport_obj.worldtravel_city:
                    continue

                city = airport_obj.worldtravel_city
                _, created = VisitedCity.objects.get_or_create(
                    user=flight.user, city=city,
                )
                if created:
                    cities_created += 1

                _, created = VisitedRegion.objects.get_or_create(
                    user=flight.user, region=city.region,
                )
                if created:
                    regions_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {cities_created} cities and "
                f"{regions_created} regions marked as visited"
            )
        )
