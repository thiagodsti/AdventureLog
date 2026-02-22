"""
Tests for BeautifulSoup-based flight email extractors.

These tests use realistic HTML email bodies to verify that the BS4 extractors
can parse flight data from the HTML structure. Each airline has its own set
of tests with HTML that mirrors real airline confirmation emails.
"""
from datetime import datetime, timezone
from django.test import TestCase

from flights.builtin_rules import get_builtin_rules
from flights.email_connector import EmailMessage
from flights.parsers import extract_flights_from_email

_LATAM_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'LA')
_SAS_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'SK')
_LH_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'LH')
_AZUL_RULE = next(r for r in get_builtin_rules() if r.airline_code == 'AD')


# ---------------------------------------------------------------------------
# HTML email fixtures
# ---------------------------------------------------------------------------

_LATAM_HTML = """\
<html><body>
<h2>Seu itinerário de viagem</h2>
<p>Olá <b>João Silva</b></p>
<p>Código de reserva: <strong>ABC123</strong></p>

<h3>Trecho 1</h3>
<table>
  <tr>
    <td>16 de mar. de 2026</td>
    <td>08:30</td>
    <td>São Paulo <strong>(GRU)</strong></td>
    <td>LA 1234</td>
  </tr>
  <tr>
    <td>16 de mar. de 2026</td>
    <td>12:45</td>
    <td>Santiago <strong>(SCL)</strong></td>
  </tr>
</table>

<h3>Trecho 2</h3>
<table>
  <tr>
    <td>20 de mar. de 2026</td>
    <td>14:00</td>
    <td>Santiago <strong>(SCL)</strong></td>
    <td>LA 1235</td>
  </tr>
  <tr>
    <td>20 de mar. de 2026</td>
    <td>18:15</td>
    <td>São Paulo <strong>(GRU)</strong></td>
  </tr>
</table>
</body></html>
"""

_SAS_HTML = """\
<html><body>
<h1>Your booking confirmation</h1>
<p>Booking: <strong>XY9012</strong></p>

<div class="flight-leg">
  <h3>07 Aug 2026</h3>
  <p>Stockholm <strong>ARN</strong> – Copenhagen <strong>CPH</strong></p>
  <p>07:30 – 09:10 (1h 40m)</p>
  <p>SK 1829 | Operated by SAS</p>
</div>

<div class="flight-leg">
  <h3>10 Aug 2026</h3>
  <p>Copenhagen <strong>CPH</strong> – Stockholm <strong>ARN</strong></p>
  <p>18:00 – 19:45 (1h 45m)</p>
  <p>SK 1834 | Operated by SAS</p>
</div>
</body></html>
"""

_LH_HTML = """\
<html><body>
<h1>Ihre Buchungsbestätigung</h1>
<p>Buchungscode: <strong>DE5678</strong></p>

<table class="itinerary">
  <tr>
    <td>15 Mar 2026</td>
    <td>10:00</td>
    <td>Frankfurt <strong>(FRA)</strong></td>
    <td>LH 1234</td>
  </tr>
  <tr>
    <td>15 Mar 2026</td>
    <td>11:30</td>
    <td>Munich <strong>(MUC)</strong></td>
  </tr>
</table>

<table class="itinerary">
  <tr>
    <td>18 Mar 2026</td>
    <td>14:15</td>
    <td>Munich <strong>(MUC)</strong></td>
    <td>LH 1235</td>
  </tr>
  <tr>
    <td>18 Mar 2026</td>
    <td>15:30</td>
    <td>Frankfurt <strong>(FRA)</strong></td>
  </tr>
</table>
</body></html>
"""

