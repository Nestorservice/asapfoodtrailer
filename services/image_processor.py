"""
ASAP Food Trailer - Image Processing Service
Handles image resizing, WebP conversion, and compression
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

    def validate_image(self, filename: str, file_size: int) -> Tuple[bool, str]:
        """Validate image file."""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"Extension non autorisée: {ext}"
        if file_size > self.MAX_FILE_SIZE:
            return (
                False,
                f"Fichier trop volumineux (max {self.MAX_FILE_SIZE // (1024*1024)}MB)",
            )
        return True, "OK"

    def process_image(self, image_data: bytes, filename: str) -> dict:
        """Process an uploaded image: resize and convert to WebP."""
        if not PIL_AVAILABLE:
            # Save as-is without processing
            saved_name = f"{uuid.uuid4()}{os.path.splitext(filename)[1]}"
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
        base_name = str(uuid.uuid4())

        for size_name, dimensions in self.SIZES.items():
            resized = img.copy()
            resized.thumbnail(dimensions, Image.LANCZOS)

            file_name = f"{base_name}_{size_name}.webp"
            file_path = os.path.join(self.upload_dir, file_name)

            resized.save(file_path, "WebP", quality=82, method=4)
            result[size_name] = f"/uploads/{file_name}"

        # Save original as WebP too
        original_name = f"{base_name}_original.webp"
        original_path = os.path.join(self.upload_dir, original_name)
        img.save(original_path, "WebP", quality=90, method=4)
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
