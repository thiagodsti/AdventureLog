"""
Auto-grouping logic for flights into trip groups.
Groups flights by booking reference and time proximity (like TripIt).
"""

import logging
from collections import defaultdict
from datetime import timedelta

from .models import Flight, FlightGroup

logger = logging.getLogger(__name__)


def auto_group_flights(user) -> dict:
    """
    Auto-group ungrouped flights into trip groups.

    Strategy:
    1. Group by booking_reference if available (same booking = same trip)
    2. For remaining flights, group by time proximity (flights within 48h
       of each other's arrival->departure are likely the same trip)

    Returns a summary of groups created and flights assigned.
    """
    ungrouped = list(
        Flight.objects.filter(user=user, flight_group__isnull=True)
        .order_by('departure_datetime')
    )

    groups_created = 0
    flights_grouped = 0

    if not ungrouped:
        # Still run merge phase even if no new ungrouped flights
        merged = _merge_overlapping_groups(user, max_gap=timedelta(hours=48))
        # Ensure all groups have linked collections
        _ensure_collections_for_all_groups(user)
        return {
            'groups_created': 0,
            'flights_grouped': 0,
            'groups_merged': merged,
            'message': 'No ungrouped flights found' + (f', merged {merged} groups' if merged else ''),
        }

    # --- Phase 1: Group by booking reference ---
    by_booking: dict[str, list[Flight]] = defaultdict(list)
    no_booking: list[Flight] = []

    for flight in ungrouped:
        if flight.booking_reference:
            by_booking[flight.booking_reference].append(flight)
        else:
            no_booking.append(flight)

    for booking_ref, flights in by_booking.items():
        if len(flights) < 1:
            continue

        # Create a group name from the route
        group = _create_group_for_flights(user, flights, booking_ref)
        if group:
            groups_created += 1
            flights_grouped += len(flights)

    # --- Phase 2: Group remaining flights by time proximity ---
    # (flights within 48h of each other belong to the same trip)
    remaining = list(
        Flight.objects.filter(user=user, flight_group__isnull=True)
        .order_by('departure_datetime')
    )

    if remaining:
        proximity_groups = _group_by_proximity(remaining, max_gap=timedelta(hours=48))
        for flight_cluster in proximity_groups:
            if len(flight_cluster) >= 2:  # Only group 2+ flights
                group = _create_group_for_flights(user, flight_cluster)
                if group:
                    groups_created += 1
                    flights_grouped += len(flight_cluster)

    # --- Phase 3: Merge groups that overlap in time ---
    # e.g. Brazil trip may have 3 bookings that are all within 48h of each other
    merged = _merge_overlapping_groups(user, max_gap=timedelta(hours=48))
    if merged:
        logger.info("Merged %d overlapping groups", merged)

    # Ensure all groups (including pre-existing ones) have a linked collection
    _ensure_collections_for_all_groups(user)

    return {
        'groups_created': groups_created,
        'flights_grouped': flights_grouped,
        'message': f'Created {groups_created} groups with {flights_grouped} flights',
    }


def _create_group_for_flights(user, flights: list[Flight], booking_ref: str = '') -> FlightGroup | None:
    """Create a FlightGroup and assign flights to it."""
    if not flights:
        return None

    sorted_flights = sorted(flights, key=lambda f: f.departure_datetime)
    first = sorted_flights[0]
    last = sorted_flights[-1]

    # Determine the "destination" — the turnaround point of the trip.
    # For one-way (ARN→FRA→GRU): last arrival (GRU).
    # For round-trip (ARN→FRA→GRU→FRA→ARN): the farthest point before
    # the traveller starts heading back toward the origin.
    origin = first.departure_airport
    destination = _find_trip_destination(sorted_flights, origin)

    # Build a nice name
    origin_name = first.departure_city or first.departure_airport
    dest_name = _get_city_for_airport(sorted_flights, destination) or destination

    date_str = first.departure_datetime.strftime('%b %Y')
    name = f"{origin_name} → {dest_name} ({date_str})"

    if booking_ref:
        name = f"{name} [{booking_ref}]"

    group = FlightGroup.objects.create(
        user=user,
        name=name,
        is_auto_generated=True,
    )

    Flight.objects.filter(
        id__in=[f.id for f in flights]
    ).update(flight_group=group)

    logger.info("Created flight group '%s' with %d flights", name, len(flights))
    return group


