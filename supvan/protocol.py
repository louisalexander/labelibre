"""Supvan T50M Pro wire protocol: command frames, print buffers, LZMA, data frames.

Ported from the open-source reverse engineering of the Katasymbol app
(heeen/supvan-cups, bbass07/price-tags, kcsfelty/supvan-labeler).
"""
from __future__ import annotations

import lzma
from dataclasses import dataclass

MAGIC = b"\x7e\x5a"

# opcodes
BUF_FULL = 0x10
INQUIRY_STA = 0x11
CHECK_DEVICE = 0x12
START_PRINT = 0x13
STOP_PRINT = 0x14
RD_DEV_NAME = 0x16
RETURN_MAT = 0x30
NEXT_ZIPPEDBULK = 0x5C
READ_FWVER = 0xC5

DOTS_PER_MM = 8
HEAD_DOTS = 384
PRINT_BUF_SIZE = 4096
PRINT_BUF_HEADER = 14
MAX_BUF_DATA = 4074
MAX_COMPRESSED_BLOCK = 4096
DATA_PAYLOAD = 500
DATA_FRAME_SIZE = 512


def cmd_frame(cmd: int, a: int = 0, b: int = 0) -> bytes:
    f = bytearray(16)
    f[0:7] = bytes([0x7E, 0x5A, 0x0C, 0x00, 0x10, 0x01, 0xAA])
    f[7] = cmd
    f[11] = 0x01
    f[12:14] = (a & 0xFFFF).to_bytes(2, "little")
    f[14:16] = (b & 0xFFFF).to_bytes(2, "little")
    f[8:10] = (sum(f[10:16]) & 0xFFFF).to_bytes(2, "little")
    return bytes(f)


@dataclass
class Status:
    raw: bytes
    buf_full: bool
    label_rw_error: bool
    label_end: bool
    label_mode_error: bool
    roll_missing: bool
    low_battery: bool
    busy: bool
    head_hot: bool
    cover_open: bool
    printing: bool
    no_label: bool

    @classmethod
    def parse(cls, f: bytes) -> "Status":
        if len(f) < 18:
            raise ValueError(f"short status frame: {f.hex()}")
        m0, m1, s0, s1 = f[14], f[15], f[16], f[17]
        return cls(
            raw=bytes(f), buf_full=bool(m0 & 1), label_rw_error=bool(m0 & 2),
            label_end=bool(m0 & 4), label_mode_error=bool(m0 & 8),
            roll_missing=bool(m0 & 0x10), low_battery=bool(m0 & 0x40),
            busy=bool(m1 & 4), head_hot=bool(m1 & 8), cover_open=bool(s0 & 8),
            printing=bool(s0 & 0x40), no_label=bool(s1 & 1),
        )

    def problems(self) -> list[str]:
        out = []
        if self.cover_open: out.append("cover is open")
        if self.label_end: out.append("out of labels")
        if self.roll_missing or self.no_label: out.append("label roll not installed")
        if self.label_mode_error: out.append("label type not recognised")
        if self.label_rw_error: out.append("cannot read label roll tag")
        if self.head_hot: out.append("print head too hot")
        return out


def parse_material(f: bytes) -> dict:
    if len(f) < 48:
        return {"raw": f.hex()}
    return {
        "paper_type": f[39],
        "width_mm": f[40],
        "length_mm": f[41],
        "gap_mm": f[42],
        "remaining": int.from_bytes(f[43:47], "little"),
        "code": f[29:37].hex(),
    }


# ---------------------------------------------------------------- raster

def to_head_lines(img, bytes_per_line: int = 48,
                  mirror: bool = True) -> bytes:
    """Convert a 1-bit PIL image (width across the head, height along feed)
    into column-major LSB-first head lines. Row 0 of the image is sent first.
    The image is centred across `bytes_per_line*8` dots and mirrored, as the
    head's dot 0 is at the image's right edge."""
    w, h = img.size
    usable = bytes_per_line * 8
    if w > usable:
        raise ValueError(f"image {w} dots wide exceeds head line of {usable}")
    off = (usable - w) // 2
    px = img.load()
    out = bytearray(h * bytes_per_line)
    for y in range(h):
        base = y * bytes_per_line
        for x in range(w):
            if px[x, y] == 0:  # black
                d = ((w - 1 - x) if mirror else x) + off
                out[base + (d >> 3)] |= 1 << (d & 7)
    return bytes(out)


