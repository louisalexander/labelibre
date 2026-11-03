"""BLE transport and print-job driver for the Supvan T50M Pro (bleak)."""
from __future__ import annotations

import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner

from . import protocol as P

SERVICE = "0000e0ff-3c17-d293-8e48-14fe2e4da212"
CHAR_WRITE = "0000ffe9-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000ffe1-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY2 = "0000ffea-0000-1000-8000-00805f9b34fb"
FRAGMENT = 128
NAME_PREFIXES = ("T0", "T5")


class PrinterError(RuntimeError):
    pass


async def find_printer(timeout: float = 15.0, name: str | None = None):
    def match(d, adv):
        n = adv.local_name or d.name or ""
        return n == name if name else n.startswith(NAME_PREFIXES)
    d = await BleakScanner.find_device_by_filter(match, timeout=timeout)
    if d is None:
        raise PrinterError("Printer not found. Is it switched on and not connected to a phone?")
    return d


class Printer:
    def __init__(self, log: Callable[[str], None] = lambda s: None):
        self.log = log
        self.client: BleakClient | None = None
        self.name = None
        self._rx = bytearray()
        self._waiters: list[tuple[int, asyncio.Future]] = []

    # ---------------------------------------------------------- connection
    async def connect(self, name: str | None = None):
        dev = await find_printer(name=name)
        self.name = dev.name
        self.log(f"connecting to {dev.name}")
        self.client = BleakClient(dev, disconnected_callback=lambda c: self._fail_all("printer disconnected"))
        await self.client.connect()
        for ch in (CHAR_NOTIFY, CHAR_NOTIFY2):
            try:
                await self.client.start_notify(ch, self._on_notify)
            except Exception:
                pass
        self.log("connected")

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()

    # ---------------------------------------------------------- receive
    def _on_notify(self, _ch, data: bytearray):
        self._rx += data
        while True:
            i = self._rx.find(P.MAGIC)
            if i < 0:
                self._rx.clear(); return
            del self._rx[:i]
            if len(self._rx) < 4:
                return
            total = 4 + int.from_bytes(self._rx[2:4], "little")
            if total < 8 or total > 4096:
                del self._rx[:2]; continue
            if len(self._rx) < total:
                return
            frame = bytes(self._rx[:total]); del self._rx[:total]
            for k, (cmd, fut) in enumerate(self._waiters):
                if frame[7] == cmd and not fut.done():
                    fut.set_result(frame); del self._waiters[k]; break

    def _fail_all(self, msg):
        for _, fut in self._waiters:
            if not fut.done():
                fut.set_exception(PrinterError(msg))
        self._waiters.clear()

    # ---------------------------------------------------------- transmit
    async def write(self, data: bytes):
        for off in range(0, len(data), FRAGMENT):
            await self.client.write_gatt_char(CHAR_WRITE, data[off:off + FRAGMENT], response=True)

    async def command(self, cmd: int, a: int = 0, b: int = 0, timeout: float = 4.0) -> bytes:
        fut = asyncio.get_running_loop().create_future()
        self._waiters.append((cmd, fut))
        await self.write(P.cmd_frame(cmd, a, b))
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._waiters = [w for w in self._waiters if w[1] is not fut]
            raise PrinterError(f"printer did not answer command 0x{cmd:02x}")

    # ---------------------------------------------------------- queries
    async def status(self) -> P.Status:
        return P.Status.parse(await self.command(P.INQUIRY_STA))

    async def material(self) -> dict:
        return P.parse_material(await self.command(P.RETURN_MAT, timeout=6))

    async def _poll(self, test, *, attempts, interval, what) -> P.Status:
        for _ in range(attempts):
            s = await self.status()
            if s.problems():
                raise PrinterError("Printer: " + ", ".join(s.problems()))
            if test(s):
                return s
            await asyncio.sleep(interval)
        raise PrinterError(f"printer never became {what}")

    # ---------------------------------------------------------- printing
    async def print_job(self, job: P.Job):
        await self.command(P.CHECK_DEVICE)
        await self._poll(lambda s: not s.busy and not s.printing, attempts=100, interval=0.1, what="ready")
        await self.command(P.START_PRINT, 0)
        await self._poll(lambda s: s.printing, attempts=60, interval=0.1, what="active")
        for block, speed in job.blocks:
            await self._poll(lambda s: not s.buf_full, attempts=500, interval=0.02, what="ready for data")
            frames = P.data_frames(block)
            await self.command(P.NEXT_ZIPPEDBULK, P.DATA_FRAME_SIZE, len(frames))
            for fr in frames:
                await self.write(fr)
            await asyncio.sleep(0.02)
            try:
                await self.command(P.BUF_FULL, len(block), speed, timeout=3)
            except PrinterError as e:
                self.log(f"BUF_FULL not acknowledged ({e}); continuing")
        for _ in range(300):
            await asyncio.sleep(0.1)
            s = await self.status()
            if not s.printing and not s.busy:
                return
        raise PrinterError("printer did not report finishing")
