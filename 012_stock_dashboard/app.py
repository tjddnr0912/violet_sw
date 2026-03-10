"""FastAPI main application: routes, WebSocket, worker lifecycle."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from config import DASHBOARD_PORT
from tiles.tile_manager import DataStore
from data_sources.yfinance_adapter import YFinanceAdapter
from workers.market_worker import MarketWorker
from workers.sector_worker import SectorWorker
from workers.sentiment_worker import SentimentWorker
from workers.news_worker import NewsWorker
from workers.alert_worker import AlertWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Global state
data_store = DataStore()
workers: list = []
worker_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global workers, worker_tasks
    logger.info("Starting dashboard workers...")

    shared_adapter = YFinanceAdapter()
    workers = [
        MarketWorker(data_store, adapter=shared_adapter),
        SectorWorker(data_store, adapter=shared_adapter),
        SentimentWorker(data_store, adapter=shared_adapter),
        NewsWorker(data_store),
        AlertWorker(data_store, adapter=shared_adapter),
    ]

    for w in workers:
        task = asyncio.create_task(w.run())
        worker_tasks.append(task)

    logger.info(f"All {len(workers)} workers started")
    yield

    logger.info("Shutting down workers...")
    for w in workers:
        w.stop()
    for t in worker_tasks:
        t.cancel()
    for ws in list(data_store._clients):
        try:
            await ws.close()
        except Exception:
            pass
    logger.info("Shutdown complete")


app = FastAPI(title="Stock Dashboard", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "workers": len(workers),
        "clients": len(data_store._clients),
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    data_store.subscribe(ws)

    # Send full state on connect
    try:
        state = await data_store.get_full_state()
        for tile_id, data in state.items():
            await ws.send_json({"type": "tile_update", "tile_id": tile_id, "data": data})
    except Exception as e:
        logger.error(f"Error sending initial state: {e}")

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        data_store.unsubscribe(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="info")
