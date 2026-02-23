"""
Tests for SAS Scandinavian Airlines email parsing.

SAS emails come from no-reply@flysas.com (or sas.se / sas.dk / sas.no).

Format 1 — "Din resa" HTML-to-text (block style):
    07 Aug 2026
    Stockholm ARN – Copenhagen CPH
    07:30 – 09:10 (1h 40m)
    SK 1829 | Operated by SAS

Format 2 — "Electronic Ticket" PDF (tabular style):
    SK 533 / 28OCT Stockholm Arlanda - London Heathrow 18:15 19:55 Terminal 5 1PC
"""
from datetime import datetime, timezone
from unittest.mock import patch
from django.test import TestCase

from flights.builtin_rules import get_builtin_rules
from flights.email_connector import EmailMessage
from flights.parsers import match_rule_to_email, extract_flights_from_email

_SAS_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'SK')

_SAS_BODY = """\
Your booking confirmation

Booking: XY9012

07 Aug 2026
Stockholm ARN – Copenhagen CPH
07:30 – 09:10 (1h 40m)
SK 1829 | Operated by SAS

10 Aug 2026
Copenhagen CPH – Stockholm ARN
18:00 – 19:45 (1h 45m)
SK 1834 | Operated by SAS
"""


class TestSASRuleMatching(TestCase):
    """Sender / subject matching for SAS emails."""

    def _make_email(self, sender, subject=None):
        return EmailMessage(
            message_id='sas-test-1',
            sender=sender,
            subject=subject or 'Booking confirmation SK1829',
            body=_SAS_BODY,
            date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

    def test_matches_flysas_com(self):
        msg = self._make_email('no-reply@flysas.com')
        rule = match_rule_to_email(msg, [_SAS_RULE])
        self.assertIsNotNone(rule)
        self.assertEqual(rule.airline_code, 'SK')

    def test_matches_sas_se(self):
        msg = self._make_email('noreply@sas.se')
        rule = match_rule_to_email(msg, [_SAS_RULE])
        self.assertIsNotNone(rule)

    def test_does_not_match_unrelated_sender(self):
        msg = self._make_email('deals@booking.com')
        rule = match_rule_to_email(msg, [_SAS_RULE])
        self.assertIsNone(rule)


class TestSASFlightExtraction(TestCase):
    """Flight data extraction for a realistic SAS itinerary."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='sas-ext-1',
            sender='no-reply@flysas.com',
            subject='Booking confirmation SK1829',
            body=_SAS_BODY,
            date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)

    def test_outbound_airports(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        leg1 = flights[0]
        self.assertEqual(leg1['departure_airport'], 'ARN')
        self.assertEqual(leg1['arrival_airport'], 'CPH')

    def test_outbound_flight_number(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertIn('SK', flights[0]['flight_number'])
        self.assertIn('1829', flights[0]['flight_number'])

    def test_outbound_times(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        dep = flights[0]['departure_datetime']
        arr = flights[0]['arrival_datetime']
        self.assertEqual(dep.hour, 7)
        self.assertEqual(dep.minute, 30)
        self.assertEqual(arr.hour, 9)
        self.assertEqual(arr.minute, 10)

    def test_date_inferred_from_context(self):
        """SAS body_pattern does not capture departure_date; parser infers it."""
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.year, 2026)
        self.assertEqual(dep.month, 8)
        self.assertEqual(dep.day, 7)

    def test_return_leg_airports(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        leg2 = flights[1]
        self.assertEqual(leg2['departure_airport'], 'CPH')
        self.assertEqual(leg2['arrival_airport'], 'ARN')


# ---------------------------------------------------------------------------
# Format 1 — Block-style text extraction (Din resa / HTML-to-text)
# ---------------------------------------------------------------------------

_SAS_BLOCK_BODY = """\
Your booking confirmation

Booking: AB1234

15 May 2025
Stockholm ARN – London LHR
10:00 – 12:30 (2h 30m)
SK 1531 | Operated by SAS

15 May 2025
London LHR – Johannesburg JNB
14:00 – 23:30 (9h 30m)
BA 55 | Operated by British Airways
"""

_SAS_SAME_DATE_BODY = """\
Booking: CD5678

15 May 2025
Stockholm ARN – London LHR
10:00 – 12:30 (2h 30m)
SK 1531 | Operated by SAS
London LHR – Johannesburg JNB
14:00 – 23:30 (9h 30m)
BA 55 | Operated by British Airways
"""


class TestSASBlockStyleExtraction(TestCase):
    """Format 1: Block-style text (Din resa / HTML-to-text fallback)."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='sas-block-1',
            sender='no-reply@flysas.com',
            subject='Din resa 15 May 2025, Bokning: AB1234',
            body=_SAS_BLOCK_BODY,
            date=datetime(2025, 5, 10, tzinfo=timezone.utc),
            html_body=None,
        )

    def test_extracts_two_connection_legs(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)

    def test_first_leg_arn_lhr(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'ARN')
        self.assertEqual(flights[0]['arrival_airport'], 'LHR')
        self.assertIn('SK', flights[0]['flight_number'])

    def test_second_leg_lhr_jnb(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[1]['departure_airport'], 'LHR')
        self.assertEqual(flights[1]['arrival_airport'], 'JNB')
        self.assertIn('BA', flights[1]['flight_number'])

    def test_booking_reference(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'AB1234')

    def test_date_parsing(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[0]['departure_datetime'].month, 5)
        self.assertEqual(flights[0]['departure_datetime'].day, 15)
        self.assertEqual(flights[0]['departure_datetime'].year, 2025)


