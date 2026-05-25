#!/usr/bin/env python

import asyncio
import json
from pathlib import Path

import httpx
import httpx_pycurl

PREFIX = "https://files.pythonhosted.org"

OUTPUT = Path("dataset")


def sort_popular(data):
    """Sort by bytes downloaded per day, not outright file size."""
    for item in data:
        item["downloads"] = int(item["downloads"])
        item["aggregate"] = item["length"] * item["downloads"]
    data.sort(key=lambda x: -x["downloads"])
    for i, item in enumerate(data):
        item["rank"] = i + 1  # ranked by number of downloads
    data.sort(key=lambda x: -x["aggregate"])  # sorted by downloads * file size


async def download_biggest(data):
    async with httpx.AsyncClient(
        transport=httpx_pycurl.AsyncPyCurlTransport(), follow_redirects=True
    ) as client:
        for line in data[:32]:
            print(line)
            response = await client.get(f"{PREFIX}{line['url']}")
            print(response.headers)
            (OUTPUT / Path(line["url"]).name).write_bytes(response.content)


if __name__ == "__main__":
    data = json.loads(Path("pypi-20260524.json").read_bytes())
    sort_popular(data)
    asyncio.run(download_biggest(data))
