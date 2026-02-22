"""
Flight email parsing engine.
Applies airline rules (regex patterns) to email messages to extract flight data.

Rules come from builtin_rules.get_builtin_rules() — they are defined in code and
are not stored in or fetched from the database.
"""

import logging
import re
from datetime import datetime, date as date_type, timedelta, timezone

from django.utils import timezone as dj_timezone

from .builtin_rules import get_builtin_rules
from .email_connector import EmailMessage
from .models import Flight, EmailAccount

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Multilingual month-name map (lowercase, no trailing dot)
# ---------------------------------------------------------------------------
MONTH_MAP: dict[str, int] = {
    # English
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
    'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9,
    'september': 9, 'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
    # Portuguese
    'fev': 2, 'fevereiro': 2, 'março': 3, 'abr': 4, 'abril': 4,
    'mai': 5, 'maio': 5, 'ago': 8, 'agosto': 8, 'set': 9, 'setembro': 9,
    'out': 10, 'outubro': 10, 'dez': 12, 'dezembro': 12,
    'janeiro': 1, 'junho': 6, 'julho': 7, 'novembro': 11,
    # Spanish
    'ene': 1, 'enero': 1, 'febrero': 2, 'marzo': 3,
    'mayo': 5, 'junio': 6, 'julio': 7, 'septiembre': 9,
    'octubre': 10, 'noviembre': 11, 'dic': 12, 'diciembre': 12,
    # German
    'mär': 3, 'märz': 3, 'okt': 10, 'oktober': 10, 'dezember': 12,
    # Scandinavian
    'maj': 5, 'marts': 3, 'juni': 6, 'juli': 7, 'augusti': 8,
}


