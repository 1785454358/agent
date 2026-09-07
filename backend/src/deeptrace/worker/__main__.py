"""Run the distributed research worker as ``python -m deeptrace.worker``."""

import asyncio

from deeptrace.config import Settings
from deeptrace.worker.service import build_worker


async def main() -> None:
    worker = build_worker(Settings.from_env())
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
