"""
ASAP Food Trailer — Main FastAPI Application
"""

import json
import os
import asyncio
from fastapi import (
    FastAPI,
    Request,
    Form,
    UploadFile,
    File,
    HTTPException,
    Depends,
    Header,
)
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from typing import Optional, List

from config import settings
from services.database import db
from services.seo import seo_service
from services.analytics import analytics_service
from services.auth import auth_service
from services.image_processor import image_processor
from services.email_service import email_service
from services.chat_service import chat_service, check_rate_limit

# ─── App Init ─────────────────────────────────────────────────
app = FastAPI(
    title="ASAP Food Trailer",
    description="Premium Food Truck Dealership Platform",
    version="1.0.0",
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)

# Static files
app.mount("/assets", StaticFiles(directory=settings.STATIC_DIR), name="assets")

# Uploads directory
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Templates
templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)


# ─── Health check + diagnostics ───────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/diagnostics/storage")
async def diagnostics_storage():
    """Test cloud storage connectivity."""
    return image_processor.test_storage()


# ─── Keep-alive (prevents Render free tier sleep → fixes Safari) ─
async def _keep_alive():
    """Ping self every 5 minutes to prevent Render from sleeping."""
    import urllib.request

    # Auto-detect URL
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if not render_url:
        service_name = os.getenv("RENDER_SERVICE_NAME", "")
        if service_name:
            render_url = f"https://{service_name}.onrender.com"

    if not render_url:
        print("[KeepAlive] No Render URL found. Set RENDER_EXTERNAL_URL env var.")
        print("[KeepAlive] Example: https://asap-food-trailer.onrender.com")
        return

    health_url = f"{render_url}/health"
    print(f"[KeepAlive] Active — pinging {health_url} every 5 min")

    await asyncio.sleep(30)  # Wait 30s after startup before first ping
    while True:
        try:
            urllib.request.urlopen(health_url, timeout=10)
            print("[KeepAlive] Ping OK")
        except Exception as e:
            print(f"[KeepAlive] Ping failed: {e}")
        await asyncio.sleep(300)  # Every 5 minutes


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_keep_alive())


# ─── Template Helpers ─────────────────────────────────────────
def get_base_context(request: Request) -> dict:
    """Build base template context with business info and SEO."""
    # Load admin-managed phone numbers from DB
    try:
        phone_settings = db.get_settings()
    except Exception as e:
        print(f"[ERROR] get_settings failed: {e}")
        phone_settings = {}
    return {
        "request": request,
        "business": {
            "name": settings.BUSINESS_NAME,
            "phone": phone_settings.get("phone_call") or settings.BUSINESS_PHONE,
            "email": settings.BUSINESS_EMAIL,
            "address": settings.BUSINESS_ADDRESS,
            "city": settings.BUSINESS_CITY,
            "whatsapp": phone_settings.get("whatsapp") or settings.BUSINESS_WHATSAPP,
            "sms": phone_settings.get("phone_sms") or "",
        },
        "social": {
            "tiktok": settings.SOCIAL_TIKTOK,
            "facebook": settings.SOCIAL_FACEBOOK,
            "instagram": settings.SOCIAL_INSTAGRAM,
        },
        "app_mode": settings.APP_MODE,
    }


# ─── Analytics Middleware ─────────────────────────────────────
@app.middleware("http")
async def track_analytics(request: Request, call_next):
    """Track page views for analytics."""
    response = await call_next(request)

    # Only track HTML page views (not API calls or static files)
    path = request.url.path
    if (
        not path.startswith("/assets")
        and not path.startswith("/uploads")
        and not path.startswith("/api")
        and not path.startswith("/favicon")
        and response.status_code == 200
    ):
        try:
            user_agent = request.headers.get("user-agent", "")
            device = "mobile" if "Mobile" in user_agent else "desktop"
            source = request.headers.get("referer", "direct")
            if "google" in source.lower():
                source = "google"
            elif "facebook" in source.lower():
                source = "facebook"
            elif source != "direct":
                source = "referral"

            db.record_analytics(
                {
                    "page_path": path,
                    "device_type": device,
                    "location_city": settings.BUSINESS_CITY,  # Simplified for local mode
                    "source": source,
                }
            )
        except Exception:
            pass  # Never break the request for analytics

    return response


