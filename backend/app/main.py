from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, commodities, dashboard, inventory, organization, regions, users, warehouses
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.rbac import sync_rbac


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        sync_rbac(db)
    yield


def create_app(*, run_startup_sync: bool = True) -> FastAPI:
    settings = get_settings()
    if settings.environment == "production" and settings.jwt_secret.startswith("change-me"):
        raise RuntimeError("Set JWT_SECRET before running in production")
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        lifespan=lifespan if run_startup_sync else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    api = APIRouter(prefix="/api")
    for module in (auth, organization, users, regions, commodities, warehouses, inventory, dashboard):
        api.include_router(module.router)
    app.include_router(api)

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
