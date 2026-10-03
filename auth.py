"""Local-first authentication and persisted feature intent; no proxy trust."""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from simulator import DashboardError

PBKDF2_ITERATIONS = 600_000
SESSION_SECONDS = 3600
MAX_SESSIONS = 128
MAX_PEERS = 512
FAILURE_WINDOW_SECONDS = 300
MAX_LOGIN_FAILURES = 8
FEATURES = ("lan_access", "remote_view", "remote_control")
COOKIE_NAME = "ft_session"


def is_loopback_peer(peer: str) -> bool:
    """Use the actual socket peer only, including IPv4-mapped IPv6."""
    try:
        address = ipaddress.ip_address(peer)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return address.is_loopback
    except ValueError:
        return False


def validate_password(password: object) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
        raise DashboardError("weak_password", "Use a new password with 12–256 characters.")
    try:
        password.encode("utf-8")
    except UnicodeError:
        raise DashboardError("weak_password", "The new password must contain valid Unicode characters.") from None
    if password.casefold() == "admin" or password.isspace():
        raise DashboardError("weak_password", "The initial password and blank passwords are not allowed.")
    # A long passphrase is accepted; short single-category strings are not.
    categories = sum((any(c.islower() for c in password), any(c.isupper() for c in password),
                      any(c.isdigit() for c in password), any(not c.isalnum() for c in password)))
    if len(password) < 20 and categories < 3:
        raise DashboardError("weak_password", "Use at least three character types, or a passphrase of 20+ characters.")
    if len(set(password)) < 6:
        raise DashboardError("weak_password", "Choose a less repetitive password.")
    return password


