"""
Tests for LATAM Airlines email parsing.

LATAM emails come from info@info.latam.com (or similar @latam.com addresses).
The HTML itinerary, after html_to_text(), has one block per flight leg:

    16 de mar. de 2026  08:30  São Paulo (GRU)  LA 1234
    16 de mar. de 2026  12:45  Santiago (SCL)

The rule captures: departure_date, departure_time, departure_airport,
flight_number, arrival_date, arrival_time, arrival_airport.
"""
from datetime import datetime, timezone
from django.test import TestCase

from flights.builtin_rules import get_builtin_rules
from flights.email_connector import EmailMessage
from flights.parsers import match_rule_to_email, extract_flights_from_email

# Grab the LATAM rule from code (no DB required)
_LATAM_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'LA')

# Realistic itinerary body (after html_to_text conversion)
_LATAM_BODY = """\
Seu itinerário de viagem

Lista de passageiros
- João Silva

Código de reserva: ABC123

Trecho 1
16 de mar. de 2026  08:30  São Paulo  (GRU)  LA 1234
16 de mar. de 2026  12:45  Santiago   (SCL)

Trecho 2
20 de mar. de 2026  14:00  Santiago   (SCL)  LA 1235
20 de mar. de 2026  18:15  São Paulo  (GRU)
"""


class TestLATAMRuleMatching(TestCase):
    """Sender / subject matching for LATAM emails."""

    def _make_email(self, sender, subject=None, body=None):
        return EmailMessage(
            message_id='latam-test-1',
            sender=sender,
            subject=subject or 'Confirmação de compra - seu itinerário',
            body=body or _LATAM_BODY,
            date=datetime(2026, 1, 10, tzinfo=timezone.utc),
        )

    def test_matches_latam_com_sender(self):
        msg = self._make_email('info@info.latam.com')
        rule = match_rule_to_email(msg, [_LATAM_RULE])
        self.assertIsNotNone(rule)
        self.assertEqual(rule.airline_code, 'LA')

    def test_matches_latamairlines_com_sender(self):
        msg = self._make_email('noreply@latamairlines.com')
        rule = match_rule_to_email(msg, [_LATAM_RULE])
        self.assertIsNotNone(rule)

    def test_does_not_match_unrelated_sender(self):
        msg = self._make_email('deals@amazon.com')
        rule = match_rule_to_email(msg, [_LATAM_RULE])
        self.assertIsNone(rule)

    def test_does_not_match_wrong_subject(self):
        # subject_pattern requires itinerary/confirm/reserv/… keywords
        msg = self._make_email(
            'info@latam.com',
            subject='Your LATAM newsletter',
        )
        rule = match_rule_to_email(msg, [_LATAM_RULE])
        self.assertIsNone(rule)


class TestLATAMFlightExtraction(TestCase):
    """Flight data extraction for a realistic LATAM itinerary."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='latam-ext-1',
            sender='info@info.latam.com',
            subject='Confirmação de compra - seu itinerário',
            body=_LATAM_BODY,
            date=datetime(2026, 1, 10, tzinfo=timezone.utc),
        )

    def test_extracts_two_flight_legs(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(len(flights), 2)

    def test_first_leg_airports(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        leg1 = flights[0]
        self.assertEqual(leg1['departure_airport'], 'GRU')
        self.assertEqual(leg1['arrival_airport'], 'SCL')

    def test_first_leg_flight_number(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertIn('LA', flights[0]['flight_number'])

    def test_first_leg_departure_datetime(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.year, 2026)
        self.assertEqual(dep.month, 3)
        self.assertEqual(dep.day, 16)
        self.assertEqual(dep.hour, 8)
        self.assertEqual(dep.minute, 30)

    def test_return_leg_airports(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        leg2 = flights[1]
        self.assertEqual(leg2['departure_airport'], 'SCL')
        self.assertEqual(leg2['arrival_airport'], 'GRU')

    def test_shared_booking_reference(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'ABC123')
        self.assertEqual(flights[1]['booking_reference'], 'ABC123')

    def test_passenger_name_extracted(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertIn('João', flights[0]['passenger_name'])

    def test_airline_metadata(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(flights[0]['airline_name'], 'LATAM Airlines')
        self.assertEqual(flights[0]['airline_code'], 'LA')
