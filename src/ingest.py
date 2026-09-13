"""PDF ingest: render pages to PNG bytes for vision models."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import fitz
from PIL import Image


@dataclass
class PageImage:
    page_index: int  # 0-based
    png_bytes: bytes
    width: int
    height: int

    @property
    def data_url(self) -> str:
        b64 = base64.b64encode(self.png_bytes).decode("ascii")
        return f"data:image/png;base64,{b64}"


def render_pdf(
    path: str,
    *,
    max_pages: int | None = None,
    dpi: float = 150.0,
    max_dim: int = 1600,
) -> list[PageImage]:
    """Render PDF pages to PNG. Caps page count and image size for API cost."""
    doc = fitz.open(path)
    pages: list[PageImage] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    n = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    for i in range(n):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = _downscale(img, max_dim)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        pages.append(PageImage(page_index=i, png_bytes=buf.getvalue(), width=img.width, height=img.height))
    doc.close()
    return pages


def page_count(path: str) -> int:
    doc = fitz.open(path)
    n = doc.page_count
    doc.close()
    return n


def _downscale(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img
    scale = max_dim / float(longest)
    return img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
