from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db import models

from flights.models import Airport
from flights.serializers import AirportSerializer


class AirportViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only airport lookup for autocomplete and map display."""
    serializer_class = AirportSerializer
    permission_classes = [IsAuthenticated]
    queryset = Airport.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                models.Q(iata_code__iexact=search) |
                models.Q(name__icontains=search) |
                models.Q(city_name__icontains=search)
            )[:50]
        return qs
