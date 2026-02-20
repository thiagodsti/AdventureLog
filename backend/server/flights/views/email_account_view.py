import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes as perm_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from flights.models import EmailAccount
from flights.serializers import EmailAccountSerializer, EmailAccountWriteSerializer
from flights.parsers import sync_email_account

logger = logging.getLogger(__name__)


@api_view(['POST'])
@perm_classes([IsAuthenticated])
def test_email_connection(request):
    """Test email connection with raw credentials (before saving an account)."""
    data = request.data
    provider = data.get('provider', 'imap')

    if provider in ('gmail', 'outlook', 'imap'):
        host = data.get('imap_host', '')
        if provider == 'gmail':
            host = 'imap.gmail.com'
        elif provider == 'outlook':
            host = 'outlook.office365.com'

        port = int(data.get('imap_port', 993))
        username = data.get('imap_username') or data.get('email_address', '')
        password = data.get('imap_password', '')
        use_ssl = data.get('use_ssl', True)

        if not password:
            return Response(
                {'error': 'Password is required to test the connection.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from flights.email_connector import connect_imap
            conn = connect_imap(
                host=host, port=port,
                username=username, password=password,
                use_ssl=use_ssl,
            )
            conn.logout()
            return Response({'status': 'Connection successful'})
        except Exception as e:
            return Response(
                {'error': f'Connection failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        return Response(
            {'error': f'Unknown provider: {provider}'},
            status=status.HTTP_400_BAD_REQUEST
        )


class EmailAccountViewSet(viewsets.ModelViewSet):
    """CRUD for email accounts + sync action."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return EmailAccountWriteSerializer
        return EmailAccountSerializer

    def get_queryset(self):
        return EmailAccount.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """Trigger a sync for a specific email account."""
        account = self.get_object()
        if not account.is_active:
            return Response(
                {'error': 'Email account is not active.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            summary = sync_email_account(account)
            return Response(summary, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("Sync failed for account %s: %s", account.id, e)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test the email connection without syncing."""
        account = self.get_object()
        try:
            if account.provider in ('gmail', 'outlook', 'imap'):
                from flights.email_connector import connect_imap
                conn = connect_imap(
                    host=account.imap_host,
                    port=account.imap_port,
                    username=account.imap_username or account.email_address,
                    password=account.imap_password,
                    use_ssl=account.use_ssl,
                )
                conn.logout()
                return Response({'status': 'Connection successful'})
            else:
                return Response(
                    {'error': f'Unknown provider: {account.provider}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response(
                {'error': f'Connection failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
