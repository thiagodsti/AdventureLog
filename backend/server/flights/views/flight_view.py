from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum
from django.utils import timezone

from flights.models import Airport, Flight
from flights.serializers import FlightSerializer, FlightWriteSerializer


class FlightViewSet(viewsets.ModelViewSet):
    """CRUD for flights."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return FlightWriteSerializer
        return FlightSerializer

    def get_queryset(self):
        qs = Flight.objects.filter(
            user=self.request.user
        ).select_related(
            'departure_airport_obj', 'arrival_airport_obj'
        )

        # Optional filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        airline = self.request.query_params.get('airline')
        if airline:
            qs = qs.filter(airline_code__iexact=airline)

        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_manually_added=True)
        # Auto-group after adding a flight
        from flights.grouping import auto_group_flights
        auto_group_flights(self.request.user)

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming flights sorted by departure date."""
        now = timezone.now()
        flights = self.get_queryset().filter(
            departure_datetime__gte=now, status='upcoming'
        ).order_by('departure_datetime')
        serializer = FlightSerializer(flights, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def past(self, request):
        """Get past flights."""
        now = timezone.now()
        flights = self.get_queryset().filter(
            departure_datetime__lt=now
        ).order_by('-departure_datetime')
        serializer = FlightSerializer(flights, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get flight statistics for the user."""
        qs = self.get_queryset()
        total_flights = qs.count()
        total_duration = qs.aggregate(total=Sum('duration_minutes'))['total'] or 0
        airlines = list(qs.exclude(airline_name='').order_by('airline_name').values_list('airline_name', flat=True).distinct())
        dep_airports = set(qs.exclude(departure_airport='').values_list('departure_airport', flat=True))
        arr_airports = set(qs.exclude(arrival_airport='').values_list('arrival_airport', flat=True))
        airports_visited = dep_airports | arr_airports

        return Response({
            'total_flights': total_flights,
            'total_duration_minutes': total_duration,
            'total_duration_hours': round(total_duration / 60, 1) if total_duration else 0,
            'unique_airlines': airlines,
            'unique_airports_count': len(airports_visited),
            'unique_airports': sorted(airports_visited),
        })

    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Return flights formatted for calendar display."""
        flights = self.get_queryset().values(
            'id', 'flight_number', 'airline_name',
            'departure_airport', 'arrival_airport',
            'departure_city', 'arrival_city',
            'departure_datetime', 'arrival_datetime', 'status',
        )
        result = []
        for f in flights:
            result.append({
                'id': str(f['id']),
                'flight_number': f['flight_number'],
                'airline_name': f['airline_name'] or '',
                'departure_airport': f['departure_airport'],
                'arrival_airport': f['arrival_airport'],
                'departure_city': f['departure_city'] or '',
                'arrival_city': f['arrival_city'] or '',
                'departure_datetime': (
                    f['departure_datetime'].isoformat()
                    if f['departure_datetime'] else None
                ),
                'arrival_datetime': (
                    f['arrival_datetime'].isoformat()
                    if f['arrival_datetime'] else None
                ),
                'status': f['status'],
            })
        return Response(result)

    @action(detail=False, methods=['get'])
    def routes(self, request):
        """Return flight routes as GeoJSON for map visualization."""
        flights = self.get_queryset().select_related(
            'departure_airport_obj', 'arrival_airport_obj'
        )
        features = []
        for f in flights:
            dep = f.departure_airport_obj
            arr = f.arrival_airport_obj
            if not dep or not arr:
                continue
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [
                        [float(dep.longitude), float(dep.latitude)],
                        [float(arr.longitude), float(arr.latitude)],
                    ]
                },
                'properties': {
                    'flight_id': str(f.id),
                    'flight_number': f.flight_number,
                    'departure_airport': f.departure_airport,
                    'arrival_airport': f.arrival_airport,
                    'departure_city': f.departure_city or dep.city_name,
                    'arrival_city': f.arrival_city or arr.city_name,
                    'status': f.status,
                    'departure_datetime': (
                        f.departure_datetime.isoformat()
                        if f.departure_datetime else None
                    ),
                    'airline_name': f.airline_name,
                }
            })

        # Also return airport points for markers
        airport_codes = set()
        for f in flights:
            if f.departure_airport_obj:
                airport_codes.add(f.departure_airport)
            if f.arrival_airport_obj:
                airport_codes.add(f.arrival_airport)

        airport_features = []
        for airport in Airport.objects.filter(iata_code__in=airport_codes):
            airport_features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [float(airport.longitude), float(airport.latitude)],
                },
                'properties': {
                    'iata_code': airport.iata_code,
                    'name': airport.name,
                    'city_name': airport.city_name,
                }
            })

        return Response({
            'routes': {
                'type': 'FeatureCollection',
                'features': features,
            },
            'airports': {
                'type': 'FeatureCollection',
                'features': airport_features,
            },
        })
