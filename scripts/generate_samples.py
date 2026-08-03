from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def make_sample(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (600, 400), (238, 181, 40))
    draw = ImageDraw.Draw(image)
    for x in range(0, 600, 20):
        color = (238 - x // 8, 80 + x // 6, 70 + x // 10)
        draw.rectangle((x, 0, x + 20, 400), fill=color)
    draw.ellipse((180, 80, 420, 320), fill=(245, 245, 230), outline=(30, 30, 30), width=6)
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)

    from reportlab.lib.utils import ImageReader

    page_width, page_height = A4
    c = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
    c.setTitle("AI Print Production OS POC Input")
    c.setFillColorRGB(0.08, 0.36, 0.62)
    c.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(15 * mm, page_height - 24 * mm, "PRINT PREFLIGHT POC")
    c.setFont("Helvetica", 11)
    c.drawString(15 * mm, page_height - 32 * mm, "RGB content / unembedded Base-14 fonts / no bleed")
    c.drawImage(ImageReader(image_buffer), 15 * mm, 73 * mm, width=180 * mm, height=120 * mm, mask="auto")
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 10)
    c.drawString(15 * mm, 58 * mm, "Embedded raster: 600 x 400 px placed at 180 x 120 mm")
    c.drawString(15 * mm, 51 * mm, "Expected effective resolution: about 84.7 DPI")
    c.showPage()
    c.save()


if __name__ == "__main__":
    make_sample(Path("tmp/pdfs/poc-input.pdf"))
