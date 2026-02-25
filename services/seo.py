"""
ASAP Food Trailer - SEO Service
Generates JSON-LD, sitemaps, meta tags, Open Graph
"""

from datetime import datetime, timezone
from config import settings


class SEOService:
    """Generates SEO elements: JSON-LD, sitemap, meta, OG tags."""

    BASE_URL = "https://asapfoodtrailer.com"

    def generate_product_jsonld(self, truck: dict) -> dict:
        """Generate JSON-LD Product + Offer structured data for a truck."""
        price_spec = {
            "@type": "UnitPriceSpecification",
            "price": truck["price"],
            "priceCurrency": "USD",
        }

        availability_map = {
            "available": "https://schema.org/InStock",
            "sold": "https://schema.org/SoldOut",
            "rented": "https://schema.org/OutOfStock",
        }

        jsonld = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": truck["title"],
            "description": truck["description"],
            "image": [f"{self.BASE_URL}{img}" for img in truck.get("images", [])],
            "brand": {
                "@type": "Brand",
                "name": settings.BUSINESS_NAME,
            },
            "offers": {
                "@type": "Offer",
                "url": f"{self.BASE_URL}/{truck['category']}/{truck['slug']}",
                "priceCurrency": "USD",
                "price": truck["price"],
                "priceSpecification": price_spec,
                "availability": availability_map.get(truck.get("status", "available")),
                "seller": {
                    "@type": "Organization",
                    "name": settings.BUSINESS_NAME,
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
                if isinstance(value, list):
                    value = ", ".join(value)
                additional_props.append(
                    {
                        "@type": "PropertyValue",
                        "name": key.replace("_", " ").title(),
                        "value": str(value),
                    }
                )
            jsonld["additionalProperty"] = additional_props

        return jsonld

    def generate_business_jsonld(self) -> dict:
        """Generate JSON-LD for the business (LocalBusiness)."""
        return {
            "@context": "https://schema.org",
            "@type": "AutoDealer",
            "name": settings.BUSINESS_NAME,
            "telephone": settings.BUSINESS_PHONE,
            "email": settings.BUSINESS_EMAIL,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": settings.BUSINESS_CITY,
                "addressCountry": "US",
            },
            "url": self.BASE_URL,
            "priceRange": "$$$",
            "openingHours": "Mo-Sa 08:00-18:00",
            "description": "Premium custom food trucks and trailers for sale and rent in the USA. New and used food trucks with full kitchen setups.",
        }

    def generate_meta_tags(self, truck: dict = None, page: str = "home") -> dict:
        """Generate meta tags for a page."""
        if truck:
            price_str = (
                f"${truck['price']:,}/mo"
                if truck.get("usage") == "rent"
                else f"${truck['price']:,}"
            )
            return {
                "title": f"{truck['title']} | {price_str} | {settings.BUSINESS_NAME}",
                "description": truck["description"][:160],
                "og_title": f"{truck['title']} - {price_str}",
                "og_description": truck["description"][:200],
                "og_image": (
                    f"{self.BASE_URL}{truck['images'][0]}"
                    if truck.get("images")
                    else ""
                ),
                "og_url": f"{self.BASE_URL}/{truck['category']}/{truck['slug']}",
                "og_type": "product",
                "canonical": f"{self.BASE_URL}/{truck['category']}/{truck['slug']}",
            }

        pages = {
            "home": {
                "title": f"Top-Rated Custom Food Trucks for Sale | {settings.BUSINESS_NAME}",
                "description": f"Browse our premium selection of custom food trucks and trailers for sale and rent. New and used food trucks in {settings.BUSINESS_CITY}. Financing available.",
                "og_title": f"{settings.BUSINESS_NAME} - Premium Food Trucks & Trailers",
                "og_description": f"Find your perfect food truck or trailer. Custom builds, used units, and rentals available. Based in {settings.BUSINESS_CITY}.",
                "og_image": f"{self.BASE_URL}/assets/img/og-home.jpg",
                "og_url": self.BASE_URL,
                "og_type": "website",
                "canonical": self.BASE_URL,
            },
            "catalog": {
                "title": f"Food Trucks & Trailers Catalog | {settings.BUSINESS_NAME}",
                "description": f"Complete catalog of food trucks and trailers for sale and rent. Filter by type, condition, and price. {settings.BUSINESS_CITY} area.",
                "og_title": f"Browse Our Food Truck Catalog | {settings.BUSINESS_NAME}",
                "og_description": "Explore our full range of custom food trucks and trailers.",
                "og_image": f"{self.BASE_URL}/assets/img/og-catalog.jpg",
                "og_url": f"{self.BASE_URL}/catalog",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/catalog",
            },
            "about": {
                "title": f"About Us | {settings.BUSINESS_NAME}",
                "description": f"{settings.BUSINESS_NAME} is the leading food truck dealership in {settings.BUSINESS_CITY}. Custom builds, financing, and support.",
                "og_title": f"About {settings.BUSINESS_NAME}",
                "og_description": f"Learn about the team behind {settings.BUSINESS_NAME}.",
                "og_image": f"{self.BASE_URL}/assets/img/og-about.jpg",
                "og_url": f"{self.BASE_URL}/about",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/about",
            },
            "contact": {
                "title": f"Contact Us | {settings.BUSINESS_NAME}",
                "description": f"Get in touch with {settings.BUSINESS_NAME}. Call {settings.BUSINESS_PHONE} or fill out our contact form.",
                "og_title": f"Contact {settings.BUSINESS_NAME}",
                "og_description": f"Reach out to our team for quotes, questions, and support.",
                "og_image": f"{self.BASE_URL}/assets/img/og-contact.jpg",
                "og_url": f"{self.BASE_URL}/contact",
                "og_type": "website",
                "canonical": f"{self.BASE_URL}/contact",
            },
        }
        return pages.get(page, pages["home"])

    def generate_sitemap(self, trucks: list) -> str:
        """Generate XML sitemap."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        urls = [
            {"loc": self.BASE_URL, "priority": "1.0", "changefreq": "daily"},
            {
                "loc": f"{self.BASE_URL}/catalog",
                "priority": "0.9",
                "changefreq": "daily",
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
            urls.append(
                {
                    "loc": f"{self.BASE_URL}/{truck['category']}/{truck['slug']}",
                    "priority": "0.8",
                    "changefreq": "weekly",
                }
            )

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

        for url_data in urls:
            xml_parts.append("  <url>")
            xml_parts.append(f"    <loc>{url_data['loc']}</loc>")
            xml_parts.append(f"    <lastmod>{now}</lastmod>")
            xml_parts.append(f"    <changefreq>{url_data['changefreq']}</changefreq>")
            xml_parts.append(f"    <priority>{url_data['priority']}</priority>")
            xml_parts.append("  </url>")

        xml_parts.append("</urlset>")
        return "\n".join(xml_parts)


seo_service = SEOService()
