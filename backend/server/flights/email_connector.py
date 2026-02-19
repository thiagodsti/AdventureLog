"""
Email connection utilities for fetching flight-related emails from various providers.
Supports IMAP (Gmail, Outlook, generic) and Tuta (placeholder).
"""

import imaplib
import email
import email.header
import email.utils
import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    """HTML-to-text converter that preserves structure via newlines after block elements."""

    BLOCK_TAGS = frozenset([
        'p', 'div', 'br', 'tr', 'td', 'th', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'table', 'blockquote', 'pre', 'section', 'article', 'header', 'footer',
    ])

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.BLOCK_TAGS:
            self._pieces.append('\n')

    def handle_endtag(self, tag):
        if tag.lower() in self.BLOCK_TAGS:
            self._pieces.append('\n')

    def handle_data(self, data):
        self._pieces.append(data)

    def get_text(self):
        text = ''.join(self._pieces)
        # Collapse horizontal whitespace (preserve newlines)
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Collapse runs of blank lines into at most one blank line
        text = re.sub(r'\n[ \t]*\n', '\n\n', text)
        lines = [line.strip() for line in text.split('\n')]
        # Deduplicate consecutive blank lines
        result: list[str] = []
        prev_empty = False
        for line in lines:
            if not line:
                if not prev_empty:
                    result.append('')
                prev_empty = True
            else:
                result.append(line)
                prev_empty = False
        return '\n'.join(result).strip()


