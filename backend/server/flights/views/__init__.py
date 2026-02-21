"""Views for DRF ViewSets - Flight email integration."""
from .email_account_view import EmailAccountViewSet, test_email_connection  # noqa: F401
from .flight_view import FlightViewSet  # noqa: F401
from .flight_group_view import FlightGroupViewSet  # noqa: F401
from .forwarding_view import forwarding_address  # noqa: F401
