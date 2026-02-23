"""
Management command to mark visited cities/regions and auto-create Location
objects for all existing completed flights that have resolved airport objects
with linked WorldTravel cities.
"""

import logging

from django.core.management.base import BaseCommand

from flights.models import Flight

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Mark visited cities/regions and create Locations from existing completed flights"

    def handle(self, *args, **options):
        from worldtravel.models import VisitedCity, VisitedRegion
        from flights.signals import _ensure_location_for_airport

        flights = (
            Flight.objects.filter(status='completed')
            .exclude(arrival_airport_obj__isnull=True)
            .select_related(
                'arrival_airport_obj__worldtravel_city__region__country',
                'departure_airport_obj__worldtravel_city__region__country',
            )
        )

        cities_created = 0
        regions_created = 0
        locations_created = 0

        for flight in flights:
            airports_and_times = [
                (flight.departure_airport_obj, flight.departure_datetime),
                (flight.arrival_airport_obj, flight.arrival_datetime or flight.departure_datetime),
            ]

            for airport_obj, visit_datetime in airports_and_times:
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

                # Auto-create Location object
                from adventures.models import Location
                before = Location.objects.filter(user=flight.user, city=city).exists()
                _ensure_location_for_airport(flight.user, airport_obj, visit_datetime)
                if not before and Location.objects.filter(user=flight.user, city=city).exists():
                    locations_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {cities_created} cities, "
                f"{regions_created} regions marked as visited, "
                f"{locations_created} locations created"
            )
        )
