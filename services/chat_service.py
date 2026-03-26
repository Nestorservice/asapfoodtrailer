"""
ASAP Food Trailer - Stream Chat Service
Real-time chat powered by Stream (getstream.io)
"""

import time
import hashlib
from config import settings


class ChatService:
    """Manages Stream Chat client, tokens, and channels."""

    def __init__(self):
        self.api_key = settings.STREAM_API_KEY
        self.api_secret = settings.STREAM_API_SECRET
        self.client = None
        self.enabled = False
        self._init_client()

    def _init_client(self):
        """Initialize Stream Chat server client."""
        if not self.api_key or not self.api_secret:
            print("[Chat] Stream Chat not configured (set STREAM_API_KEY + STREAM_API_SECRET)")
            return
        try:
            from stream_chat import StreamChat
            self.client = StreamChat(api_key=self.api_key, api_secret=self.api_secret)
            self.enabled = True
            print("[Chat] Stream Chat initialized ✓")
        except Exception as e:
            print(f"[Chat] Stream Chat init failed: {e}")

    def create_visitor_token(self, visitor_id: str) -> str:
        """Generate a Stream user token for a visitor (24h expiry)."""
        if not self.enabled:
            return ""
        try:
            exp = int(time.time()) + 86400  # 24 hours
            return self.client.create_token(visitor_id, exp)
        except Exception as e:
            print(f"[Chat] Token generation failed: {e}")
            return ""

    def generate_visitor_id(self, name: str, email: str) -> str:
        """Generate a stable, unique visitor ID from name + email."""
        raw = f"{email.lower().strip()}"
        return "visitor-" + hashlib.md5(raw.encode()).hexdigest()[:12]

    def upsert_visitor(self, visitor_id: str, name: str, email: str, page: str = "/"):
        """Register/update visitor user in Stream."""
        if not self.enabled:
            return
        try:
            self.client.upsert_user({
                "id": visitor_id,
                "name": name,
                "email": email,
                "role": "user",
                "image": f"https://ui-avatars.com/api/?name={name.replace(' ', '+')}&background=ff6b00&color=fff&bold=true",
                "current_page": page,
            })
        except Exception as e:
            print(f"[Chat] Upsert visitor failed: {e}")

    def ensure_admin_user(self):
        """Ensure the admin user exists in Stream."""
        if not self.enabled:
            return
        try:
            self.client.upsert_user({
                "id": "asap-admin",
                "name": "ASAP Support",
                "role": "admin",
                "image": "/assets/img/logo/logo.jpg",
            })
        except Exception as e:
            print(f"[Chat] Ensure admin user failed: {e}")

    def get_or_create_channel(self, visitor_id: str, visitor_name: str, email: str, page: str = "/") -> dict:
        """Create or retrieve a support channel for a visitor."""
        if not self.enabled:
            return {}
        try:
            self.ensure_admin_user()
            channel_id = f"support-{visitor_id}"
            channel = self.client.channel(
                "messaging",
                channel_id,
                data={
                    "name": f"Chat with {visitor_name}",
                    "members": [visitor_id, "asap-admin"],
                    "visitor_name": visitor_name,
                    "visitor_email": email,
                    "visitor_page": page,
                    "created_by_id": visitor_id,
                },
            )
            resp = channel.create(visitor_id)
            return {
                "channel_id": channel_id,
                "channel_type": "messaging",
                "created": resp.get("created", False) if isinstance(resp, dict) else True,
            }
        except Exception as e:
            print(f"[Chat] Channel creation failed: {e}")
            return {}

    def list_channels(self) -> list:
        """List all support channels (for admin view)."""
        if not self.enabled:
            return []
        try:
            self.ensure_admin_user()
            resp = self.client.query_channels(
                filter_conditions={"type": "messaging", "members": {"$in": ["asap-admin"]}},
                sort=[{"field": "last_message_at", "direction": -1}],
                limit=50,
            )
            channels = []
            for ch in resp.get("channels", []):
                ch_data = ch.get("channel", {})
                msgs = ch.get("messages", [])
                last_msg = msgs[-1] if msgs else {}
                channels.append({
                    "id": ch_data.get("id", ""),
                    "visitor_name": ch_data.get("visitor_name", "Unknown"),
                    "visitor_email": ch_data.get("visitor_email", ""),
                    "visitor_page": ch_data.get("visitor_page", "/"),
                    "last_message": last_msg.get("text", ""),
                    "last_message_at": ch_data.get("last_message_at", ""),
                    "unread_count": ch.get("read", [{}])[0].get("unread_messages", 0) if ch.get("read") else 0,
                    "member_count": ch_data.get("member_count", 0),
                })
            return channels
        except Exception as e:
            print(f"[Chat] List channels failed: {e}")
            return []

    def create_admin_token(self) -> str:
        """Generate a Stream token for the admin user."""
        if not self.enabled:
            return ""
        try:
            exp = int(time.time()) + 86400
            return self.client.create_token("asap-admin", exp)
        except Exception as e:
            print(f"[Chat] Admin token generation failed: {e}")
            return ""


# ─── Rate limiter (simple in-memory) ─────────────────────────
_rate_limits: dict = {}  # { ip: [timestamp, ...] }
RATE_LIMIT_MAX = 10  # max requests
RATE_LIMIT_WINDOW = 60  # per 60 seconds


def check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    if ip not in _rate_limits:
        _rate_limits[ip] = []
    # Clean old entries
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[ip].append(now)
    return True


# Singleton
chat_service = ChatService()
