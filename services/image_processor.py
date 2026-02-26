"""
ASAP Food Trailer - Image Processing Service
Handles image resizing, WebP conversion, and compression.
Uses Firebase Storage for permanent cloud hosting.
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
        self._bucket_tried = False
        if self.use_firebase:
            print(
                f"[ImageProcessor] Firebase mode ON, bucket: {settings.FIREBASE_STORAGE_BUCKET}"
            )
        else:
            print(
                f"[ImageProcessor] Local mode (APP_MODE={settings.APP_MODE}, BUCKET={settings.FIREBASE_STORAGE_BUCKET})"
            )

    def _get_bucket(self):
        """Lazy-load Firebase Storage bucket."""
        if self._bucket is not None:
            return self._bucket
        if self._bucket_tried or not self.use_firebase:
            return None

        self._bucket_tried = True
        try:
            import firebase_admin
            from firebase_admin import storage

            # Firebase should already be initialized by database.py
            # Just get the default bucket
            if firebase_admin._apps:
                self._bucket = storage.bucket()
                print(f"[ImageProcessor] Got bucket: {self._bucket.name}")
            else:
                print("[ImageProcessor] ERROR: Firebase not initialized yet!")
                self.use_firebase = False
            return self._bucket
        except Exception as e:
            print(f"[ImageProcessor] Firebase Storage init FAILED: {e}")
            traceback.print_exc()
            self.use_firebase = False
            return None

    def _upload_to_firebase(
        self, file_data: bytes, remote_path: str, content_type: str = "image/webp"
    ) -> str:
        """Upload file to Firebase Storage and return a permanent download URL."""
        bucket = self._get_bucket()
        if not bucket:
            print(f"[ImageProcessor] No bucket available, cannot upload {remote_path}")
            return ""

        try:
            blob = bucket.blob(remote_path)
            # Set download token for permanent public access
            token = uuid.uuid4().hex
            blob.metadata = {"firebaseStorageDownloadTokens": token}
            blob.upload_from_string(file_data, content_type=content_type)

            # Build permanent download URL
            encoded_path = remote_path.replace("/", "%2F")
            url = (
                f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}"
                f"/o/{encoded_path}?alt=media&token={token}"
            )
            print(f"[ImageProcessor] Uploaded: {remote_path} -> {url[:80]}...")
            return url
        except Exception as e:
            print(f"[ImageProcessor] Upload FAILED for {remote_path}: {e}")
            traceback.print_exc()
            return ""

    def test_firebase_storage(self) -> dict:
        """Test Firebase Storage connectivity. Returns diagnostic info."""
        result = {
            "app_mode": settings.APP_MODE,
            "bucket_configured": settings.FIREBASE_STORAGE_BUCKET,
            "use_firebase": self.use_firebase,
            "bucket_ready": False,
            "upload_test": False,
            "error": None,
        }
        try:
            bucket = self._get_bucket()
            if bucket:
                result["bucket_ready"] = True
                result["bucket_name"] = bucket.name
                # Try a small test upload
                test_blob = bucket.blob("_test_connection.txt")
                test_blob.upload_from_string(b"ok", content_type="text/plain")
                test_blob.delete()
                result["upload_test"] = True
            else:
                result["error"] = "Could not initialize bucket"
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
        """Process an uploaded image: resize, convert to WebP, store permanently."""
        base_name = str(uuid.uuid4())

        if not PIL_AVAILABLE:
            ext = os.path.splitext(filename)[1]
            saved_name = f"{base_name}{ext}"
            ct = (
                "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
            )

            if self.use_firebase:
                url = self._upload_to_firebase(image_data, f"uploads/{saved_name}", ct)
                if url:
                    return {"original": url, "thumb": url, "medium": url, "large": url}

            # Local fallback
            path = os.path.join(self.upload_dir, saved_name)
            with open(path, "wb") as f:
                f.write(image_data)
            local = f"/uploads/{saved_name}"
            return {"original": local, "thumb": local, "medium": local, "large": local}

        img = Image.open(BytesIO(image_data))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = bg

        result = {}
        upload_failed = False

        for size_name, dims in self.SIZES.items():
            resized = img.copy()
            resized.thumbnail(dims, Image.LANCZOS)
            fname = f"{base_name}_{size_name}.webp"
            buf = BytesIO()
            resized.save(buf, "WebP", quality=82, method=4)
            data = buf.getvalue()

            if self.use_firebase and not upload_failed:
                url = self._upload_to_firebase(data, f"uploads/{fname}")
                if url:
                    result[size_name] = url
                    continue
                else:
                    upload_failed = True
                    print(
                        f"[ImageProcessor] Firebase failed, switching to local for remaining"
                    )

            # Local fallback
            fpath = os.path.join(self.upload_dir, fname)
            with open(fpath, "wb") as f:
                f.write(data)
            result[size_name] = f"/uploads/{fname}"

        # Original
        orig_name = f"{base_name}_original.webp"
        buf = BytesIO()
        img.save(buf, "WebP", quality=90, method=4)
        orig_data = buf.getvalue()

        if self.use_firebase and not upload_failed:
            url = self._upload_to_firebase(orig_data, f"uploads/{orig_name}")
            if url:
                result["original"] = url
                return result

        fpath = os.path.join(self.upload_dir, orig_name)
        with open(fpath, "wb") as f:
            f.write(orig_data)
        result["original"] = f"/uploads/{orig_name}"
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
