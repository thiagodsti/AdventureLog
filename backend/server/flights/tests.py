from django.test import TestCase
from django.contrib.auth import get_user_model
from flights.models import EmailAccount, AirlineRule, Flight
from flights.email_connector import EmailMessage
from flights.parsers import match_rule_to_email, extract_flights_from_email

User = get_user_model()


class AirlineRuleMatchTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.latam_rule = AirlineRule.objects.create(
            airline_name='LATAM Airlines',
            airline_code='LA',
            sender_pattern=r'latam\.com',
            subject_pattern=r'confirm',
            body_pattern=(
                r'flight[:\s]*(?P<flight_number>LA\s*\d{3,5})\s*'
                r'.*?from[:\s]*(?P<departure_airport>[A-Z]{3})'
                r'.*?to[:\s]*(?P<arrival_airport>[A-Z]{3})'
                r'.*?date[:\s]*(?P<departure_date>\d{1,2}\s+\w{3}\s+\d{4})'
                r'.*?depart[:\s]*(?P<departure_time>\d{1,2}:\d{2})'
                r'.*?arriv[:\s]*(?P<arrival_time>\d{1,2}:\d{2})'
            ),
            date_format='%d %b %Y',
            time_format='%H:%M',
            is_builtin=True,
            is_active=True,
            priority=10,
        )

    def test_rule_matches_sender(self):
        email_msg = EmailMessage(
            message_id='test-1',
            sender='noreply@latam.com',
            subject='Your booking confirmation',
            body='flight: LA 1234 from: GRU to: SCL date: 15 Mar 2026 depart: 08:30 arriv: 12:45',
            date=None,
        )
        rule = match_rule_to_email(email_msg, [self.latam_rule])
        self.assertIsNotNone(rule)
        self.assertEqual(rule.airline_code, 'LA')

    def test_rule_does_not_match_wrong_sender(self):
        email_msg = EmailMessage(
            message_id='test-2',
            sender='noreply@amazon.com',
            subject='Your order confirmation',
            body='Some random email body',
            date=None,
        )
        rule = match_rule_to_email(email_msg, [self.latam_rule])
        self.assertIsNone(rule)

    def test_extract_flight_from_email(self):
        email_msg = EmailMessage(
            message_id='test-3',
            sender='noreply@latam.com',
            subject='Your booking confirmation',
            body='flight: LA 1234 from: GRU to: SCL date: 15 Mar 2026 depart: 08:30 arriv: 12:45',
            date=None,
        )
        flights = extract_flights_from_email(email_msg, self.latam_rule)
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0]['flight_number'], 'LA 1234')
        self.assertEqual(flights[0]['departure_airport'], 'GRU')
        self.assertEqual(flights[0]['arrival_airport'], 'SCL')