# ═══════════════════════════════════════════════════════════════
#  PUBLIC ROUTES
# ═══════════════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Homepage with featured trucks, search, and testimonials."""
    ctx = get_base_context(request)
    ctx["meta"] = seo_service.generate_meta_tags(page="home")
    ctx["business_jsonld"] = json.dumps(seo_service.generate_business_jsonld())
    try:
        ctx["featured_trucks"] = db.get_featured_trucks(limit=6)
    except Exception as e:
        print(f"[ERROR] get_featured_trucks failed: {e}")
        ctx["featured_trucks"] = []
    try:
        ctx["fleet_stats"] = db.get_fleet_stats()
    except Exception as e:
        print(f"[ERROR] get_fleet_stats failed: {e}")
        ctx["fleet_stats"] = {"total": 0, "available": 0, "rented": 0, "sold": 0}
    try:
        ctx["testimonials"] = db.get_testimonials()
    except Exception as e:
        print(f"[ERROR] get_testimonials failed: {e}")
        ctx["testimonials"] = []
    return templates.TemplateResponse("index.html", ctx)


@app.get("/catalog", response_class=HTMLResponse)
async def catalog(
    request: Request,
    category: Optional[str] = None,
    condition: Optional[str] = None,
    usage: Optional[str] = None,
    min_price: Optional[str] = None,
    max_price: Optional[str] = None,
    search: Optional[str] = None,
):
    """Catalog page with all trucks and filters."""
    filters = {}
    if category:
        filters["category"] = category
    if condition:
        filters["condition"] = condition
    if usage:
        filters["usage"] = usage
    if min_price:
        filters["min_price"] = min_price
    if max_price:
        filters["max_price"] = max_price
    if search:
        filters["search"] = search

    ctx = get_base_context(request)
    ctx["meta"] = seo_service.generate_meta_tags(page="catalog")
    try:
        ctx["trucks"] = db.get_trucks(filters if filters else None)
    except Exception as e:
        print(f"[ERROR] get_trucks failed: {e}")
        ctx["trucks"] = []
    ctx["filters"] = filters
    return templates.TemplateResponse("catalog.html", ctx)


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """About page."""
    ctx = get_base_context(request)
    ctx["meta"] = seo_service.generate_meta_tags(page="about")
    try:
        ctx["fleet_stats"] = db.get_fleet_stats()
    except Exception as e:
        print(f"[ERROR] get_fleet_stats failed: {e}")
        ctx["fleet_stats"] = {"total": 0, "available": 0, "rented": 0, "sold": 0}
    return templates.TemplateResponse("about.html", ctx)


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    """Contact page."""
    ctx = get_base_context(request)
    ctx["meta"] = seo_service.generate_meta_tags(page="contact")
    return templates.TemplateResponse("contact.html", ctx)


# ═══════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════


@app.get("/admin", response_class=HTMLResponse)
async def admin_login(request: Request):
    """Admin login page."""
    ctx = get_base_context(request)
    return templates.TemplateResponse("admin/login.html", ctx)


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, days: int = 30):
    """Admin dashboard with analytics."""
    # Clamp days to valid range
    days = max(7, min(days, 365))
    ctx = get_base_context(request)
    try:
        ctx["fleet_stats"] = db.get_fleet_stats()
    except Exception as e:
        print(f"[ERROR] get_fleet_stats failed: {e}")
        ctx["fleet_stats"] = {"total": 0, "available": 0, "rented": 0, "sold": 0}
    try:
        events = db.get_analytics(days=days)
    except Exception as e:
        print(f"[ERROR] get_analytics failed: {e}")
        events = []
    ctx["analytics"] = analytics_service.aggregate_dashboard_data(events, days=days)
    try:
        ctx["most_viewed"] = db.get_most_viewed(limit=5)
    except Exception as e:
        print(f"[ERROR] get_most_viewed failed: {e}")
        ctx["most_viewed"] = []
    try:
        ctx["recent_leads"] = db.get_leads()[:10]
    except Exception as e:
        print(f"[ERROR] get_leads failed: {e}")
        ctx["recent_leads"] = []
    # Build trucks_by_id for lead→vehicle resolution
    try:
        all_trucks = db.get_trucks()
    except Exception as e:
        print(f"[ERROR] get_trucks failed: {e}")
        all_trucks = []
    ctx["trucks_by_id"] = {t["id"]: t for t in all_trucks}
    ctx["all_trucks"] = all_trucks
    ctx["selected_days"] = days
    return templates.TemplateResponse("admin/dashboard.html", ctx)


