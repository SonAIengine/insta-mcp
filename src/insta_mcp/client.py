"""Instagram client wrapper around instagrapi with rate limiting."""

import json
import logging
import os
import re
import random
import time
import threading
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired

logger = logging.getLogger("insta-mcp")

SESSION_DIR = Path(os.environ.get("INSTA_SESSION_DIR", Path.home() / ".insta-mcp"))

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


# ── Accounts ──
#
# "default" keeps the original single-account layout so existing setups keep working:
#   credentials: INSTA_USERNAME / INSTA_PASSWORD env vars, else SESSION_DIR/credentials.json
#   session:     SESSION_DIR/session.json
# Named accounts live in SESSION_DIR/accounts/<name>/{credentials.json,session.json}.
# credentials.json: {"username": ..., "password": ..., "proxy": optional}

DEFAULT_ACCOUNT = "default"
ACCOUNTS_DIR = SESSION_DIR / "accounts"
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_lock = threading.Lock()
_active_account = os.environ.get("INSTA_ACCOUNT", DEFAULT_ACCOUNT)
_clients: dict[str, Client] = {}
_rate_limiters: dict[str, RateLimiter] = {}


def _validate_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise ValueError(f"Invalid account name: {name!r} (allowed: letters, digits, _ . -)")
    return name


def _account_dir(name: str) -> Path:
    if name == DEFAULT_ACCOUNT:
        return SESSION_DIR
    return ACCOUNTS_DIR / _validate_name(name)


def _session_file(name: str) -> Path:
    return _account_dir(name) / "session.json"


def _credentials_file(name: str) -> Path:
    return _account_dir(name) / "credentials.json"


def _load_credentials(name: str) -> dict:
    """Return {"username", "password", "proxy"} for an account."""
    if name == DEFAULT_ACCOUNT:
        username = os.environ.get("INSTA_USERNAME")
        password = os.environ.get("INSTA_PASSWORD")
        if username and password:
            return {"username": username, "password": password, "proxy": os.environ.get("INSTA_PROXY")}
    path = _credentials_file(name)
    if not path.exists():
        if name == DEFAULT_ACCOUNT:
            raise ValueError("INSTA_USERNAME and INSTA_PASSWORD environment variables are required")
        raise ValueError(f"Unknown account: {name!r} (register with: python -m insta_mcp.accounts add {name})")
    data = json.loads(path.read_text())
    if not data.get("username") or not data.get("password"):
        raise ValueError(f"Account {name!r} credentials are incomplete: {path}")
    proxy = data.get("proxy")
    if name == DEFAULT_ACCOUNT and not proxy:
        proxy = os.environ.get("INSTA_PROXY")
    return {"username": data["username"], "password": data["password"], "proxy": proxy}


def list_accounts() -> list[dict]:
    """List registered accounts (no secrets)."""
    names = []
    if (os.environ.get("INSTA_USERNAME") and os.environ.get("INSTA_PASSWORD")) or _credentials_file(
        DEFAULT_ACCOUNT
    ).exists():
        names.append(DEFAULT_ACCOUNT)
    if ACCOUNTS_DIR.exists():
        names += sorted(p.name for p in ACCOUNTS_DIR.iterdir() if (p / "credentials.json").exists())
    result = []
    for name in names:
        try:
            creds = _load_credentials(name)
        except ValueError:
            continue
        result.append(
            {
                "name": name,
                "username": creds["username"],
                "proxy": bool(creds["proxy"]),
                "has_session": _session_file(name).exists(),
                "active": name == _active_account,
            }
        )
    return result


def save_account(name: str, username: str, password: str, proxy: str | None = None) -> None:
    """Register or update an account's credentials (file mode 0600)."""
    path = _credentials_file(_validate_name(name))
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"username": username, "password": password}
    if proxy:
        data["proxy"] = proxy
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    with _lock:
        _clients.pop(name, None)


def remove_account(name: str) -> None:
    """Remove a named account's credentials and session. The default account cannot be removed."""
    if name == DEFAULT_ACCOUNT:
        raise ValueError("The default account cannot be removed")
    d = _account_dir(name)
    for f in ("credentials.json", "session.json"):
        (d / f).unlink(missing_ok=True)
    if d.exists() and not any(d.iterdir()):
        d.rmdir()
    with _lock:
        _clients.pop(name, None)
        _rate_limiters.pop(name, None)
    global _active_account
    if _active_account == name:
        _active_account = DEFAULT_ACCOUNT


def get_active_account() -> str:
    return _active_account


def set_active_account(name: str) -> None:
    """Switch the account used by client() / rate_limit() when no account is given."""
    global _active_account
    _load_credentials(name)  # raises if unknown
    _active_account = name


def rate_limit(action: str = "default", account: str | None = None):
    """Apply per-account rate limiting before an action."""
    name = account or _active_account
    with _lock:
        limiter = _rate_limiters.setdefault(name, RateLimiter())
    limiter.wait(action)


def _handle_challenge(cl: Client):
    """Auto-resolve Instagram challenge (security checkpoint)."""
    try:
        cl.challenge_resolve(cl.last_json)
        logger.info("Challenge resolved automatically")
    except Exception as e:
        logger.error(f"Challenge resolve failed: {e}")
        raise


def get_client(account: str | None = None) -> Client:
    """Get authenticated Instagram client for an account. Reuses saved session if available."""
    name = account or _active_account
    creds = _load_credentials(name)
    session_file = _session_file(name)

    cl = Client()

    # Mimic real device
    cl.delay_range = [3, 8]

    # Auto challenge handler
    cl.challenge_code_handler = lambda username, choice: ""
    cl.change_password_handler = lambda username: ""

    # Proxy support (per account)
    if creds["proxy"]:
        cl.set_proxy(creds["proxy"])

    # Try to load existing session
    if session_file.exists():
        cl.load_settings(session_file)

    try:
        cl.login(creds["username"], creds["password"])
    except ChallengeRequired:
        logger.warning("Challenge required, attempting auto-resolve...")
        _handle_challenge(cl)
        # Retry login after challenge
        cl.login(creds["username"], creds["password"])

    _save_session(cl, session_file)
    return cl


def _save_session(cl: Client, session_file: Path):
    """Save session to disk for reuse."""
    session_file.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(session_file)
    session_file.chmod(0o600)


def client(account: str | None = None) -> Client:
    """Get or create the cached Instagram client for an account (default: active account)."""
    name = account or _active_account
    with _lock:
        cl = _clients.get(name)
    if cl is None:
        cl = get_client(name)
        with _lock:
            _clients[name] = cl
    return cl
