#!/usr/bin/env python3
"""
Periodic sync runner for AdventureLog.
Runs two periodic tasks:
  1. sync_visited_regions — once daily at midnight
  2. sync_flight_emails — every 10 minutes
Managed by supervisord to ensure it inherits container environment variables.
"""
import os
import sys
import logging
import signal
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Setup Django
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

import django
django.setup()

from django.core.management import call_command

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

FLIGHT_SYNC_INTERVAL = 600  # 10 minutes

# Event used to signal shutdown from signal handlers
_stop_event = threading.Event()


def _seconds_until_next_midnight() -> float:
    """Return number of seconds until the next local midnight."""
    now = datetime.now()
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (next_midnight - now).total_seconds()


def _handle_termination(signum, frame):
    """Signal handler for SIGTERM and SIGINT: request graceful shutdown."""
    logger.info(f"Received signal {signum}; shutting down gracefully...")
    _stop_event.set()


def run_region_sync():
    """Run the sync_visited_regions command."""
    try:
        logger.info("Running sync_visited_regions...")
        call_command('sync_visited_regions')
        logger.info("Region sync completed successfully")
    except Exception as e:
        logger.error(f"Region sync failed: {e}", exc_info=True)


def run_flight_email_sync():
    """Run the sync_flight_emails command."""
    try:
        logger.info("Running sync_flight_emails...")
        call_command('sync_flight_emails')
        logger.info("Flight email sync completed successfully")
    except Exception as e:
        logger.error(f"Flight email sync failed: {e}", exc_info=True)


def midnight_sync_loop():
    """Thread: run region sync at midnight daily."""
    while not _stop_event.is_set():
        wait_seconds = _seconds_until_next_midnight()
        hours = wait_seconds / 3600.0
        logger.info(
            f"Next region sync in {wait_seconds:.0f}s (~{hours:.2f}h) at midnight"
        )
        if _stop_event.wait(wait_seconds):
            break
        run_region_sync()


def flight_sync_loop():
    """Thread: run flight email sync every 10 minutes."""
    # Small initial delay to let the app fully start
    if _stop_event.wait(30):
        return
    while not _stop_event.is_set():
        run_flight_email_sync()
        if _stop_event.wait(FLIGHT_SYNC_INTERVAL):
            break


def main():
    """Start both periodic sync loops in separate threads."""
    logger.info("Starting periodic sync worker (region@midnight + flights@10min)...")

    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGINT, _handle_termination)

    midnight_thread = threading.Thread(target=midnight_sync_loop, name='midnight-sync', daemon=True)
    flight_thread = threading.Thread(target=flight_sync_loop, name='flight-sync', daemon=True)

    midnight_thread.start()
    flight_thread.start()

    try:
        # Block main thread until stop event; check periodically so signals are handled
        while not _stop_event.is_set():
            _stop_event.wait(1)
    except Exception:
        logger.exception("Unexpected error in periodic sync main")
    finally:
        _stop_event.set()
        midnight_thread.join(timeout=5)
        flight_thread.join(timeout=5)
        logger.info("Periodic sync worker exiting")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received — exiting")
        _stop_event.set()
    except SystemExit:
        logger.info("SystemExit received — exiting")
    finally:
        logger.info("run_periodic_sync terminated")
