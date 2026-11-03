"""Command line: preview, query and print .aml labels on a Supvan T50M Pro."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from PIL import Image

from . import aml, protocol as P
from .ble import Printer


def add_render_args(p):
    p.add_argument("--threshold", type=int, default=200, help="black/white cutoff 0-255 (default 200)")
    p.add_argument("--dither", action="store_true", help="dither greys instead of thresholding")
    p.add_argument("--rotate180", action="store_true", help="rotate output 180 degrees")


def render(path, a) -> Image.Image:
    lab = aml.load(path)
    if lab.unsupported:
        print(f"warning: {path}: ignoring unsupported elements {sorted(set(lab.unsupported))}", file=sys.stderr)
    img = aml.render(lab, a.threshold, a.dither)
    if a.rotate180:
        img = img.rotate(180)
    return img


async def cmd_status(a):
    async with Printer(print) as pr:
        s = await pr.status()
        print("status:", s.raw.hex(), "problems:", s.problems() or "none",
              "printing" if s.printing else "", "busy" if s.busy else "")
        try:
            print("material:", await pr.material())
        except Exception as e:
            print("material query failed:", e)


async def cmd_print(a):
    jobs = []
    for f in a.files:
        img = render(f, a)
        jobs.append((Path(f).name, P.make_job(img, bytes_per_line=a.bytes_per_line, density=a.density,
                                              margin_top=a.margin, margin_bottom=a.margin)))
    total = len(jobs) * a.copies
    n = 0
    async with Printer(print) as pr:
        for name, job in jobs:
            for _ in range(a.copies):
                n += 1
                print(f"[{n}/{total}] {name}")
                await pr.print_job(job)
                await asyncio.sleep(0.3)
    print("done")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="labelprint")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("preview", help="render .aml files to PNG previews")
    pv.add_argument("files", nargs="+")
    pv.add_argument("-o", "--out", default=".")
    add_render_args(pv)

    sub.add_parser("status", help="connect and show printer status / loaded labels")

    pp = sub.add_parser("print", help="print .aml files")
    pp.add_argument("files", nargs="+")
    pp.add_argument("-n", "--copies", type=int, default=1)
    pp.add_argument("--density", type=int, default=8, help="darkness 1-15 (default 8)")
    pp.add_argument("--margin", type=int, default=8, help="blank dots at each end of feed (default 8)")
    pp.add_argument("--bytes-per-line", type=int, default=48, choices=(40, 48))
    add_render_args(pp)

    a = ap.parse_args(argv)
    if a.cmd == "preview":
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        for f in a.files:
            dst = out / (Path(f).stem + ".png")
            render(f, a).save(dst)
            print(dst)
    elif a.cmd == "status":
        asyncio.run(cmd_status(a))
    else:
        asyncio.run(cmd_print(a))


if __name__ == "__main__":
    main()
