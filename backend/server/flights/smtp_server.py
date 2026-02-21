"""
Inbound SMTP server for receiving forwarded flight confirmation emails.

Users forward their airline confirmation emails to {username}@{FLIGHT_SMTP_DOMAIN}.
The server identifies the user by username, extracts the original email content,
and processes it through the existing flight parsing pipeline.
"""

import asyncio
import email
import email.policy
import logging
import re
from datetime import datetime, timezone

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session, SMTP

from django.conf import settings
from django.contrib.auth import get_user_model

from .email_connector import EmailMessage, get_email_body, decode_header_value
from .parsers import process_email_for_flights
from .grouping import auto_group_flights

logger = logging.getLogger(__name__)
User = get_user_model()


def _extract_forwarded_email(raw_body: str) -> tuple[str, str, str]:
    """
    Extract the original sender, subject, and body from a forwarded email.

    Returns (sender, subject, body). If no forwarding markers are found,
    returns empty sender/subject and the full body (treating it as a
    direct email rather than a forward).
    """
    # Common forwarding patterns
    # Gmail: "---------- Forwarded message ---------"
    # Outlook: "From: ... Sent: ... To: ... Subject: ..."
    # Tuta: "------- Forwarded Message -------"
    # Generic: "Begin forwarded message:" or "-------- Original Message --------"

    fwd_patterns = [
        r'-{3,}\s*Forwarded\s+[Mm]essage\s*-{3,}',
        r'-{3,}\s*Original\s+[Mm]essage\s*-{3,}',
        r'Begin\s+forwarded\s+message:',
    ]

    fwd_start = None
    for pattern in fwd_patterns:
        m = re.search(pattern, raw_body)
        if m:
            fwd_start = m.end()
            break

    if fwd_start is None:
        # No forwarding marker found - use full body
        return '', '', raw_body

    forwarded_part = raw_body[fwd_start:]

    # Try to extract original From/Subject from forwarded headers
    sender = ''
    subject = ''

    from_match = re.search(
        r'(?:From|De|Von|Fra):\s*(.+?)(?:\n|$)', forwarded_part, re.IGNORECASE
    )
    if from_match:
        sender = from_match.group(1).strip()

    subject_match = re.search(
        r'(?:Subject|Assunto|Betreff|Emne|Ämne):\s*(.+?)(?:\n|$)',
        forwarded_part, re.IGNORECASE,
    )
    if subject_match:
        subject = subject_match.group(1).strip()

    # The actual body starts after the forwarded headers block
    # Look for a blank line after the headers
    header_end = re.search(r'\n\s*\n', forwarded_part)
    if header_end:
        body = forwarded_part[header_end.end():]
    else:
        body = forwarded_part

    return sender, subject, body.strip()


class FlightEmailHandler:
    """aiosmtpd handler that processes incoming emails for flight data."""

    async def handle_RCPT(self, server: SMTP, session: Session, envelope: Envelope, address: str, rcpt_options: list) -> str:
        """Validate the recipient address and check if the user exists."""
        domain = settings.FLIGHT_SMTP_DOMAIN
        if not domain:
            logger.error("FLIGHT_SMTP_DOMAIN not configured")
            return '550 Service not configured'

        # Extract username from address
        if '@' not in address:
            return '550 Invalid address'

        local_part, addr_domain = address.rsplit('@', 1)

        if addr_domain.lower() != domain.lower():
            return '550 Unknown domain'

        # Check if user exists
        try:
            User.objects.get(username=local_part)
        except User.DoesNotExist:
            return '550 Unknown user'

        envelope.rcpt_tos.append(address)
        return '250 OK'

    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        """Process the received email data."""
        domain = settings.FLIGHT_SMTP_DOMAIN

        for rcpt in envelope.rcpt_tos:
            local_part = rcpt.rsplit('@', 1)[0]

            try:
                user = User.objects.get(username=local_part)
            except User.DoesNotExist:
                logger.warning("User not found for SMTP recipient: %s", rcpt)
                continue

            try:
                # Parse the raw email
                msg = email.message_from_bytes(
                    envelope.content, policy=email.policy.default
                )

                # Extract email body (handles multipart, HTML-to-text, etc.)
                body = get_email_body(msg)
                raw_sender = decode_header_value(msg.get('From', ''))
                raw_subject = decode_header_value(msg.get('Subject', ''))

                # Parse date
                date_str = msg.get('Date', '')
                msg_date = None
                if date_str:
                    try:
                        msg_date = email.utils.parsedate_to_datetime(date_str)
                    except Exception:
                        msg_date = datetime.now(timezone.utc)

                # Try to extract the original forwarded email content
                fwd_sender, fwd_subject, fwd_body = _extract_forwarded_email(body)

                # Use forwarded sender/subject if available, otherwise use envelope values
                effective_sender = fwd_sender or raw_sender
                effective_subject = fwd_subject or raw_subject
                effective_body = fwd_body or body

                # Build message ID for deduplication
                message_id = msg.get('Message-ID', f'smtp-fwd-{id(envelope)}')

                email_msg = EmailMessage(
                    message_id=message_id,
                    sender=effective_sender,
                    subject=effective_subject,
                    body=effective_body,
                    date=msg_date,
                )

                logger.info(
                    "Processing forwarded email for user=%s sender=%s subject=%s",
                    user.username, effective_sender, effective_subject[:60],
                )

                # Process through the existing flight parsing pipeline
                # We pass email_account=None since this comes from forwarding
                created_flights = process_email_for_flights(email_msg, user, email_account=None)

                if created_flights:
                    auto_group_flights(user)
                    logger.info(
                        "Created %d flight(s) from forwarded email for user=%s",
                        len(created_flights), user.username,
                    )
                else:
                    logger.info(
                        "No flights extracted from forwarded email for user=%s (sender=%s)",
                        user.username, effective_sender,
                    )

            except Exception:
                logger.exception("Error processing forwarded email for user=%s", local_part)

        return '250 Message accepted for delivery'


def start_smtp_server(host: str = None, port: int = None) -> Controller:
    """Start the SMTP server and return the controller."""
    host = host or settings.FLIGHT_SMTP_HOST
    port = port or settings.FLIGHT_SMTP_PORT

    handler = FlightEmailHandler()
    controller = Controller(
        handler,
        hostname=host,
        port=port,
    )
    controller.start()
    logger.info("Flight SMTP server started on %s:%d", host, port)
    return controller
