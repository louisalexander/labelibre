import asyncio
from bleak import BleakScanner

async def main():
    devs = await BleakScanner.discover(timeout=12, return_adv=True)
    for addr, (d, adv) in sorted(devs.items(), key=lambda x: -x[1][1].rssi):
        print(f"{adv.rssi:4d} {addr} name={d.name!r} local={adv.local_name!r} uuids={adv.service_uuids} mfr={ {k: v.hex() for k, v in adv.manufacturer_data.items()} }")

asyncio.run(main())