def html_to_text(html_content: str) -> str:
    """Convert HTML to structured plain text, preserving block-level line breaks."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html_content)
    return extractor.get_text()


def decode_header_value(raw: str) -> str:
    """Decode an RFC-2047 encoded header value into a Python string."""
    parts = email.header.decode_header(raw)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    return ''.join(decoded_parts)


def get_email_body(msg) -> str:
    """Extract text from an email message.
    Collects both plain-text AND HTML-to-text to maximise flight-data coverage.
    Many airlines put itinerary details only in the HTML part.
    """
    plain_body = ''
    html_body = ''

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain' and not plain_body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    plain_body = payload.decode(charset, errors='replace')
            elif content_type == 'text/html' and not html_body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    html_body = html_to_text(payload.decode(charset, errors='replace'))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            if msg.get_content_type() == 'text/html':
                html_body = html_to_text(payload.decode(charset, errors='replace'))
            else:
                plain_body = payload.decode(charset, errors='replace')

    # Return both parts combined so regex patterns can match data from either
    parts = []
    if plain_body:
        parts.append(plain_body.strip())
    if html_body:
        parts.append(html_body.strip())
    return '\n\n'.join(parts) if parts else ''


class EmailMessage:
    """Lightweight container for a fetched email."""

    def __init__(self, message_id: str, sender: str, subject: str, body: str, date: datetime | None):
        self.message_id = message_id
        self.sender = sender
        self.subject = subject
        self.body = body
        self.date = date

    def __repr__(self):
        return f"<EmailMessage {self.message_id!r} from={self.sender!r} subj={self.subject[:40]!r}>"


def connect_imap(host: str, port: int, username: str, password: str, use_ssl: bool = True) -> imaplib.IMAP4:
    """Connect and authenticate to an IMAP server."""
    if use_ssl:
        conn = imaplib.IMAP4_SSL(host, port)
    else:
        conn = imaplib.IMAP4(host, port)
    conn.login(username, password)
    return conn


def fetch_emails_imap(
    host: str, port: int, username: str, password: str,
    use_ssl: bool = True,
    sender_patterns: list[str] | None = None,
    since_date: datetime | None = None,
    folder: str = 'INBOX',
    max_results: int = 200,
) -> list[EmailMessage]:
    """
    Fetch emails from an IMAP server, optionally filtering by sender patterns and date.

    Args:
        sender_patterns: List of regex patterns to match against From header.
        since_date: Only fetch emails after this date.
        max_results: Maximum number of emails to return.
    """
    messages: list[EmailMessage] = []
    try:
        conn = connect_imap(host, port, username, password, use_ssl)
        conn.select(folder, readonly=True)

        # Build IMAP search criteria
        search_criteria = []
        if since_date:
            date_str = since_date.strftime('%d-%b-%Y')
            search_criteria.append(f'SINCE {date_str}')

        criteria_str = ' '.join(search_criteria) if search_criteria else 'ALL'
        status, data = conn.search(None, criteria_str)
        if status != 'OK':
            logger.error("IMAP search failed: %s", status)
            return messages

        msg_ids = data[0].split()
        # Process most recent first
        msg_ids = msg_ids[-max_results:]
        msg_ids.reverse()

        for msg_id in msg_ids:
            try:
                status, msg_data = conn.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender = decode_header_value(msg.get('From', ''))
                subject = decode_header_value(msg.get('Subject', ''))
                message_id = msg.get('Message-ID', f'imap-{msg_id.decode()}')

                # Filter by sender patterns if provided
                if sender_patterns:
                    matched = False
                    for pattern in sender_patterns:
                        if re.search(pattern, sender, re.IGNORECASE):
                            matched = True
                            break
                    if not matched:
                        continue

                body = get_email_body(msg)

                # Parse date
                date_str = msg.get('Date', '')
                date = None
                if date_str:
                    date_tuple = email.utils.parsedate_to_datetime(date_str)
                    date = date_tuple if date_tuple else None

                messages.append(EmailMessage(
                    message_id=message_id,
                    sender=sender,
                    subject=subject,
                    body=body,
                    date=date,
                ))
            except Exception as e:
                logger.warning("Error processing email %s: %s", msg_id, e)
                continue

        conn.logout()
    except Exception as e:
        logger.error("IMAP connection error: %s", e)
        raise

    return messages


def fetch_emails_tuta(
    tuta_user: str, tuta_password: str,
    sender_patterns: list[str] | None = None,
    since_date: datetime | None = None,
    max_results: int = 200,
) -> list[EmailMessage]:
    """
    Fetch emails from a Tuta (Tutanota) account.

    NOTE: Tutanota does not provide public IMAP access.
    This is a placeholder that uses the tutanota-client approach.
    Full Tuta integration requires their encrypted API which is complex.
    For now this raises a descriptive error.
    """
    raise NotImplementedError(
        "Tuta (Tutanota) email fetching requires the Tuta API client. "
        "Tutanota does not support standard IMAP. "
        "This feature is planned for a future release. "
        "Please use IMAP-compatible providers (Gmail, Outlook) for now."
    )


def fetch_emails_for_account(email_account, since_date=None, max_results=200) -> list[EmailMessage]:
    """
    High-level function: fetch flight-related emails from an EmailAccount model instance.
    Uses the account's provider to select the right fetching method.
    """
    from django.db.models import Q
    from .models import AirlineRule

    # Get all active rules (user-specific + system)
    user_rules = AirlineRule.objects.filter(is_active=True).filter(
        Q(user=email_account.user) | Q(user__isnull=True)
    )
    sender_patterns = [r.sender_pattern for r in user_rules if r.sender_pattern]

    provider = email_account.provider
    if provider in ('gmail', 'outlook', 'imap'):
        return fetch_emails_imap(
            host=email_account.imap_host,
            port=email_account.imap_port,
            username=email_account.imap_username or email_account.email_address,
            password=email_account.imap_password,
            use_ssl=email_account.use_ssl,
            sender_patterns=sender_patterns if sender_patterns else None,
            since_date=since_date,
            max_results=max_results,
        )
    elif provider == 'tuta':
        return fetch_emails_tuta(
            tuta_user=email_account.tuta_user,
            tuta_password=email_account.tuta_password,
            sender_patterns=sender_patterns if sender_patterns else None,
            since_date=since_date,
            max_results=max_results,
        )
    else:
        raise ValueError(f"Unsupported email provider: {provider}")
