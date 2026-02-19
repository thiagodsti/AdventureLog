from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from flights.models import FlightGroup, Flight
from flights.serializers import FlightGroupSerializer, FlightGroupWriteSerializer


class FlightGroupViewSet(viewsets.ModelViewSet):
    """CRUD for flight groups (trips)."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return FlightGroupWriteSerializer
        return FlightGroupSerializer

    def get_queryset(self):
        return FlightGroup.objects.filter(
            user=self.request.user
        ).prefetch_related('flights')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='add-flights')
    def add_flights(self, request, pk=None):
        """Add flights to this group."""
        group = self.get_object()
        flight_ids = request.data.get('flight_ids', [])
        if not flight_ids:
            return Response(
                {'error': 'flight_ids is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = Flight.objects.filter(
            id__in=flight_ids, user=request.user
        ).update(flight_group=group)
        return Response({'flights_added': updated})

    @action(detail=True, methods=['post'], url_path='remove-flights')
    def remove_flights(self, request, pk=None):
        """Remove flights from this group."""
        group = self.get_object()
        flight_ids = request.data.get('flight_ids', [])
        if not flight_ids:
            return Response(
                {'error': 'flight_ids is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = Flight.objects.filter(
            id__in=flight_ids, user=request.user, flight_group=group
        ).update(flight_group=None)
        return Response({'flights_removed': updated})

    @action(detail=False, methods=['post'], url_path='auto-group')
    def auto_group(self, request):
        """
        Auto-group ungrouped flights into trips based on booking reference
        and time proximity.
        """
        from flights.grouping import auto_group_flights
        result = auto_group_flights(request.user)
        return Response(result)
