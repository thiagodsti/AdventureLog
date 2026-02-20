from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from flights.models import Flight
from flights.serializers import FlightSerializer, FlightWriteSerializer


class FlightViewSet(viewsets.ModelViewSet):
    """CRUD for flights."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return FlightWriteSerializer
        return FlightSerializer

    def get_queryset(self):
        qs = Flight.objects.filter(user=self.request.user)

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
        total_duration = sum(
            f.duration_minutes for f in qs if f.duration_minutes
        )
        airlines = qs.values_list('airline_name', flat=True).distinct()
        airports_visited = set()
        for f in qs:
            airports_visited.add(f.departure_airport)
            airports_visited.add(f.arrival_airport)
        airports_visited.discard('')

        return Response({
            'total_flights': total_flights,
            'total_duration_minutes': total_duration,
            'total_duration_hours': round(total_duration / 60, 1) if total_duration else 0,
            'unique_airlines': list(airlines),
            'unique_airports_count': len(airports_visited),
            'unique_airports': sorted(airports_visited),
        })
