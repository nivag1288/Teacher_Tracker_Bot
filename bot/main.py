import asyncio
import uvicorn
from bot import config
from bot.client import StatsClient
from tracker.backfill import BackfillStatus
from tracker.db import create_tables


async def main() -> None:
    await create_tables(config.DB_PATH)

    status = BackfillStatus()
    bot = StatsClient(db_path=config.DB_PATH, status=status)

    from web.app import create_app
    app = create_app(db_path=config.DB_PATH, status=status)

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=config.WEB_PORT, log_level="warning")
    )

    print(f"[web] Portal starting at http://127.0.0.1:{config.WEB_PORT}")
    await asyncio.gather(bot.start(config.DISCORD_TOKEN), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
