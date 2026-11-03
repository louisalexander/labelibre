import asyncio, sys
from bleak import BleakScanner, BleakClient

async def main():
    d = await BleakScanner.find_device_by_filter(lambda d, a: (a.local_name or d.name or "").startswith("T0"), timeout=15)
    print("found", d)
    async with BleakClient(d) as c:
        print("mtu", c.mtu_size)
        for s in c.services:
            print("SVC", s.uuid, s.description)
            for ch in s.characteristics:
                val = ""
                if "read" in ch.properties:
                    try: val = (await c.read_gatt_char(ch)).hex()
                    except Exception as e: val = f"<{e}>"
                print("   CHR", ch.uuid, ch.handle, ch.properties, ch.max_write_without_response_size, val)
asyncio.run(main())
