"""
BeautifulSoup-based flight data extraction from HTML emails.

Uses semantic markers and DOM structure to extract flight data — more robust
than regex on flattened text because it leverages the HTML hierarchy.

Each airline gets a dedicated extractor. If extraction fails (returns []),
the caller falls back to the existing regex-based approach.
"""

import logging
import re
from datetime import datetime, date as date_type, timedelta, timezone

from bs4 import BeautifulSoup, NavigableString

from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)

# Reuse the multilingual date parser from parsers.py
from .parsers import parse_flight_date, MONTH_MAP


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _get_text(soup_or_tag) -> str:
    """Get clean text from a BS4 element, collapsing whitespace."""
    if soup_or_tag is None:
        return ''
    text = soup_or_tag.get_text(separator=' ', strip=True)
    return re.sub(r'\s+', ' ', text).strip()


def _find_by_text(soup, pattern, tag=None):
    """Find elements whose text matches a regex pattern."""
    compiled = re.compile(pattern, re.IGNORECASE)
    if tag:
        return soup.find_all(tag, string=compiled)
    return soup.find_all(string=compiled)


def _extract_airports(text: str) -> list[str]:
    """Extract all 3-letter IATA airport codes in parentheses from text."""
    return re.findall(r'\(([A-Z]{3})\)', text)


def _extract_bare_airports(text: str) -> list[str]:
    """Extract standalone 3-letter codes (on their own or in parentheses)."""
    # Parenthesized first
    parens = re.findall(r'\(([A-Z]{3})\)', text)
    if parens:
        return parens
    # Standalone: 3 uppercase letters surrounded by whitespace/line boundaries
    return re.findall(r'(?:^|\s)([A-Z]{3})(?:\s|$)', text)


def _extract_time(text: str) -> str | None:
    """Extract HH:MM time from text."""
    m = re.search(r'(\d{1,2}:\d{2})', text)
    return m.group(1) if m else None


def _extract_times(text: str) -> list[str]:
    """Extract all HH:MM times from text."""
    return re.findall(r'\d{1,2}:\d{2}', text)


def _extract_flight_number(text: str, airline_codes: list[str] | None = None) -> str | None:
    """Extract a flight number like 'LA 1234' or 'SK1829' from text."""
    if airline_codes:
        codes = '|'.join(re.escape(c) for c in airline_codes)
        m = re.search(rf'({codes})\s*(\d{{2,5}})', text)
        if m:
            return f"{m.group(1)}{m.group(2)}"
    # Generic: 2-letter code + digits
    m = re.search(r'([A-Z]{2})\s*(\d{2,5})', text)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return None


def _make_aware_dt(dt: datetime) -> datetime:
    """Make a naive datetime timezone-aware (UTC)."""
    return dj_timezone.make_aware(dt, timezone.utc)


def _build_datetime(date_obj: date_type, time_str: str) -> datetime | None:
    """Combine a date and HH:MM string into a timezone-aware datetime."""
    if not date_obj or not time_str:
        return None
    try:
        h, m = map(int, time_str.split(':'))
        return _make_aware_dt(datetime(date_obj.year, date_obj.month, date_obj.day, h, m))
    except (ValueError, TypeError):
        return None


