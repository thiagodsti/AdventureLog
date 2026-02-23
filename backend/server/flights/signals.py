"""
Signals for the flights app.
Auto-marks visited cities/regions when flights are completed.
Auto-creates Location objects so flight-visited cities appear on the Locations page.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='flights.Flight')
def mark_visited_on_completed_flight(sender, instance, **kwargs):
    """
    When a flight is saved with status='completed', mark the departure
    and arrival cities/regions as visited in the WorldTravel system,
    and create Location objects so they appear on the Locations page.
    """
    if instance.status != 'completed':
        return

    user = instance.user

    airports_and_times = [
        (instance.departure_airport_obj, instance.departure_datetime),
        (instance.arrival_airport_obj, instance.arrival_datetime or instance.departure_datetime),
    ]

    for airport_obj, visit_datetime in airports_and_times:
        if not airport_obj:
            continue
        _mark_airport_visited(user, airport_obj)
        _ensure_location_for_airport(user, airport_obj, visit_datetime)


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


def _ensure_location_for_airport(user, airport, visit_datetime):
    """
    Auto-create a Location + Visit for an airport's city so it appears
    on the Locations page. Skips if the user already has a Location
    linked to this city.
    """
    if not airport.worldtravel_city:
        return

    from adventures.models import Location, Visit, Category

    city = airport.worldtravel_city

    # Skip if user already has a Location for this city
    if Location.objects.filter(user=user, city=city).exists():
        return

    # Get or create a "City" category for the user
    category, _ = Category.objects.get_or_create(
        user=user, name='city',
        defaults={'display_name': 'City', 'icon': '🏙️'}
    )

    location = Location.objects.create(
        user=user,
        name=airport.city_name or city.name,
        category=category,
        latitude=airport.latitude,
        longitude=airport.longitude,
        city=city,
        region=city.region,
        country=city.region.country,
    )

    if visit_datetime:
        Visit.objects.create(
            location=location,
            start_date=visit_datetime,
            end_date=visit_datetime,
        )

    logger.info(
        "Auto-created location '%s' for user %s (from airport %s)",
        location.name, user.username, airport.iata_code,
    )