class TestSASSameDateMultiLeg(TestCase):
    """Two connection legs under a single date header (block style)."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='sas-samedate-1',
            sender='no-reply@flysas.com',
            subject='Din resa, Bokning: CD5678',
            body=_SAS_SAME_DATE_BODY,
            date=datetime(2025, 5, 10, tzinfo=timezone.utc),
            html_body=None,
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)

    def test_first_leg(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'ARN')
        self.assertEqual(flights[0]['arrival_airport'], 'LHR')

    def test_second_leg(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[1]['departure_airport'], 'LHR')
        self.assertEqual(flights[1]['arrival_airport'], 'JNB')


class TestSASBS4FallbackToText(TestCase):
    """When BS4 returns [] (HTML has no itinerary), text extractor kicks in."""

    def test_falls_back_to_text_extractor(self):
        msg = EmailMessage(
            message_id='sas-fallback-1',
            sender='no-reply@flysas.com',
            subject='Din resa, Bokning: AB1234',
            body=_SAS_BLOCK_BODY,
            date=datetime(2025, 5, 10, tzinfo=timezone.utc),
            html_body='<html><body><p>See attached PDF for itinerary</p></body></html>',
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)


# ---------------------------------------------------------------------------
# Format 2 — PDF tabular extraction (Electronic Ticket Itinerary)
# ---------------------------------------------------------------------------

_SAS_PDF_TABULAR_BODY = """\
Electronic Ticket Itinerary and Receipt
Mr Thiago Diniz Da Silveira Date of Issue: 15MAY25
Booking Reference: WD7WYD IATA Number: 80494912
Flight/Date Route Departure Arrival Latest Flight Baggage
Class/Status Meal Check-in Duration Allowance
Scandinavian Airlines Operated by Sas Connect
SK 533 / 28OCT Stockholm Arlanda - London Heathrow 18:15 19:55 17:35 Terminal 5 1PC
X / Confirmed Refreshments For Purchase 02:40
Virgin Atlantic
VS 449 / 28OCT London Heathrow - Johannesburg JNB 22:30 11:30 Terminal 3 1PC
A / Confirmed 11:00
Ticket Number: 117 - 2532530332
"""

_SAS_PDF_AF_BODY = """\
Electronic Ticket Itinerary and Receipt
Ms Barbara Caroline Kogus Date of Issue: 09SEP25
Booking Reference: KI4K6A IATA Number: 80494912
Flight/Date Route Departure Arrival Latest Flight Baggage
Class/Status Meal Check-in Duration Allowance
Air France
AF 871 / 12NOV Cape Town CPT - Paris CDG 07:55 19:15 07:15 1PC
X / Confirmed Meal (Non-Specific) 12:20
Air France
AF 1462 / 12NOV Paris CDG - Stockholm ARN 21:00 23:40 20:20 Terminal 2F 1PC
X / Confirmed Snack Or Brunch 02:40
Ticket Number: 117 - 2536718272
"""


def _mock_resolve_airport(text):
    """Mock airport resolver for tests (no DB needed)."""
    _MAP = {
        'stockholm arlanda': 'ARN', 'arlanda': 'ARN', 'stockholm': 'ARN',
        'london heathrow': 'LHR', 'heathrow': 'LHR', 'london': 'LHR',
        'cape town': 'CPT',
    }
    import re
    # Check for explicit IATA code at the end
    m = re.search(r'\b([A-Z]{3})$', text)
    if m:
        return m.group(1)
    return _MAP.get(text.lower().strip(), '')


class TestSASPDFTabularExtraction(TestCase):
    """Format 2: Electronic Ticket PDF tabular format."""

    def setUp(self):
        self._patcher = patch(
            'flights.parsers._resolve_sas_airport',
            side_effect=_mock_resolve_airport,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_extracts_two_legs(self):
        msg = EmailMessage(
            message_id='sas-pdf-tab-1',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket Itinerary and Receipt from SAS - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)

    def test_first_leg_sk533(self):
        msg = EmailMessage(
            message_id='sas-pdf-tab-2',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[0]['flight_number'], 'SK533')
        self.assertEqual(flights[0]['departure_airport'], 'ARN')
        self.assertEqual(flights[0]['arrival_airport'], 'LHR')
        self.assertEqual(flights[0]['departure_datetime'].hour, 18)
        self.assertEqual(flights[0]['departure_datetime'].minute, 15)
        self.assertEqual(flights[0]['arrival_datetime'].hour, 19)
        self.assertEqual(flights[0]['arrival_datetime'].minute, 55)

    def test_second_leg_vs449(self):
        msg = EmailMessage(
            message_id='sas-pdf-tab-3',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[1]['flight_number'], 'VS449')
        self.assertEqual(flights[1]['departure_airport'], 'LHR')
        self.assertEqual(flights[1]['arrival_airport'], 'JNB')
        # VS 449 departs 22:30, arrives 11:30 next day (overnight)
        self.assertEqual(flights[1]['departure_datetime'].day, 28)
        self.assertEqual(flights[1]['arrival_datetime'].day, 29)

    def test_booking_reference(self):
        msg = EmailMessage(
            message_id='sas-pdf-tab-4',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'WD7WYD')

    def test_terminal_extraction(self):
        msg = EmailMessage(
            message_id='sas-pdf-tab-5',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[0]['departure_terminal'], '5')
        self.assertEqual(flights[1]['departure_terminal'], '3')

    def test_passenger_name(self):
        msg = EmailMessage(
            message_id='sas-pdf-tab-6',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertIn('Thiago', flights[0]['passenger_name'])

    def test_date_inferred_from_email_year(self):
        """28OCT has no year — infer from email date (2025)."""
        msg = EmailMessage(
            message_id='sas-pdf-tab-7',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference WD7WYD',
            body=_SAS_PDF_TABULAR_BODY,
            date=datetime(2025, 5, 15, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[0]['departure_datetime'].year, 2025)
        self.assertEqual(flights[0]['departure_datetime'].month, 10)
        self.assertEqual(flights[0]['departure_datetime'].day, 28)


class TestSASPDFAirFranceCodeshare(TestCase):
    """PDF with Air France codeshare flights (AF prefix)."""

    def setUp(self):
        self._patcher = patch(
            'flights.parsers._resolve_sas_airport',
            side_effect=_mock_resolve_airport,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_extracts_af_flights(self):
        msg = EmailMessage(
            message_id='sas-pdf-af-1',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference KI4K6A',
            body=_SAS_PDF_AF_BODY,
            date=datetime(2025, 9, 9, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)

    def test_first_leg_af871(self):
        msg = EmailMessage(
            message_id='sas-pdf-af-2',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference KI4K6A',
            body=_SAS_PDF_AF_BODY,
            date=datetime(2025, 9, 9, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[0]['flight_number'], 'AF871')
        self.assertEqual(flights[0]['departure_airport'], 'CPT')
        self.assertEqual(flights[0]['arrival_airport'], 'CDG')

    def test_second_leg_af1462(self):
        msg = EmailMessage(
            message_id='sas-pdf-af-3',
            sender='no-reply@flysas.com',
            subject='Electronic Ticket - Booking reference KI4K6A',
            body=_SAS_PDF_AF_BODY,
            date=datetime(2025, 9, 9, tzinfo=timezone.utc),
            html_body=None,
        )
        flights = extract_flights_from_email(msg, _SAS_RULE)
        self.assertEqual(flights[1]['flight_number'], 'AF1462')
        self.assertEqual(flights[1]['departure_airport'], 'CDG')
        self.assertEqual(flights[1]['arrival_airport'], 'ARN')
