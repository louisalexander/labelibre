"""Parse Labelife/LPAPI .aml label files and render them to a 1-bit bitmap."""
from __future__ import annotations

import base64
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

DOTS_PER_MM = 8


def _f(el, tag, default=0.0) -> float:
    t = el.findtext(tag)
    try:
        return float(t) if t is not None else default
    except ValueError:
        return default


@dataclass
class Label:
    path: Path
    name: str
    width_mm: float
    height_mm: float
    rotate180: bool
    images: list[dict] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


def load(path: str | Path) -> Label:
    path = Path(path)
    with open(path, "rb") as fh:
        return load_bytes(fh, path.name)


def load_bytes(fh, filename: str) -> Label:
    path = Path(filename)
    root = ET.parse(fh).getroot()
    if root.tag != "LPAPI":
        raise ValueError("not a Labelife .aml label file")
    lab = Label(
        path=path,
        name=path.stem,
        width_mm=_f(root, "labelWidth", 40),
        height_mm=_f(root, "labelHeight", 30),
        rotate180=root.findtext("isRotate180", "0").strip() == "1",
    )
    for page in root.iter("WdPage"):
        contents = page.find("contents")
        if contents is None:
            continue
        for el in contents:
            if el.tag == "Image":
                lab.images.append({
                    "png": base64.b64decode(el.findtext("content", "")),
                    "x": _f(el, "x"), "y": _f(el, "y"),
                    "w": _f(el, "width"), "h": _f(el, "height"),
                    "rot": _f(el, "orientation"),
                    "mirror": el.findtext("isMirror", "0").strip() == "1",
                    "invert": el.findtext("antiColor", "0").strip() == "1",
                })
            else:
                lab.unsupported.append(el.tag)
        break  # first page only
    return lab


def render(lab: Label, threshold: int = 200, dither: bool = False) -> Image.Image:
    """Render the label as an 'L' image (white background) at 8 dots/mm,
    width = label width, height = label height, then threshold to mode '1'."""
    W = round(lab.width_mm * DOTS_PER_MM)
    H = round(lab.height_mm * DOTS_PER_MM)
    canvas = Image.new("L", (W, H), 255)
    for it in lab.images:
        src = Image.open(io.BytesIO(it["png"]))
        if src.mode in ("RGBA", "LA", "P"):
            src = src.convert("RGBA")
            bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
            src = Image.alpha_composite(bg, src)
        g = src.convert("L")
        bw, bh = max(1, round(it["w"] * DOTS_PER_MM)), max(1, round(it["h"] * DOTS_PER_MM))
        g = g.resize((bw, bh), Image.LANCZOS)
        if it["mirror"]:
            g = ImageOps.mirror(g)
        if it["invert"]:
            g = ImageOps.invert(g)
        if it["rot"]:
            # LPAPI orientation is clockwise degrees about the box centre
            g = g.rotate(-it["rot"], expand=True, resample=Image.BICUBIC, fillcolor=255)
        cx = (it["x"] + it["w"] / 2) * DOTS_PER_MM
        cy = (it["y"] + it["h"] / 2) * DOTS_PER_MM
        canvas.paste(g, (round(cx - g.width / 2), round(cy - g.height / 2)))
    if lab.rotate180:
        canvas = canvas.rotate(180)
    if dither:
        return canvas.convert("1")
    return canvas.point(lambda v: 255 if v >= threshold else 0, mode="1")
