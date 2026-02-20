"""
Tests for SAS Scandinavian Airlines email parsing.

SAS emails come from no-reply@flysas.com (or sas.se / sas.dk / sas.no).
After html_to_text() each flight leg looks like:

    07 Aug 2026
    Stockholm ARN – Copenhagen CPH
    07:30 – 09:10 (1h 40m)
    SK 1829 | Operated by SAS

The departure_date is NOT captured by the body regex; the parser infers it
from the closest preceding date found in the body.
"""
from datetime import datetime, timezone
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
