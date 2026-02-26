"""
ASAP Food Trailer - Image Processing Service
Handles image resizing, WebP conversion, and compression.
Uses Cloudinary for permanent cloud image hosting (free tier: 25GB).
"""

import os
import uuid
import traceback
from io import BytesIO
from typing import List, Tuple

from config import settings

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow not installed. Image processing disabled.")

# Cloudinary setup
CLOUDINARY_AVAILABLE = False
try:
    import cloudinary
    import cloudinary.uploader

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    api_key = os.getenv("CLOUDINARY_API_KEY", "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "")

    if cloud_name and api_key and api_secret:
        cloudinary.config(
            cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True
        )
        CLOUDINARY_AVAILABLE = True
        print(f"[ImageProcessor] Cloudinary ready (cloud: {cloud_name})")
    else:
        print("[ImageProcessor] Cloudinary not configured (missing env vars)")
except ImportError:
    print("[ImageProcessor] cloudinary package not installed")


class ImageProcessor:
    """Handles image processing: resize, convert to WebP, compress."""

    SIZES = {
        "thumb": (400, 300),
        "medium": (800, 600),
        "large": (1200, 900),
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)
        self.use_cloud = CLOUDINARY_AVAILABLE

    def _upload_to_cloudinary(
        self, image_data: bytes, folder: str = "asap_uploads"
    ) -> str:
        """Upload image to Cloudinary and return permanent URL."""
        if not self.use_cloud:
            return ""
        try:
            result = cloudinary.uploader.upload(
                image_data,
                folder=folder,
                resource_type="image",
                quality="auto:good",
                fetch_format="auto",
            )
            url = result.get("secure_url", "")
            print(f"[ImageProcessor] Cloudinary upload OK: {url[:80]}...")
            return url
        except Exception as e:
            print(f"[ImageProcessor] Cloudinary upload FAILED: {e}")
            traceback.print_exc()
            return ""

    def test_storage(self) -> dict:
        """Test cloud storage connectivity."""
        result = {
            "provider": "cloudinary" if self.use_cloud else "local",
            "cloud_configured": CLOUDINARY_AVAILABLE,
            "upload_test": False,
            "error": None,
        }
        if not CLOUDINARY_AVAILABLE:
            result["error"] = (
                "Cloudinary not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET"
            )
            return result

        try:
            # Upload a tiny test image
            import cloudinary.uploader

            test_result = cloudinary.uploader.upload(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82",
                folder="asap_test",
                resource_type="image",
            )
            # Clean up test
            if test_result.get("public_id"):
                cloudinary.uploader.destroy(test_result["public_id"])
            result["upload_test"] = True
            result["cloud_name"] = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        except Exception as e:
            result["error"] = str(e)
        return result

    def validate_image(self, filename: str, file_size: int) -> Tuple[bool, str]:
        """Validate image file."""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"Extension not allowed: {ext}"
        if file_size > self.MAX_FILE_SIZE:
            return False, f"File too large (max {self.MAX_FILE_SIZE // (1024*1024)}MB)"
        return True, "OK"

    def process_image(self, image_data: bytes, filename: str) -> dict:
        """Process an uploaded image and store permanently."""
        base_name = str(uuid.uuid4())

        # ── Cloud upload (Cloudinary) ─────────────────────────
        if self.use_cloud:
            if PIL_AVAILABLE:
                try:
                    img = Image.open(BytesIO(image_data))
                    if img.mode in ("RGBA", "LA", "P"):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "P":
                            img = img.convert("RGBA")
                        bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                        img = bg

                    result = {}
                    for size_name, dims in self.SIZES.items():
                        resized = img.copy()
                        resized.thumbnail(dims, Image.LANCZOS)
                        buf = BytesIO()
                        resized.save(buf, "WebP", quality=82, method=4)
                        url = self._upload_to_cloudinary(buf.getvalue(), "asap_uploads")
                        if url:
                            result[size_name] = url
                        else:
                            break  # Cloud failed, fall through to local

                    if len(result) == len(self.SIZES):
                        # Upload original too
                        buf = BytesIO()
                        img.save(buf, "WebP", quality=90, method=4)
                        orig_url = self._upload_to_cloudinary(
                            buf.getvalue(), "asap_uploads"
                        )
                        if orig_url:
                            result["original"] = orig_url
                            return result
                except Exception as e:
                    print(f"[ImageProcessor] PIL processing error: {e}")

            else:
                # No PIL, upload raw
                url = self._upload_to_cloudinary(image_data, "asap_uploads")
                if url:
                    return {"original": url, "thumb": url, "medium": url, "large": url}

        # ── Local fallback ────────────────────────────────────
        if PIL_AVAILABLE:
            try:
                img = Image.open(BytesIO(image_data))
                if img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                    img = bg

                result = {}
                for size_name, dims in self.SIZES.items():
                    resized = img.copy()
                    resized.thumbnail(dims, Image.LANCZOS)
                    fname = f"{base_name}_{size_name}.webp"
                    fpath = os.path.join(self.upload_dir, fname)
                    resized.save(fpath, "WebP", quality=82, method=4)
                    result[size_name] = f"/uploads/{fname}"

                orig_name = f"{base_name}_original.webp"
                orig_path = os.path.join(self.upload_dir, orig_name)
                img.save(orig_path, "WebP", quality=90, method=4)
                result["original"] = f"/uploads/{orig_name}"
                return result
            except Exception as e:
                print(f"[ImageProcessor] Local PIL error: {e}")

        # Raw fallback
        ext = os.path.splitext(filename)[1]
        saved_name = f"{base_name}{ext}"
        path = os.path.join(self.upload_dir, saved_name)
        with open(path, "wb") as f:
            f.write(image_data)
        local = f"/uploads/{saved_name}"
        return {"original": local, "thumb": local, "medium": local, "large": local}

    async def process_upload(self, file) -> dict:
        """Process a file upload from FastAPI UploadFile."""
        contents = await file.read()
        valid, msg = self.validate_image(file.filename, len(contents))
        if not valid:
            raise ValueError(msg)
        return self.process_image(contents, file.filename)

    async def process_multiple_uploads(self, files: list) -> List[dict]:
        """Process multiple file uploads."""
        results = []
        for file in files:
            result = await self.process_upload(file)
            results.append(result)
        return results


image_processor = ImageProcessor()