def _get_city_for_airport(flights: list[Flight], airport_code: str) -> str:
    """Find the city name for an airport code from the flight data."""
    for f in flights:
        if f.departure_airport == airport_code and f.departure_city:
            return f.departure_city
        if f.arrival_airport == airport_code and f.arrival_city:
            return f.arrival_city
    return ''


def _find_trip_destination(flights: list[Flight], origin: str) -> str:
    """
    Determine the main destination of a trip.

    For a one-way trip (ARN → FRA → GRU), returns the last arrival (GRU).
    For a round-trip (ARN → FRA → GRU → ... → FRA → ARN), returns the
    first "real destination" — the arrival airport of the first flight
    followed by a stay of 24 h or more (i.e. not a short connection).
    Falls back to the midpoint flight's arrival airport.
    """
    if not flights:
        return origin

    last_arrival = flights[-1].arrival_airport

    # One-way (possibly with connections): destination is the last arrival.
    if last_arrival != origin:
        return last_arrival

    # Round-trip: find the first real destination stay (gap >= 24 h).
    _CONNECTION_THRESHOLD = timedelta(hours=24)
    for i in range(len(flights) - 1):
        gap = flights[i + 1].departure_datetime - flights[i].arrival_datetime
        if gap >= _CONNECTION_THRESHOLD and flights[i].arrival_airport != origin:
            return flights[i].arrival_airport

    # Fallback: use the midpoint flight's arrival.
    mid = (len(flights) - 1) // 2
    arr = flights[mid].arrival_airport
    return arr if arr != origin else flights[0].arrival_airport


def _group_by_proximity(flights: list[Flight], max_gap: timedelta) -> list[list[Flight]]:
    """
    Group flights by time proximity.
    Flights where the next departure is within max_gap of the previous arrival
    are considered part of the same trip.
    """
    if not flights:
        return []

    groups: list[list[Flight]] = []
    current_group = [flights[0]]

    for i in range(1, len(flights)):
        prev = flights[i - 1]
        curr = flights[i]
        gap = curr.departure_datetime - prev.arrival_datetime

        if gap <= max_gap:
            current_group.append(curr)
        else:
            groups.append(current_group)
            current_group = [curr]

    groups.append(current_group)
    return groups


def _merge_overlapping_groups(user, max_gap: timedelta) -> int:
    """
    Merge flight groups whose flights overlap or are within max_gap of each
    other.  This catches cases where separate bookings (e.g. multiple airlines)
    are actually part of the same trip.

    Returns the number of merges performed.
    """
    merges = 0
    changed = True

    while changed:
        changed = False
        groups = list(
            FlightGroup.objects.filter(user=user, is_auto_generated=True)
            .order_by('id')
        )

        for i, g1 in enumerate(groups):
            g1_flights = list(g1.flights.order_by('departure_datetime'))
            if not g1_flights:
                continue
            g1_start = g1_flights[0].departure_datetime
            g1_end = g1_flights[-1].arrival_datetime

            for g2 in groups[i + 1:]:
                g2_flights = list(g2.flights.order_by('departure_datetime'))
                if not g2_flights:
                    continue
                g2_start = g2_flights[0].departure_datetime
                g2_end = g2_flights[-1].arrival_datetime

                # Check if the groups overlap or are within max_gap
                overlap = (
                    (g1_start <= g2_end + max_gap and g2_start <= g1_end + max_gap)
                )
                if overlap:
                    # Merge g2 into g1
                    Flight.objects.filter(flight_group=g2).update(flight_group=g1)

                    # Rebuild name from combined flights
                    all_flights = list(g1.flights.order_by('departure_datetime'))
                    first = all_flights[0]
                    origin = first.departure_airport
                    destination = _find_trip_destination(all_flights, origin)
                    dest_name = _get_city_for_airport(all_flights, destination) or destination
                    origin_name = first.departure_city or origin
                    date_str = first.departure_datetime.strftime('%b %Y')

                    # Collect all booking references
                    refs = set()
                    for f in all_flights:
                        if f.booking_reference:
                            refs.add(f.booking_reference)
                    ref_str = '/'.join(sorted(refs)) if refs else ''
                    g1.name = f"{origin_name} → {dest_name} ({date_str})"
                    if ref_str:
                        g1.name = f"{g1.name} [{ref_str}]"
                    g1.save(update_fields=['name'])

                    g2.delete()
                    logger.info("Merged group '%s' into '%s'", g2.name, g1.name)
                    merges += 1
                    changed = True
                    break  # Restart the loop since groups changed

            if changed:
                break

    return merges