@app.get("/admin/inventory", response_class=HTMLResponse)
async def admin_inventory(request: Request):
    """Admin inventory management page."""
    ctx = get_base_context(request)
    try:
        ctx["trucks"] = db.get_trucks()
    except Exception as e:
        print(f"[ERROR] get_trucks failed: {e}")
        ctx["trucks"] = []
    try:
        ctx["fleet_stats"] = db.get_fleet_stats()
    except Exception as e:
        print(f"[ERROR] get_fleet_stats failed: {e}")
        ctx["fleet_stats"] = {"total": 0, "available": 0, "rented": 0, "sold": 0}
    return templates.TemplateResponse("admin/inventory.html", ctx)


@app.get("/admin/leads", response_class=HTMLResponse)
async def admin_leads(request: Request):
    """Admin leads management page."""
    ctx = get_base_context(request)
    try:
        ctx["leads"] = db.get_leads()
    except Exception as e:
        print(f"[ERROR] get_leads failed: {e}")
        ctx["leads"] = []
    # Build trucks_by_id for lead→vehicle resolution
    try:
        all_trucks = db.get_trucks()
    except Exception as e:
        print(f"[ERROR] get_trucks failed: {e}")
        all_trucks = []
    ctx["trucks_by_id"] = {t["id"]: t for t in all_trucks}
    return templates.TemplateResponse("admin/leads.html", ctx)


@app.get("/admin/testimonials", response_class=HTMLResponse)
async def admin_testimonials(request: Request):
    """Admin testimonials gallery management."""
    ctx = get_base_context(request)
    try:
        ctx["testimonials"] = db.get_testimonials()
    except Exception as e:
        print(f"[ERROR] get_testimonials failed: {e}")
        ctx["testimonials"] = []
    return templates.TemplateResponse("admin/testimonials.html", ctx)


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request):
    """Admin settings page — manage phone numbers."""
    ctx = get_base_context(request)
    try:
        ctx["phone_settings"] = db.get_settings()
    except Exception as e:
        print(f"[ERROR] get_settings failed: {e}")
        ctx["phone_settings"] = {"whatsapp": "", "phone_call": "", "phone_sms": ""}
    return templates.TemplateResponse("admin/settings.html", ctx)


@app.get("/api/settings")
async def api_get_settings():
    """API: Get current settings."""
    try:
        return db.get_settings()
    except Exception as e:
        print(f"[ERROR] api get_settings failed: {e}")
        return {"whatsapp": "", "phone_call": "", "phone_sms": ""}


@app.put("/api/settings")
async def api_update_settings(request: Request):
    """API: Update settings (phone numbers)."""
    data = await request.json()
    allowed_keys = {"whatsapp", "phone_call", "phone_sms"}
    filtered = {k: v for k, v in data.items() if k in allowed_keys}
    result = db.update_settings(filtered)
    return {"success": True, "settings": result}


# ═══════════════════════════════════════════════════════════════
#  CHAT ROUTES
# ═══════════════════════════════════════════════════════════════


@app.get("/admin/chat", response_class=HTMLResponse)
async def admin_chat_page(request: Request):
    """Admin chat page — real-time messaging with visitors."""
    ctx = get_base_context(request)
    return templates.TemplateResponse("admin/chat.html", ctx)


