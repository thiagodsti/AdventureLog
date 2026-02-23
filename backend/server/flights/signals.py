"""
Signals for the flights app.
Auto-marks visited cities/regions when flights are completed.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='flights.Flight')
def mark_visited_on_completed_flight(sender, instance, **kwargs):
    """
    When a flight is saved with status='completed', mark the departure
    and arrival cities/regions as visited in the WorldTravel system.
    """
    if instance.status != 'completed':
        return

    user = instance.user

    for airport_obj in (instance.departure_airport_obj, instance.arrival_airport_obj):
        if not airport_obj:
            continue
        _mark_airport_visited(user, airport_obj)


def _mark_airport_visited(user, airport):
    """Mark the city and region for an airport as visited."""
    from worldtravel.models import VisitedCity, VisitedRegion, Region

    if airport.worldtravel_city:
        city = airport.worldtravel_city
        _, created_city = VisitedCity.objects.get_or_create(
            user=user, city=city
        )
        _, created_region = VisitedRegion.objects.get_or_create(
            user=user, region=city.region
        )
        if created_city:
            logger.info(
                "Auto-marked city '%s' as visited for user %s (from airport %s)",
                city.name, user.username, airport.iata_code,
            )
        if created_region:
            logger.info(
                "Auto-marked region '%s' as visited for user %s",
                city.region.name, user.username,
            )
    elif airport.region_code:
        # Fallback: mark just the region if no city match
        region = Region.objects.filter(id=airport.region_code).first()
        if region:
            _, created = VisitedRegion.objects.get_or_create(
                user=user, region=region
            )
            if created:
                logger.info(
                    "Auto-marked region '%s' as visited for user %s (no city match for %s)",
                    region.name, user.username, airport.iata_code,
                )
