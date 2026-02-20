"""
Tests for Azul Brazilian Airlines email parsing.

Azul emails come from noreply@voeazul-news.com.br.
After html_to_text() each flight leg has a distinctive structure:

    GRU
    São Paulo
    02/03 • 13:20
    Voo 4849
    CNF
    Belo Horizonte
    02/03 • 14:35

The date format is DD/MM (no year); the parser infers the year from the
email's received date.  The flight number is digits-only; the parser
prepends the 'AD' airline code.
"""
from datetime import datetime, timezone
from django.test import TestCase

from flights.builtin_rules import get_builtin_rules
from flights.email_connector import EmailMessage
from flights.parsers import match_rule_to_email, extract_flights_from_email

_AZUL_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'AD')

_AZUL_BODY = """
Seu itinerário

Código de reserva: ZX3344

GRU
São Paulo
02/03 • 13:20
Voo 4849
CNF
Belo Horizonte
02/03 • 14:35

CNF
Belo Horizonte
05/03 • 10:00
Voo 4852
GRU
São Paulo
05/03 • 11:15
"""


class TestAzulRuleMatching(TestCase):
    """Sender / subject matching for Azul emails."""

    def _make_email(self, sender, subject=None):
        return EmailMessage(
            message_id='azul-test-1',
            sender=sender,
            subject=subject or 'Confirmação de bilhete eletrônico',
            body=_AZUL_BODY,
            date=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )

    def test_matches_voeazul_news(self):
        msg = self._make_email('noreply@voeazul-news.com.br')
        rule = match_rule_to_email(msg, [_AZUL_RULE])
        self.assertIsNotNone(rule)
        self.assertEqual(rule.airline_code, 'AD')

    def test_matches_azullinhasaereas(self):
        msg = self._make_email('contato@azullinhasaereas.com')
        rule = match_rule_to_email(msg, [_AZUL_RULE])
        self.assertIsNotNone(rule)

    def test_does_not_match_unrelated_sender(self):
        msg = self._make_email('ofertas@tam.com.br')
        rule = match_rule_to_email(msg, [_AZUL_RULE])
        self.assertIsNone(rule)


class TestAzulFlightExtraction(TestCase):
    """Flight data extraction for a realistic Azul itinerary."""

    def setUp(self):
        # Email received in Feb 2026; flights are in March 2026
        self.msg = EmailMessage(
            message_id='azul-ext-1',
            sender='noreply@voeazul-news.com.br',
            subject='Confirmação de bilhete eletrônico',
            body=_AZUL_BODY,
            date=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(len(flights), 2)

    def test_outbound_airports(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'GRU')
        self.assertEqual(flights[0]['arrival_airport'], 'CNF')

    def test_flight_number_has_ad_prefix(self):
        """Parser should prefix bare digits with the 'AD' airline code."""
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertTrue(flights[0]['flight_number'].startswith('AD'))
        self.assertIn('4849', flights[0]['flight_number'])

    def test_year_inferred_from_email_date(self):
        """Date in email body is 02/03 (no year); year must be inferred as 2026."""
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.year, 2026)
        self.assertEqual(dep.month, 3)
        self.assertEqual(dep.day, 2)

    def test_departure_time(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.hour, 13)
        self.assertEqual(dep.minute, 20)

    def test_return_leg(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(flights[1]['departure_airport'], 'CNF')
        self.assertEqual(flights[1]['arrival_airport'], 'GRU')
        self.assertIn('4852', flights[1]['flight_number'])

    def test_airline_metadata(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(flights[0]['airline_name'], 'Azul Brazilian Airlines')
        self.assertEqual(flights[0]['airline_code'], 'AD')
