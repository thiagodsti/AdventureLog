from django.urls import path, include
from rest_framework.routers import DefaultRouter
from flights.views import EmailAccountViewSet, FlightViewSet, FlightGroupViewSet, test_email_connection

router = DefaultRouter()
router.register(r'email-accounts', EmailAccountViewSet, basename='email-account')
router.register(r'flights', FlightViewSet, basename='flight')
router.register(r'flight-groups', FlightGroupViewSet, basename='flight-group')

urlpatterns = [
    path('email-accounts/test-connection/', test_email_connection, name='test-email-connection'),
    path('', include(router.urls)),
]
