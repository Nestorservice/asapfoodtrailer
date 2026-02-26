"""
ASAP Food Trailer - Configuration centralisée
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # App mode
    APP_MODE = os.getenv("APP_MODE", "local")  # "local" or "firebase"
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    # Firebase
    FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
    FIREBASE_SERVICE_ACCOUNT_PATH = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")
    FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
    FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "")
    FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "")

    # Admin
    ADMIN_EMAILS = [
        e.strip()
        for e in os.getenv("ADMIN_EMAILS", "admin@asapfoodtrailer.com").split(",")
    ]

    # Server
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    # Business Info
    BUSINESS_NAME = os.getenv("BUSINESS_NAME", "ASAP Food Trailer")
    BUSINESS_PHONE = os.getenv("BUSINESS_PHONE", "+12016453364")
    BUSINESS_EMAIL = os.getenv(
        "BUSINESS_EMAIL", "ffoodtruckandtrailerforsaleand@gmail.com"
    )
    BUSINESS_ADDRESS = os.getenv("BUSINESS_ADDRESS", "Houston, TX")
    BUSINESS_CITY = os.getenv("BUSINESS_CITY", "Houston")
    BUSINESS_WHATSAPP = os.getenv("BUSINESS_WHATSAPP", "12104607427")

    # Social Media
    SOCIAL_TIKTOK = os.getenv(
        "SOCIAL_TIKTOK", "https://www.tiktok.com/@food.truck.and.tr"
    )
    SOCIAL_FACEBOOK = os.getenv(
        "SOCIAL_FACEBOOK", "https://www.facebook.com/share/1AhBtVhbus/?mibextid=wwXIfr"
    )
    SOCIAL_INSTAGRAM = os.getenv(
        "SOCIAL_INSTAGRAM",
        "https://www.instagram.com/asap_trailers?igsh=MTB5ZjNiajFqNGtm&utm_source=qr",
    )

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
    STATIC_DIR = os.path.join(BASE_DIR, "assets")
    DATA_DIR = os.path.join(BASE_DIR, "data")
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")


settings = Settings()
