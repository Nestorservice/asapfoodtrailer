"""
ASAP Food Trucks - SEO Service
Generates JSON-LD, sitemaps, meta tags, Open Graph
"""

from datetime import datetime, timezone
from config import settings

# Official canonical domain
BASE_URL = "https://asapfoodtrucks.site"


def _clean_social_url(url: str) -> str:
    """Strip tracking/UTM query parameters from social profile URLs."""
    if not url:
        return url
    try:
        base = url.split("?")[0].rstrip("/")
        return base
    except Exception:
        return url


class SEOService:
    """Generates SEO elements: JSON-LD, sitemap, meta, OG tags."""

    BASE_URL = BASE_URL

    # ─── URL helpers ─────────────────────────────────────────
    @staticmethod
    def absolute_url(path: str) -> str:
        """Return an absolute URL, handling both relative and absolute paths."""
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{BASE_URL}{path}"

    # ─── Structured data ─────────────────────────────────────
    def generate_website_jsonld(self) -> dict:
        """WebSite schema with real site search action (/catalog?search=...)."""
        return {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "@id": f"{self.BASE_URL}/#website",
            "name": "ASAP Food Trucks",
            "alternateName": "ASAP Food Trailer",
            "url": f"{self.BASE_URL}/",
            "inLanguage": "en-US",
            "publisher": {"@id": f"{self.BASE_URL}/#organization"},
            "potentialAction": {
                "@type": "SearchAction",
                "target": {
                    "@type": "EntryPoint",
                    "urlTemplate": f"{self.BASE_URL}/catalog?search={{search_term_string}}",
                },
                "query-input": "required name=search_term_string",
            },
        }

    def generate_organization_jsonld(self) -> dict:
        """Organization schema built ONLY from data present in the project
        (business info from config.py + social profiles from config.py)."""
        same_as = [
            _clean_social_url(settings.SOCIAL_TIKTOK),
            _clean_social_url(settings.SOCIAL_FACEBOOK),
            _clean_social_url(settings.SOCIAL_INSTAGRAM),
            _clean_social_url(settings.SOCIAL_X),
        ]
        same_as = [u for u in same_as if u]

        return {
            "@context": "https://schema.org",
            "@type": "Organization",
            "@id": f"{self.BASE_URL}/#organization",
            "name": "ASAP Food Trucks",
            "url": f"{self.BASE_URL}/",
            "telephone": settings.BUSINESS_PHONE,
            "email": settings.BUSINESS_EMAIL,
            "description": (
                "ASAP Food Trucks sells new, used and custom-built food trucks "
                "and food trailers, with rental and financing options."
            ),
            "address": {
                "@type": "PostalAddress",
                "addressLocality": settings.BUSINESS_CITY,
                "addressRegion": "TX",
                "addressCountry": "US",
            },
            "sameAs": same_as,
        }

    def generate_business_jsonld(self) -> dict:
        """Homepage graph: WebSite + Organization."""
        return {
            "@context": "https://schema.org",
            "@graph": [
                self.generate_website_jsonld(),
                self.generate_organization_jsonld(),
            ],
        }

    def generate_breadcrumbs_jsonld(self, crumbs: list) -> dict:
        """BreadcrumbList schema. `crumbs` = list of (name, url) tuples."""
        item_list = [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": self.absolute_url(url),
            }
            for i, (name, url) in enumerate(crumbs)
        ]
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": item_list,
        }

    def generate_product_jsonld(self, truck: dict) -> dict:
        """Generate JSON-LD Product + Offer structured data for a truck."""
        availability_map = {
            "available": "https://schema.org/InStock",
            "sold": "https://schema.org/SoldOut",
            "rented": "https://schema.org/OutOfStock",
        }

        truck_url = f"{self.BASE_URL}/{truck['category']}/{truck['slug']}"
        images = [
            self.absolute_url(img)
            for img in truck.get("images", [])
            if img
        ]

        jsonld = {
            "@context": "https://schema.org",
            "@type": "Product",
            "@id": f"{truck_url}#product",
            "name": truck["title"],
            "description": truck["description"],
            "url": truck_url,
            "image": images,
            "brand": {
                "@type": "Brand",
                "name": "ASAP Food Trucks",
            },
            "offers": {
                "@type": "Offer",
                "url": truck_url,
                "priceCurrency": "USD",
                "price": truck["price"],
                "availability": availability_map.get(truck.get("status", "available")),
                "seller": {
                    "@type": "Organization",
                    "name": "ASAP Food Trucks",
                },
                "itemCondition": (
                    "https://schema.org/NewCondition"
                    if truck.get("condition") == "new"
                    else "https://schema.org/UsedCondition"
                ),
            },
            "category": (
                "Food Truck" if truck.get("category") == "truck" else "Food Trailer"
            ),
        }

        # Add specs if available
        specs = truck.get("specs", {})
        if specs:
            additional_props = []
            for key, value in specs.items():
                if value in (None, ""):
                    continue
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                additional_props.append(
                    {
                        "@type": "PropertyValue",
                        "name": key.replace("_", " ").title(),
                        "value": str(value),
                    }
                )
            if additional_props:
                jsonld["additionalProperty"] = additional_props

        return jsonld

    # ─── Meta tags ───────────────────────────────────────────
    def generate_meta_tags(self, truck: dict = None, page: str = "home") -> dict:
        """Generate meta tags for a page."""
        if truck:
            price_str = (
                f"${truck['price']:,}/mo"
                if truck.get("usage") == "rent"
                else f"${truck['price']:,}"
            )
            og_image = (
                self.absolute_url(truck["images"][0])
                if truck.get("images")
                else f"{self.BASE_URL}/assets/img/logo/logo.jpg"
            )
            truck_url = f"{self.BASE_URL}/{truck['category']}/{truck['slug']}"
            return {
                "title": f"{truck['title']} | {price_str} | ASAP Food Trucks",
                "description": truck["description"][:160],
                "og_title": f"{truck['title']} - {price_str} | ASAP Food Trucks",
                "og_description": truck["description"][:200],
                "og_image": og_image,
                "og_url": truck_url,
                "og_type": "product",
                "canonical": truck_url,
            }

        pages = {
            "home": {
                "title": "ASAP Food Trucks | Food Trucks & Food Trailers",
                "description": (
                    "ASAP Food Trucks is a Houston-based dealer of new, used and "
                    "custom-built food trucks and food trailers for sale and rent. "
                    "Get a free quote today."
                ),
                "og_title": "ASAP Food Trucks | Food Trucks & Food Trailers",
                "og_description": (
                    "New, used and custom food trucks and trailers for sale and "
                    "rent in the USA. Build your mobile food business with ASAP Food Trucks."
                ),
                "og_image": f"{self.BASE_URL}/assets/img/logo/logo.jpg",
                "og_url": f"{self.BASE_URL}/",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/",
            },
            "catalog": {
                "title": "Food Trucks & Trailers for Sale | ASAP Food Trucks",
                "description": (
                    "Browse food trucks and food trailers for sale and rent. Filter "
                    "by type, condition and price. New, used and custom-built units available."
                ),
                "og_title": "Food Trucks & Trailers for Sale | ASAP Food Trucks",
                "og_description": (
                    "Explore our full inventory of food trucks and food trailers "
                    "for sale and rent across the USA."
                ),
                "og_image": f"{self.BASE_URL}/assets/img/logo/logo.jpg",
                "og_url": f"{self.BASE_URL}/catalog",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/catalog",
            },
            "food_trucks": {
                "title": "Food Trucks for Sale | ASAP Food Trucks",
                "description": (
                    "New and used food trucks for sale, plus custom-built mobile "
                    "kitchens. Browse our fleet of food trucks and get a quote from ASAP Food Trucks."
                ),
                "og_title": "Food Trucks for Sale | ASAP Food Trucks",
                "og_description": (
                    "Browse food trucks for sale — new, used and custom built. "
                    "Financing and delivery available."
                ),
                "og_image": f"{self.BASE_URL}/assets/img/logo/logo.jpg",
                "og_url": f"{self.BASE_URL}/food-trucks",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/food-trucks",
            },
            "food_trailers": {
                "title": "Food Trailers for Sale | ASAP Food Trucks",
                "description": (
                    "Food trailers for sale — new, used and custom built. Explore "
                    "our trailer fleet and request a free quote from ASAP Food Trucks."
                ),
                "og_title": "Food Trailers for Sale | ASAP Food Trucks",
                "og_description": (
                    "Browse food trailers for sale — new, used and custom built. "
                    "Financing and delivery available."
                ),
                "og_image": f"{self.BASE_URL}/assets/img/logo/logo.jpg",
                "og_url": f"{self.BASE_URL}/food-trailers",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/food-trailers",
            },
            "about": {
                "title": "About Us | ASAP Food Trucks",
                "description": (
                    "Learn about ASAP Food Trucks — a trusted dealer of food trucks "
                    "and food trailers in Houston, TX, serving the USA."
                ),
                "og_title": "About ASAP Food Trucks",
                "og_description": (
                    "Meet the team behind ASAP Food Trucks and discover how we help "
                    "entrepreneurs launch their mobile food business."
                ),
                "og_image": f"{self.BASE_URL}/assets/img/logo/logo.jpg",
                "og_url": f"{self.BASE_URL}/about",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/about",
            },
            "contact": {
                "title": "Contact ASAP Food Trucks | Free Quotes",
                "description": (
                    "Contact ASAP Food Trucks for quotes, questions and support. "
                    "Call us or send a message — our team replies within 24 hours."
                ),
                "og_title": "Contact ASAP Food Trucks",
                "og_description": (
                    "Get in touch with ASAP Food Trucks for free quotes, questions "
                    "and support about food trucks and trailers."
                ),
                "og_image": f"{self.BASE_URL}/assets/img/logo/logo.jpg",
                "og_url": f"{self.BASE_URL}/contact",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/contact",
            },
        }
        return pages.get(page, pages["home"])

    # ─── Sitemap ─────────────────────────────────────────────
    def generate_sitemap(self, trucks: list) -> str:
        """Generate XML sitemap with static pages + truck detail pages."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        urls = [
            {"loc": f"{self.BASE_URL}/", "priority": "1.0", "changefreq": "daily"},
            {
                "loc": f"{self.BASE_URL}/catalog",
                "priority": "0.9",
                "changefreq": "daily",
            },
            {
                "loc": f"{self.BASE_URL}/food-trucks",
                "priority": "0.8",
                "changefreq": "weekly",
            },
            {
                "loc": f"{self.BASE_URL}/food-trailers",
                "priority": "0.8",
                "changefreq": "weekly",
            },
            {
                "loc": f"{self.BASE_URL}/about",
                "priority": "0.6",
                "changefreq": "monthly",
            },
            {
                "loc": f"{self.BASE_URL}/contact",
                "priority": "0.6",
                "changefreq": "monthly",
            },
        ]

        for truck in trucks:
            lastmod = now
            created = truck.get("created_at")
            if created:
                try:
                    lastmod = created[:10]
                except Exception:
                    pass
            urls.append(
                {
                    "loc": f"{self.BASE_URL}/{truck['category']}/{truck['slug']}",
                    "priority": "0.8",
                    "changefreq": "weekly",
                    "lastmod": lastmod,
                }
            )

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

        for url_data in urls:
            xml_parts.append("  <url>")
            xml_parts.append(f"    <loc>{url_data['loc']}</loc>")
            xml_parts.append(f"    <lastmod>{url_data.get('lastmod', now)}</lastmod>")
            xml_parts.append(f"    <changefreq>{url_data['changefreq']}</changefreq>")
            xml_parts.append(f"    <priority>{url_data['priority']}</priority>")
            xml_parts.append("  </url>")

        xml_parts.append("</urlset>")
        return "\n".join(xml_parts)


seo_service = SEOService()
