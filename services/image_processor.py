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
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)
        self.use_firebase = settings.APP_MODE == "firebase" and bool(
            settings.FIREBASE_STORAGE_BUCKET
        )
        self._bucket = None

    def _get_bucket(self):
        """Lazy-load Firebase Storage bucket."""
        if self._bucket is not None:
            return self._bucket

        if not self.use_firebase:
            return None

        try:
            import firebase_admin
            from firebase_admin import storage

            if not firebase_admin._apps:
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

            self._bucket = storage.bucket(settings.FIREBASE_STORAGE_BUCKET)
            print(f"Firebase Storage bucket ready: {settings.FIREBASE_STORAGE_BUCKET}")
            return self._bucket
        except Exception as e:
            print(f"WARNING: Firebase Storage init failed: {e}")
            self.use_firebase = False
            return None

    def _upload_to_firebase(
        self, file_data: bytes, remote_path: str, content_type: str = "image/webp"
    ) -> str:
        """Upload file to Firebase Storage and return a permanent download URL."""
        bucket = self._get_bucket()
        if not bucket:
            return ""

        try:
            blob = bucket.blob(remote_path)
            # Generate a download token for permanent public access
            token = uuid.uuid4().hex
            blob.metadata = {"firebaseStorageDownloadTokens": token}
            blob.upload_from_string(file_data, content_type=content_type)
            # Build the Firebase Storage download URL with token
            bucket_name = settings.FIREBASE_STORAGE_BUCKET
            encoded_path = remote_path.replace("/", "%2F")
            url = f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}/o/{encoded_path}?alt=media&token={token}"
            return url
        except Exception as e:
            print(f"Firebase upload error for {remote_path}: {e}")
            return ""

    def validate_image(self, filename: str, file_size: int) -> Tuple[bool, str]:
        """Validate image file."""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"Extension not allowed: {ext}"
        if file_size > self.MAX_FILE_SIZE:
            return False, f"File too large (max {self.MAX_FILE_SIZE // (1024*1024)}MB)"
        return True, "OK"

    def process_image(self, image_data: bytes, filename: str) -> dict:
        """Process an uploaded image: resize, convert to WebP, store permanently."""
        base_name = str(uuid.uuid4())

        if not PIL_AVAILABLE:
            ext = os.path.splitext(filename)[1]
            saved_name = f"{base_name}{ext}"
            content_type = (
                "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
            )

            if self.use_firebase:
                url = self._upload_to_firebase(
                    image_data, f"uploads/{saved_name}", content_type
                )
                if url:
                    return {"original": url, "thumb": url, "medium": url, "large": url}

            # Fallback: save locally
            saved_path = os.path.join(self.upload_dir, saved_name)
            with open(saved_path, "wb") as f:
                f.write(image_data)
            return {
                "original": f"/uploads/{saved_name}",
                "thumb": f"/uploads/{saved_name}",
                "medium": f"/uploads/{saved_name}",
                "large": f"/uploads/{saved_name}",
            }

        img = Image.open(BytesIO(image_data))

        # Convert to RGB for WebP
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

        # Save original as WebP
        original_name = f"{base_name}_original.webp"
        buffer = BytesIO()
        img.save(buffer, "WebP", quality=90, method=4)
        original_data = buffer.getvalue()

        if self.use_firebase:
            url = self._upload_to_firebase(original_data, f"uploads/{original_name}")
            if url:
                result["original"] = url
                return result

        # Local fallback
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
