#!/usr/bin/env python3
"""
ASAP Food Trucks — Script d'optimisation et conversion des images (PageSpeed Insights)
Convertit les images JPEG en WebP avec compression adaptée et génère les logos redimensionnés.
"""

import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets", "img")

# 1. Configuration des images à convertir
IMAGES_TO_CONVERT = [
    # (chemin relatif, qualité WebP, redimensionnement max optionnel)
    ("hero/truck1.jpeg", "hero/truck1.webp", 70),
    ("hero/truck2.jpeg", "hero/truck2.webp", 75),
    ("hero/truck3.jpeg", "hero/truck3.webp", 70),
    ("deliver.jpeg", "deliver.webp", 72),
]

def optimize_images():
    print("=" * 60)
    print("ASAP Food Trucks — Conversion des images en WebP")
    print("=" * 60)

    total_orig = 0
    total_opt = 0

    for src_rel, dst_rel, quality in IMAGES_TO_CONVERT:
        src = os.path.join(ASSETS_DIR, src_rel)
        dst = os.path.join(ASSETS_DIR, dst_rel)

        if not os.path.exists(src):
            print(f"[!] Source introuvable : {src}")
            continue

        im = Image.open(src)
        if im.mode in ("RGBA", "LA") and not dst.endswith(".webp"):
            im = im.convert("RGB")

        orig_size = os.path.getsize(src)
        im.save(dst, "WEBP", quality=quality, method=6)
        opt_size = os.path.getsize(dst)

        total_orig += orig_size
        total_opt += opt_size
        pct = (1 - opt_size / orig_size) * 100
        print(f"[OK] {src_rel} ({orig_size:,} octets) -> {dst_rel} ({opt_size:,} octets) [-{pct:.1f}%]")

    # 2. Traitement du logo (~50px affiché, 100px pour écrans Retina 2x)
    logo_src = os.path.join(ASSETS_DIR, "logo", "logo.jpg")
    if os.path.exists(logo_src):
        logo = Image.open(logo_src)
        
        # 50x50 (taille affichée)
        logo_50 = logo.resize((50, 50), Image.Resampling.LANCZOS)
        p50_webp = os.path.join(ASSETS_DIR, "logo", "logo-50.webp")
        p50_png = os.path.join(ASSETS_DIR, "logo", "logo-50.png")
        logo_50.save(p50_webp, "WEBP", quality=85, method=6)
        logo_50.save(p50_png, "PNG", optimize=True)

        # 100x100 (Retina 2x)
        logo_100 = logo.resize((100, 100), Image.Resampling.LANCZOS)
        p100_webp = os.path.join(ASSETS_DIR, "logo", "logo-100.webp")
        p100_png = os.path.join(ASSETS_DIR, "logo", "logo-100.png")
        logo_100.save(p100_webp, "WEBP", quality=85, method=6)
        logo_100.save(p100_png, "PNG", optimize=True)

        orig_logo_size = os.path.getsize(logo_src)
        size_50_webp = os.path.getsize(p50_webp)
        size_50_png = os.path.getsize(p50_png)
        size_100_webp = os.path.getsize(p100_webp)
        size_100_png = os.path.getsize(p100_png)

        print("-" * 60)
        print(f"[OK] Logo original : {orig_logo_size:,} octets (320x320)")
        print(f"[OK] logo-50.webp  : {size_50_webp:,} octets (-{(1 - size_50_webp / orig_logo_size)*100:.1f}%)")
        print(f"[OK] logo-50.png   : {size_50_png:,} octets")
        print(f"[OK] logo-100.webp : {size_100_webp:,} octets")
        print(f"[OK] logo-100.png  : {size_100_png:,} octets")

    print("=" * 60)
    if total_orig > 0:
        total_pct = (1 - total_opt / total_orig) * 100
        print(f"Total économisé sur les images : {total_orig - total_opt:,} octets (-{total_pct:.1f}%)")
    print("=" * 60)

if __name__ == "__main__":
    optimize_images()
