import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from main import app
import re

client = TestClient(app)
html = client.get('/').text

print("=== 1. PRELOAD LCP ===")
for m in re.findall(r'<link\s+rel=["\']preload["\'][^>]+>', html):
    print(m)

print("\n=== 2. HERO LCP IMAGE ===")
for m in re.findall(r'<picture>[\s\S]*?truck1[\s\S]*?</picture>', html):
    print(m)

print("\n=== 3. LOGO ===")
for m in re.findall(r'<picture>[\s\S]*?logo[\s\S]*?</picture>', html)[:2]:
    print(m)

print("\n=== 4. CSS MIN LINKS ===")
for m in re.findall(r'<link\s+rel=["\']stylesheet["\'][^>]+>', html):
    print(m)

print("\n=== 5. SCRIPT TAGS ===")
for m in re.findall(r'<script[^>]+src=[^>]+>', html):
    print(m)

print("\n=== 6. ACCESSIBILITY ARIA-LABELS ===")
for m in re.findall(r'<[^>]+aria-label=[^>]+>', html):
    print(m)

print("\n=== 7. HEADINGS ===")
for tag, text in re.findall(r'<(h[1-6])[^>]*>([\s\S]*?)</\1>', html):
    clean = re.sub(r'<[^>]+>', '', text).strip()
    if clean:
        print(f"{tag}: {clean[:50]}")

print("\n=== 8. LOCAL BUSINESS JSON-LD ===")
for m in re.findall(r'<script\s+type=["\']application/ld\+json["\']>([\s\S]*?)</script>', html):
    if "LocalBusiness" in m:
        print("Found LocalBusiness JSON-LD snippet:\n", m[:300], "...")
