from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from flights.models import AirlineRule
from flights.serializers import AirlineRuleSerializer


class AirlineRuleViewSet(viewsets.ModelViewSet):
    """CRUD for airline parsing rules.
    Users see their own rules plus system built-in rules.
    Users can only edit/delete their own rules, not built-in ones.
    """
    serializer_class = AirlineRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AirlineRule.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).filter(is_active=True)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, is_builtin=False)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.is_builtin and instance.user is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Cannot modify built-in airline rules. Create a custom rule instead.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_builtin and instance.user is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Cannot delete built-in airline rules. You can deactivate them instead.")
        instance.delete()
