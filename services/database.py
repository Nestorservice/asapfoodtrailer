"""
ASAP Food Trailer - Database Service
Dual mode: local JSON storage or Firebase Firestore
Includes in-memory cache (5 min TTL) to reduce Firestore reads.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from config import settings

# ─── Cache TTL (seconds) ─────────────────────────────────────
CACHE_TTL = 300  # 5 minutes


class DatabaseService:
    """Database abstraction layer supporting local JSON and Firestore."""

    def __init__(self):
        self.mode = settings.APP_MODE
        self.data_file = os.path.join(settings.DATA_DIR, "seed.json")
        self._data = None
        # In-memory cache: { key: { "data": ..., "ts": timestamp } }
        self._cache: dict = {}

        if self.mode == "firebase":
            self._init_firebase()

    # ─── Cache helpers ────────────────────────────────────────

    def _cache_get(self, key: str):
        """Return cached value if present and not expired, else None."""
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
        return None

    def _cache_set(self, key: str, data):
        """Store a value in the cache with current timestamp."""
        self._cache[key] = {"data": data, "ts": time.time()}

    def _cache_invalidate(self, prefix: str = ""):
        """Remove cache entries whose key starts with *prefix*.
        If prefix is empty, flush the entire cache."""
        if not prefix:
            self._cache.clear()
        else:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]

    def _init_firebase(self):
        """Initialize Firebase Admin SDK."""
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            if not firebase_admin._apps:
                # Try JSON string from env var first (for Railway/cloud deploys)
                sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
                if sa_json:
                    import json as _json

                    cred = credentials.Certificate(_json.loads(sa_json))
                else:
                    # Fall back to file path
                    cred = credentials.Certificate(
                        settings.FIREBASE_SERVICE_ACCOUNT_PATH
                    )
                firebase_admin.initialize_app(
                    cred, {"storageBucket": settings.FIREBASE_STORAGE_BUCKET}
                )
            self.db = firestore.client()
        except Exception as e:
            print(f"Firebase init failed, falling back to local mode: {e}")
            self.mode = "local"

    def _load_local_data(self):
        """Load data from local JSON file."""
        if self._data is None:
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except FileNotFoundError:
                self._data = {
                    "trucks": [],
                    "analytics": [],
                    "leads": [],
                    "testimonials": [],
                }
        return self._data

    def _save_local_data(self):
        """Save data to local JSON file."""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)

    # ─── Trucks ───────────────────────────────────────────────

    def get_trucks(self, filters: Optional[dict] = None) -> list:
        """Get all trucks with optional filters."""
        if self.mode == "local":
            data = self._load_local_data()
            trucks = data.get("trucks", [])
            if filters:
                if filters.get("category"):
                    trucks = [t for t in trucks if t["category"] == filters["category"]]
                if filters.get("condition"):
                    trucks = [
                        t for t in trucks if t["condition"] == filters["condition"]
                    ]
                if filters.get("usage"):
                    trucks = [t for t in trucks if t["usage"] == filters["usage"]]
                if filters.get("status"):
                    trucks = [t for t in trucks if t["status"] == filters["status"]]
                if filters.get("min_price"):
                    trucks = [
                        t for t in trucks if t["price"] >= int(filters["min_price"])
                    ]
                if filters.get("max_price"):
                    trucks = [
                        t for t in trucks if t["price"] <= int(filters["max_price"])
                    ]
                if filters.get("search"):
                    q = filters["search"].lower()
                    trucks = [
                        t
                        for t in trucks
                        if q in t["title"].lower() or q in t["description"].lower()
                    ]
            return trucks
        else:
            # Build a stable cache key from the filters
            cache_key = f"trucks:{json.dumps(filters, sort_keys=True) if filters else 'all'}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            ref = self.db.collection("trucks")
            if filters:
                if filters.get("category"):
                    ref = ref.where("category", "==", filters["category"])
                if filters.get("condition"):
                    ref = ref.where("condition", "==", filters["condition"])
                if filters.get("usage"):
                    ref = ref.where("usage", "==", filters["usage"])
                if filters.get("status"):
                    ref = ref.where("status", "==", filters["status"])
            docs = ref.stream()
            result = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            self._cache_set(cache_key, result)
            return result

    def get_truck(self, truck_id: str) -> Optional[dict]:
        """Get a single truck by ID."""
        if self.mode == "local":
            data = self._load_local_data()
            for truck in data.get("trucks", []):
                if truck["id"] == truck_id:
                    return truck
            return None
        else:
            cache_key = f"truck:{truck_id}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            doc = self.db.collection("trucks").document(truck_id).get()
            if doc.exists:
                result = {"id": doc.id, **doc.to_dict()}
                self._cache_set(cache_key, result)
                return result
            return None

    def get_truck_by_slug(self, slug: str) -> Optional[dict]:
        """Get a single truck by slug."""
        if self.mode == "local":
            data = self._load_local_data()
            for truck in data.get("trucks", []):
                if truck.get("slug") == slug:
                    return truck
            return None
        else:
            cache_key = f"truck_slug:{slug}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            docs = (
                self.db.collection("trucks").where("slug", "==", slug).limit(1).stream()
            )
            for doc in docs:
                result = {"id": doc.id, **doc.to_dict()}
                self._cache_set(cache_key, result)
                return result
            return None

    def create_truck(self, truck_data: dict) -> dict:
        """Create a new truck."""
        truck_data["id"] = str(uuid.uuid4())
        truck_data["created_at"] = datetime.now(timezone.utc).isoformat()
        truck_data["views"] = 0

        if self.mode == "local":
            data = self._load_local_data()
            data["trucks"].append(truck_data)
            self._save_local_data()
        else:
            self.db.collection("trucks").document(truck_data["id"]).set(truck_data)
            self._cache_invalidate("trucks:")
            self._cache_invalidate("featured:")
            self._cache_invalidate("fleet_stats")
        return truck_data

    def update_truck(self, truck_id: str, update_data: dict) -> Optional[dict]:
        """Update an existing truck."""
        if self.mode == "local":
            data = self._load_local_data()
            for i, truck in enumerate(data["trucks"]):
                if truck["id"] == truck_id:
                    data["trucks"][i].update(update_data)
                    self._save_local_data()
                    return data["trucks"][i]
            return None
        else:
            ref = self.db.collection("trucks").document(truck_id)
            ref.update(update_data)
            # Invalidate related caches
            self._cache_invalidate("truck:")
            self._cache_invalidate("trucks:")
            self._cache_invalidate("featured:")
            self._cache_invalidate("fleet_stats")
            self._cache_invalidate("most_viewed")
            return {"id": truck_id, **ref.get().to_dict()}

    def delete_truck(self, truck_id: str) -> bool:
        """Delete a truck."""
        if self.mode == "local":
            data = self._load_local_data()
            original_len = len(data["trucks"])
            data["trucks"] = [t for t in data["trucks"] if t["id"] != truck_id]
            if len(data["trucks"]) < original_len:
                self._save_local_data()
                return True
            return False
        else:
            self.db.collection("trucks").document(truck_id).delete()
            self._cache_invalidate("truck:")
            self._cache_invalidate("trucks:")
            self._cache_invalidate("featured:")
            self._cache_invalidate("fleet_stats")
            self._cache_invalidate("most_viewed")
            return True

    def increment_views(self, truck_id: str):
        """Increment view count for a truck."""
        if self.mode == "local":
            data = self._load_local_data()
            for truck in data["trucks"]:
                if truck["id"] == truck_id:
                    truck["views"] = truck.get("views", 0) + 1
                    self._save_local_data()
                    break
        else:
            from google.cloud.firestore_v1 import Increment

            self.db.collection("trucks").document(truck_id).update(
                {"views": Increment(1)}
            )
            # Don't invalidate cache here — views are cosmetic, avoids extra reads

    # ─── Featured & Stats ─────────────────────────────────────

    def get_featured_trucks(self, limit: int = 6) -> list:
        """Get featured trucks for homepage."""
        if self.mode == "local":
            data = self._load_local_data()
            featured = [
                t
                for t in data["trucks"]
                if t.get("featured") and t["status"] == "available"
            ]
            return featured[:limit]
        else:
            cache_key = f"featured:{limit}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            docs = (
                self.db.collection("trucks")
                .where("featured", "==", True)
                .where("status", "==", "available")
                .limit(limit)
                .stream()
            )
            result = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            self._cache_set(cache_key, result)
            return result

    def get_fleet_stats(self) -> dict:
        """Get fleet status counters."""
        if self.mode == "local":
            data = self._load_local_data()
            trucks = data.get("trucks", [])
            return {
                "total": len(trucks),
                "available": len([t for t in trucks if t["status"] == "available"]),
                "rented": len([t for t in trucks if t["status"] == "rented"]),
                "sold": len([t for t in trucks if t["status"] == "sold"]),
            }
        else:
            cache_key = "fleet_stats"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            trucks = [doc.to_dict() for doc in self.db.collection("trucks").stream()]
            result = {
                "total": len(trucks),
                "available": len([t for t in trucks if t.get("status") == "available"]),
                "rented": len([t for t in trucks if t.get("status") == "rented"]),
                "sold": len([t for t in trucks if t.get("status") == "sold"]),
            }
            self._cache_set(cache_key, result)
            return result

    # ─── Leads ────────────────────────────────────────────────

    def create_lead(self, lead_data: dict) -> dict:
        """Create a new lead."""
        lead_data["id"] = str(uuid.uuid4())
        lead_data["date"] = datetime.now(timezone.utc).isoformat()

        if self.mode == "local":
            data = self._load_local_data()
            data.setdefault("leads", []).append(lead_data)
            self._save_local_data()
        else:
            self.db.collection("leads").document(lead_data["id"]).set(lead_data)
            self._cache_invalidate("leads")
        return lead_data

    def get_leads(self) -> list:
        """Get all leads."""
        if self.mode == "local":
            data = self._load_local_data()
            return data.get("leads", [])
        else:
            cache_key = "leads"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            docs = (
                self.db.collection("leads")
                .order_by("date", direction="DESCENDING")
                .stream()
            )
            result = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            self._cache_set(cache_key, result)
            return result

    # ─── Analytics ────────────────────────────────────────────

    def record_analytics(self, event: dict):
        """Record an analytics event."""
        event["id"] = str(uuid.uuid4())
        event["timestamp"] = datetime.now(timezone.utc).isoformat()

        if self.mode == "local":
            data = self._load_local_data()
            data.setdefault("analytics", []).append(event)
            # Keep only last 10000 events locally
            if len(data["analytics"]) > 10000:
                data["analytics"] = data["analytics"][-10000:]
            self._save_local_data()
        else:
            self.db.collection("analytics").document(event["id"]).set(event)
            # Don't invalidate analytics cache on every write — too frequent

    def get_analytics(self, days: int = 30) -> list:
        """Get analytics events for the last N days."""
        if self.mode == "local":
            data = self._load_local_data()
            return data.get("analytics", [])
        else:
            cache_key = f"analytics:{days}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            from datetime import timedelta

            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            docs = (
                self.db.collection("analytics")
                .where("timestamp", ">=", cutoff)
                .order_by("timestamp", direction="DESCENDING")
                .stream()
            )
            result = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            self._cache_set(cache_key, result)
            return result

    # ─── Testimonials ─────────────────────────────────────────

    def get_testimonials(self) -> list:
        """Get all testimonials."""
        if self.mode == "local":
            data = self._load_local_data()
            return data.get("testimonials", [])
        else:
            cache_key = "testimonials"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            docs = self.db.collection("testimonials").stream()
            result = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            self._cache_set(cache_key, result)
            return result

    def create_testimonial(self, testimonial_data: dict) -> dict:
        """Create a new testimonial (image card)."""
        testimonial_data["id"] = str(uuid.uuid4())
        testimonial_data["created_at"] = datetime.now(timezone.utc).isoformat()

        if self.mode == "local":
            data = self._load_local_data()
            data.setdefault("testimonials", []).append(testimonial_data)
            self._save_local_data()
        else:
            self.db.collection("testimonials").document(testimonial_data["id"]).set(
                testimonial_data
            )
            self._cache_invalidate("testimonials")
        return testimonial_data

    def delete_testimonial(self, testimonial_id: str) -> bool:
        """Delete a testimonial."""
        if self.mode == "local":
            data = self._load_local_data()
            original_len = len(data.get("testimonials", []))
            data["testimonials"] = [
                t for t in data.get("testimonials", []) if t.get("id") != testimonial_id
            ]
            if len(data["testimonials"]) < original_len:
                self._save_local_data()
                return True
            return False
        else:
            self.db.collection("testimonials").document(testimonial_id).delete()
            self._cache_invalidate("testimonials")
            return True

    # ─── Most Viewed Trucks ──────────────────────────────────

    def get_most_viewed(self, limit: int = 5) -> list:
        """Get most viewed trucks."""
        if self.mode == "local":
            data = self._load_local_data()
            trucks = sorted(
                data.get("trucks", []), key=lambda t: t.get("views", 0), reverse=True
            )
            return trucks[:limit]
        else:
            cache_key = f"most_viewed:{limit}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            docs = (
                self.db.collection("trucks")
                .order_by("views", direction="DESCENDING")
                .limit(limit)
                .stream()
            )
            result = [{"id": doc.id, **doc.to_dict()} for doc in docs]
            self._cache_set(cache_key, result)
            return result

    # ─── Settings ─────────────────────────────────────────────

    def get_settings(self) -> dict:
        """Get app settings (phone numbers, etc.)."""
        defaults = {
            "whatsapp": "",
            "phone_call": "",
            "phone_sms": "",
        }
        if self.mode == "local":
            data = self._load_local_data()
            return {**defaults, **data.get("settings", {})}
        else:
            cache_key = "settings"
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

            try:
                doc = self.db.collection("settings").document("phone_numbers").get()
                if doc.exists:
                    result = {**defaults, **doc.to_dict()}
                    self._cache_set(cache_key, result)
                    return result
            except Exception as e:
                print(f"Error loading settings: {e}")
            return defaults

    def update_settings(self, settings_data: dict) -> dict:
        """Update app settings."""
        if self.mode == "local":
            data = self._load_local_data()
            data.setdefault("settings", {}).update(settings_data)
            self._save_local_data()
            return data["settings"]
        else:
            self.db.collection("settings").document("phone_numbers").set(
                settings_data, merge=True
            )
            self._cache_invalidate("settings")
            return settings_data


# Singleton
db = DatabaseService()
