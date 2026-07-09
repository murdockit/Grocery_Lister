from __future__ import annotations

import argparse
import asyncio

from app.config import get_settings
from app.kroger import KrogerClient


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Find Kroger location IDs near a ZIP code.")
    parser.add_argument("zip_code")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    locations = await KrogerClient(get_settings()).find_locations(args.zip_code, args.limit)
    for location in locations:
        address = location.get("address") or {}
        line = ", ".join(
            part
            for part in [address.get("addressLine1"), address.get("city"), address.get("state")]
            if part
        )
        print(f"{location.get('locationId')}\t{location.get('name')}\t{line}")


if __name__ == "__main__":
    asyncio.run(_main())