def parse_flight_date(raw: str) -> date_type | None:
    """
    Parse a date string that may use Portuguese/Spanish/German/Scandinavian month
    names.  Handles e.g. "16 de mar. de 2026", "16 Mar 2026", "2026-03-16".
    """
    raw = raw.strip()

    # ISO / numeric formats first
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    # "16 de mar. de 2026"  or  "16 Mar 2026"  or  "Mar 16, 2026"
    m = re.match(
        r'(\d{1,2})\s+(?:de\s+)?([A-Za-zÀ-ÿ]+)\.?\s+(?:de\s+)?(\d{4})', raw
    )
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower().rstrip('.'), int(m.group(3))
        month = MONTH_MAP.get(month_name)
        if month:
            try:
                return date_type(year, month, day)
            except ValueError:
                pass

    # English "Mar 16, 2026"
    m = re.match(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', raw)
    if m:
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month = MONTH_MAP.get(month_name)
        if month:
            try:
                return date_type(year, month, day)
            except ValueError:
                pass

    # Last resort: strftime with current locale
    for fmt in ('%d %b %Y', '%d %B %Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


def get_rules_for_user(user):
    """Return the active built-in airline rules (code-defined, no DB query).
    The `user` argument is kept for API compatibility but is no longer used.
    """
    return sorted(get_builtin_rules(), key=lambda r: (-r.priority, r.airline_name))


def match_rule_to_email(email_msg: EmailMessage, rules):
    """
    Find the first matching airline rule for an email message.
    Checks sender_pattern and optionally subject_pattern.
    """
    for rule in rules:
        try:
            # Check sender pattern
            if not re.search(rule.sender_pattern, email_msg.sender, re.IGNORECASE):
                continue

            # Check subject pattern if specified
            if rule.subject_pattern:
                if not re.search(rule.subject_pattern, email_msg.subject, re.IGNORECASE):
                    continue

            return rule
        except re.error as e:
            logger.warning("Invalid regex in rule %s: %s", rule.id, e)
            continue
    return None


def _extract_latam_flights(email_msg: EmailMessage, rule) -> list[dict]:
    """
    Custom LATAM extractor that handles connection flights.

    LATAM purchase-confirmation emails list each direction (outbound/return)
    with a departure point, zero or more "Troca de avião em:" connection
    points, and an arrival point.  Only the overall departure and arrival
    have explicit date+time; connection segments have layover durations
    instead.  This function parses all segments and estimates intermediate
    times from the layover information.
    """
    body = email_msg.body
    flights_data: list[dict] = []

    # ---- Shared metadata (booking ref, passenger) ----
    shared_booking = ''
    booking_match = re.search(
        r'(?:C[óo]digo\s+de\s+reserva|booking\s*(?:ref|code|reference)|'
        r'Bokning|Reserva|PNR|confirmation\s*code)[:\s\[]+([A-Z0-9]{5,8})',
        email_msg.subject + '\n' + body, re.IGNORECASE,
    )
    if booking_match:
        shared_booking = booking_match.group(1).strip()

    shared_passenger = ''
    # Try "Lista de passageiros" / "Passenger list" pattern first
    passenger_match = re.search(
        r'(?:Lista\s+de\s+passageiros|passenger\s*(?:list|name))'
        r'[\s:]*[-•·]?\s*'
        r'([A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+)*)',
        body, re.IGNORECASE,
    )
    if not passenger_match:
        # Fall back to greeting pattern
        passenger_match = re.search(
            r'(?:Ol[áa]|Hello|Hola)\s+(?:<b[^>]*>)?\s*([A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+)',
            body, re.IGNORECASE,
        )
    if passenger_match:
        shared_passenger = passenger_match.group(1).strip()

    # ---- Regex building blocks ----
    _DATE_RE = r'(\d{1,2}\s+(?:de\s+)?[A-Za-zÀ-ÿ]+\.?\s+(?:de\s+)?\d{4})'
    _TIME_RE = r'(\d{1,2}:\d{2})'
    _AIRPORT_RE = r'\(([A-Z]{3})\)'
    _FLIGHT_NUM_RE = r'([A-Z0-9]{2}\s*\d{3,5})'

    # ---- Split body into directions (Voo de ida / Voo de volta) ----
    # Find direction headers
    direction_starts = list(re.finditer(
        r'Voo de (?:ida|volta)|(?:Outbound|Return|Inbound)\s+(?:flight|journey)',
        body, re.IGNORECASE,
    ))

    # If no direction headers found, try "Trecho N" sections, then fall back
    if not direction_starts:
        # Try "Trecho 1", "Trecho 2", etc.
        trecho_starts = list(re.finditer(r'Trecho\s+\d+', body, re.IGNORECASE))
        if trecho_starts:
            sections = []
            for i, m in enumerate(trecho_starts):
                start = m.start()
                end = trecho_starts[i + 1].start() if i + 1 < len(trecho_starts) else len(body)
                sections.append(body[start:end])
        else:
            # Fall back: look for "Itinerário" and treat everything after as one block
            itin_match = re.search(r'Itiner[áa]rio', body, re.IGNORECASE)
            sections = [body[itin_match.start():] if itin_match else body]
    else:
        sections = []
        for i, m in enumerate(direction_starts):
            start = m.start()
            end = direction_starts[i + 1].start() if i + 1 < len(direction_starts) else len(body)
            sections.append(body[start:end])

    for section in sections:
        # ---- Find departure: date + time + airport ----
        dep_match = re.search(
            _DATE_RE + r'\s+' + _TIME_RE + r'.*?' + _AIRPORT_RE,
            section, re.DOTALL,
        )
        if not dep_match:
            continue

        dep_date_str = dep_match.group(1)
        dep_time_str = dep_match.group(2)
        dep_airport = dep_match.group(3)

        # ---- Find arrival: date + time + airport (last one in section) ----
        arr_matches = list(re.finditer(
            _DATE_RE + r'\s+' + _TIME_RE + r'.*?' + _AIRPORT_RE,
            section, re.DOTALL,
        ))
        if len(arr_matches) < 2:
            # Only one date+time+airport found — this is a direct flight
            arr_date_str = dep_date_str
            arr_time_str = dep_time_str
            arr_airport = dep_airport
            # Try to find arrival airport after the flight number
            flight_match = re.search(
                r'\(' + re.escape(dep_airport) + r'\)' + r'.*?' + _FLIGHT_NUM_RE + r'.*?' + _AIRPORT_RE,
                section, re.DOTALL,
            )
            if flight_match:
                flight_num = flight_match.group(1).strip()
                arr_airport = flight_match.group(2)
                # No separate arrival time — use departure as fallback
                flights_data.append(_make_latam_flight(
                    rule, dep_date_str, dep_time_str, dep_airport,
                    dep_date_str, dep_time_str, arr_airport,
                    flight_num, shared_booking, shared_passenger,
                ))
            continue

        arr_match = arr_matches[-1]
        arr_date_str = arr_match.group(1)
        arr_time_str = arr_match.group(2)
        arr_airport = arr_match.group(3)

        # ---- Find all flight numbers and connection airports ----
        # Find connections: "Troca de avião em:" ... (AIRPORT) ... flight_number ... "Tempo de espera: X hr Y min"
        connection_re = (
            r'Troca\s+de\s+avi[ãa]o\s+em:\s*'
            r'([A-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]*?)\s*'
            r'\(([A-Z]{3})\)\s+'
            r'([A-Z0-9]{2}\s*\d{3,5})'
            r'.*?'
            r'Tempo\s+de\s+espera:\s*(\d+)\s*hr?\s*(\d+)\s*min'
        )
        connections = list(re.finditer(connection_re, section, re.DOTALL | re.IGNORECASE))

        # Also find the first flight number (right after departure airport)
        first_flight_match = re.search(
            r'\(' + re.escape(dep_airport) + r'\)\s+' + _FLIGHT_NUM_RE,
            section,
        )
        first_flight_num = first_flight_match.group(1).strip() if first_flight_match else ''

        if connections:
            # Build segments: dep_airport → conn1 → conn2 → ... → arr_airport
            # Segment 1: dep_airport → first_connection (using first_flight_num)
            # Segment N: last_connection → arr_airport (using last connection's flight_num)

            segments = []
            prev_airport = dep_airport

            # First segment: departure → first connection
            first_conn = connections[0]
            conn_airport = first_conn.group(2)
            conn_flight = first_conn.group(3).strip()
            layover_h = int(first_conn.group(4))
            layover_m = int(first_conn.group(5))
            segments.append({
                'dep_airport': prev_airport,
                'arr_airport': conn_airport,
                'flight_number': first_flight_num,
                'layover_after_minutes': layover_h * 60 + layover_m,
                'next_flight': conn_flight,
            })
            prev_airport = conn_airport

            # Middle connections
            for i in range(1, len(connections)):
                conn = connections[i]
                conn_airport = conn.group(2)
                conn_flight = conn.group(3).strip()
                layover_h = int(conn.group(4))
                layover_m = int(conn.group(5))
                # This segment uses the flight number from the PREVIOUS connection
                segments.append({
                    'dep_airport': prev_airport,
                    'arr_airport': conn_airport,
                    'flight_number': segments[-1]['next_flight'],
                    'layover_after_minutes': layover_h * 60 + layover_m,
                    'next_flight': conn_flight,
                })
                prev_airport = conn_airport

            # Last segment: last connection → arrival
            segments.append({
                'dep_airport': prev_airport,
                'arr_airport': arr_airport,
                'flight_number': segments[-1]['next_flight'],
                'layover_after_minutes': 0,
                'next_flight': '',
            })

            # ---- Estimate intermediate times ----
            dep_date = parse_flight_date(dep_date_str)
            arr_date = parse_flight_date(arr_date_str)
            if dep_date is None or arr_date is None:
                continue

            dep_h, dep_m = map(int, dep_time_str.split(':'))
            arr_h, arr_m = map(int, arr_time_str.split(':'))

            dep_dt = datetime(dep_date.year, dep_date.month, dep_date.day, dep_h, dep_m)
            arr_dt = datetime(arr_date.year, arr_date.month, arr_date.day, arr_h, arr_m)

            total_elapsed = (arr_dt - dep_dt).total_seconds()
            total_layover = sum(s['layover_after_minutes'] * 60 for s in segments)
            total_flight = total_elapsed - total_layover
            n_segments = len(segments)

            if total_flight <= 0 or n_segments == 0:
                continue

            # Distribute flight time proportionally (equal per segment as estimate)
            flight_per_segment = total_flight / n_segments

            current_dt = dep_dt
            for seg in segments:
                seg_dep_dt = current_dt
                seg_arr_dt = seg_dep_dt + timedelta(seconds=flight_per_segment)

                flight_data = {
                    'airline_name': rule.airline_name,
                    'airline_code': rule.airline_code,
                    'flight_number': seg['flight_number'],
                    'departure_airport': seg['dep_airport'],
                    'arrival_airport': seg['arr_airport'],
                    'departure_datetime': dj_timezone.make_aware(seg_dep_dt, timezone.utc),
                    'arrival_datetime': dj_timezone.make_aware(seg_arr_dt, timezone.utc),
                    'booking_reference': shared_booking,
                    'passenger_name': shared_passenger,
                    'seat': '',
                    'cabin_class': '',
                    'departure_terminal': '',
                    'arrival_terminal': '',
                    'departure_gate': '',
                    'arrival_gate': '',
                }

                if flight_data['flight_number'] and flight_data['departure_airport'] and flight_data['arrival_airport']:
                    flights_data.append(flight_data)

                # Move to next segment: arrival + layover
                current_dt = seg_arr_dt + timedelta(minutes=seg['layover_after_minutes'])

        else:
            # Direct flight (no connections)
            if first_flight_num:
                flights_data.append(_make_latam_flight(
                    rule, dep_date_str, dep_time_str, dep_airport,
                    arr_date_str, arr_time_str, arr_airport,
                    first_flight_num, shared_booking, shared_passenger,
                ))

    return flights_data


def _make_latam_flight(
    rule, dep_date_str, dep_time_str, dep_airport,
    arr_date_str, arr_time_str, arr_airport,
    flight_number, booking_ref, passenger,
) -> dict:
    """Helper to create a flight dict for a direct LATAM segment."""
    dep_date = parse_flight_date(dep_date_str)
    arr_date = parse_flight_date(arr_date_str) or dep_date
    if dep_date is None:
        return {}

    dep_h, dep_m = map(int, dep_time_str.split(':'))
    dep_dt = dj_timezone.make_aware(
        datetime(dep_date.year, dep_date.month, dep_date.day, dep_h, dep_m),
        timezone.utc,
    )

    arr_h, arr_m = map(int, arr_time_str.split(':'))
    arr_dt = dj_timezone.make_aware(
        datetime(arr_date.year, arr_date.month, arr_date.day, arr_h, arr_m),
        timezone.utc,
    )

    return {
        'airline_name': rule.airline_name,
        'airline_code': rule.airline_code,
        'flight_number': flight_number,
        'departure_airport': dep_airport,
        'arrival_airport': arr_airport,
        'departure_datetime': dep_dt,
        'arrival_datetime': arr_dt,
        'booking_reference': booking_ref,
        'passenger_name': passenger,
        'seat': '',
        'cabin_class': '',
        'departure_terminal': '',
        'arrival_terminal': '',
        'departure_gate': '',
        'arrival_gate': '',
    }


def extract_flights_from_email(email_msg: EmailMessage, rule) -> list[dict]:
    """
    Apply a rule's body_pattern regex to an email body and extract flight data.
    Returns a list of dicts, one per flight found (regex finditer for multi-leg trips).

    Rules with a ``custom_extractor`` field use a dedicated parsing function
    instead of the generic regex approach (e.g. LATAM connection handling).
    """
    # ---- Try BS4 extraction first if HTML body is available ----
    if email_msg.html_body:
        from .bs4_extractors import extract_with_bs4
        bs4_result = extract_with_bs4(email_msg.html_body, rule, email_msg)
        if bs4_result:
            return bs4_result

    # ---- Dispatch to custom extractor if configured (regex fallback) ----
    extractor = getattr(rule, 'custom_extractor', '')
    if extractor == 'latam':
        return _extract_latam_flights(email_msg, rule)

    flights_data = []
    body = email_msg.body

    # ---- Extract shared metadata from anywhere in the body ----
    shared_booking = ''
    # Also try extracting booking ref from the subject line
    booking_match = re.search(
        r'(?:C[óo]digo\s+de\s+reserva|booking\s*(?:ref|code|reference)|'
        r'Bokning|Reserva|PNR|Buchungscode|Buchungsnummer|reservation\s*code|'
        r'confirmation\s*code|Reservierungscode)[:\s\[]+([A-Z0-9]{5,8})',
        email_msg.subject + '\n' + body, re.IGNORECASE,
    )
    if booking_match:
        shared_booking = booking_match.group(1).strip()

    shared_passenger = ''
    passenger_match = re.search(
        r'(?:Lista\s+de\s+passageiros|passenger\s*(?:list|name)|'
        r'Passagier|Reisender|passager|passasjer)'
        r'[\s:]*\n\s*(?:[-•·]\s*)?'
        r'([A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+(?:[ ]+[A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+)+)',
        body, re.IGNORECASE,
    )
    if passenger_match:
        shared_passenger = passenger_match.group(1).strip()

    # ---- Apply the rule's body_pattern to find flight legs ----
    try:
        matches = list(re.finditer(rule.body_pattern, body, re.IGNORECASE | re.DOTALL))
        if not matches:
            logger.debug(
                "No body_pattern matches for rule '%s' in email %s",
                rule.airline_name, email_msg.message_id,
            )
            return flights_data

        for match in matches:
            groups = match.groupdict()
            # If flight_number is purely digits, prefix with airline code
            raw_flight_num = groups.get('flight_number', '').strip()
            if raw_flight_num and raw_flight_num.isdigit() and rule.airline_code:
                raw_flight_num = f"{rule.airline_code}{raw_flight_num}"

            flight_data = {
                'airline_name': rule.airline_name,
                'airline_code': rule.airline_code,
                'flight_number': raw_flight_num,
                'departure_airport': groups.get('departure_airport', '').strip().upper(),
                'arrival_airport': groups.get('arrival_airport', '').strip().upper(),
                'booking_reference': groups.get('booking_reference', '').strip() or shared_booking,
                'passenger_name': groups.get('passenger_name', '').strip() or shared_passenger,
                'seat': groups.get('seat', '').strip(),
                'cabin_class': groups.get('cabin_class', '').strip().lower(),
                'departure_terminal': groups.get('departure_terminal', '').strip(),
                'arrival_terminal': groups.get('arrival_terminal', '').strip(),
                'departure_gate': groups.get('departure_gate', '').strip(),
                'arrival_gate': groups.get('arrival_gate', '').strip(),
            }

            # --- Parse departure date + time ---
            dep_date_str = groups.get('departure_date', '').strip()
            dep_time_str = groups.get('departure_time', '').strip()

            # If the regex didn't capture departure_date (e.g. connecting
            # legs that share a date header), look for the closest preceding
            # date in the email body before this match's position.
            if not dep_date_str:
                _ctx_date_re = r'(\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})'
                _ctx_dates = list(re.finditer(_ctx_date_re, body[:match.start()]))
                if _ctx_dates:
                    dep_date_str = _ctx_dates[-1].group(1)
                    logger.debug(
                        "Inferred departure_date %r from context for match at %d",
                        dep_date_str, match.start(),
                    )

            arr_date_str = groups.get('arrival_date', '').strip() or dep_date_str
            arr_time_str = groups.get('arrival_time', '').strip()

            # Determine reference year from the email date (for DD/MM without year)
            ref_year = email_msg.date.year if email_msg.date else datetime.now().year

            dep_date = parse_flight_date(dep_date_str)
            if dep_date is None and dep_date_str:
                # Fallback to rule-level date_format
                try:
                    dep_date = datetime.strptime(dep_date_str, rule.date_format).date()
                except (ValueError, TypeError):
                    pass
            # If year came back as 1900 (parsed DD/MM without year), infer year
            if dep_date is not None and dep_date.year == 1900:
                candidate = dep_date.replace(year=ref_year)
                # If the flight date is before the email date, it's likely next year
                if email_msg.date and candidate < email_msg.date.date():
                    candidate = dep_date.replace(year=ref_year + 1)
                dep_date = candidate
            if dep_date is None or not dep_time_str:
                logger.warning("Cannot parse departure datetime: %r %r", dep_date_str, dep_time_str)
                continue

            try:
                h, m = dep_time_str.split(':')
                dep_dt = datetime(dep_date.year, dep_date.month, dep_date.day, int(h), int(m))
                flight_data['departure_datetime'] = dj_timezone.make_aware(dep_dt, timezone.utc)
            except (ValueError, TypeError) as e:
                logger.warning("Bad departure time %r: %s", dep_time_str, e)
                continue

            # --- Parse arrival date + time ---
            arr_date = parse_flight_date(arr_date_str)
            if arr_date is None and arr_date_str:
                try:
                    arr_date = datetime.strptime(arr_date_str, rule.date_format).date()
                except (ValueError, TypeError):
                    pass
            # If year came back as 1900 (parsed DD/MM without year), infer year
            if arr_date is not None and arr_date.year == 1900:
                candidate = arr_date.replace(year=ref_year)
                if email_msg.date and candidate < email_msg.date.date():
                    candidate = arr_date.replace(year=ref_year + 1)
                arr_date = candidate
            if arr_date is None:
                arr_date = dep_date  # assume same day

            if arr_time_str:
                try:
                    h, m = arr_time_str.split(':')
                    arr_dt = datetime(arr_date.year, arr_date.month, arr_date.day, int(h), int(m))
                    flight_data['arrival_datetime'] = dj_timezone.make_aware(arr_dt, timezone.utc)
                except (ValueError, TypeError) as e:
                    logger.warning("Bad arrival time %r: %s", arr_time_str, e)
                    continue
            else:
                logger.warning("No arrival time found, skipping")
                continue

            # Normalise cabin class
            cabin_map = {
                'economy': 'economy', 'eco': 'economy', 'y': 'economy',
                'premium economy': 'premium_economy', 'premium': 'premium_economy', 'w': 'premium_economy',
                'business': 'business', 'j': 'business', 'c': 'business',
                'first': 'first', 'f': 'first',
                'econômica': 'economy', 'económica': 'economy', 'ejecutiva': 'business',
            }
            raw_cabin = flight_data.get('cabin_class', '')
            flight_data['cabin_class'] = cabin_map.get(raw_cabin, '')

            if flight_data['flight_number'] and flight_data['departure_airport'] and flight_data['arrival_airport']:
                flights_data.append(flight_data)
            else:
                logger.debug("Skipping incomplete flight match: %s", flight_data)

    except re.error as e:
        logger.error("Regex error in rule %s body_pattern: %s", rule.id, e)

    return flights_data


def process_email_for_flights(email_msg: EmailMessage, user, email_account: EmailAccount | None = None) -> list[Flight]:
    """
    Process a single email message: match against rules, extract flights, save to DB.
    Skips duplicates based on email_message_id.
    """
    rules = get_rules_for_user(user)
    rule = match_rule_to_email(email_msg, rules)
    if not rule:
        return []

    flights_data = extract_flights_from_email(email_msg, rule)
    created_flights = []

    for flight_data in flights_data:
        # Check for duplicate
        msg_id_for_dedup = f"{email_msg.message_id}:{flight_data['flight_number']}"
        if Flight.objects.filter(user=user, email_message_id=msg_id_for_dedup).exists():
            logger.debug("Skipping duplicate flight: %s", msg_id_for_dedup)
            continue

        try:
            flight = Flight.objects.create(
                user=user,
                email_account=email_account,
                airline_rule=None,  # rules are code-defined, not DB rows
                email_subject=email_msg.subject[:512],
                email_date=email_msg.date,
                email_message_id=msg_id_for_dedup,
                **flight_data,
            )
            created_flights.append(flight)
            logger.info("Created flight: %s", flight)
        except Exception as e:
            logger.error("Error creating flight from email %s: %s", email_msg.message_id, e)

    return created_flights


def sync_email_account(email_account: EmailAccount) -> dict:
    """
    Full sync: fetch emails from an account, process all of them for flights.
    Returns a summary dict.

    If the builtin rules version has changed since the last sync, the date
    filter is dropped so that older emails are re-scanned against the new
    rules.  Duplicate flights are prevented by the email_message_id dedup
    check in process_email_for_flights().
    """
    from .email_connector import fetch_emails_for_account
    from .builtin_rules import RULES_VERSION

    user = email_account.user
    summary = {
        'emails_fetched': 0,
        'flights_created': 0,
        'errors': [],
    }

    try:
        since_date = email_account.last_synced_at
        # If rules version changed, do a full rescan (dedup prevents duplicates)
        if email_account.last_rules_version != RULES_VERSION:
            logger.info(
                "Rules version changed (%s -> %s) for account %s, doing full rescan",
                email_account.last_rules_version, RULES_VERSION, email_account.id,
            )
            since_date = None

        email_messages = fetch_emails_for_account(
            email_account, since_date=since_date, max_results=500
        )
        summary['emails_fetched'] = len(email_messages)

        for email_msg in email_messages:
            try:
                created = process_email_for_flights(email_msg, user, email_account)
                summary['flights_created'] += len(created)
            except Exception as e:
                summary['errors'].append(str(e))
                logger.error("Error processing email %s: %s", email_msg.message_id, e)

        # Update last synced timestamp and rules version
        email_account.last_synced_at = dj_timezone.now()
        email_account.last_rules_version = RULES_VERSION
        email_account.save(update_fields=['last_synced_at', 'last_rules_version'])

        # Auto-group flights after every sync
        if summary['flights_created'] > 0:
            from .grouping import auto_group_flights
            auto_group_flights(user)

    except NotImplementedError as e:
        summary['errors'].append(str(e))
    except Exception as e:
        summary['errors'].append(f"Connection error: {str(e)}")
        logger.error("Sync error for account %s: %s", email_account.id, e)

    return summary
