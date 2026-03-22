"""Instagram client wrapper around instagrapi with rate limiting."""

import logging
import os
import random
import time
import threading
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired

logger = logging.getLogger("insta-mcp")

SESSION_DIR = Path(os.environ.get("INSTA_SESSION_DIR", Path.home() / ".insta-mcp"))
SESSION_FILE = SESSION_DIR / "session.json"

# Rate limit settings
MIN_DELAY = 3.0   # minimum seconds between requests
MAX_DELAY = 8.0   # maximum seconds between requests
HOURLY_LIMITS = {
    "like": 20,
    "comment": 10,
    "follow": 10,
    "dm": 15,
    "default": 60,
}


class RateLimiter:
    """Simple rate limiter with random delays and hourly counters."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._hourly_counts: dict[str, list[float]] = {}

    def wait(self, action: str = "default"):
        """Wait appropriate delay before next request."""
        with self._lock:
            # Random delay between requests
            now = time.time()
            elapsed = now - self._last_request
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            if elapsed < delay:
                sleep_time = delay - elapsed
                logger.debug(f"Rate limit: sleeping {sleep_time:.1f}s before {action}")
                time.sleep(sleep_time)

            # Check hourly limit
            limit = HOURLY_LIMITS.get(action, HOURLY_LIMITS["default"])
            hour_ago = time.time() - 3600
            counts = self._hourly_counts.get(action, [])
            counts = [t for t in counts if t > hour_ago]  # prune old entries
            if len(counts) >= limit:
                wait_until = counts[0] + 3600
                sleep_time = wait_until - time.time()
                if sleep_time > 0:
                    logger.warning(f"Hourly limit reached for {action} ({limit}/hr). Waiting {sleep_time:.0f}s")
                    time.sleep(sleep_time)

            counts.append(time.time())
            self._hourly_counts[action] = counts
            self._last_request = time.time()


_rate_limiter = RateLimiter()


def rate_limit(action: str = "default"):
    """Apply rate limiting before an action."""
    _rate_limiter.wait(action)


def _handle_challenge(cl: Client):
    """Auto-resolve Instagram challenge (security checkpoint)."""
    try:
        cl.challenge_resolve(cl.last_json)
        logger.info("Challenge resolved automatically")
    except Exception as e:
        logger.error(f"Challenge resolve failed: {e}")
        raise


def get_client() -> Client:
    """Get authenticated Instagram client. Reuses saved session if available."""
    cl = Client()

    # Mimic real device
    cl.delay_range = [3, 8]

    # Auto challenge handler
    cl.challenge_code_handler = lambda username, choice: ""
    cl.change_password_handler = lambda username: ""

    # Proxy support
    proxy = os.environ.get("INSTA_PROXY")
    if proxy:
        cl.set_proxy(proxy)

    username = os.environ.get("INSTA_USERNAME")
    password = os.environ.get("INSTA_PASSWORD")
    if not username or not password:
        raise ValueError("INSTA_USERNAME and INSTA_PASSWORD environment variables are required")

    # Try to load existing session
    if SESSION_FILE.exists():
        cl.load_settings(SESSION_FILE)

    try:
        cl.login(username, password)
    except ChallengeRequired:
        logger.warning("Challenge required, attempting auto-resolve...")
        _handle_challenge(cl)
        # Retry login after challenge
        cl.login(username, password)

    _save_session(cl)
    return cl


def _save_session(cl: Client):
    """Save session to disk for reuse."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(SESSION_FILE)


# Lazy singleton
_client: Client | None = None


def client() -> Client:
    """Get or create singleton Instagram client."""
    global _client
    if _client is None:
        _client = get_client()
    return _client
