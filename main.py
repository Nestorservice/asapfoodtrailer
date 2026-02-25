"""
ASAP Food Trailer — Main FastAPI Application
"""

import json
import os
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
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
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


# ─── Template Helpers ─────────────────────────────────────────
def get_base_context(request: Request) -> dict:
    """Build base template context with business info and SEO."""
    return {
        "request": request,
        "business": {
            "name": settings.BUSINESS_NAME,
            "phone": settings.BUSINESS_PHONE,
            "email": settings.BUSINESS_EMAIL,
            "address": settings.BUSINESS_ADDRESS,
            "city": settings.BUSINESS_CITY,
            "whatsapp": settings.BUSINESS_WHATSAPP,
        },
        "firebase_config": {
            "apiKey": settings.FIREBASE_API_KEY,
            "authDomain": settings.FIREBASE_AUTH_DOMAIN,
            "projectId": settings.FIREBASE_PROJECT_ID,
            "storageBucket": settings.FIREBASE_STORAGE_BUCKET,
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
    ctx["featured_trucks"] = db.get_featured_trucks(limit=6)
    ctx["fleet_stats"] = db.get_fleet_stats()
    ctx["testimonials"] = db.get_testimonials()
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
    ctx["trucks"] = db.get_trucks(filters if filters else None)
    ctx["filters"] = filters
    return templates.TemplateResponse("catalog.html", ctx)


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """About page."""
    ctx = get_base_context(request)
    ctx["meta"] = seo_service.generate_meta_tags(page="about")
    ctx["fleet_stats"] = db.get_fleet_stats()
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
async def admin_dashboard(request: Request):
    """Admin dashboard with analytics."""
    ctx = get_base_context(request)
    ctx["fleet_stats"] = db.get_fleet_stats()
    events = db.get_analytics(days=30)
    ctx["analytics"] = analytics_service.aggregate_dashboard_data(events)
    ctx["most_viewed"] = db.get_most_viewed(limit=5)
    ctx["recent_leads"] = db.get_leads()[:10]
    # Build trucks_by_id for lead→vehicle resolution
    all_trucks = db.get_trucks()
    ctx["trucks_by_id"] = {t["id"]: t for t in all_trucks}
    ctx["all_trucks"] = all_trucks
    return templates.TemplateResponse("admin/dashboard.html", ctx)


@app.get("/admin/inventory", response_class=HTMLResponse)
async def admin_inventory(request: Request):
    """Admin inventory management page."""
    ctx = get_base_context(request)
    ctx["trucks"] = db.get_trucks()
    ctx["fleet_stats"] = db.get_fleet_stats()
    return templates.TemplateResponse("admin/inventory.html", ctx)


@app.get("/admin/leads", response_class=HTMLResponse)
async def admin_leads(request: Request):
    """Admin leads management page."""
    ctx = get_base_context(request)
    ctx["leads"] = db.get_leads()
    # Build trucks_by_id for lead→vehicle resolution
    all_trucks = db.get_trucks()
    ctx["trucks_by_id"] = {t["id"]: t for t in all_trucks}
    return templates.TemplateResponse("admin/leads.html", ctx)


# ═══════════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════════


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """API: Admin login endpoint."""
    body = await request.json()
    email = body.get("email", "")
    password = body.get("password", "")

    # Local development mode — simple credentials
    if settings.APP_MODE == "local":
        if email == "admin@asapfoodtrailer.com" and password == "admin123":
            from starlette.responses import JSONResponse

            response = JSONResponse({"success": True, "redirect": "/admin/dashboard"})
            response.set_cookie(
                "admin_token", "dev-admin-token", httponly=True, max_age=86400
            )
            return response
        return {"success": False, "detail": "Invalid email or password"}

    # Firebase mode — verify with Firebase Auth
    try:
        token = auth_service.verify_admin_token(body.get("token", ""))
        if token:
            from starlette.responses import JSONResponse

            response = JSONResponse({"success": True, "redirect": "/admin/dashboard"})
            response.set_cookie(
                "admin_token", body.get("token", ""), httponly=True, max_age=86400
            )
            return response
        return {"success": False, "detail": "Access denied. Not an admin account."}
    except Exception:
        return {"success": False, "detail": "Authentication failed"}


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


@app.post("/api/leads")
async def api_create_lead(
    customer_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    truck_id: str = Form(""),
    message: str = Form(""),
):
    """API: Create a new lead from quote request or contact form."""
    lead = db.create_lead(
        {
            "customer_name": customer_name,
            "email": email,
            "phone": phone,
            "truck_id": truck_id,
            "message": message,
        }
    )
    return {"success": True, "lead": lead}


@app.get("/api/analytics/dashboard")
async def api_analytics_dashboard():
    """API: Get dashboard analytics data."""
    events = db.get_analytics(days=30)
    data = analytics_service.aggregate_dashboard_data(events)
    data["fleet_stats"] = db.get_fleet_stats()
    data["most_viewed"] = db.get_most_viewed(limit=5)
    return data


@app.get("/api/fleet-stats")
async def api_fleet_stats():
    """API: Get fleet status counters."""
    return db.get_fleet_stats()


# ═══════════════════════════════════════════════════════════════
#  SEO ROUTES
# ═══════════════════════════════════════════════════════════════


@app.get("/sitemap.xml")
async def sitemap():
    """Dynamic XML sitemap."""
    trucks = db.get_trucks()
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

    truck = db.get_truck_by_slug(slug)
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found")

    # Increment views
    db.increment_views(truck["id"])

    ctx = get_base_context(request)
    ctx["truck"] = truck
    ctx["meta"] = seo_service.generate_meta_tags(truck=truck)
    ctx["product_jsonld"] = json.dumps(seo_service.generate_product_jsonld(truck))
    ctx["related_trucks"] = db.get_trucks({"category": truck_type})[:4]
    return templates.TemplateResponse("truck_detail.html", ctx)


# ═══════════════════════════════════════════════════════════════
#  ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    ctx = get_base_context(request)
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
