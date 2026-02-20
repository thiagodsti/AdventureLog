import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

User = get_user_model()


def _find_trip_destination(flights, origin: str) -> str:
    """
    Determine the main destination of a trip.

    For a one-way trip (ARN → FRA → GRU), returns the last arrival (GRU).
    For a round-trip (ARN → FRA → GRU → ... → FRA → ARN), returns the
    first "real destination" — the arrival airport of the first flight
    followed by a stay of 24 h or more (i.e. not a short connection).
    Falls back to the midpoint flight's arrival airport.
    """
    from datetime import timedelta as _td

    if not flights:
        return origin

    last_arrival = flights[-1].arrival_airport

    # One-way (possibly with connections): destination is the last arrival.
    if last_arrival != origin:
        return last_arrival

    # Round-trip: find the first real destination stay (gap >= 24 h).
    _CONNECTION_THRESHOLD = _td(hours=24)
    for i in range(len(flights) - 1):
        gap = flights[i + 1].departure_datetime - flights[i].arrival_datetime
        if gap >= _CONNECTION_THRESHOLD and flights[i].arrival_airport != origin:
            return flights[i].arrival_airport

    # Fallback: use the midpoint flight's arrival.
    mid = (len(flights) - 1) // 2
    arr = flights[mid].arrival_airport
    return arr if arr != origin else flights[0].arrival_airport


class FlightGroup(models.Model):
    """
    Groups related flights into a trip (like TripIt).
    E.g. all flights for a round trip to Brazil are in one group.
    """

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flight_groups')
    name = models.CharField(max_length=255, help_text="Trip name, e.g. 'Brazil Trip 2026'")
    description = models.TextField(blank=True, default='')
    is_auto_generated = models.BooleanField(
        default=False,
        help_text="True if this group was auto-created from booking references"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.flights.count()} flights)"

    @property
    def start_date(self):
        first = self.flights.order_by('departure_datetime').first()
        return first.departure_datetime if first else None

    @property
    def end_date(self):
        last = self.flights.order_by('-arrival_datetime').first()
        return last.arrival_datetime if last else None

    @property
    def origin(self):
        first = self.flights.order_by('departure_datetime').first()
        return first.departure_airport if first else ''

    @property
    def destination(self):
        """Farthest point from origin (the destination city)."""
        flights = list(self.flights.order_by('departure_datetime'))
        if not flights:
            return ''
        origin = flights[0].departure_airport
        return _find_trip_destination(flights, origin)


class EmailAccount(models.Model):
    """
    Represents a connected email account used to scan for flight emails.
    Supports IMAP-based providers (Gmail, Outlook, etc.) and Tuta (via API).
    """

    PROVIDER_CHOICES = [
        ('gmail', 'Gmail (IMAP/OAuth)'),
        ('outlook', 'Outlook (IMAP)'),
        ('imap', 'Generic IMAP'),
        ('tuta', 'Tuta (Tutanota)'),
    ]

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_accounts')
    name = models.CharField(max_length=255, help_text="Friendly name for this email account")
    email_address = models.EmailField(help_text="Email address used to connect")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='imap')

    # IMAP connection settings (for gmail, outlook, generic imap)
    imap_host = models.CharField(max_length=255, blank=True, default='')
    imap_port = models.PositiveIntegerField(default=993)
    imap_username = models.CharField(max_length=255, blank=True, default='')
    imap_password = models.CharField(
        max_length=1024, blank=True, default='',
        help_text="App password or OAuth token for IMAP login"
    )
    use_ssl = models.BooleanField(default=True)

    # Tuta connection settings
    tuta_user = models.CharField(max_length=255, blank=True, default='')
    tuta_password = models.CharField(max_length=1024, blank=True, default='')

    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_rules_version = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Tracks which RULES_VERSION was last used for syncing"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('user', 'email_address')]

    def __str__(self):
        return f"{self.name} ({self.email_address})"


