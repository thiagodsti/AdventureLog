from rest_framework import serializers
from main.utils import CustomModelSerializer
from .models import EmailAccount, AirlineRule, Flight, FlightGroup


class EmailAccountSerializer(CustomModelSerializer):
    flight_count = serializers.SerializerMethodField()

    class Meta:
        model = EmailAccount
        fields = [
            'id', 'name', 'email_address', 'provider',
            'imap_host', 'imap_port', 'imap_username', 'use_ssl',
            'is_active', 'last_synced_at',
            'created_at', 'updated_at', 'flight_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_synced_at', 'flight_count']

    def get_flight_count(self, obj):
        return obj.flights.count()

    def to_internal_value(self, data):
        """Accept password fields on write but never expose them on read."""
        return super().to_internal_value(data)


class EmailAccountWriteSerializer(CustomModelSerializer):
    """Separate serializer for create/update that accepts password fields."""

    class Meta:
        model = EmailAccount
        fields = [
            'id', 'name', 'email_address', 'provider',
            'imap_host', 'imap_port', 'imap_username', 'imap_password', 'use_ssl',
            'is_active',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'imap_password': {'write_only': True},
        }

    def validate(self, attrs):
        provider = attrs.get('provider', getattr(self.instance, 'provider', 'imap'))
        if provider in ('gmail', 'outlook', 'imap'):
            # For known providers, always force the correct IMAP host
            if provider == 'gmail':
                attrs['imap_host'] = 'imap.gmail.com'
            elif provider == 'outlook':
                attrs['imap_host'] = 'outlook.office365.com'
            elif not attrs.get('imap_host') and not getattr(self.instance, 'imap_host', ''):
                raise serializers.ValidationError(
                    {'imap_host': 'IMAP host is required for generic IMAP provider.'}
                )
            if not attrs.get('imap_password') and not getattr(self.instance, 'imap_password', ''):
                raise serializers.ValidationError(
                    {'imap_password': 'Password/App password is required.'}
                )
        return attrs


class AirlineRuleSerializer(CustomModelSerializer):
    class Meta:
        model = AirlineRule
        fields = [
            'id', 'airline_name', 'airline_code',
            'sender_pattern', 'subject_pattern', 'body_pattern',
            'date_format', 'time_format',
            'is_active', 'is_builtin', 'priority',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_builtin']


class FlightSerializer(CustomModelSerializer):
    class Meta:
        model = Flight
        fields = [
            'id', 'airline_name', 'airline_code', 'flight_number',
            'booking_reference',
            'departure_airport', 'departure_city', 'departure_datetime',
            'departure_terminal', 'departure_gate',
            'arrival_airport', 'arrival_city', 'arrival_datetime',
            'arrival_terminal', 'arrival_gate',
            'passenger_name', 'seat', 'cabin_class',
            'status', 'duration_minutes',
            'flight_group',
            'email_account', 'airline_rule', 'email_subject', 'email_date',
            'is_manually_added',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'email_account', 'airline_rule', 'email_subject', 'email_date',
        ]


class FlightWriteSerializer(CustomModelSerializer):
    """Used for manually creating/editing flights."""

    class Meta:
        model = Flight
        fields = [
            'id', 'airline_name', 'airline_code', 'flight_number',
            'booking_reference',
            'departure_airport', 'departure_city', 'departure_datetime',
            'departure_terminal', 'departure_gate',
            'arrival_airport', 'arrival_city', 'arrival_datetime',
            'arrival_terminal', 'arrival_gate',
            'passenger_name', 'seat', 'cabin_class',
            'status', 'duration_minutes',
            'flight_group',
            'notes',
        ]
        read_only_fields = ['id']


class FlightGroupFlightSerializer(CustomModelSerializer):
    """Lightweight flight serializer used when nesting inside FlightGroup."""

    class Meta:
        model = Flight
        fields = [
            'id', 'airline_name', 'airline_code', 'flight_number',
            'booking_reference',
            'departure_airport', 'departure_city', 'departure_datetime',
            'departure_terminal', 'departure_gate',
            'arrival_airport', 'arrival_city', 'arrival_datetime',
            'arrival_terminal', 'arrival_gate',
            'passenger_name', 'seat', 'cabin_class',
            'status', 'duration_minutes',
            'is_manually_added', 'notes',
        ]


class FlightGroupSerializer(CustomModelSerializer):
    flights = FlightGroupFlightSerializer(many=True, read_only=True)
    start_date = serializers.DateTimeField(read_only=True)
    end_date = serializers.DateTimeField(read_only=True)
    origin = serializers.CharField(read_only=True)
    destination = serializers.CharField(read_only=True)
    flight_count = serializers.SerializerMethodField()
    route_stops = serializers.SerializerMethodField()

    class Meta:
        model = FlightGroup
        fields = [
            'id', 'name', 'description', 'is_auto_generated',
            'flights', 'flight_count',
            'start_date', 'end_date', 'origin', 'destination',
            'route_stops',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_auto_generated']

    def get_flight_count(self, obj):
        return obj.flights.count()

    def get_route_stops(self, obj):
        """Return ordered list of airport codes representing the full route."""
        flights = list(obj.flights.order_by('departure_datetime'))
        if not flights:
            return []
        stops = [flights[0].departure_airport]
        for f in flights:
            if f.arrival_airport and f.arrival_airport != stops[-1]:
                stops.append(f.arrival_airport)
        return stops


class FlightGroupWriteSerializer(CustomModelSerializer):
    flight_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, write_only=True,
    )

    class Meta:
        model = FlightGroup
        fields = ['id', 'name', 'description', 'flight_ids']
        read_only_fields = ['id']

    def create(self, validated_data):
        flight_ids = validated_data.pop('flight_ids', [])
        group = super().create(validated_data)
        if flight_ids:
            Flight.objects.filter(
                id__in=flight_ids, user=group.user
            ).update(flight_group=group)
        return group

    def update(self, instance, validated_data):
        flight_ids = validated_data.pop('flight_ids', None)
        group = super().update(instance, validated_data)
        if flight_ids is not None:
            # Remove all flights from this group first
            group.flights.update(flight_group=None)
            # Then add the specified ones
            Flight.objects.filter(
                id__in=flight_ids, user=group.user
            ).update(flight_group=group)
        return group
