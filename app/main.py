from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.status_page import render_status_page
from app.api.v1.api import api_router
from app.core.config import get_settings
from app.core.deps import get_db
from app.core.exceptions import DomainError
from app.integrations.fcm import fcm_push_sender, init_firebase
from app.repositories import user_repo
from app.services import notification_service
from app.tasks.scheduler import start_scheduler
from app.ws.manager import connection_manager
from app.ws.router import router as ws_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    notification_service.register_connection_broadcaster(connection_manager)
    init_firebase()
    notification_service.register_push_sender(fcm_push_sender)
    scheduler = start_scheduler()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Device Info X Server",
    version="0.0.1",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/api/v1/openapi.json" if settings.enable_docs else None,
    lifespan=lifespan,
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# FastAPI's own default handler for a Pydantic validation failure (e.g. a registration username
# that's too short, or a password under the minimum length) returns {"detail": [{"loc": ...,
# "msg": ...}, ...]} — a list, not the {"detail": "<string>"} shape every other error on this API
# uses (see domain_error_handler above and ApiErrorBodyDto on the Android client, which only
# decodes a string). Left unhandled, that shape mismatch fails to parse client-side and the real
# validation reason ("password must be at least 8 characters") never reaches the user — flattened
# here into the same string shape so it does.
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'] if part != 'body')}: {error['msg']}" for error in exc.errors()
    )
    return JSONResponse(status_code=422, content={"detail": detail})


app.include_router(api_router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def status_page(db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    registered_count: int | None = None
    paired: bool | None = None
    try:
        await db.execute(text("SELECT 1"))
        database_reachable = True
        registered_count = await user_repo.count_users(db)
        paired = await user_repo.any_paired(db)
    except Exception:
        database_reachable = False
    return HTMLResponse(
        render_status_page(database_reachable=database_reachable, registered_count=registered_count, paired=paired)
    )