_AZUL_HTML = """\
<html><body>
<h2>Seu itinerário</h2>
<p>Código de reserva: <strong>ZX3344</strong></p>

<table>
  <tr><td><strong>GRU</strong></td></tr>
  <tr><td>São Paulo</td></tr>
  <tr><td>02/03 • 13:20</td></tr>
  <tr><td>Voo 4849</td></tr>
  <tr><td><strong>CNF</strong></td></tr>
  <tr><td>Belo Horizonte</td></tr>
  <tr><td>02/03 • 14:35</td></tr>
</table>

<table>
  <tr><td><strong>CNF</strong></td></tr>
  <tr><td>Belo Horizonte</td></tr>
  <tr><td>05/03 • 10:00</td></tr>
  <tr><td>Voo 4852</td></tr>
  <tr><td><strong>GRU</strong></td></tr>
  <tr><td>São Paulo</td></tr>
  <tr><td>05/03 • 11:15</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# LATAM BS4 tests
# ---------------------------------------------------------------------------

class TestLATAMBS4Extraction(TestCase):
    """Test BS4 extraction for LATAM Airlines HTML emails."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='latam-bs4-1',
            sender='info@info.latam.com',
            subject='Confirmação de compra - seu itinerário',
            body='',  # empty — forces BS4 path via html_body
            date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            html_body=_LATAM_HTML,
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(len(flights), 2)

    def test_first_leg_airports(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'GRU')
        self.assertEqual(flights[0]['arrival_airport'], 'SCL')

    def test_first_leg_flight_number(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertIn('LA', flights[0]['flight_number'])
        self.assertIn('1234', flights[0]['flight_number'])

    def test_first_leg_datetime(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.year, 2026)
        self.assertEqual(dep.month, 3)
        self.assertEqual(dep.day, 16)
        self.assertEqual(dep.hour, 8)
        self.assertEqual(dep.minute, 30)

    def test_return_leg_airports(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(flights[1]['departure_airport'], 'SCL')
        self.assertEqual(flights[1]['arrival_airport'], 'GRU')

    def test_booking_reference(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'ABC123')
        self.assertEqual(flights[1]['booking_reference'], 'ABC123')

    def test_airline_metadata(self):
        flights = extract_flights_from_email(self.msg, _LATAM_RULE)
        self.assertEqual(flights[0]['airline_name'], 'LATAM Airlines')
        self.assertEqual(flights[0]['airline_code'], 'LA')


# ---------------------------------------------------------------------------
# SAS BS4 tests
# ---------------------------------------------------------------------------

class TestSASBS4Extraction(TestCase):
    """Test BS4 extraction for SAS HTML emails."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='sas-bs4-1',
            sender='no-reply@flysas.com',
            subject='Booking confirmation SK1829',
            body='',
            date=datetime(2026, 7, 1, tzinfo=timezone.utc),
            html_body=_SAS_HTML,
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(len(flights), 2)

    def test_outbound_airports(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'ARN')
        self.assertEqual(flights[0]['arrival_airport'], 'CPH')

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

    def test_outbound_date(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        dep = flights[0]['departure_datetime']
        self.assertEqual(dep.year, 2026)
        self.assertEqual(dep.month, 8)
        self.assertEqual(dep.day, 7)

    def test_return_leg(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[1]['departure_airport'], 'CPH')
        self.assertEqual(flights[1]['arrival_airport'], 'ARN')

    def test_booking_reference(self):
        flights = extract_flights_from_email(self.msg, _SAS_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'XY9012')


# ---------------------------------------------------------------------------
# Lufthansa BS4 tests
# ---------------------------------------------------------------------------

class TestLufthansaBS4Extraction(TestCase):
    """Test BS4 extraction for Lufthansa HTML emails."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='lh-bs4-1',
            sender='info@lufthansa.com',
            subject='Ihre Buchungsbestätigung',
            body='',
            date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            html_body=_LH_HTML,
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
        self.assertIn('1234', flights[0]['flight_number'])

    def test_outbound_datetime(self):
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

    def test_booking_reference(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'DE5678')

    def test_airline_metadata(self):
        flights = extract_flights_from_email(self.msg, _LH_RULE)
        self.assertEqual(flights[0]['airline_name'], 'Lufthansa')
        self.assertEqual(flights[0]['airline_code'], 'LH')


# ---------------------------------------------------------------------------
# Azul BS4 tests
# ---------------------------------------------------------------------------

class TestAzulBS4Extraction(TestCase):
    """Test BS4 extraction for Azul Brazilian Airlines HTML emails."""

    def setUp(self):
        self.msg = EmailMessage(
            message_id='azul-bs4-1',
            sender='noreply@voeazul-news.com.br',
            subject='Confirmação de bilhete eletrônico',
            body='',
            date=datetime(2026, 2, 15, tzinfo=timezone.utc),
            html_body=_AZUL_HTML,
        )

    def test_extracts_two_legs(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(len(flights), 2)

    def test_outbound_airports(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(flights[0]['departure_airport'], 'GRU')
        self.assertEqual(flights[0]['arrival_airport'], 'CNF')

    def test_flight_number_has_ad_prefix(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertTrue(flights[0]['flight_number'].startswith('AD'))
        self.assertIn('4849', flights[0]['flight_number'])

    def test_year_inferred(self):
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

    def test_booking_reference(self):
        flights = extract_flights_from_email(self.msg, _AZUL_RULE)
        self.assertEqual(flights[0]['booking_reference'], 'ZX3344')


# ---------------------------------------------------------------------------
# Fallback tests — ensure regex still works when html_body is None
# ---------------------------------------------------------------------------

class TestRegexFallback(TestCase):
    """Verify that when html_body is None, the regex fallback is used."""

    def test_latam_regex_fallback(self):
        """Plain text body with no html_body should use regex extraction."""
        body = """\
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
        msg = EmailMessage(
            message_id='fallback-1',
            sender='info@info.latam.com',
            subject='Confirmação de compra - seu itinerário',
            body=body,
            date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            html_body=None,  # no HTML — forces regex fallback
        )
        flights = extract_flights_from_email(msg, _LATAM_RULE)
        self.assertEqual(len(flights), 2)
        self.assertEqual(flights[0]['departure_airport'], 'GRU')

    def test_bs4_returns_empty_for_invalid_html(self):
        """BS4 extractor should return [] for garbage HTML, triggering regex fallback."""
        from flights.bs4_extractors import extract_with_bs4
        result = extract_with_bs4('<html><body>nothing useful here</body></html>', _LATAM_RULE, None)
        self.assertEqual(result, [])