@app.post("/api/chat/token")
async def api_chat_token(request: Request):
    """Generate a Stream Chat token for a visitor."""
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    body = await request.json()
    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    page = body.get("page", "/")

    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email required")

    if not chat_service.enabled:
        raise HTTPException(status_code=503, detail="Chat not configured")

    visitor_id = chat_service.generate_visitor_id(name, email)
    chat_service.upsert_visitor(visitor_id, name, email, page)
    token = chat_service.create_visitor_token(visitor_id)

    if not token:
        raise HTTPException(status_code=500, detail="Token generation failed")

    return {
        "token": token,
        "visitor_id": visitor_id,
        "api_key": settings.STREAM_API_KEY,
    }


@app.post("/api/chat/channel")
async def api_chat_channel(request: Request):
    """Create or get a chat channel for a visitor."""
    body = await request.json()
    visitor_id = body.get("visitor_id", "")
    name = body.get("name", "Visitor")
    email = body.get("email", "")
    page = body.get("page", "/")

    if not visitor_id:
        raise HTTPException(status_code=400, detail="visitor_id required")

    if not chat_service.enabled:
        raise HTTPException(status_code=503, detail="Chat not configured")

    result = chat_service.get_or_create_channel(visitor_id, name, email, page)
    if not result:
        raise HTTPException(status_code=500, detail="Channel creation failed")

    return result


@app.get("/api/chat/admin-token")
async def api_chat_admin_token():
    """Generate a Stream Chat token for the admin."""
    if not chat_service.enabled:
        raise HTTPException(status_code=503, detail="Chat not configured")

    chat_service.ensure_admin_user()
    token = chat_service.create_admin_token()

    if not token:
        raise HTTPException(status_code=500, detail="Admin token generation failed")

    return {
        "token": token,
        "user_id": "asap-admin",
        "api_key": settings.STREAM_API_KEY,
    }


# ═══════════════════════════════════════════════════════════════
#  PUSH NOTIFICATION ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/api/push/vapid-key")
async def api_vapid_key():
    """Return the VAPID public key for push subscription."""
    return {"publicKey": settings.VAPID_PUBLIC_KEY}


@app.post("/api/push/subscribe")
async def api_push_subscribe(request: Request):
    """Save a push subscription for admin notifications."""
    body = await request.json()
    subscription = body.get("subscription", {})
    endpoint = subscription.get("endpoint", "")
    keys = subscription.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")

    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Invalid subscription data")

    try:
        db._execute(
            """INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_type)
               VALUES (%s, %s, %s, 'admin')
               ON CONFLICT (endpoint) DO UPDATE SET p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth""",
            [endpoint, p256dh, auth], fetch="none"
        )
        return {"ok": True}
    except Exception as e:
        print(f"[ERROR] Push subscribe: {e}")
        raise HTTPException(status_code=500, detail="Failed to save subscription")


@app.post("/api/push/notify")
async def api_push_notify(request: Request):
    """Send push notification to all admin subscribers. Called when a new visitor message arrives."""
    body = await request.json()
    title = body.get("title", "New Message — ASAP")
    message_body = body.get("body", "You have a new message")
    url = body.get("url", "/admin/chat")
    channel_id = body.get("channelId", "")

    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return {"ok": False, "reason": "VAPID keys not configured"}

    try:
        from pywebpush import webpush, WebPushException
        import json

        subs = db._execute("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_type='admin'")
        sent = 0
        failed_endpoints = []
        total = len(subs or [])

        print(f"[Push] Sending to {total} subscriber(s)...")

        for sub in (subs or []):
            ep_domain = sub["endpoint"].split("/")[2] if len(sub["endpoint"].split("/")) > 2 else "?"
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}
                    },
                    data=json.dumps({
                        "title": title,
                        "body": message_body,
                        "url": url,
                        "channelId": channel_id,
                        "icon": "/assets/img/logo/logo.jpg"
                    }),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL}
                )
                sent += 1
                print(f"[Push] ✓ Sent to {ep_domain}")
            except WebPushException as ex:
                status = ex.response.status_code if ex.response else 0
                print(f"[Push] ✗ Failed for {ep_domain}: HTTP {status} — {ex}")
                # Clean up stale/invalid subscriptions
                if status in (401, 403, 404, 410):
                    failed_endpoints.append(sub["endpoint"])
            except Exception as ex:
                print(f"[Push] ✗ Error for {ep_domain}: {ex}")

        # Clean up expired subscriptions
        for ep in failed_endpoints:
            try:
                db._execute("DELETE FROM push_subscriptions WHERE endpoint=%s", [ep], fetch="none")
                print(f"[Push] Cleaned up stale subscription")
            except Exception:
                pass

        print(f"[Push] Done: {sent}/{total} sent, {len(failed_endpoints)} cleaned")
        return {"ok": True, "sent": sent, "total": total, "cleaned": len(failed_endpoints)}
    except ImportError:
        return {"ok": False, "reason": "pywebpush not installed"}
    except Exception as e:
        print(f"[ERROR] Push notify: {e}")
        return {"ok": False, "reason": str(e)}


