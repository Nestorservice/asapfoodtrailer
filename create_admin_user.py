"""Create a Firebase Auth user for admin login."""

import sys, os, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Load env
from dotenv import load_dotenv

load_dotenv()

import firebase_admin
from firebase_admin import credentials, auth

# Init Firebase
sa_path = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_PATH",
    "asapfoodtrailer-firebase-adminsdk-fbsvc-69e4615c0b.json",
)
if not firebase_admin._apps:
    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)

email = "admin@asapfoodtrailer.com"
password = "Admin2026!"

try:
    user = auth.get_user_by_email(email)
    print(f"User already exists: {user.uid}")
except auth.UserNotFoundError:
    user = auth.create_user(email=email, password=password, display_name="ASAP Admin")
    print(f"Created admin user: {user.uid}")

print(f"Email: {email}")
print(f"Password: {password}")
print("Use these credentials to login at /admin/login")
