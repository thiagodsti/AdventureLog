"""
Tests for Lufthansa email parsing.

Lufthansa emails come from info@lufthansa.com (or @lh.com).
After html_to_text() each flight leg looks like:

    15 Mar 2026  10:00  Frankfurt (FRA)  LH 1234
    15 Mar 2026  11:30  Munich    (MUC)
"""
from datetime import datetime, timezone
from django.test import TestCase

from flights.builtin_rules import get_builtin_rules
from flights.email_connector import EmailMessage
from flights.parsers import match_rule_to_email, extract_flights_from_email

_LH_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'LH')

_LH_BODY = """\
Ihre Buchungsbestätigung

Buchungscode: DE5678

15 Mar 2026  10:00  Frankfurt (FRA)  LH 1234
15 Mar 2026  11:30  Munich    (MUC)

18 Mar 2026  14:15  Munich    (MUC)  LH 1235
18 Mar 2026  15:30  Frankfurt (FRA)
"""


class TestLufthansaRuleMatching(TestCase):
    """Sender / subject matching for Lufthansa emails."""

    def _make_email(self, sender, subject=None):
        return EmailMessage(
            message_id='lh-test-1',
            sender=sender,
            subject=subject or 'Ihre Buchungsbestätigung',
            body=_LH_BODY,
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )

    def test_matches_lufthansa_com(self):
        msg = self._make_email('info@lufthansa.com')
        rule = match_rule_to_email(msg, [_LH_RULE])
        self.assertIsNotNone(rule)
        self.assertEqual(rule.airline_code, 'LH')

    def test_matches_lh_com(self):
        msg = self._make_email('noreply@lh.com')
        rule = match_rule_to_email(msg, [_LH_RULE])
        self.assertIsNotNone(rule)

    def test_does_not_match_unrelated_sender(self):
        msg = self._make_email('newsletter@swiss.com')
        rule = match_rule_to_email(msg, [_LH_RULE])
        self.assertIsNone(rule)

    def test_does_not_match_wrong_subject(self):
        msg = self._make_email('info@lufthansa.com', subject='Ihre Meilen-Übersicht')
        rule = match_rule_to_email(msg, [_LH_RULE])
        self.assertIsNone(rule)


class TestLufthansaFlightExtraction(TestCase):
    """Flight data extraction for a realistic Lufthansa itinerary."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='lh-ext-1',
            sender='info@lufthansa.com',
            subject='Ihre Buchungsbestätigung',
            body=_LH_BODY,
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertEqual(len(flights), 2)

    def test_outbound_airports(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'FRA')
        self.assertEqual(flights[0]['arrival_airport'], 'MUC')

    def test_outbound_flight_number(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertIn('LH', flights[0]['flight_number'])

    def test_outbound_departure_datetime(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.year, 2026)
        self.assertEqual(dep.month, 3)
        self.assertEqual(dep.day, 15)
        self.assertEqual(dep.hour, 10)
        self.assertEqual(dep.minute, 0)

    def test_return_leg(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertEqual(flights[1]['departure_airport'], 'MUC')
        self.assertEqual(flights[1]['arrival_airport'], 'FRA')

    def test_airline_metadata(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertEqual(flights[0]['airline_name'], 'Lufthansa')
        self.assertEqual(flights[0]['airline_code'], 'LH')