def build_print_buffers(lines: bytes, bytes_per_line: int, *, margin_top: int = 8,
                        margin_bottom: int = 8, density: int = 8) -> list[bytes]:
    total_cols = len(lines) // bytes_per_line
    printable = max(0, total_cols - margin_top - margin_bottom)
    max_cols = MAX_BUF_DATA // bytes_per_line
    chunks = [(s, min(max_cols, printable - s)) for s in range(0, printable, max_cols)] or [(0, 0)]
    bufs = []
    for i, (start, count) in enumerate(chunks):
        last = i == len(chunks) - 1
        buf = bytearray(PRINT_BUF_SIZE)
        b0 = (0x02 if i == 0 else 0) | (0x04 if last else 0) | (0x08 if last else 0)
        buf[2] = b0
        buf[3] = ((density & 0x0F) << 2) | (1 << 6)
        buf[4:6] = count.to_bytes(2, "little")
        buf[6] = bytes_per_line
        mt = min(max(margin_top, 1), 900)
        mb = min(max(margin_bottom, 1), 900)
        buf[8:10] = mt.to_bytes(2, "little")
        buf[10:12] = mb.to_bytes(2, "little")
        buf[12] = min(density, 15)
        frm = (margin_top + start) * bytes_per_line
        data = lines[frm: frm + count * bytes_per_line]
        buf[PRINT_BUF_HEADER: PRINT_BUF_HEADER + len(data)] = data
        chk = sum(buf[2:14])
        data_end = count * bytes_per_line + PRINT_BUF_HEADER
        for k in range(1, data_end // 256 + 1):
            chk += buf[k * 256 - 1]
        buf[0:2] = (chk & 0xFFFF).to_bytes(2, "little")
        bufs.append(bytes(buf))
    return bufs


def lzma_alone(data: bytes) -> bytes:
    filters = [{"id": lzma.FILTER_LZMA1, "dict_size": 8192, "lc": 3, "lp": 0, "pb": 2,
                "mode": lzma.MODE_NORMAL, "nice_len": 128, "mf": lzma.MF_BT4}]
    raw = lzma.compress(data, format=lzma.FORMAT_RAW, filters=filters)
    return bytes([0x5D, 0x00, 0x20, 0x00, 0x00]) + len(data).to_bytes(8, "little") + raw


def compress_blocks(bufs: list[bytes], max_group: int = 4) -> list[tuple[bytes, int]]:
    """Group buffers into LZMA blocks of <=4096 bytes. Returns (block, n_buffers)."""
    blocks, i = [], 0
    while i < len(bufs):
        n = min(max_group, len(bufs) - i)
        while True:
            c = lzma_alone(b"".join(bufs[i:i + n]))
            if len(c) <= MAX_COMPRESSED_BLOCK or n == 1:
                break
            n -= 1
        if len(c) > MAX_COMPRESSED_BLOCK:
            raise ValueError("a single print buffer does not compress below 4096 bytes")
        blocks.append((c, n))
        i += n
    return blocks


def speed_for(avg_compressed: int) -> int:
    for lim, sp in ((3000, 10), (2800, 15), (2500, 20), (2000, 25), (1500, 40), (1000, 45), (500, 55)):
        if avg_compressed > lim:
            return sp
    return 60


def data_frames(block: bytes) -> list[bytes]:
    total = -(-len(block) // DATA_PAYLOAD)
    frames = []
    for i in range(total):
        chunk = block[i * DATA_PAYLOAD:(i + 1) * DATA_PAYLOAD]
        pkt = bytearray(506)
        pkt[0:2] = b"\xaa\xbb"
        pkt[4] = i & 0xFF
        pkt[5] = total & 0xFF
        pkt[6:6 + len(chunk)] = chunk
        pkt[2:4] = (sum(pkt[4:506]) & 0xFFFF).to_bytes(2, "little")
        frames.append(bytes([0x7E, 0x5A, 0xFC, 0x01, 0x10, 0x02]) + bytes(pkt))
    return frames


@dataclass
class Job:
    """One page ready to send: list of (compressed block, speed)."""
    blocks: list[tuple[bytes, int]]


def make_job(img, *, bytes_per_line: int = 48, density: int = 8, margin_top: int = 8,
             margin_bottom: int = 8, mirror: bool = True) -> Job:
    lines = to_head_lines(img, bytes_per_line, mirror)
    bufs = build_print_buffers(lines, bytes_per_line, margin_top=margin_top,
                               margin_bottom=margin_bottom, density=density)
    blocks = compress_blocks(bufs)
    return Job([(c, speed_for(len(c) // n)) for c, n in blocks])