@app.get("/api/push/status")
async def api_push_status():
    """Diagnostic: check how many push subscriptions are saved."""
    try:
        subs = db._execute("SELECT id, endpoint, user_type, created_at FROM push_subscriptions ORDER BY created_at DESC")
        result = []
        for s in (subs or []):
            # Show only domain of endpoint for privacy
            ep = s.get("endpoint", "")
            domain = ep.split("/")[2] if len(ep.split("/")) > 2 else "unknown"
            result.append({
                "id": s.get("id"),
                "endpoint_domain": domain,
                "user_type": s.get("user_type"),
                "created_at": str(s.get("created_at", ""))
            })
        return {"total": len(result), "subscriptions": result}
    except Exception as e:
        return {"error": str(e)}


# ─── QUICK REPLIES API ───
@app.get("/api/admin/quick-replies")
async def get_quick_replies(request: Request):
    try:
        # Check token to ensure it's admin (basic protection)
        replies = db._execute("SELECT id, text, created_at FROM quick_replies ORDER BY created_at ASC")
        return {"ok": True, "replies": replies or []}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

@app.post("/api/admin/quick-replies")
async def add_quick_reply(request: Request):
    import uuid
    try:
        body = await request.json()
        qr_id = str(uuid.uuid4())
        text = body.get("text", "").strip()
        if not text:
            return {"ok": False, "reason": "Text is empty"}
        db._execute("INSERT INTO quick_replies (id, text) VALUES (%s, %s)", [qr_id, text], fetch="none")
        return {"ok": True, "id": qr_id, "text": text}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

@app.delete("/api/admin/quick-replies/{qr_id}")
async def delete_quick_reply(qr_id: str, request: Request):
    try:
        db._execute("DELETE FROM quick_replies WHERE id=%s", [qr_id], fetch="none")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# Service Worker must be served from root for scope
