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

    # Determine the "destination" — farthest point from origin
    origin = first.departure_airport
    destination = last.arrival_airport
    for f in sorted_flights:
        if f.arrival_airport != origin:
            destination = f.arrival_airport
            break

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
                    destination = first.arrival_airport
                    for f in all_flights:
                        if f.arrival_airport != origin:
                            destination = f.arrival_airport
                            break
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
