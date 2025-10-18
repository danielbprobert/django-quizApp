from io import BytesIO
from typing import Optional, Tuple
from PIL import Image, ImageOps
from django.core.files.base import ContentFile

def _ensure_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        return img.convert("RGB")
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img

def resize_and_optional_crop(
    file_field,
    max_size: Tuple[int, int] = (1600, 1600),
    crop_ratio: Optional[Tuple[int, int]] = None,
    quality: int = 85,
    format_hint: Optional[str] = None,
):
    """
    - Resizes image to fit within max_size (keeps aspect).
    - If crop_ratio is provided (w,h), center-crops to that ratio after resize.
    - Writes back to the same FileField (JPEG by default).
    """
    if not file_field:
        return

    file_field.seek(0)
    with Image.open(file_field) as img:
        img = _ensure_rgb(img)

        # 1) Constrain by max_size
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # 2) Optional center-crop to specific ratio (e.g. 4:3 or 1:1)
        if crop_ratio:
            target_w, target_h = crop_ratio
            target_aspect = target_w / target_h
            w, h = img.size
            current_aspect = w / h
            if current_aspect > target_aspect:
                # crop width
                new_w = int(h * target_aspect)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            elif current_aspect < target_aspect:
                # crop height
                new_h = int(w / target_aspect)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))

        # 3) Save back
        buf = BytesIO()
        fmt = (format_hint or "JPEG").upper()
        if fmt not in ("JPEG", "JPG", "WEBP", "PNG"):
            fmt = "JPEG"
        save_kwargs = dict(quality=quality, optimize=True)
        if fmt == "WEBP":
            save_kwargs.update(method=6)
        img.save(buf, fmt, **save_kwargs)
        file_field.save(file_field.name, ContentFile(buf.getvalue()), save=False)
