import logging

from fastapi import APIRouter, Depends
from pydantic.networks import EmailStr
from pytest import Session
from sqlmodel import select

from app.api.deps import get_current_active_superuser, get_db
from app.api.services.elasticsearch.elasticsearch import ElasticSearchService
from app.models.item import Item as DatabaseItem
from app.models.message import Message
from app.utils import generate_test_email, send_email

router = APIRouter(prefix="/utils", tags=["utils"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.post(
    "/test-email/",
    dependencies=[Depends(get_current_active_superuser)],
    status_code=201,
)
def test_email(email_to: EmailStr) -> Message:
    """
    Test emails.
    """
    email_data = generate_test_email(email_to=email_to)
    send_email(
        email_to=email_to,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    return Message(message="Test email sent")


@router.get("/health-check/")
async def health_check() -> bool:
    return True

@router.post("/reindex")
async def reindex_products(db: Session = Depends(get_db)):
    engine = db.get_bind()
    # Get the URL components directly
    url_dict = {
        'drivername': engine.url.drivername,
        'username': engine.url.username,
        'password': engine.url.password,
        'host': engine.url.host,
        'port': engine.url.port,
        'database': engine.url.database
    }
    logger.info(f"Full database URL: {url_dict}")

    statement = select(DatabaseItem)
    items = db.exec(statement).all()

    if not items:
        return {"status": "error", "message": "No items found in database"}

    es_service = ElasticSearchService()
    await es_service.setup_index()
    result = await es_service.index_products([item.dict() for item in items])

    return {
        "status": "success",
        "indexed": len(items),
        "result": result
    }
