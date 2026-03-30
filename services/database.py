"""
ASAP Food Trailer - Database Service
PostgreSQL (Supabase) with psycopg2 + in-memory cache.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2 import pool

from config import settings

# ─── Cache TTL (seconds) ─────────────────────────────────────
CACHE_TTL = 1800  # 30 minutes


class DatabaseService:
    """PostgreSQL database service with connection pooling and caching."""

    def __init__(self):
        self._pool = None
        self._cache: dict = {}
        self._init_pool()
        self._create_tables()
        self._seed_from_json()

    # ─── Connection Pool ──────────────────────────────────────

    def _init_pool(self):
        """Initialize PostgreSQL connection pool."""
        db_url = settings.DATABASE_URL
        if not db_url:
            print("[WARN] DATABASE_URL not set. Database will not work.")
            return
        try:
            from urllib.parse import urlparse, quote
            import re

            parsed = urlparse(db_url)
            host = parsed.hostname or ""
            password = parsed.password or ""

            # Auto-convert Supabase direct URL → pooler URL (IPv4 compatible)
            # Direct:  db.<ref>.supabase.co:5432
            # Pooler:  aws-0-<region>.pooler.supabase.com:6543
            match = re.match(r"db\.([a-z0-9]+)\.supabase\.co", host)
            if match:
                ref = match.group(1)
                print(f"[DB] Supabase project detected: {ref}")
                print(f"[DB] Converting to pooler URL (IPv4 compatible)...")

                # Try common AWS regions for Supabase pooler
                regions = ["us-east-1", "us-west-1", "eu-west-1", "eu-central-1", "ap-southeast-1"]
                connected = False

                for region in regions:
                    pooler_host = f"aws-0-{region}.pooler.supabase.com"
                    pooler_user = f"postgres.{ref}"
                    try:
                        print(f"[DB] Trying pooler: {pooler_host} ...")
                        self._pool = pool.ThreadedConnectionPool(
                            1, 5,
                            host=pooler_host, port=6543,
                            dbname="postgres",
                            user=pooler_user,
                            password=password,
                            sslmode="require",
                            connect_timeout=10
                        )
                        print(f"[DB] ✓ Connected via pooler ({region})")
                        connected = True
                        break
                    except Exception as e:
                        print(f"[DB] ✗ {region}: {e}")
                        continue

                if not connected:
                    # Fallback: try direct connection anyway
                    print("[DB] All pooler regions failed, trying direct connection...")
                    self._pool = pool.ThreadedConnectionPool(1, 5, db_url)
            else:
                # Non-Supabase URL: use as-is
                self._pool = pool.ThreadedConnectionPool(1, 5, db_url)

            print("[DB] PostgreSQL connection pool created")
        except Exception as e:
            print(f"[ERROR] PostgreSQL connection failed: {e}")
            self._pool = None

    def _get_conn(self):
        """Get a connection from the pool."""
        if not self._pool:
            raise Exception("Database pool not initialized")
        return self._pool.getconn()

    def _put_conn(self, conn):
        """Return a connection to the pool."""
        if self._pool and conn:
            self._pool.putconn(conn)

    def _create_tables(self):
        """Create tables if they don't exist."""
        if not self._pool:
            return
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trucks (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        slug TEXT UNIQUE,
                        description TEXT,
                        price INTEGER DEFAULT 0,
                        category TEXT DEFAULT 'truck',
                        condition TEXT DEFAULT 'new',
                        usage TEXT DEFAULT 'sale',
                        status TEXT DEFAULT 'available',
                        featured BOOLEAN DEFAULT FALSE,
                        specs JSONB DEFAULT '{}',
                        images JSONB DEFAULT '[]',
                        views INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS leads (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        email TEXT,
                        phone TEXT,
                        message TEXT,
                        truck_id TEXT,
                        source TEXT,
                        date TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS analytics (
                        id TEXT PRIMARY KEY,
                        event_type TEXT,
                        page TEXT,
                        data JSONB DEFAULT '{}',
                        ip TEXT,
                        user_agent TEXT,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS testimonials (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        description TEXT,
                        image_url TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    );

                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id TEXT PRIMARY KEY,
                        visitor_id TEXT,
                        visitor_name TEXT,
                        visitor_email TEXT,
                        channel_id TEXT,
                        status TEXT DEFAULT 'active',
                        page TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_trucks_status ON trucks(status);
                    CREATE INDEX IF NOT EXISTS idx_trucks_featured ON trucks(featured);
                    CREATE INDEX IF NOT EXISTS idx_trucks_category ON trucks(category);
                    CREATE INDEX IF NOT EXISTS idx_trucks_slug ON trucks(slug);
                    CREATE INDEX IF NOT EXISTS idx_leads_date ON leads(date);
                    CREATE INDEX IF NOT EXISTS idx_analytics_timestamp ON analytics(timestamp);
                """)
            conn.commit()
            print("[DB] Tables created/verified")
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Create tables failed: {e}")
        finally:
            self._put_conn(conn)

    def _seed_from_json(self):
        """Auto-seed from data/seed.json if tables are empty or FORCE_RESEED=1."""
        if not self._pool:
            return
        force = os.environ.get("FORCE_RESEED", "0") == "1"
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM trucks")
                count = cur.fetchone()[0]
                if count > 0 and not force:
                    print(f"[DB] Trucks table has {count} rows, skipping seed")
                    return
                if force and count > 0:
                    print(f"[DB] FORCE_RESEED: Clearing all tables...")
                    for table in ["settings", "analytics", "testimonials", "leads", "trucks"]:
                        cur.execute(f"DELETE FROM {table}")
                    conn.commit()
                    print("[DB] Tables cleared")

            # Load seed data
            seed_file = os.path.join(settings.DATA_DIR, "seed.json")
            if not os.path.exists(seed_file):
                print("[DB] No seed.json found, skipping seed")
                return

            with open(seed_file, "r", encoding="utf-8") as f:
                seed = json.load(f)

            with conn.cursor() as cur:
                # Seed trucks (handle duplicate slugs from Firebase)
                trucks = seed.get("trucks", [])
                seen_slugs = set()
                for t in trucks:
                    slug = t.get("slug", "")
                    # Auto-fix duplicate slugs
                    if slug in seen_slugs or not slug:
                        base = slug or "truck"
                        counter = 2
                        while f"{base}-{counter}" in seen_slugs:
                            counter += 1
                        slug = f"{base}-{counter}"
                    seen_slugs.add(slug)
                    cur.execute("""
                        INSERT INTO trucks (id, title, slug, description, price, category, condition, usage, status, featured, specs, images, views, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, [
                        t.get("id", str(uuid.uuid4())), t.get("title", ""),
                        slug, t.get("description", ""),
                        int(t.get("price", 0)), t.get("category", "truck"),
                        t.get("condition", "new"), t.get("usage", "sale"),
                        t.get("status", "available"), bool(t.get("featured", False)),
                        json.dumps(t.get("specs", {})), json.dumps(t.get("images", [])),
                        int(t.get("views", 0)), t.get("created_at")
                    ])

                # Seed leads
                leads = seed.get("leads", [])
                for l in leads:
                    cur.execute("""
                        INSERT INTO leads (id, name, email, phone, message, truck_id, source, date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, [
                        l.get("id", str(uuid.uuid4())),
                        l.get("name", l.get("customer_name", "")),
                        l.get("email", l.get("customer_email", "")),
                        l.get("phone", l.get("customer_phone", "")),
                        l.get("message", ""), l.get("truck_id", ""),
                        l.get("source", ""), l.get("date")
                    ])

                # Seed testimonials
                testimonials = seed.get("testimonials", [])
                for tm in testimonials:
                    cur.execute("""
                        INSERT INTO testimonials (id, title, description, image_url, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, [
                        tm.get("id", str(uuid.uuid4())),
                        tm.get("title", tm.get("name", "")),
                        tm.get("description", tm.get("text", "")),
                        tm.get("image_url", tm.get("image", "")),
                        tm.get("created_at")
                    ])

                # Seed settings
                settings_data = seed.get("settings", {})
                for key, value in settings_data.items():
                    cur.execute("""
                        INSERT INTO settings (key, value) VALUES (%s, %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, [key, str(value)])

            conn.commit()
            print(f"[DB] Seeded from seed.json: {len(trucks)} trucks, {len(leads)} leads, {len(testimonials)} testimonials")

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Seed failed: {e}")
        finally:
            self._put_conn(conn)

    # ─── Cache helpers ────────────────────────────────────────

    def _cache_get(self, key: str):
        entry = self._cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
        return None

    def _cache_get_fallback(self, key: str):
        entry = self._cache.get(key)
        if entry:
            return entry["data"]
        return None

    def _cache_set(self, key: str, data):
        self._cache[key] = {"data": data, "ts": time.time()}

    def _cache_invalidate(self, prefix: str = ""):
        if not prefix:
            self._cache.clear()
        else:
            keys = [k for k in self._cache if k.startswith(prefix)]
            for k in keys:
                del self._cache[k]

    # ─── Helper: execute query ────────────────────────────────

    def _execute(self, query, params=None, fetch="all"):
        """Execute a query and return results."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch == "all":
                    return [dict(r) for r in cur.fetchall()]
                elif fetch == "one":
                    r = cur.fetchone()
                    return dict(r) if r else None
                elif fetch == "none":
                    conn.commit()
                    return None
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._put_conn(conn)

    # ─── Trucks ───────────────────────────────────────────────

    def get_trucks(self, filters: Optional[dict] = None) -> list:
        cache_key = f"trucks:{json.dumps(filters, sort_keys=True) if filters else 'all'}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            conditions = []
            params = []
            if filters:
                if filters.get("category"):
                    conditions.append("category = %s")
                    params.append(filters["category"])
                if filters.get("condition"):
                    conditions.append("condition = %s")
                    params.append(filters["condition"])
                if filters.get("usage"):
                    conditions.append("usage = %s")
                    params.append(filters["usage"])
                if filters.get("status"):
                    conditions.append("status = %s")
                    params.append(filters["status"])
                if filters.get("min_price"):
                    conditions.append("price >= %s")
                    params.append(int(filters["min_price"]))
                if filters.get("max_price"):
                    conditions.append("price <= %s")
                    params.append(int(filters["max_price"]))
                if filters.get("search"):
                    conditions.append("(LOWER(title) LIKE %s OR LOWER(description) LIKE %s)")
                    q = f"%{filters['search'].lower()}%"
                    params.extend([q, q])

            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            result = self._execute(f"SELECT * FROM trucks{where} ORDER BY created_at DESC", params)
            # Convert JSONB fields
            for r in result:
                if isinstance(r.get("specs"), str):
                    r["specs"] = json.loads(r["specs"])
                if isinstance(r.get("images"), str):
                    r["images"] = json.loads(r["images"])
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_trucks: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    def get_truck(self, truck_id: str) -> Optional[dict]:
        cache_key = f"truck:{truck_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute("SELECT * FROM trucks WHERE id = %s", [truck_id], fetch="one")
            if result:
                if isinstance(result.get("specs"), str):
                    result["specs"] = json.loads(result["specs"])
                if isinstance(result.get("images"), str):
                    result["images"] = json.loads(result["images"])
                self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_truck: {e}")
            return self._cache_get_fallback(cache_key)

    def get_truck_by_slug(self, slug: str) -> Optional[dict]:
        cache_key = f"truck_slug:{slug}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute("SELECT * FROM trucks WHERE slug = %s", [slug], fetch="one")
            if result:
                if isinstance(result.get("specs"), str):
                    result["specs"] = json.loads(result["specs"])
                if isinstance(result.get("images"), str):
                    result["images"] = json.loads(result["images"])
                self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_truck_by_slug: {e}")
            return self._cache_get_fallback(cache_key)

    def create_truck(self, truck_data: dict) -> dict:
        truck_data["id"] = str(uuid.uuid4())
        truck_data["created_at"] = datetime.now(timezone.utc).isoformat()
        truck_data["views"] = 0
        try:
            self._execute("""
                INSERT INTO trucks (id, title, slug, description, price, category, condition, usage, status, featured, specs, images, views, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [
                truck_data["id"], truck_data.get("title", ""),
                truck_data.get("slug", ""), truck_data.get("description", ""),
                truck_data.get("price", 0), truck_data.get("category", "truck"),
                truck_data.get("condition", "new"), truck_data.get("usage", "sale"),
                truck_data.get("status", "available"), truck_data.get("featured", False),
                json.dumps(truck_data.get("specs", {})),
                json.dumps(truck_data.get("images", [])),
                0, truck_data["created_at"]
            ], fetch="none")
            self._cache_invalidate("trucks:")
            self._cache_invalidate("featured:")
            self._cache_invalidate("fleet_stats")
        except Exception as e:
            print(f"[ERROR] create_truck: {e}")
        return truck_data

    def update_truck(self, truck_id: str, update_data: dict) -> Optional[dict]:
        try:
            sets = []
            params = []
            for key, val in update_data.items():
                if key in ("specs", "images"):
                    val = json.dumps(val) if not isinstance(val, str) else val
                sets.append(f"{key} = %s")
                params.append(val)
            params.append(truck_id)
            self._execute(f"UPDATE trucks SET {', '.join(sets)} WHERE id = %s", params, fetch="none")
            self._cache_invalidate("truck:")
            self._cache_invalidate("trucks:")
            self._cache_invalidate("featured:")
            self._cache_invalidate("fleet_stats")
            self._cache_invalidate("most_viewed")
            return self.get_truck(truck_id)
        except Exception as e:
            print(f"[ERROR] update_truck: {e}")
            return None

    def delete_truck(self, truck_id: str) -> bool:
        try:
            self._execute("DELETE FROM trucks WHERE id = %s", [truck_id], fetch="none")
            self._cache_invalidate("truck:")
            self._cache_invalidate("trucks:")
            self._cache_invalidate("featured:")
            self._cache_invalidate("fleet_stats")
            self._cache_invalidate("most_viewed")
            return True
        except Exception as e:
            print(f"[ERROR] delete_truck: {e}")
            return False

    def increment_views(self, truck_id: str):
        try:
            self._execute("UPDATE trucks SET views = views + 1 WHERE id = %s", [truck_id], fetch="none")
        except Exception as e:
            print(f"[ERROR] increment_views: {e}")

    # ─── Featured & Stats ─────────────────────────────────────

    def get_featured_trucks(self, limit: int = 6) -> list:
        cache_key = f"featured:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute(
                "SELECT * FROM trucks WHERE featured = TRUE AND status = 'available' LIMIT %s",
                [limit]
            )
            for r in result:
                if isinstance(r.get("specs"), str):
                    r["specs"] = json.loads(r["specs"])
                if isinstance(r.get("images"), str):
                    r["images"] = json.loads(r["images"])
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_featured_trucks: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    def get_fleet_stats(self) -> dict:
        cache_key = "fleet_stats"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            rows = self._execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'available') as available,
                    COUNT(*) FILTER (WHERE status = 'rented') as rented,
                    COUNT(*) FILTER (WHERE status = 'sold') as sold
                FROM trucks
            """, fetch="one")
            result = {
                "total": rows["total"] if rows else 0,
                "available": rows["available"] if rows else 0,
                "rented": rows["rented"] if rows else 0,
                "sold": rows["sold"] if rows else 0,
            }
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_fleet_stats: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else {"total": 0, "available": 0, "rented": 0, "sold": 0}

    # ─── Leads ────────────────────────────────────────────────

    def create_lead(self, lead_data: dict) -> dict:
        lead_data["id"] = str(uuid.uuid4())
        lead_data["date"] = datetime.now(timezone.utc).isoformat()
        try:
            self._execute("""
                INSERT INTO leads (id, name, email, phone, message, truck_id, source, date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, [
                lead_data["id"], lead_data.get("name", ""),
                lead_data.get("email", ""), lead_data.get("phone", ""),
                lead_data.get("message", ""), lead_data.get("truck_id", ""),
                lead_data.get("source", ""), lead_data["date"]
            ], fetch="none")
            self._cache_invalidate("leads")
        except Exception as e:
            print(f"[ERROR] create_lead: {e}")
        return lead_data

    def get_leads(self) -> list:
        cache_key = "leads"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute("SELECT * FROM leads ORDER BY date DESC")
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_leads: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    # ─── Analytics ────────────────────────────────────────────

    def record_analytics(self, event: dict):
        event["id"] = str(uuid.uuid4())
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            self._execute("""
                INSERT INTO analytics (id, event_type, page, data, ip, user_agent, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, [
                event["id"], event.get("event_type", ""),
                event.get("page", ""), json.dumps(event.get("data", {})),
                event.get("ip", ""), event.get("user_agent", ""),
                event["timestamp"]
            ], fetch="none")
        except Exception as e:
            print(f"[ERROR] record_analytics: {e}")

    def get_analytics(self, days: int = 30) -> list:
        cache_key = f"analytics:{days}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            result = self._execute(
                "SELECT * FROM analytics WHERE timestamp >= %s ORDER BY timestamp DESC",
                [cutoff]
            )
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_analytics: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    # ─── Testimonials ─────────────────────────────────────────

    def get_testimonials(self) -> list:
        cache_key = "testimonials"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute("SELECT * FROM testimonials ORDER BY created_at DESC")
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_testimonials: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    def create_testimonial(self, testimonial_data: dict) -> dict:
        testimonial_data["id"] = str(uuid.uuid4())
        testimonial_data["created_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._execute("""
                INSERT INTO testimonials (id, title, description, image_url, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, [
                testimonial_data["id"], testimonial_data.get("title", ""),
                testimonial_data.get("description", ""),
                testimonial_data.get("image_url", ""),
                testimonial_data["created_at"]
            ], fetch="none")
            self._cache_invalidate("testimonials")
        except Exception as e:
            print(f"[ERROR] create_testimonial: {e}")
        return testimonial_data

    def delete_testimonial(self, testimonial_id: str) -> bool:
        try:
            self._execute("DELETE FROM testimonials WHERE id = %s", [testimonial_id], fetch="none")
            self._cache_invalidate("testimonials")
            return True
        except Exception as e:
            print(f"[ERROR] delete_testimonial: {e}")
            return False

    # ─── Most Viewed Trucks ──────────────────────────────────

    def get_most_viewed(self, limit: int = 5) -> list:
        cache_key = f"most_viewed:{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute(
                "SELECT * FROM trucks ORDER BY views DESC LIMIT %s",
                [limit]
            )
            for r in result:
                if isinstance(r.get("specs"), str):
                    r["specs"] = json.loads(r["specs"])
                if isinstance(r.get("images"), str):
                    r["images"] = json.loads(r["images"])
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_most_viewed: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    # ─── Settings ─────────────────────────────────────────────

    def get_settings(self) -> dict:
        defaults = {"whatsapp": "", "phone_call": "", "phone_sms": ""}
        cache_key = "settings"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            rows = self._execute("SELECT key, value FROM settings")
            result = {**defaults}
            for row in rows:
                result[row["key"]] = row["value"]
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_settings: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else defaults

    def update_settings(self, settings_data: dict) -> dict:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                for key, value in settings_data.items():
                    cur.execute("""
                        INSERT INTO settings (key, value) VALUES (%s, %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, [key, str(value)])
            conn.commit()
            self._put_conn(conn)
            self._cache_invalidate("settings")
            return settings_data
        except Exception as e:
            print(f"[ERROR] update_settings: {e}")
            return settings_data

    # ─── Chat Sessions ────────────────────────────────────────

    def save_chat_session(self, session_data: dict) -> dict:
        session_data.setdefault("id", str(uuid.uuid4()))
        session_data["created_at"] = datetime.now(timezone.utc).isoformat()
        session_data.setdefault("status", "active")
        try:
            self._execute("""
                INSERT INTO chat_sessions (id, visitor_id, visitor_name, visitor_email, channel_id, status, page, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status
            """, [
                session_data["id"], session_data.get("visitor_id", ""),
                session_data.get("visitor_name", ""), session_data.get("visitor_email", ""),
                session_data.get("channel_id", ""), session_data.get("status", "active"),
                session_data.get("page", ""), session_data["created_at"]
            ], fetch="none")
            self._cache_invalidate("chat_sessions")
        except Exception as e:
            print(f"[ERROR] save_chat_session: {e}")
        return session_data

    def get_chat_sessions(self) -> list:
        cache_key = "chat_sessions"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._execute("SELECT * FROM chat_sessions ORDER BY created_at DESC")
            self._cache_set(cache_key, result)
            return result
        except Exception as e:
            print(f"[ERROR] get_chat_sessions: {e}")
            fallback = self._cache_get_fallback(cache_key)
            return fallback if fallback is not None else []

    def update_chat_session(self, session_id: str, update_data: dict) -> dict:
        try:
            sets = []
            params = []
            for key, val in update_data.items():
                sets.append(f"{key} = %s")
                params.append(val)
            params.append(session_id)
            self._execute(f"UPDATE chat_sessions SET {', '.join(sets)} WHERE id = %s", params, fetch="none")
            self._cache_invalidate("chat_sessions")
            return {"id": session_id, **update_data}
        except Exception as e:
            print(f"[ERROR] update_chat_session: {e}")
            return {}


# Singleton
db = DatabaseService()
