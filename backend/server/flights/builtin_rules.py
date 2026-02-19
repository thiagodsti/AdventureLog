"""
Built-in airline parsing rules.
These are loaded via management command `load_airline_rules`.

Each body_pattern uses regex named groups to capture flight data.
Required named groups: flight_number, departure_airport, arrival_airport,
    departure_time, arrival_time.
Optional: departure_date, arrival_date, booking_reference, passenger_name,
    seat, cabin_class, departure_terminal, arrival_terminal, departure_gate,
    arrival_gate.
Note: If departure_date is not captured by the pattern, the parser will
attempt to find the closest preceding date in the email body.

The patterns are designed to work against the output of html_to_text()
which inserts newlines after block-level HTML elements.
"""

# ---------------------------------------------------------------------------
# Flexible date sub-pattern (reusable)
# Matches: "16 de mar. de 2026", "16 Mar 2026", "Mar 16, 2026", "16/03/2026"
# ---------------------------------------------------------------------------
_DATE = r'\d{1,2}\s+(?:de\s+)?[A-Za-zÀ-ÿ]+\.?\s+(?:de\s+)?\d{4}'
_TIME = r'\d{1,2}:\d{2}'

BUILTIN_AIRLINE_RULES = [
    # =========================================================================
    # LATAM Airlines (LA / JJ / 4C / 4M)
    #
    # Real emails come from info@info.latam.com with subjects in PT/ES/EN.
    # The HTML itinerary uses this structure per flight leg:
    #   <date>  <time> <city>  (<AIRPORT>)  <flight_number>
    #   ...
    #   <date>  <time> <city>  (<AIRPORT>)
    # =========================================================================
    {
        'airline_name': 'LATAM Airlines',
        'airline_code': 'LA',
        'sender_pattern': r'(latam\.com|latamairlines\.com|info\.latam\.|@latam\.)',
        'subject_pattern': (
            r'(itinerar|confirm|reserv|booking|e-?ticket|'
            r'compr|viage|viaje|vuelo|voo|trip|travel)'
        ),
        'body_pattern': (
            # Departure: date, time, then airport code in parentheses
            r'(?P<departure_date>' + _DATE + r')'
            r'\s+'
            r'(?P<departure_time>' + _TIME + r')'
            r'.*?'
            r'\((?P<departure_airport>[A-Z]{3})\)'
            r'.*?'
            # Flight number (LA, JJ, 4C, 4M prefixes used by LATAM group)
            r'(?P<flight_number>(?:LA|JJ|4C|4M)\s*\d{3,5})'
            r'.*?'
            # Arrival: date, time, then airport code in parentheses
            r'(?P<arrival_date>' + _DATE + r')'
            r'\s+'
            r'(?P<arrival_time>' + _TIME + r')'
            r'.*?'
            r'\((?P<arrival_airport>[A-Z]{3})\)'
        ),
        'date_format': '%d %b %Y',
        'time_format': '%H:%M',
        'is_active': True,
        'is_builtin': True,
        'priority': 10,
    },
    # =========================================================================
    # SAS Scandinavian Airlines (SK)
    #
    # Real emails come from flysas.com / no-reply@flysas.com.
    # Three email types contain flight data:
    #   1. "Your Flight [date], Booking: [REF]"  (English, older format)
    #   2. "Din flygning [date], Bokning :[REF]"  (Swedish, 2023 format)
    #   3. "Din resa [date], Bokning: [REF]"      (Swedish, 2025+ format)
    #
    # After html_to_text(), per flight leg the structure is:
    #   <City> <AIRPORT> [-–] <City> <AIRPORT>
    #   <dep_time> [-–] <arr_time> (<duration>)
    #   ...terminal info...
    #   SK <number> | <operator>
    #
    # Date for the segment appears as a section header earlier, e.g.:
    #   "07 Aug 2020" or "10 May 2023" or "28 okt 2025"
    # For multi-leg (connecting) flights, connecting legs may share a
    # single date header. The parser finds the closest preceding date.
    # =========================================================================
    {
        'airline_name': 'SAS Scandinavian Airlines',
        'airline_code': 'SK',
        'sender_pattern': r'(flysas\.com|sas\.se|sas\.dk|sas\.no|@sas\.)',
        'subject_pattern': (
            r'(booking\s*confirm|itinerary|e-?ticket|receipt|'
            r'reservation|billet|resa|rejse|reise|trip|travel|'
            r'flight|flygning|bokningsbek|bokning|Din\s+resa|Your\s+Flight)'
        ),
        'body_pattern': (
            # Route: "<City> <DEP_AIRPORT> – <City> <ARR_AIRPORT>"
            # (departure_date is NOT in the regex – the parser infers it
            # from the closest preceding date found in the email body)
            r'(?P<departure_airport>[A-Z]{3})'
            r'\s*[-–]\s*'
            r'(?:[A-ZÀ-ÿ][A-Za-zÀ-ÿ\s-]*?\s+)?'
            r'(?P<arrival_airport>[A-Z]{3})'
            r'\s+'
            # Times: "16:55 – 20:00" or "07:30 - 09:10"
            r'(?P<departure_time>' + _TIME + r')'
            r'\s*[-–]\s*'
            r'(?P<arrival_time>' + _TIME + r')'
            r'.*?'
            # Flight number: "SK1829", "SK 2601", "VS 449"
            r'(?P<flight_number>(?:SK|VS|LH|LX|OS|TP|A3|SN)\s*\d{2,5})'
        ),
        'date_format': '%d %b %Y',
        'time_format': '%H:%M',
        'is_active': True,
        'is_builtin': True,
        'priority': 10,
    },
    # =========================================================================
    # Lufthansa (LH)
    # =========================================================================
    {
        'airline_name': 'Lufthansa',
        'airline_code': 'LH',
        'sender_pattern': r'(lufthansa\.com|@lh\.com|noreply@lufthansa)',
        'subject_pattern': (
            r'(booking\s*confirm|itinerary|e-?ticket|receipt|'
            r'buchungsbest[äa]tigung|flugbest[äa]tigung|reservation|'
            r'Reise|trip|travel)'
        ),
        'body_pattern': (
            r'(?:'
            r'(?P<departure_date>' + _DATE + r')'
            r'\s+'
            r'(?P<departure_time>' + _TIME + r')'
            r'.*?'
            r'\((?P<departure_airport>[A-Z]{3})\)'
            r'.*?'
            r'(?P<flight_number>LH\s*\d{3,5})'
            r'.*?'
            r'(?P<arrival_date>' + _DATE + r')'
            r'\s+'
            r'(?P<arrival_time>' + _TIME + r')'
            r'.*?'
            r'\((?P<arrival_airport>[A-Z]{3})\)'
            r')'
        ),
        'date_format': '%d %b %Y',
        'time_format': '%H:%M',
        'is_active': True,
        'is_builtin': True,
        'priority': 10,
    },
    # =========================================================================
    # Azul Brazilian Airlines (AD)
    #
    # Emails come from noreply@voeazul-news.com.br.
    # The HTML itinerary structure (after html_to_text):
    #   <DEPARTURE_AIRPORT>      (standalone 3-letter code on its own line)
    #   <city name>
    #   DD/MM • HH:MM            (date • time, no year)
    #   Voo NNNN                 (flight number without AD prefix)
    #   <ARRIVAL_AIRPORT>
    #   <city name>
    #   DD/MM • HH:MM
    # =========================================================================
    {
        'airline_name': 'Azul Brazilian Airlines',
        'airline_code': 'AD',
        'sender_pattern': r'(voeazul[\w-]*\.com\.br|azullinhasaereas\.com|@azul\.com)',
        'subject_pattern': (
            r'(itinerar|confirm|reserv|booking|e-?ticket|'
            r'compr|viage|voo|passagem|bilhete|trip|travel)'
        ),
        'body_pattern': (
            # Departure airport (3-letter code on its own line to avoid matching 'AZU' from text)
            r'\n\s*(?P<departure_airport>[A-Z]{3})\s*\n'
            r'.*?'
            # Departure date/time: "02/03 • 13:20"
            r'(?P<departure_date>\d{2}/\d{2})'
            r'\s*[•·]\s*'
            r'(?P<departure_time>' + _TIME + r')'
            r'.*?'
            # Flight number: "Voo 4849" (Azul doesn't use AD prefix in emails)
            r'(?:Voo|Flight)\s+(?P<flight_number>\d{3,5})'
            r'.*?'
            # Arrival airport (on its own line)
            r'\n\s*(?P<arrival_airport>[A-Z]{3})\s*\n'
            r'.*?'
            # Arrival date/time: "02/03 • 14:35"
            r'(?P<arrival_date>\d{2}/\d{2})'
            r'\s*[•·]\s*'
            r'(?P<arrival_time>' + _TIME + r')'
        ),
        'date_format': '%d/%m',
        'time_format': '%H:%M',
        'is_active': True,
        'is_builtin': True,
        'priority': 10,
    },
]
