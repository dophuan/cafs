import logging

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.deps import get_db
from app.api.main import api_router
from app.api.services.webhook.inventory import InventoryService
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate a unique ID for the route that includes its tag if available."""
    tag = route.tags[0] if route.tags else "untagged"
    return f"{tag}-{route.name}"


# Initialize Sentry
if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)
    logger.info("Sentry initialized successfully")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)


# Middleware to log requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(
        f"Request completed: {request.method} {request.url.path} - Status: {response.status_code}"
    )
    return response


@app.get("/zalo_verifierE8_WTUc2QoyViSuAciPh2tEnv1MVnp98DZ8t.html")
async def serve_zalo_verifier():
    logger.info("Serving Zalo verifier file")
    try:
        return FileResponse(
            "/app/static/zalo_verifierE8_WTUc2QoyViSuAciPh2tEnv1MVnp98DZ8t.html"
        )
    except Exception as e:
        logger.error(f"Error serving Zalo verifier: {str(e)}", exc_info=True)
        raise


# Set all CORS enabled origins
if settings.all_cors_origins:
    logger.info(f"Configuring CORS with origins: {settings.all_cors_origins}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return {"detail": str(exc)}


# Startup event handler
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.PROJECT_NAME} API")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"API Version: {settings.API_V1_STR}")

    # Initialize Elasticsearch sync
    try:
        db = next(get_db())
        inventory_service = InventoryService(db)
        await inventory_service.sync_products_to_elasticsearch()
        logger.info("Successfully synchronized products to Elasticsearch")
    except Exception as e:
        logger.error(f"Failed to sync products to Elasticsearch: {str(e)}")


# Shutdown event handler
@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {settings.PROJECT_NAME} API")


app.include_router(api_router, prefix=settings.API_V1_STR)

logger.info("FastAPI application configured successfully")
