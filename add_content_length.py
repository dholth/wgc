#!/usr/bin/env python

import asyncio
import json
from pathlib import Path

import httpx
import httpx_pycurl

PREFIX = "https://files.pythonhosted.org"


async def enrich(data):
    async with httpx.AsyncClient(
        transport=httpx_pycurl.AsyncPyCurlTransport()
    ) as client:
        for line in data:
            response = await client.head(f"{PREFIX}{line['url']}")
            print(response)
            line["length"] = int(response.headers["content-length"])


if __name__ == "__main__":
    data = json.loads(
        Path("/home/dholth/prog/wgc/bquxjob_3ea49f04_19e5f2c57f9.json").read_bytes()
    )
    asyncio.run(enrich(data))
    Path("pypi-20260524.json").write_text(json.dumps(data))
