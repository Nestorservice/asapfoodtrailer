"""
ASAP Food Trailer - Authentication Service
Firebase Auth verification + admin whitelist
"""

from config import settings


class AuthService:
    """Handles admin authentication and authorization."""

    def __init__(self):
        self.admin_emails = settings.ADMIN_EMAILS
        self.mode = settings.APP_MODE

    def verify_admin_token(self, token: str) -> dict:
        """Verify Firebase ID token and check admin whitelist."""
        if self.mode == "local":
            # In local mode, accept a simple token for dev
            if token == "dev-admin-token":
                return {
                    "uid": "local-admin",
                    "email": "admin@asapfoodtrailer.com",
                    "is_admin": True,
                }
            return None

        try:
            import firebase_admin.auth as firebase_auth

            decoded = firebase_auth.verify_id_token(token)
            email = decoded.get("email", "")

            if email in self.admin_emails:
                return {
                    "uid": decoded["uid"],
                    "email": email,
                    "is_admin": True,
                }
            return None
        except Exception as e:
            print(f"Auth verification failed: {e}")
            return None

    def is_admin_email(self, email: str) -> bool:
        """Check if an email is in the admin whitelist."""
        return email in self.admin_emails


auth_service = AuthService()
