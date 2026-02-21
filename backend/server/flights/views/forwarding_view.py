"""View for the flight email forwarding address endpoint."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.conf import settings


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def forwarding_address(request):
    """Return the user's forwarding email address for flight imports."""
    if not settings.FLIGHT_SMTP_ENABLED or not settings.FLIGHT_SMTP_DOMAIN:
        return Response({
            'enabled': False,
            'address': None,
        })

    address = f"{request.user.username}@{settings.FLIGHT_SMTP_DOMAIN}"
    return Response({
        'enabled': True,
        'address': address,
        'domain': settings.FLIGHT_SMTP_DOMAIN,
    })
