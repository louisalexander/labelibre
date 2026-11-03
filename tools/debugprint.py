import asyncio, sys, time
sys.path.insert(0, ".")
from supvan import aml, protocol as P
from supvan.ble import Printer

f = sys.argv[1]
img = aml.render(aml.load(f))
job = P.make_job(img)
print("blocks:", [(len(b), s) for b, s in job.blocks])
t0 = time.time()
def ts(): return f"{time.time()-t0:6.2f}"

async def main():
    pr = Printer(print)
    orig = pr.status
    async def status():
        s = await orig()
        print(ts(), "STA", s.raw[14:20].hex(), "printing" if s.printing else "", "busy" if s.busy else "", "buffull" if s.buf_full else "", s.problems())
        return s
    pr.status = status
    origcmd = pr.command
    async def command(cmd, a=0, b=0, timeout=4.0):
        r = await origcmd(cmd, a, b, timeout)
        if cmd != P.INQUIRY_STA: print(ts(), f"cmd {cmd:02x} a={a} b={b} -> {r.hex()}")
        return r
    pr.command = command
    await pr.connect()
    try:
        await pr.print_job(job)
    finally:
        await pr.disconnect()
asyncio.run(main())
