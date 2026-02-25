"""
ASAP Food Trailer - Image Processing Service
Handles image resizing, WebP conversion, and compression.
Supports local storage and Firebase Storage for permanent hosting.
"""

import os
import uuid
from io import BytesIO
from typing import List, Tuple

from config import settings

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow not installed. Image processing disabled.")


class ImageProcessor:
    """Handles image processing: resize, convert to WebP, compress."""

    SIZES = {
        "thumb": (400, 300),
        "medium": (800, 600),
        "large": (1200, 900),
    }
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)
        self.use_firebase = (
            settings.APP_MODE == "firebase" and settings.FIREBASE_STORAGE_BUCKET
        )
        self._bucket = None

    def _get_bucket(self):
        """Lazy-load Firebase Storage bucket."""
        if self._bucket is None and self.use_firebase:
            try:
                import firebase_admin
                from firebase_admin import storage

                # firebase_admin should already be initialized by database.py
                if not firebase_admin._apps:
                    # Safety fallback — init if not already done
                    from firebase_admin import credentials

                    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
                    if sa_json:
                        import json

                        cred = credentials.Certificate(json.loads(sa_json))
                    else:
                        cred = credentials.Certificate(
                            settings.FIREBASE_SERVICE_ACCOUNT_PATH
                        )
                    firebase_admin.initialize_app(
                        cred, {"storageBucket": settings.FIREBASE_STORAGE_BUCKET}
                    )
                else:
                    # App already initialized, check if storage bucket is set
                    app = firebase_admin.get_app()
                    if not app.options.get("storageBucket"):
                        # Re-init not possible, but we can still get bucket directly
                        pass

                self._bucket = storage.bucket(settings.FIREBASE_STORAGE_BUCKET)
            except Exception as e:
                print(
                    f"WARNING: Firebase Storage init failed: {e}. Falling back to local."
                )
                self.use_firebase = False
        return self._bucket

    def _upload_to_firebase(
        self, file_data: bytes, remote_path: str, content_type: str = "image/webp"
    ) -> str:
        """Upload file to Firebase Storage and return public URL."""
        bucket = self._get_bucket()
        if not bucket:
            return ""

        blob = bucket.blob(remote_path)
        blob.upload_from_string(file_data, content_type=content_type)
        blob.make_public()
        return blob.public_url

    def validate_image(self, filename: str, file_size: int) -> Tuple[bool, str]:
        """Validate image file."""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"Extension not allowed: {ext}"
        if file_size > self.MAX_FILE_SIZE:
            return (
                False,
                f"File too large (max {self.MAX_FILE_SIZE // (1024*1024)}MB)",
            )
        return True, "OK"

    def process_image(self, image_data: bytes, filename: str) -> dict:
        """Process an uploaded image: resize, convert to WebP, store permanently."""
        base_name = str(uuid.uuid4())

        if not PIL_AVAILABLE:
            # Save as-is without processing
            ext = os.path.splitext(filename)[1]
            saved_name = f"{base_name}{ext}"

            if self.use_firebase:
                content_type = (
                    "image/jpeg"
                    if ext in (".jpg", ".jpeg")
                    else f"image/{ext.lstrip('.')}"
                )
                url = self._upload_to_firebase(
                    image_data, f"uploads/{saved_name}", content_type
                )
                if url:
                    return {"original": url, "thumb": url, "medium": url, "large": url}

            # Fallback: save locally
            saved_path = os.path.join(self.upload_dir, saved_name)
            with open(saved_path, "wb") as f:
                f.write(image_data)
            url = f"/uploads/{saved_name}"
            return {"original": url, "thumb": url, "medium": url, "large": url}

        img = Image.open(BytesIO(image_data))

        # Convert RGBA to RGB for WebP
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = background

        result = {}

        for size_name, dimensions in self.SIZES.items():
            resized = img.copy()
            resized.thumbnail(dimensions, Image.LANCZOS)

            file_name = f"{base_name}_{size_name}.webp"
            buffer = BytesIO()
            resized.save(buffer, "WebP", quality=82, method=4)
            webp_data = buffer.getvalue()

            if self.use_firebase:
                url = self._upload_to_firebase(webp_data, f"uploads/{file_name}")
                if url:
                    result[size_name] = url
                    continue

            # Fallback: save locally
            file_path = os.path.join(self.upload_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(webp_data)
            result[size_name] = f"/uploads/{file_name}"

        # Save original as WebP too
        original_name = f"{base_name}_original.webp"
        buffer = BytesIO()
        img.save(buffer, "WebP", quality=90, method=4)
        original_data = buffer.getvalue()

        if self.use_firebase:
            url = self._upload_to_firebase(original_data, f"uploads/{original_name}")
            if url:
                result["original"] = url
            else:
                original_path = os.path.join(self.upload_dir, original_name)
                with open(original_path, "wb") as f:
                    f.write(original_data)
                result["original"] = f"/uploads/{original_name}"
        else:
            original_path = os.path.join(self.upload_dir, original_name)
            with open(original_path, "wb") as f:
                f.write(original_data)
            result["original"] = f"/uploads/{original_name}"

        return result

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
