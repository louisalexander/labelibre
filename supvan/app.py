"""Label Printer app: a local web UI for batch printing .aml labels to a Supvan T50M Pro."""
from __future__ import annotations

import asyncio
import io
import itertools
import os
import socket
import sys
import time
import traceback
import webbrowser
from pathlib import Path

from aiohttp import web

from . import aml, protocol as P
from .ble import Printer, PrinterError

HERE = Path(__file__).parent
_ids = itertools.count(1)


class State:
    def __init__(self):
        self.labels: dict[str, aml.Label] = {}
        self.lock = asyncio.Lock()          # one BLE session at a time
        self.job = {"running": False, "done": 0, "total": 0, "current": "", "error": None,
                    "cancel": False, "log": []}
        self.last_seen = time.time()

    def log(self, msg):
        self.job["log"] = (self.job["log"] + [f"{time.strftime('%H:%M:%S')} {msg}"])[-50:]


S = State()


def settings_from(d) -> dict:
    def num(k, default, lo, hi):
        try:
            return max(lo, min(hi, int(d.get(k, default))))
        except (TypeError, ValueError):
            return default
    return {
        "threshold": num("threshold", 200, 1, 254),
        "density": num("density", 8, 1, 15),
        "rotate180": str(d.get("rotate180", "")).lower() in ("1", "true", "on", "yes"),
        "dither": str(d.get("dither", "")).lower() in ("1", "true", "on", "yes"),
    }


def render(lab: aml.Label, st: dict):
    img = aml.render(lab, st["threshold"], st["dither"])
    return img.rotate(180) if st["rotate180"] else img


# ------------------------------------------------------------------ routes
async def index(_req):
    return web.FileResponse(HERE / "static" / "index.html")


async def upload(req: web.Request):
    reader = await req.multipart()
    added, errors = [], []
    async for part in reader:
        if part.name != "files":
            continue
        name = Path(part.filename or "label.aml").name
        data = await part.read()
        try:
            tmp = io.BytesIO(data)
            lab = aml.load_bytes(tmp, name)
            lid = str(next(_ids))
            S.labels[lid] = lab
            added.append(label_info(lid, lab))
        except Exception as e:
            errors.append(f"{name}: {e}")
    return web.json_response({"added": added, "errors": errors})


def label_info(lid, lab):
    return {"id": lid, "name": lab.name, "width_mm": lab.width_mm, "height_mm": lab.height_mm,
            "warnings": sorted(set(lab.unsupported))}


async def list_labels(_req):
    return web.json_response([label_info(k, v) for k, v in S.labels.items()])


async def remove(req: web.Request):
    S.labels.pop(req.match_info["id"], None)
    return web.json_response({"ok": True})


async def preview(req: web.Request):
    lab = S.labels.get(req.match_info["id"])
    if not lab:
        raise web.HTTPNotFound()
    img = render(lab, settings_from(req.query)).convert("L")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return web.Response(body=buf.getvalue(), content_type="image/png",
                        headers={"Cache-Control": "no-store"})


async def status(_req):
    if S.job["running"]:
        return web.json_response({"connected": True, "busy": True})
    async with S.lock:
        try:
            pr = Printer()
            await pr.connect()
            try:
                st = await pr.status()
                try:
                    mat = await pr.material()
                except Exception:
                    mat = {}
            finally:
                await pr.disconnect()
            return web.json_response({"connected": True, "name": pr.name, "problems": st.problems(),
                                      "low_battery": st.low_battery, "material": mat})
        except Exception as e:
            return web.json_response({"connected": False, "error": str(e)})


async def run_job(items, st):
    j = S.job
    try:
        jobs = []
        for it in items:
            lab = S.labels[it["id"]]
            img = render(lab, st)
            jobs.append((lab.name, P.make_job(img, density=st["density"]), it["copies"]))
        j["total"] = sum(c for *_, c in jobs)
        async with S.lock:
            pr = Printer(S.log)
            await pr.connect()
            try:
                for name, job, copies in jobs:
                    for _ in range(copies):
                        if j["cancel"]:
                            S.log("cancelled")
                            return
                        j["current"] = name
                        S.log(f"printing {name}")
                        await pr.print_job(job)
                        j["done"] += 1
                        await asyncio.sleep(0.3)
            finally:
                await pr.disconnect()
        S.log(f"finished: {j['done']} label(s)")
    except Exception as e:
        traceback.print_exc()
        j["error"] = str(e)
        S.log(f"error: {e}")
    finally:
        j["running"] = False
        j["current"] = ""


async def start_print(req: web.Request):
    if S.job["running"]:
        return web.json_response({"error": "a print job is already running"}, status=409)
    body = await req.json()
    items = []
    for it in body.get("items", []):
        try:
            copies = max(0, min(999, int(it.get("copies", 1))))
        except (TypeError, ValueError):
            copies = 1
        if it.get("id") in S.labels and copies > 0:
            items.append({"id": it["id"], "copies": copies})
    if not items:
        return web.json_response({"error": "nothing selected to print"}, status=400)
    S.job.update(running=True, done=0, total=sum(i["copies"] for i in items), current="",
                 error=None, cancel=False)
    asyncio.get_running_loop().create_task(run_job(items, settings_from(body.get("settings", {}))))
    return web.json_response({"ok": True})


async def cancel(_req):
    S.job["cancel"] = True
    return web.json_response({"ok": True})


async def progress(_req):
    S.last_seen = time.time()
    j = S.job
    return web.json_response({k: j[k] for k in ("running", "done", "total", "current", "error", "log")})


async def watchdog(app):
    """Quit when no browser tab has polled for a while (the app was closed)."""
    async def loop():
        while True:
            await asyncio.sleep(15)
            if not S.job["running"] and time.time() - S.last_seen > 120:
                print("no browser activity; exiting")
                os._exit(0)
    t = asyncio.create_task(loop())
    yield
    t.cancel()


def make_app(auto_quit: bool) -> web.Application:
    app = web.Application(client_max_size=200 * 1024 * 1024)
    app.add_routes([
        web.get("/", index),
        web.post("/api/upload", upload),
        web.get("/api/labels", list_labels),
        web.delete("/api/labels/{id}", remove),
        web.get("/api/preview/{id}.png", preview),
        web.get("/api/status", status),
        web.post("/api/print", start_print),
        web.post("/api/cancel", cancel),
        web.get("/api/progress", progress),
        web.static("/static", HERE / "static"),
    ])
    if auto_quit:
        app.cleanup_ctx.append(watchdog)
    return app


PORT = 8738


def main():
    url = f"http://127.0.0.1:{PORT}/"
    # Already running? Just open another window.
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            webbrowser.open(url)
            return
    auto_quit = "--no-auto-quit" not in sys.argv
    if "--no-browser" not in sys.argv:
        import threading
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    web.run_app(make_app(auto_quit), host="127.0.0.1", port=PORT, print=lambda *_: print(f"Label Printer at {url}"))


if __name__ == "__main__":
    main()
