import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.event_handler import handle_feishu_message_event
from app.schemas import FeishuChallenge
from app.settlement_scheduler import start_settlement_scheduler
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("service starting ...")
    tasks = []
    if settings.settlement_enabled:
        task = asyncio.create_task(start_settlement_scheduler())
        tasks.append(task)
        logger.info("settlement scheduler started")
    yield
    for t in tasks:
        t.cancel()
    logger.info("service shutting down ...")


app = FastAPI(title="housework-feishu-bot", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/feishu/events")
async def feishu_events(request: Request):
    body = await request.json()
    logger.info("received feishu event: %s", body)

    if body.get("type") == "url_verification":
        challenge = FeishuChallenge(**body)
        return JSONResponse({"challenge": challenge.challenge})

    await handle_feishu_message_event(body)
    return {"code": 0, "message": "ack"}
