"""统一启动脚本。

根据 BOT_RUN_MODE 环境变量选择运行模式：
  ws   — 启动飞书 WebSocket 长连接（默认）
  http — 启动 FastAPI HTTP 服务

用法：
  python scripts/run.py
  BOT_RUN_MODE=http python scripts/run.py
"""

import os
import sys
import logging

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BOT_RUN_MODE = os.getenv("BOT_RUN_MODE", "ws")


def main():
    if BOT_RUN_MODE == "ws":
        logger.info("BOT_RUN_MODE=ws, starting feishu websocket channel ...")
        from scripts.start_feishu_ws import main as ws_main

        import asyncio

        asyncio.run(ws_main())
    elif BOT_RUN_MODE == "http":
        logger.info("BOT_RUN_MODE=http, starting FastAPI HTTP server on 0.0.0.0:8000 ...")
        import uvicorn

        uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
    else:
        logger.error("Invalid BOT_RUN_MODE=%s, must be ws or http", BOT_RUN_MODE)
        sys.exit(1)


if __name__ == "__main__":
    main()