class AirlineRule(models.Model):
    """
    Defines parsing rules for a specific airline's confirmation emails.
    Rules are regex-based patterns that extract flight information from email body/subject.
    Users can create custom rules or use built-in ones.
    """

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='airline_rules',
        null=True, blank=True,
        help_text="Null for system-wide built-in rules"
    )
    airline_name = models.CharField(max_length=255, help_text="Name of the airline")
    airline_code = models.CharField(
        max_length=10, blank=True, default='',
        help_text="IATA airline code (e.g. LA, SK, LH)"
    )

    # Sender matching: regex applied to From header
    sender_pattern = models.TextField(
        help_text="Regex pattern to match the email sender (From header)"
    )
    # Subject matching: regex applied to Subject header
    subject_pattern = models.TextField(
        blank=True, default='',
        help_text="Optional regex for matching email subject"
    )

    # Body extraction patterns (named groups used to extract fields)
    # Named groups expected: flight_number, departure_airport, arrival_airport,
    # departure_date, departure_time, arrival_date, arrival_time,
    # booking_reference, passenger_name, seat, cabin_class
    body_pattern = models.TextField(
        help_text="Regex pattern with named groups applied to email body (plain text or HTML stripped)"
    )

    # Date format strings for parsing extracted date/time strings
    date_format = models.CharField(
        max_length=64, default='%d %b %Y',
        help_text="Python strptime format for dates, e.g. '%%d %%b %%Y'"
    )
    time_format = models.CharField(
        max_length=64, default='%H:%M',
        help_text="Python strptime format for times, e.g. '%%H:%%M'"
    )

    is_active = models.BooleanField(default=True)
    is_builtin = models.BooleanField(
        default=False,
        help_text="Built-in rules ship with the system"
    )
    priority = models.IntegerField(
        default=0,
        help_text="Higher priority rules are tried first"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'airline_name']

    def __str__(self):
        owner = "system" if self.user is None else self.user.username
        return f"[{owner}] {self.airline_name} ({self.airline_code})"


class Flight(models.Model):
    """
    A parsed flight extracted from an email.
    """

    CABIN_CLASS_CHOICES = [
        ('economy', 'Economy'),
        ('premium_economy', 'Premium Economy'),
        ('business', 'Business'),
        ('first', 'First'),
    ]

    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flights')

    # Group / trip association
    flight_group = models.ForeignKey(
        FlightGroup, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='flights',
        help_text="Trip/group this flight belongs to"
    )

    # Flight details
    airline_name = models.CharField(max_length=255, blank=True, default='')
    airline_code = models.CharField(max_length=10, blank=True, default='')
    flight_number = models.CharField(max_length=20)
    booking_reference = models.CharField(max_length=50, blank=True, default='')

    # Departure
    departure_airport = models.CharField(max_length=10, help_text="IATA airport code")
    departure_city = models.CharField(max_length=255, blank=True, default='')
    departure_datetime = models.DateTimeField()
    departure_terminal = models.CharField(max_length=20, blank=True, default='')
    departure_gate = models.CharField(max_length=20, blank=True, default='')

    # Arrival
    arrival_airport = models.CharField(max_length=10, help_text="IATA airport code")
    arrival_city = models.CharField(max_length=255, blank=True, default='')
    arrival_datetime = models.DateTimeField()
    arrival_terminal = models.CharField(max_length=20, blank=True, default='')
    arrival_gate = models.CharField(max_length=20, blank=True, default='')

    # Passenger / seat
    passenger_name = models.CharField(max_length=255, blank=True, default='')
    seat = models.CharField(max_length=10, blank=True, default='')
    cabin_class = models.CharField(
        max_length=20, choices=CABIN_CLASS_CHOICES,
        blank=True, default=''
    )

    # Status
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='upcoming'
    )
    duration_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1)]
    )

    # Provenance
    email_account = models.ForeignKey(
        EmailAccount, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='flights'
    )
    airline_rule = models.ForeignKey(
        AirlineRule, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    email_subject = models.CharField(max_length=512, blank=True, default='')
    email_date = models.DateTimeField(null=True, blank=True)
    email_message_id = models.CharField(
        max_length=512, blank=True, default='',
        help_text="Message-ID header or UID for deduplication"
    )
    is_manually_added = models.BooleanField(default=False)

    # Metadata
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['departure_datetime']
        unique_together = [('user', 'email_message_id')]

    def __str__(self):
        return f"{self.flight_number}: {self.departure_airport} → {self.arrival_airport} ({self.departure_datetime.date()})"

    def save(self, *args, **kwargs):
        if self.departure_datetime and self.arrival_datetime and not self.duration_minutes:
            delta = self.arrival_datetime - self.departure_datetime
            self.duration_minutes = max(int(delta.total_seconds() / 60), 1)
            # Auto-compute status based on arrival time; never override a manual 'cancelled'
        if self.status != 'cancelled' and self.arrival_datetime:
            from django.utils import timezone as _tz
            self.status = 'completed' if self.arrival_datetime < _tz.now() else 'upcoming'
        super().save(*args, **kwargs)