def _digest(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


class AuthStore:
    """SQLite holds only a salted password hash and flags; sessions stay in memory."""
    def __init__(self, db_path: str | Path, *, initial_password: str = "admin", clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.sessions = OrderedDict()
        self.failures = OrderedDict()
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            path = Path(self.db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Create private storage without temporarily writing plaintext secrets.
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS auth_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)")
        stored = self.db.execute("SELECT payload FROM auth_state WHERE singleton=1").fetchone()
        if stored:
            self.state = json.loads(stored[0])
            self._validate_state()
        else:
            if initial_password != "admin":
                validate_password(initial_password)
            salt = secrets.token_bytes(32)
            self.state = {"version": 1, "username": "admin", "salt": salt.hex(),
                          "password_hash": _digest(initial_password, salt), "iterations": PBKDF2_ITERATIONS,
                          "bootstrap_required": True, "features": {key: True for key in FEATURES}}
            self._save()

    def _validate_state(self):
        state = self.state
        valid = (isinstance(state, dict) and state.get("version") == 1 and state.get("username") == "admin"
                 and type(state.get("bootstrap_required")) is bool and state.get("iterations") == PBKDF2_ITERATIONS
                 and isinstance(state.get("features"), dict) and set(state["features"]) == set(FEATURES)
                 and all(type(value) is bool for value in state["features"].values()))
        try:
            valid = valid and len(bytes.fromhex(state["salt"])) == 32 and len(bytes.fromhex(state["password_hash"])) == 32
        except (KeyError, ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError("Invalid authentication storage; refusing to reset credentials or security flags.")

    def _save(self):
        encoded = json.dumps(self.state, separators=(",", ":"), allow_nan=False)
        with self.db:
            self.db.execute("INSERT INTO auth_state(singleton,payload) VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload", (encoded,))

    def close(self):
        with self.lock:
            self.sessions.clear()
            self.db.close()

    @property
    def bootstrap_required(self):
        with self.lock:
            return self.state["bootstrap_required"]

    def settings(self, *, listener_lan=False, tls=False):
        with self.lock:
            configured = dict(self.state["features"])
            enabled = not self.state["bootstrap_required"] and listener_lan
            lan = enabled and configured["lan_access"]
            return {"configured": configured,
                    "effective": {"lan_access": lan, "remote_view": lan and configured["remote_view"],
                                  "remote_control": lan and configured["remote_control"]},
                    "bootstrap_required": self.state["bootstrap_required"],
                    "listener_lan": listener_lan, "tls": tls}

    def guard_peer(self, peer: str, *, operation=None):
        if is_loopback_peer(peer):
            return
        with self.lock:
            if self.state["bootstrap_required"]:
                raise DashboardError("local_setup_required", "Complete first login and password change on loopback before LAN access.", 403)
            if not self.state["features"]["lan_access"]:
                raise DashboardError("lan_disabled", "LAN access is disabled by the administrator.", 403)
            if operation in {"remote_view", "remote_control"} and not self.state["features"][operation]:
                raise DashboardError(operation + "_disabled", "This remote operation is disabled by the administrator.", 403)

    def _prune(self):
        now = self.clock()
        for key in list(self.sessions):
            if self.sessions[key]["expires_at"] <= now:
                del self.sessions[key]
        for peer in list(self.failures):
            if self.failures[peer]["since"] + FAILURE_WINDOW_SECONDS <= now:
                del self.failures[peer]

    def _limited(self, peer):
        self._prune()
        entry = self.failures.get(peer)
        if entry and entry["count"] >= MAX_LOGIN_FAILURES:
            raise DashboardError("login_rate_limited", "Too many failed attempts. Wait five minutes before trying again.", 429)

    def _failure(self, peer):
        if peer not in self.failures:
            if len(self.failures) >= MAX_PEERS:
                self.failures.popitem(last=False)
            self.failures[peer] = {"since": self.clock(), "count": 0}
        self.failures[peer]["count"] += 1
        self.failures.move_to_end(peer)

    def _verify(self, password):
        if not isinstance(password, str) or len(password) > 256:
            return False
        try:
            digest = _digest(password, bytes.fromhex(self.state["salt"]), self.state["iterations"])
        except UnicodeError:
            return False
        return hmac.compare_digest(digest, self.state["password_hash"])

    def _new_session(self, peer):
        self._prune()
        if len(self.sessions) >= MAX_SESSIONS:
            self.sessions.popitem(last=False)
        token = secrets.token_urlsafe(32)
        session = {"username": "admin", "csrf_token": secrets.token_urlsafe(32),
                   "expires_at": self.clock() + SESSION_SECONDS, "peer": peer}
        self.sessions[hashlib.sha256(token.encode("ascii")).hexdigest()] = session
        return token, dict(session)

    def login(self, username, password, peer):
        with self.lock:
            self.guard_peer(peer)
            self._limited(peer)
            # Verify the hash even when the username is wrong.
            valid = self._verify(password)
            if username != "admin" or not valid:
                self._failure(peer)
                raise DashboardError("invalid_credentials", "Invalid administrator ID or password.", 401)
            self.failures.pop(peer, None)
            return self._new_session(peer)

    def session(self, token, peer):
        with self.lock:
            self._prune()
            if not isinstance(token, str) or len(token) > 128 or not token.isascii():
                return None
            key = hashlib.sha256(token.encode("ascii")).hexdigest()
            session = self.sessions.get(key)
            if not session or session["peer"] != peer:
                return None
            return dict(session)

    def require_session(self, token, peer, *, csrf=None, mutation=False, allow_bootstrap=False):
        with self.lock:
            self.guard_peer(peer)
            session = self.session(token, peer)
            if not session:
                raise DashboardError("authentication_required", "Log in as the administrator.", 401)
            if mutation and (not isinstance(csrf, str) or not hmac.compare_digest(csrf.encode("utf-8"), session["csrf_token"].encode("utf-8"))):
                raise DashboardError("invalid_csrf", "A valid session CSRF token is required.", 403)
            if self.state["bootstrap_required"] and not allow_bootstrap:
                raise DashboardError("password_change_required", "Change the initial password locally before using dashboard data or controls.", 403)
            return session

    def change_password(self, token, peer, current_password, new_password, csrf):
        with self.lock:
            self.require_session(token, peer, csrf=csrf, mutation=True, allow_bootstrap=True)
            if self.state["bootstrap_required"] and not is_loopback_peer(peer):
                raise DashboardError("local_setup_required", "Initial password change requires an actual loopback connection.", 403)
            self._limited(peer)
            if not self._verify(current_password):
                self._failure(peer)
                raise DashboardError("invalid_credentials", "Current password is incorrect.", 401)
            password = validate_password(new_password)
            if hmac.compare_digest(current_password.encode("utf-8"), password.encode("utf-8")):
                raise DashboardError("weak_password", "The new password must differ from the current password.")
            salt = secrets.token_bytes(32)
            self.state.update(salt=salt.hex(), password_hash=_digest(password, salt), bootstrap_required=False)
            self._save()
            self.sessions.clear()
            self.failures.pop(peer, None)
            return self._new_session(peer)

    def update_settings(self, payload):
        if not isinstance(payload, dict) or not payload or set(payload) - set(FEATURES) or any(type(value) is not bool for value in payload.values()):
            raise DashboardError("invalid_settings", "Provide only boolean LAN access, remote view or remote control settings.")
        with self.lock:
            self.state["features"].update(payload)
            self._save()

    def logout(self, token):
        with self.lock:
            if isinstance(token, str) and token.isascii():
                self.sessions.pop(hashlib.sha256(token.encode("ascii")).hexdigest(), None)