def _ensure_collection_for_group(group):
    """
    Create or update a Collection linked to this FlightGroup.
    Also creates CollectionItineraryItem records so flights appear on
    the correct days in the itinerary planner.
    Returns the Collection instance, or None if the group has no flights.
    """
    from adventures.models import Collection, CollectionItineraryItem  # lazy import
    from django.contrib.contenttypes.models import ContentType

    flights = list(group.flights.order_by('departure_datetime'))
    if not flights:
        return None

    if group.collection:
        # Update existing collection dates and name
        collection = group.collection
        collection.start_date = flights[0].departure_datetime.date()
        collection.end_date = flights[-1].arrival_datetime.date() if flights[-1].arrival_datetime else flights[-1].departure_datetime.date()
        collection.name = group.name
        collection.save(update_fields=['name', 'start_date', 'end_date'])
        # Ensure all flights in the group are linked to the collection
        group.flights.filter(collection__isnull=True).update(collection=collection)
        # Ensure itinerary items exist for all flights
        _ensure_itinerary_items_for_flights(collection, flights)
        return collection

    end_date = flights[-1].arrival_datetime.date() if flights[-1].arrival_datetime else flights[-1].departure_datetime.date()
    collection = Collection.objects.create(
        user=group.user,
        name=group.name,
        start_date=flights[0].departure_datetime.date(),
        end_date=end_date,
    )
    group.collection = collection
    group.save(update_fields=['collection'])

    # Link all flights in this group to the collection
    group.flights.update(collection=collection)

    # Create itinerary items for the flights
    _ensure_itinerary_items_for_flights(collection, flights)

    logger.info(
        "Auto-created collection '%s' for flight group '%s'",
        collection.name, group.name,
    )
    return collection


def _ensure_itinerary_items_for_flights(collection, flights):
    """
    Create CollectionItineraryItem records for flights that don't have one yet.
    Places each flight on its departure date in the itinerary.
    """
    from adventures.models import CollectionItineraryItem
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Max

    flight_ct = ContentType.objects.get_for_model(Flight)

    # Find which flights already have itinerary items
    existing_ids = set(
        CollectionItineraryItem.objects.filter(
            collection=collection,
            content_type=flight_ct,
            object_id__in=[f.id for f in flights],
        ).values_list('object_id', flat=True)
    )

    for flight in flights:
        if flight.id in existing_ids:
            continue
        if not flight.departure_datetime:
            continue

        flight_date = flight.departure_datetime.date()

        # Clamp to collection date range
        if collection.start_date and flight_date < collection.start_date:
            flight_date = collection.start_date
        if collection.end_date and flight_date > collection.end_date:
            flight_date = collection.end_date

        # Get next order for this date
        max_order = CollectionItineraryItem.objects.filter(
            collection=collection,
            date=flight_date,
            is_global=False,
        ).aggregate(max_order=Max('order'))['max_order']
        next_order = (max_order + 1) if max_order is not None else 0

        CollectionItineraryItem.objects.create(
            collection=collection,
            content_type=flight_ct,
            object_id=flight.id,
            date=flight_date,
            order=next_order,
        )


def _ensure_collections_for_all_groups(user):
    """Ensure every FlightGroup for this user has a linked Collection."""
    groups = FlightGroup.objects.filter(user=user)
    for group in groups:
        _ensure_collection_for_group(group)
