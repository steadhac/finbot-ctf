"""CTF Event Processor
Background task that processes events from Redis streams, detects
challenge completions and awards badges.
"""

import json
import logging
import os
import socket
import time
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from finbot.config import settings
from finbot.core.data.database import SessionLocal
from finbot.core.data.models import CTFEvent
from finbot.ctf.processor.badge_service import BadgeService
from finbot.ctf.processor.challenge_service import ChallengeService

logger = logging.getLogger(__name__)


# Processor Config
DEFAULT_LOOKBACK_HOURS = 4
STALE_CLAIM_TIMEOUT_MS = 60_000
STREAM_RETENTION_DAYS = 7


class CTFEventProcessor:
    """
    Processes events from Redis Streams for CTF functionality.

    Responsibilities:
    - Subscribe to Redis event streams (consumer groups for horizontal scaling)
    - Store events as CTFEvent records
    - Run challenge detectors
    - Run badge evaluators
    - Handle stream cleanup
    """

    CONSUMER_GROUP = "ctf-processor"
    STREAMS = ["finbot:events:agents", "finbot:events:business"]

    def __init__(
        self,
        redis_client=None,
    ):
        self.redis = redis_client
        self.default_lookback_hours = DEFAULT_LOOKBACK_HOURS
        self.stale_claim_timeout_ms = STALE_CLAIM_TIMEOUT_MS
        self.stream_retention_days = STREAM_RETENTION_DAYS

        self.consumer_name = f"ctf-{socket.gethostname()}-{os.getpid()}"

        # init services
        self.challenge_service = ChallengeService()
        self.badge_service = BadgeService()
        self._running = False

    def start_sync(self):
        """Start the event processor in synchronous mode
        - This is a blocking operation - either run in a thread, daemon or use start_async()
        """
        if self.redis is None:
            logger.warning("Redis client not configured, CTF processor disabled")
            return
        logger.info("Starting CTF event processor (consumer: %s)", self.consumer_name)
        self._ensure_consumer_groups()
        self._running = True
        while self._running:
            try:
                self._process_batch()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in CTF processor loop: %s", e)
                time.sleep(5)  # Back off on error

    def stop(self):
        """Stop the processor"""
        self._running = False
        logger.info("CTF event processor stopped")

    def _ensure_consumer_groups(self):
        """Create consumer groups if they don't exist"""
        lookback_ms = int(time.time() * 1000) - (
            self.default_lookback_hours * 3600 * 1000
        )
        start_id = f"{lookback_ms}-0"
        for stream in self.STREAMS:
            try:
                self.redis.xgroup_create(
                    stream, self.CONSUMER_GROUP, id=start_id, mkstream=True
                )
                logger.info(
                    "Created consumer group %s on %s from %s",
                    self.CONSUMER_GROUP,
                    stream,
                    start_id,
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                if "BUSYGROUP" in str(e):
                    logger.debug(
                        "Consumer group %s already exists on %s",
                        self.CONSUMER_GROUP,
                        stream,
                    )
                else:
                    raise

    def _process_batch(self):
        """Process a batch of events from Redis streams"""
        # Read from all streams
        streams_dict = {stream: ">" for stream in self.STREAMS}
        try:
            results = self.redis.xreadgroup(
                self.CONSUMER_GROUP,
                self.consumer_name,
                streams_dict,
                count=10,
                block=5000,  # 5 second timeout
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error reading from streams: %s", e)
            return
        if not results:
            return

        db = SessionLocal()
        processed_ids = []

        try:
            for stream, messages in results:
                for message_id, data in messages:
                    try:
                        event = self._decode_event(data)
                        if event:
                            self._process_single_event(event, db, stream)
                        # ack the message
                        self.redis.xack(stream, self.CONSUMER_GROUP, message_id)
                        processed_ids.append((stream, message_id))
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logger.error("Error processing messages %s: %s", message_id, e)
                        db.rollback()

            # Batch delete processed messages
            for stream, msg_id in processed_ids:
                try:
                    self.redis.xdel(stream, msg_id)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning("Failed to delete message %s: %s", msg_id, e)
        finally:
            db.close()
            logger.info(
                "CTF event processor batch processed %d messages", len(processed_ids)
            )

    def _decode_event(self, data: dict) -> dict[str, Any] | None:
        """Decode event from Redis stream format"""
        try:
            decoded = {}
            for key, value in data.items():
                k = key.decode() if isinstance(key, bytes) else key
                v = value.decode() if isinstance(value, bytes) else value

                if k == "event_data" and isinstance(v, str):
                    try:
                        decoded[k] = json.loads(v)
                    except json.JSONDecodeError:
                        decoded[k] = v
                else:
                    decoded[k] = v
            return decoded
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to decode event: %s", e)
            return None

    def _process_single_event(self, event: dict[str, Any], db: Session, stream: str):
        """Process a single event"""
        # Determine event category from stream
        if "agents" in stream:
            event_category = "agent"
        elif "business" in stream:
            event_category = "business"
        else:
            event_category = "unknown"

        # Store as CTFEvent
        self._store_ctf_event(event, event_category, db)

        # Check for challenge completions
        completed_challenges = self.challenge_service.check_event_for_challenges(
            event, db
        )

        # Check for badge awards
        awarded_badges = self.badge_service.check_event_for_badges(event, db)

        if completed_challenges:
            logger.info(
                "Challenges completed: %s", [c[0] for c in completed_challenges]
            )
        if awarded_badges:
            logger.info("Badges awarded: %s", [b[0] for b in awarded_badges])

    def _store_ctf_event(self, event: dict[str, Any], category: str, db: Session):
        """Store event as CTFEvent (idempotent)"""
        # Generate external event ID for idempotency
        external_id = (
            event.get("event_id")
            or f"{event.get('timestamp', '')}-{event.get('event_type', '')}"
        )

        # Extract common fields
        event_data = event.get("event_data", {})
        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except json.JSONDecodeError:
                event_data = {}

        values = {
            "external_event_id": external_id,
            "namespace": event.get("namespace", "unknown"),
            "user_id": event.get("user_id", "unknown"),
            "session_id": event.get("session_id"),
            "workflow_id": event.get("workflow_id"),
            "vendor_id": event_data.get("vendor_id"),
            "event_category": category,
            "event_type": event.get("event_type", "unknown"),
            "event_subtype": event_data.get("subtype"),
            "summary": event_data.get("summary"),  # human readable summary for UI
            "details": json.dumps(event),
            "severity": event_data.get("severity", "info"),
            "agent_name": event.get("agent_name"),
            "tool_name": event_data.get("tool_name"),
            "llm_model": event_data.get("model"),
            "duration_ms": event_data.get("duration_ms"),
            "timestamp": datetime.now(UTC),
        }

        # Upsert (idempotent insert)
        dialect = db.bind.dialect.name if db.bind else "sqlite"

        if dialect == "sqlite":
            stmt = sqlite_insert(CTFEvent).values(**values)
            stmt = stmt.on_conflict_do_nothing(index_elements=["external_event_id"])
        elif dialect == "postgresql":
            stmt = pg_insert(CTFEvent).values(**values)
            stmt = stmt.on_conflict_do_nothing(index_elements=["external_event_id"])
        else:
            # Fallback: check exists first
            existing = (
                db.query(CTFEvent)
                .filter(CTFEvent.external_event_id == external_id)
                .first()
            )
            if existing:
                return
            db.add(CTFEvent(**values))
            db.commit()
            return

        db.execute(stmt)
        db.commit()

    def reload_definitions(self):
        """Reload detector and evaluator caches"""
        self.challenge_service.clear_cache()
        self.badge_service.clear_cache()
        logger.info("CTF processor caches cleared")


# Singleton instance
_processor: CTFEventProcessor | None = None


def get_processor() -> CTFEventProcessor:
    """Get singleton processor instance"""
    global _processor  # pylint: disable=global-statement
    if _processor is None:
        # Get Redis client if available
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting Redis client: %s", e)
            redis_client = None

        _processor = CTFEventProcessor(redis_client=redis_client)
    return _processor


def start_processor_thread():
    """Start processor in background thread"""
    import threading  # pylint: disable=import-outside-toplevel

    processor = get_processor()
    thread = threading.Thread(target=processor.start_sync, daemon=True)
    thread.start()
    logger.info("CTF processor thread started")
    return thread