def _extract_booking_reference(soup, subject: str = '') -> str:
    """Extract booking reference using semantic markers."""
    full_text = subject + '\n' + _get_text(soup)
    m = re.search(
        r'(?:C[óo]digo\s+de\s+reserva|booking\s*(?:ref|code|reference)|'
        r'Bokning|Reserva|PNR|Buchungscode|Buchungsnummer|'
        r'reservation\s*code|confirmation\s*code)[:\s\[]+([A-Z0-9]{5,8})',
        full_text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Fallback: "Booking: XXXX" (standalone keyword with colon)
    m = re.search(r'Booking\s*:\s*([A-Z0-9]{5,8})', full_text, re.IGNORECASE)
    return m.group(1).strip() if m else ''


def _extract_passenger_name(soup) -> str:
    """Extract passenger name using semantic markers."""
    text = _get_text(soup)

    # "Lista de passageiros" / "Passenger list" pattern
    m = re.search(
        r'(?:Lista\s+de\s+passageiros|passenger\s*(?:list|name)|'
        r'Passagier|Reisender|passager|passasjer)'
        r'[\s:]*[-•·]?\s*'
        r'([A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+)*)',
        text, re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # "Olá <Name>" pattern
    m = re.search(
        r'(?:Ol[áa]|Hello|Hola)\s+(?:<b[^>]*>)?\s*([A-ZÀ-ÿ][a-zA-ZÀ-ÿ]+)',
        text, re.IGNORECASE,
    )
    return m.group(1).strip() if m else ''


def _make_flight_dict(
    rule, flight_number, dep_airport, arr_airport,
    dep_dt, arr_dt, booking_ref='', passenger='',
) -> dict | None:
    """Create a flight data dict if all required fields are present."""
    if not all([flight_number, dep_airport, arr_airport, dep_dt, arr_dt]):
        return None
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


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def extract_with_bs4(html: str, rule, email_msg) -> list[dict]:
    """
    Try BS4 extraction. Returns [] if extraction not possible or fails,
    signaling the caller to fall back to regex.
    """
    if not html or not html.strip():
        return []

    extractor_name = getattr(rule, 'custom_extractor', '')
    extractors = {
        'latam': _extract_latam_bs4,
        'sas': _extract_sas_bs4,
        'lufthansa': _extract_lufthansa_bs4,
        'azul': _extract_azul_bs4,
    }

    extractor = extractors.get(extractor_name)
    if not extractor:
        return []

    try:
        result = extractor(html, rule, email_msg)
        if result:
            logger.debug(
                "BS4 extractor '%s' found %d flight(s)", extractor_name, len(result)
            )
        return result
    except Exception:
        logger.debug("BS4 extractor '%s' failed, falling back to regex", extractor_name, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# LATAM Airlines
# ---------------------------------------------------------------------------

def _extract_latam_bs4(html: str, rule, email_msg) -> list[dict]:
    """
    Extract flights from LATAM HTML emails.

    Strategy:
    1. Find direction sections (Voo de ida / Voo de volta) or itinerary blocks
    2. Within each section, find airport codes, dates, times, flight numbers
    3. Handle connections via "Troca de avião em:" markers
    """
    soup = BeautifulSoup(html, 'lxml')
    text = _get_text(soup)
    flights = []

    booking_ref = _extract_booking_reference(soup, email_msg.subject)
    passenger = _extract_passenger_name(soup)

    # Find all text nodes/elements containing airport codes in parentheses
    # LATAM uses: "São Paulo (GRU)" pattern
    _DATE_RE = r'(\d{1,2}\s+(?:de\s+)?[A-Za-zÀ-ÿ]+\.?\s+(?:de\s+)?\d{4})'
    _TIME_RE = r'(\d{1,2}:\d{2})'
    _AIRPORT_RE = r'\(([A-Z]{3})\)'
    _FLIGHT_NUM_RE = r'([A-Z0-9]{2}\s*\d{3,5})'

    # Split by direction headers
    direction_splits = re.split(
        r'(Voo de (?:ida|volta)|(?:Outbound|Return|Inbound)\s+(?:flight|journey))',
        text, flags=re.IGNORECASE,
    )

    # Build sections: if we found direction headers, pair them with content
    sections = []
    if len(direction_splits) <= 1:
        # No direction headers — try "Trecho" or treat whole text as one section
        trecho_splits = re.split(r'Trecho\s+\d+', text, flags=re.IGNORECASE)
        if len(trecho_splits) > 1:
            sections = trecho_splits[1:]  # skip preamble before first Trecho
        else:
            sections = [text]
    else:
        # Pair direction headers with their content
        i = 1
        while i < len(direction_splits):
            content = direction_splits[i + 1] if i + 1 < len(direction_splits) else ''
            sections.append(direction_splits[i] + content)
            i += 2

    for section in sections:
        # Find all date+time+airport tuples
        segment_matches = list(re.finditer(
            _DATE_RE + r'\s+' + _TIME_RE + r'.*?' + _AIRPORT_RE,
            section, re.DOTALL,
        ))

        # Find flight numbers in section
        flight_nums = re.findall(_FLIGHT_NUM_RE, section)

        if len(segment_matches) >= 2 and flight_nums:
            # Process pairs: (departure, arrival) for each leg
            # Check for connections
            connections = list(re.finditer(
                r'Troca\s+de\s+avi[ãa]o\s+em:.*?\(([A-Z]{3})\)\s+'
                r'([A-Z0-9]{2}\s*\d{3,5}).*?'
                r'Tempo\s+de\s+espera:\s*(\d+)\s*hr?\s*(\d+)\s*min',
                section, re.DOTALL | re.IGNORECASE,
            ))

            if connections:
                # Multi-leg with connections — use same interpolation logic
                dep_match = segment_matches[0]
                arr_match = segment_matches[-1]

                dep_date = parse_flight_date(dep_match.group(1))
                dep_time = dep_match.group(2)
                dep_airport = dep_match.group(3)

                arr_date = parse_flight_date(arr_match.group(1))
                arr_time = arr_match.group(2)
                arr_airport = arr_match.group(3)

                if not dep_date or not arr_date:
                    continue

                dep_dt = _build_datetime(dep_date, dep_time)
                arr_dt = _build_datetime(arr_date, arr_time)
                if not dep_dt or not arr_dt:
                    continue

                # Build segment chain
                segments = []
                prev_airport = dep_airport
                first_flight = flight_nums[0].strip() if flight_nums else ''

                for conn in connections:
                    conn_airport = conn.group(1)
                    conn_flight = conn.group(2).strip()
                    layover_min = int(conn.group(3)) * 60 + int(conn.group(4))
                    segments.append({
                        'dep_airport': prev_airport,
                        'arr_airport': conn_airport,
                        'flight_number': first_flight if not segments else segments[-1].get('next_flight', conn_flight),
                        'layover_minutes': layover_min,
                        'next_flight': conn_flight,
                    })
                    prev_airport = conn_airport

                # Last segment to arrival
                segments.append({
                    'dep_airport': prev_airport,
                    'arr_airport': arr_airport,
                    'flight_number': segments[-1]['next_flight'] if segments else first_flight,
                    'layover_minutes': 0,
                })

                # Interpolate times
                total_elapsed = (arr_dt - dep_dt).total_seconds()
                total_layover = sum(s['layover_minutes'] * 60 for s in segments)
                total_flight = total_elapsed - total_layover
                n_segments = len(segments)

                if total_flight <= 0 or n_segments == 0:
                    continue

                flight_per_seg = total_flight / n_segments
                current_dt = dep_dt

                for seg in segments:
                    seg_dep_dt = current_dt
                    seg_arr_dt = seg_dep_dt + timedelta(seconds=flight_per_seg)

                    flight = _make_flight_dict(
                        rule, seg['flight_number'], seg['dep_airport'], seg['arr_airport'],
                        seg_dep_dt, seg_arr_dt, booking_ref, passenger,
                    )
                    if flight:
                        flights.append(flight)

                    current_dt = seg_arr_dt + timedelta(minutes=seg['layover_minutes'])
            else:
                # Direct flights (no connections) — pair departure/arrival
                # Simple case: 2 matches = 1 flight, 4 matches = 2 flights
                for i in range(0, len(segment_matches) - 1, 2):
                    dep_m = segment_matches[i]
                    arr_m = segment_matches[i + 1]

                    dep_date = parse_flight_date(dep_m.group(1))
                    arr_date = parse_flight_date(arr_m.group(1))
                    if not dep_date or not arr_date:
                        continue

                    dep_dt = _build_datetime(dep_date, dep_m.group(2))
                    arr_dt = _build_datetime(arr_date, arr_m.group(2))

                    # Find flight number for this leg
                    fn_idx = i // 2
                    fn = flight_nums[fn_idx].strip() if fn_idx < len(flight_nums) else ''

                    flight = _make_flight_dict(
                        rule, fn, dep_m.group(3), arr_m.group(3),
                        dep_dt, arr_dt, booking_ref, passenger,
                    )
                    if flight:
                        flights.append(flight)

    return flights


# ---------------------------------------------------------------------------
# SAS Scandinavian Airlines
# ---------------------------------------------------------------------------

def _extract_sas_bs4(html: str, rule, email_msg) -> list[dict]:
    """
    Extract flights from SAS HTML emails.

    Strategy:
    1. Find date elements (section headers like "07 Aug 2026")
    2. Find route blocks: "Stockholm ARN – Copenhagen CPH"
    3. Find time blocks: "07:30 – 09:10"
    4. Find flight numbers: "SK 1829"
    """
    soup = BeautifulSoup(html, 'lxml')
    text = _get_text(soup)
    flights = []

    booking_ref = _extract_booking_reference(soup, email_msg.subject)

    # Use finditer to locate date headers, then extract data from the text between them
    date_re = re.compile(r'(?:^|\s)(\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4})(?:\s|$)')
    route_re = re.compile(r'([A-Z]{3})\s*[-–]\s*(?:[A-ZÀ-ÿ][A-Za-zÀ-ÿ\s-]*?\s+)?([A-Z]{3})')
    time_re = re.compile(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})')
    flight_num_re = re.compile(r'((?:SK|VS|LH|LX|OS|TP|A3|SN)\s*\d{2,5})')

    # Find all date positions, then build blocks from date to next date
    date_matches = list(date_re.finditer(text))

    for i, date_m in enumerate(date_matches):
        dep_date = parse_flight_date(date_m.group(1))
        if not dep_date:
            continue

        # Block extends from this date to the next date (or end of text)
        block_start = date_m.start()
        block_end = date_matches[i + 1].start() if i + 1 < len(date_matches) else len(text)
        block = text[block_start:block_end]

        route_m = route_re.search(block)
        time_m = time_re.search(block)
        fn_m = flight_num_re.search(block)

        if not all([route_m, time_m, fn_m]):
            continue

        dep_airport = route_m.group(1)
        arr_airport = route_m.group(2)
        dep_time = time_m.group(1)
        arr_time = time_m.group(2)
        flight_number = fn_m.group(1).replace(' ', '')

        dep_dt = _build_datetime(dep_date, dep_time)
        arr_dt = _build_datetime(dep_date, arr_time)

        # Handle overnight flights
        if arr_dt and dep_dt and arr_dt < dep_dt:
            arr_dt = _build_datetime(
                date_type(dep_date.year, dep_date.month, dep_date.day) + timedelta(days=1),
                arr_time,
            )

        flight = _make_flight_dict(
            rule, flight_number, dep_airport, arr_airport,
            dep_dt, arr_dt, booking_ref,
        )
        if flight:
            flights.append(flight)

    return flights


# ---------------------------------------------------------------------------
# Lufthansa
# ---------------------------------------------------------------------------

def _extract_lufthansa_bs4(html: str, rule, email_msg) -> list[dict]:
    """
    Extract flights from Lufthansa HTML emails.

    Strategy:
    1. Find flight blocks containing date + time + airport + flight number
    2. Each leg has departure and arrival info with full dates
    """
    soup = BeautifulSoup(html, 'lxml')
    text = _get_text(soup)
    flights = []

    booking_ref = _extract_booking_reference(soup, email_msg.subject)

    _DATE = r'(\d{1,2}\s+(?:de\s+)?[A-Za-zÀ-ÿ]+\.?\s+(?:de\s+)?\d{4})'
    _TIME = r'(\d{1,2}:\d{2})'
    _AIRPORT = r'\(([A-Z]{3})\)'

    # Find all date+time+airport occurrences
    dta_pattern = re.compile(
        _DATE + r'\s+' + _TIME + r'.*?' + _AIRPORT,
        re.DOTALL,
    )
    matches = list(dta_pattern.finditer(text))

    # Find flight numbers
    fn_pattern = re.compile(r'(LH\s*\d{3,5})')
    fn_matches = list(fn_pattern.finditer(text))

    # Pair matches: dep+arr for each leg
    for i in range(0, len(matches) - 1, 2):
        dep_m = matches[i]
        arr_m = matches[i + 1]

        dep_date = parse_flight_date(dep_m.group(1))
        arr_date = parse_flight_date(arr_m.group(1))
        if not dep_date or not arr_date:
            continue

        dep_dt = _build_datetime(dep_date, dep_m.group(2))
        arr_dt = _build_datetime(arr_date, arr_m.group(2))

        # Find the flight number between departure and arrival positions
        flight_number = ''
        for fn_m in fn_matches:
            if dep_m.start() <= fn_m.start() <= arr_m.start():
                flight_number = fn_m.group(1).replace(' ', '')
                break

        flight = _make_flight_dict(
            rule, flight_number, dep_m.group(3), arr_m.group(3),
            dep_dt, arr_dt, booking_ref,
        )
        if flight:
            flights.append(flight)

    return flights


# ---------------------------------------------------------------------------
# Azul Brazilian Airlines
# ---------------------------------------------------------------------------

def _extract_azul_bs4(html: str, rule, email_msg) -> list[dict]:
    """
    Extract flights from Azul HTML emails.

    Strategy:
    1. Find airport codes (standalone 3-letter codes in table cells)
    2. Find date/time pairs: "DD/MM . HH:MM"
    3. Find flight numbers: "Voo NNNN"
    4. Infer year from email date
    """
    soup = BeautifulSoup(html, 'lxml')
    flights = []

    booking_ref = _extract_booking_reference(soup, email_msg.subject)

    ref_year = email_msg.date.year if email_msg.date else datetime.now().year

    # Strategy: find all table cells or elements containing airport codes,
    # dates, times, and flight numbers, then assemble them in order.
    text = _get_text(soup)

    # Find flight blocks using the Azul pattern:
    # AIRPORT_CODE ... DD/MM . HH:MM ... Voo NNNN ... AIRPORT_CODE ... DD/MM . HH:MM
    block_re = re.compile(
        r'(?:^|\s)([A-Z]{3})\s'          # departure airport
        r'.*?'
        r'(\d{2}/\d{2})\s*[•·]\s*'       # departure date
        r'(\d{1,2}:\d{2})'               # departure time
        r'.*?'
        r'(?:Voo|Flight)\s+(\d{3,5})'    # flight number
        r'.*?'
        r'(?:^|\s)([A-Z]{3})\s'          # arrival airport
        r'.*?'
        r'(\d{2}/\d{2})\s*[•·]\s*'       # arrival date
        r'(\d{1,2}:\d{2})',              # arrival time
        re.DOTALL | re.MULTILINE,
    )

    for m in block_re.finditer(text):
        dep_airport = m.group(1)
        dep_date_str = m.group(2)
        dep_time = m.group(3)
        flight_num_raw = m.group(4)
        arr_airport = m.group(5)
        arr_date_str = m.group(6)
        arr_time = m.group(7)

        # Parse DD/MM dates and infer year
        dep_date = _parse_ddmm_date(dep_date_str, ref_year, email_msg.date)
        arr_date = _parse_ddmm_date(arr_date_str, ref_year, email_msg.date)
        if not dep_date or not arr_date:
            continue

        dep_dt = _build_datetime(dep_date, dep_time)
        arr_dt = _build_datetime(arr_date, arr_time)

        # Prefix bare digit flight number with airline code
        flight_number = f"{rule.airline_code}{flight_num_raw}"

        flight = _make_flight_dict(
            rule, flight_number, dep_airport, arr_airport,
            dep_dt, arr_dt, booking_ref,
        )
        if flight:
            flights.append(flight)

    return flights


def _parse_ddmm_date(date_str: str, ref_year: int, email_date=None) -> date_type | None:
    """Parse a DD/MM date string and infer the year."""
    m = re.match(r'(\d{2})/(\d{2})', date_str)
    if not m:
        return None
    try:
        day, month = int(m.group(1)), int(m.group(2))
        candidate = date_type(ref_year, month, day)
        # If flight date is before email date, it might be next year
        if email_date and candidate < email_date.date():
            candidate = date_type(ref_year + 1, month, day)
        return candidate
    except ValueError:
        return None
