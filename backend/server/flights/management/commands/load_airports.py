"""
Management command to import airport data from OurAirports CSV.
Downloads ~4,500 medium/large airports with IATA codes, then links
each to the nearest WorldTravel City for visited-city integration.
"""

import csv
import io
import logging
import math
import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from flights.models import Airport, Flight

logger = logging.getLogger(__name__)

AIRPORTS_CSV_URL = (
    "https://davidmegginson.github.io/ourairports-data/airports.csv"
)
VALID_TYPES = {"large_airport", "medium_airport"}


def _haversine_km(lat1, lon1, lat2, lon2):
    """Return distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(float(lat1)))
        * math.cos(math.radians(float(lat2)))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class Command(BaseCommand):
    help = "Import airport data from OurAirports and link to WorldTravel cities"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-download of airports.csv even if cached",
        )
        parser.add_argument(
            "--link-only",
            action="store_true",
            help="Skip download and only re-run city linking + flight backfill",
        )
        parser.add_argument(
            "--max-distance-km",
            type=float,
            default=50.0,
            help="Maximum distance in km for city matching (default: 50)",
        )

    def handle(self, *args, **options):
        if not options["link_only"]:
            self._download_and_import(force=options["force"])
        self._link_cities(max_distance_km=options["max_distance_km"])
        self._backfill_flights()
        self.stdout.write(self.style.SUCCESS("Done."))

    def _download_and_import(self, force=False):
        csv_path = os.path.join(settings.MEDIA_ROOT, "airports.csv")

        if os.path.exists(csv_path) and not force:
            self.stdout.write(f"Using cached {csv_path} (use --force to re-download)")
        else:
            self.stdout.write(f"Downloading airports.csv from OurAirports...")
            resp = requests.get(AIRPORTS_CSV_URL, timeout=60)
            resp.raise_for_status()
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
            with open(csv_path, "wb") as f:
                f.write(resp.content)
            self.stdout.write(f"Saved to {csv_path}")

        # Parse and import
        airports_to_create = []
        seen_iata = set()

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                iata = (row.get("iata_code") or "").strip()
                airport_type = (row.get("type") or "").strip()

                if not iata or len(iata) != 3 or airport_type not in VALID_TYPES:
                    continue

                iata_upper = iata.upper()
                if iata_upper in seen_iata:
                    continue
                seen_iata.add(iata_upper)

                # Parse region code: OurAirports uses "CC-XX" format (e.g. "BR-SP")
                iso_region = (row.get("iso_region") or "").strip()

                try:
                    lat = float(row.get("latitude_deg") or 0)
                    lon = float(row.get("longitude_deg") or 0)
                except (ValueError, TypeError):
                    continue

                # Extract city name from municipality field
                city_name = (row.get("municipality") or "").strip()

                airports_to_create.append(
                    Airport(
                        iata_code=iata_upper,
                        icao_code=(row.get("ident") or "").strip()[:4],
                        name=(row.get("name") or "").strip()[:255],
                        city_name=city_name[:255],
                        country_code=(row.get("iso_country") or "").strip()[:2],
                        region_code=iso_region[:10],
                        latitude=lat,
                        longitude=lon,
                    )
                )

        self.stdout.write(f"Parsed {len(airports_to_create)} airports with IATA codes")

        with transaction.atomic():
            # Upsert: create or update all airports
            Airport.objects.bulk_create(
                airports_to_create,
                update_conflicts=True,
                unique_fields=["iata_code"],
                update_fields=[
                    "icao_code", "name", "city_name", "country_code",
                    "region_code", "latitude", "longitude",
                ],
                batch_size=500,
            )

        self.stdout.write(
            self.style.SUCCESS(f"Imported {len(airports_to_create)} airports")
        )

    def _link_cities(self, max_distance_km=50.0):
        """Link each airport to the nearest WorldTravel City."""
        from worldtravel.models import City, Region

        airports = list(Airport.objects.all())
        self.stdout.write(f"Linking {len(airports)} airports to WorldTravel cities...")

        # Build region lookup for fast exact matching
        region_ids = set(Region.objects.values_list("id", flat=True))

        linked = 0
        updated = []

        for airport in airports:
            city = None

            # Strategy 1: Exact match by region + city name
            if airport.region_code and airport.region_code in region_ids:
                city = City.objects.filter(
                    region_id=airport.region_code,
                    name__iexact=airport.city_name,
                ).first()

            # Strategy 2: Country-wide city name match (for when region codes differ)
            if not city and airport.city_name and airport.country_code:
                city = City.objects.filter(
                    region__country__country_code=airport.country_code,
                    name__iexact=airport.city_name,
                ).first()

            # Strategy 3: Nearest city by coordinates within max_distance_km
            if not city and airport.latitude and airport.longitude:
                # Get candidate cities within a rough bounding box first
                lat_range = max_distance_km / 111.0  # ~111 km per degree latitude
                lon_range = max_distance_km / (
                    111.0 * max(math.cos(math.radians(float(airport.latitude))), 0.01)
                )
                candidates = City.objects.filter(
                    latitude__range=(
                        float(airport.latitude) - lat_range,
                        float(airport.latitude) + lat_range,
                    ),
                    longitude__range=(
                        float(airport.longitude) - lon_range,
                        float(airport.longitude) + lon_range,
                    ),
                )
                best_city = None
                best_dist = max_distance_km
                for c in candidates:
                    if c.latitude is None or c.longitude is None:
                        continue
                    dist = _haversine_km(
                        airport.latitude, airport.longitude,
                        c.latitude, c.longitude,
                    )
                    if dist < best_dist:
                        best_dist = dist
                        best_city = c
                city = best_city

            if city and airport.worldtravel_city_id != city.id:
                airport.worldtravel_city = city
                updated.append(airport)
                linked += 1

        if updated:
            Airport.objects.bulk_update(updated, ["worldtravel_city"], batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"Linked {linked} airports to cities"))

    def _backfill_flights(self):
        """Resolve airport FKs for existing flights that lack them."""
        airport_map = {a.iata_code: a for a in Airport.objects.all()}

        flights_to_update = []
        update_fields = {
            "departure_airport_obj", "arrival_airport_obj",
            "departure_city", "arrival_city",
        }

        # Process each flight that needs either departure or arrival resolved
        from django.db.models import Q
        needs_backfill = Flight.objects.filter(
            Q(departure_airport_obj__isnull=True) | Q(arrival_airport_obj__isnull=True)
        )
        for flight in needs_backfill:
            changed = False

            if not flight.departure_airport_obj_id and flight.departure_airport:
                airport = airport_map.get(flight.departure_airport.upper())
                if airport:
                    flight.departure_airport_obj = airport
                    changed = True
                    if not flight.departure_city and airport.city_name:
                        flight.departure_city = airport.city_name

            if not flight.arrival_airport_obj_id and flight.arrival_airport:
                airport = airport_map.get(flight.arrival_airport.upper())
                if airport:
                    flight.arrival_airport_obj = airport
                    changed = True
                    if not flight.arrival_city and airport.city_name:
                        flight.arrival_city = airport.city_name

            if changed:
                flights_to_update.append(flight)

        if flights_to_update:
            Flight.objects.bulk_update(
                flights_to_update,
                list(update_fields),
                batch_size=500,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backfilled airport FKs for {len(flights_to_update)} flights"
                )
            )
        else:
            self.stdout.write("No flights to backfill")
