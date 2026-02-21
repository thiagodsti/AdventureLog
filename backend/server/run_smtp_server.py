#!/usr/bin/env python3
"""
Inbound SMTP server runner for AdventureLog flight email forwarding.

Starts an SMTP server that receives forwarded flight confirmation emails
and processes them through the existing flight parsing pipeline.

Only runs if FLIGHT_SMTP_ENABLED=true in the environment.
Managed by supervisord.
"""
import os
import sys
import logging
import signal
import asyncio
from pathlib import Path

# Setup Django
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

import django
django.setup()

from django.conf import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def main():
    if not settings.FLIGHT_SMTP_ENABLED:
        logger.info("Flight SMTP server is disabled (FLIGHT_SMTP_ENABLED=false). Exiting.")
        sys.exit(0)

    if not settings.FLIGHT_SMTP_DOMAIN:
        logger.error("FLIGHT_SMTP_DOMAIN is not set. Cannot start SMTP server.")
        sys.exit(1)

    from flights.smtp_server import start_smtp_server

    logger.info(
        "Starting flight SMTP server on %s:%d for domain %s",
        settings.FLIGHT_SMTP_HOST,
        settings.FLIGHT_SMTP_PORT,
        settings.FLIGHT_SMTP_DOMAIN,
    )

    controller = start_smtp_server()

    # Handle shutdown signals
    stop_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info("Received signal %d, shutting down SMTP server...", signum)
        controller.stop()
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        # Block until shutdown signal
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(stop_event.wait())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
    finally:
        controller.stop()
        logger.info("Flight SMTP server stopped.")


if __name__ == '__main__':
    main()