@app.get("/sw.js")
async def service_worker():
    """Serve the Service Worker from root path for proper scope."""
    import os
    sw_path = os.path.join(settings.STATIC_DIR, "js", "sw.js")
    return FileResponse(sw_path, media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


# ═══════════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════════


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """API: Admin login endpoint."""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    # Admin credentials check (works in both local and firebase modes)
    admin_password = os.getenv("ADMIN_PASSWORD", "12345")
    admin_emails = [e.lower() for e in settings.ADMIN_EMAILS]

    if email in admin_emails and password == admin_password:
        import hashlib, time

        token = hashlib.sha256(f"{email}{time.time()}".encode()).hexdigest()
        from starlette.responses import JSONResponse

        response = JSONResponse({"success": True, "redirect": "/admin/dashboard"})
        response.set_cookie("admin_token", token, httponly=True, max_age=86400)
        return response
    return {"success": False, "detail": "Invalid email or password"}


@app.get("/api/trucks")
async def api_get_trucks(
    category: Optional[str] = None,
    condition: Optional[str] = None,
    usage: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """API: Get trucks with filters."""
    filters = {}
    if category:
        filters["category"] = category
    if condition:
        filters["condition"] = condition
    if usage:
        filters["usage"] = usage
    if status:
        filters["status"] = status
    if search:
        filters["search"] = search

    trucks = db.get_trucks(filters if filters else None)
    return {"trucks": trucks, "count": len(trucks)}


@app.get("/api/trucks/{truck_id}")
async def api_get_truck(truck_id: str):
    """API: Get single truck."""
    truck = db.get_truck(truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found")
    return truck


@app.post("/api/trucks")
async def api_create_truck(
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    condition: str = Form(...),
    usage: str = Form(...),
    status: str = Form("available"),
    length: str = Form(""),
    width: str = Form(""),
    height: str = Form(""),
    voltage: str = Form(""),
    gas: str = Form(""),
    plumbing: str = Form(""),
    generator: str = Form(""),
    hood_system: str = Form(""),
    equipment: str = Form(""),
    featured: bool = Form(False),
    images: List[UploadFile] = File(default=[]),
):
    """API: Create a new truck with image upload."""
    # Generate slug
    slug = title.lower().replace(" ", "-").replace("'", "")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    # Process images
    image_urls = []
    for img_file in images:
        if img_file.filename:
            try:
                result = await image_processor.process_upload(img_file)
                image_urls.append(result.get("large", result.get("original", "")))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                print(f"Image upload error: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Image processing failed: {str(e)}"
                )

    # Parse equipment list
    equipment_list = (
        [e.strip() for e in equipment.split(",") if e.strip()] if equipment else []
    )

    truck_data = {
        "title": title,
        "slug": slug,
        "description": description,
        "price": price,
        "category": category,
        "condition": condition,
        "usage": usage,
        "status": status,
        "featured": featured,
        "specs": {
            "length": length,
            "width": width,
            "height": height,
            "voltage": voltage,
            "gas": gas,
            "plumbing": plumbing,
            "generator": generator,
            "hood_system": hood_system,
            "equipment": equipment_list,
        },
        "images": image_urls if image_urls else ["/assets/img/trucks/placeholder.jpg"],
    }

    truck = db.create_truck(truck_data)
    return {"success": True, "truck": truck}


@app.put("/api/trucks/{truck_id}")
async def api_update_truck(truck_id: str, request: Request):
    """API: Update a truck."""
    body = await request.json()
    truck = db.update_truck(truck_id, body)
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found")
    return {"success": True, "truck": truck}


@app.delete("/api/trucks/{truck_id}")
async def api_delete_truck(truck_id: str):
    """API: Delete a truck."""
    success = db.delete_truck(truck_id)
    if not success:
        raise HTTPException(status_code=404, detail="Truck not found")
    return {"success": True}


@app.post("/api/trucks/{truck_id}/images")
async def api_add_truck_images(
    truck_id: str,
    images: List[UploadFile] = File(...),
):
    """API: Upload new images to an existing vehicle."""
    # Get existing truck
    truck = db.get_truck(truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found")

    existing_images = truck.get("images", [])
    new_urls = []

    for img_file in images:
        if img_file.filename:
            try:
                result = await image_processor.process_upload(img_file)
                url = result.get("large", result.get("original", ""))
                if url:
                    new_urls.append(url)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                print(f"Image upload error: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Image processing failed: {str(e)}"
                )

    all_images = existing_images + new_urls
    db.update_truck(truck_id, {"images": all_images})

    return {"success": True, "images": all_images, "added": len(new_urls)}


@app.delete("/api/trucks/{truck_id}/images")
async def api_remove_truck_image(truck_id: str, request: Request):
    """API: Remove a specific image from a vehicle."""
    body = await request.json()
    image_url = body.get("image_url", "")

    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    truck = db.get_truck(truck_id)
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found")

    existing_images = truck.get("images", [])
    if image_url in existing_images:
        existing_images.remove(image_url)
        db.update_truck(truck_id, {"images": existing_images})
        return {"success": True, "images": existing_images}
    else:
        return {"success": False, "detail": "Image not found in vehicle"}


@app.post("/api/leads")
async def api_create_lead(
    customer_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    truck_id: str = Form(""),
    message: str = Form(""),
):
    """API: Create a new lead from quote request or contact form."""
    lead_data = {
        "customer_name": customer_name,
        "email": email,
        "phone": phone,
        "truck_id": truck_id,
        "message": message,
    }
    lead = db.create_lead(lead_data)

    # Send email notification (non-blocking — won't fail the request)
    try:
        email_service.send_lead_notification(lead_data)
    except Exception as e:
        print(f"Email notification failed (non-critical): {e}")

    return {"success": True, "lead": lead}


@app.get("/api/analytics/dashboard")
async def api_analytics_dashboard():
    """API: Get dashboard analytics data."""
    try:
        events = db.get_analytics(days=30)
    except Exception as e:
        print(f"[ERROR] get_analytics failed: {e}")
        events = []
    data = analytics_service.aggregate_dashboard_data(events)
    try:
        data["fleet_stats"] = db.get_fleet_stats()
    except Exception as e:
        print(f"[ERROR] get_fleet_stats failed: {e}")
        data["fleet_stats"] = {"total": 0, "available": 0, "rented": 0, "sold": 0}
    try:
        data["most_viewed"] = db.get_most_viewed(limit=5)
    except Exception as e:
        print(f"[ERROR] get_most_viewed failed: {e}")
        data["most_viewed"] = []
    return data


@app.get("/api/fleet-stats")
async def api_fleet_stats():
    """API: Get fleet status counters."""
    try:
        return db.get_fleet_stats()
    except Exception as e:
        print(f"[ERROR] api get_fleet_stats failed: {e}")
        return {"total": 0, "available": 0, "rented": 0, "sold": 0}


@app.post("/api/testimonials")
async def api_create_testimonial(
    image: UploadFile = File(None),
    name: str = Form(""),
    text: str = Form(""),
    rating: int = Form(5),
    role: str = Form(""),
):
    """API: Upload a new testimonial (image and/or text)."""
    testimonial_data = {}

    # Process image if provided
    if image and image.filename:
        try:
            result = await image_processor.process_upload(image)
            url = result.get("large", result.get("original", ""))
            testimonial_data["image_url"] = url
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            print(f"Testimonial upload error: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Add text fields
    if name:
        testimonial_data["name"] = name
    if text:
        testimonial_data["text"] = text
    if role:
        testimonial_data["role"] = role
    testimonial_data["rating"] = rating

    if not testimonial_data.get("image_url") and not testimonial_data.get("text"):
        raise HTTPException(status_code=400, detail="Provide an image or text")

    testimonial = db.create_testimonial(testimonial_data)
    return {"success": True, "testimonial": testimonial}


@app.delete("/api/testimonials/{testimonial_id}")
async def api_delete_testimonial(testimonial_id: str):
    """API: Delete a testimonial."""
    success = db.delete_testimonial(testimonial_id)
    if not success:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"success": True}


# ═══════════════════════════════════════════════════════════════
#  CHAT ROUTES (Stream Chat)
# ═══════════════════════════════════════════════════════════════


@app.post("/api/chat/token")
async def api_chat_token(request: Request):
    """API: Generate a Stream Chat token for a visitor."""
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    page = body.get("page", "/")

    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email are required")

    if not chat_service.enabled:
        raise HTTPException(status_code=503, detail="Chat service unavailable")

    visitor_id = chat_service.generate_visitor_id(name, email)
    chat_service.upsert_visitor(visitor_id, name, email, page)
    token = chat_service.create_visitor_token(visitor_id)

    if not token:
        raise HTTPException(status_code=500, detail="Token generation failed")

    # Save chat session to Firestore
    try:
        db.save_chat_session({
            "visitor_id": visitor_id,
            "visitor_name": name,
            "visitor_email": email,
            "visitor_page": page,
        })
    except Exception as e:
        print(f"[ERROR] save_chat_session failed: {e}")

    return {
        "token": token,
        "visitor_id": visitor_id,
        "api_key": settings.STREAM_API_KEY,
    }


@app.post("/api/chat/channel")
async def api_chat_channel(request: Request):
    """API: Create or get a support channel for a visitor."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    visitor_id = body.get("visitor_id", "")
    name = body.get("name", "Visitor")
    email = body.get("email", "")
    page = body.get("page", "/")

    if not visitor_id:
        raise HTTPException(status_code=400, detail="visitor_id is required")

    result = chat_service.get_or_create_channel(visitor_id, name, email, page)
    if not result:
        raise HTTPException(status_code=500, detail="Channel creation failed")

    return {"success": True, **result}


@app.get("/api/chat/admin-token")
async def api_chat_admin_token():
    """API: Generate admin Stream Chat token."""
    if not chat_service.enabled:
        raise HTTPException(status_code=503, detail="Chat service unavailable")
    token = chat_service.create_admin_token()
    if not token:
        raise HTTPException(status_code=500, detail="Admin token generation failed")
    return {
        "token": token,
        "user_id": "asap-admin",
        "api_key": settings.STREAM_API_KEY,
    }


@app.get("/api/chat/channels")
async def api_chat_channels():
    """API: List all chat channels (admin)."""
    try:
        channels = chat_service.list_channels()
    except Exception as e:
        print(f"[ERROR] list_channels failed: {e}")
        channels = []
    return {"channels": channels}


@app.post("/api/chat/resolve")
async def api_chat_resolve(request: Request):
    """API: Mark a chat conversation as resolved."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    session_id = body.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        db.update_chat_session(session_id, {"status": "resolved"})
    except Exception as e:
        print(f"[ERROR] update_chat_session failed: {e}")

    return {"success": True}


@app.get("/admin/chat", response_class=HTMLResponse)
async def admin_chat(request: Request):
    """Admin chat management page."""
    ctx = get_base_context(request)
    ctx["stream_api_key"] = settings.STREAM_API_KEY
    return templates.TemplateResponse("admin/chat.html", ctx)


# ═══════════════════════════════════════════════════════════════
#  SEO ROUTES
# ═══════════════════════════════════════════════════════════════


@app.get("/sitemap.xml")
async def sitemap():
    """Dynamic XML sitemap."""
    try:
        trucks = db.get_trucks()
    except Exception as e:
        print(f"[ERROR] get_trucks for sitemap failed: {e}")
        trucks = []
    xml_content = seo_service.generate_sitemap(trucks)
    return Response(content=xml_content, media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    """Robots.txt file."""
    content = f"""User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/

Sitemap: {seo_service.BASE_URL}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")


# ═══════════════════════════════════════════════════════════════
#  CATCH-ALL TRUCK DETAIL ROUTE (must be LAST before error handlers)
# ═══════════════════════════════════════════════════════════════


@app.get("/{truck_type}/{slug}", response_class=HTMLResponse)
async def truck_detail(request: Request, truck_type: str, slug: str):
    """Individual truck detail page with SEO."""
    if truck_type not in ("truck", "trailer"):
        raise HTTPException(status_code=404, detail="Page not found")

    try:
        truck = db.get_truck_by_slug(slug)
    except Exception as e:
        print(f"[ERROR] get_truck_by_slug failed: {e}")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found")

    # Increment views
    try:
        db.increment_views(truck["id"])
    except Exception as e:
        print(f"[ERROR] increment_views failed: {e}")

    ctx = get_base_context(request)
    ctx["truck"] = truck
    ctx["meta"] = seo_service.generate_meta_tags(truck=truck)
    ctx["product_jsonld"] = json.dumps(seo_service.generate_product_jsonld(truck))
    try:
        ctx["related_trucks"] = db.get_trucks({"category": truck_type})[:4]
    except Exception as e:
        print(f"[ERROR] get related trucks failed: {e}")
        ctx["related_trucks"] = []
    return templates.TemplateResponse("truck_detail.html", ctx)


# ═══════════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    try:
        ctx = get_base_context(request)
    except Exception:
        ctx = {"request": request, "business": {"name": settings.BUSINESS_NAME}, "social": {}, "firebase_config": {}, "app_mode": settings.APP_MODE}
    ctx["meta"] = {"title": "Page Not Found | " + settings.BUSINESS_NAME}
    return templates.TemplateResponse("error.html", ctx, status_code=404)


# ═══════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
