"""Draw a simple label-printer icon and build an .icns with iconutil."""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(sys.argv[1])
S = 1024
im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((90, 90, 934, 934), 190, fill=(47, 111, 79, 255))
# label
d.rounded_rectangle((230, 300, 794, 724), 40, fill=(250, 249, 244, 255))
d.rectangle((285, 360, 520, 410), fill=(29, 29, 27, 255))
for i, w in enumerate((420, 330, 380)):
    d.rectangle((285, 450 + i * 60, 285 + w, 478 + i * 60), fill=(29, 29, 27, 255))
# QR-ish block
for r in range(4):
    for c in range(4):
        if (r * 3 + c) % 3 != 1:
            d.rectangle((600 + c * 36, 540 + r * 36, 630 + c * 36, 570 + r * 36), fill=(29, 29, 27, 255))

with tempfile.TemporaryDirectory() as t:
    iset = Path(t) / "AppIcon.iconset"
    iset.mkdir()
    for s in (16, 32, 128, 256, 512):
        im.resize((s, s), Image.LANCZOS).save(iset / f"icon_{s}x{s}.png")
        im.resize((s * 2, s * 2), Image.LANCZOS).save(iset / f"icon_{s}x{s}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iset), "-o", str(out)], check=True)
