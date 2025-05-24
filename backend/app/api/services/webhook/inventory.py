import logging
from typing import Any

from sqlmodel import Session, select

from app.api.constants.actions import (
    ADD_NEW_ITEMS,
    CHECK_STOCK_LEVELS,
    CREATE_RECEIPT,
    NORMAL_CONVERSATION,
    SEARCH_PRODUCTS,
    UPDATE_ITEM,
    UPDATE_STOCK_QUANTITIES,
)
from app.api.services.conversation.chat import LLMService
from app.api.services.supabase.supabase import SupabaseService  # Use SupabaseService
from app.core.config import settings
from app.models.item import Item
from app.models.search_params import SearchParams

logger = logging.getLogger(__name__)


class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.supabase_service = SupabaseService()  # Replace ElasticSearchService with SupabaseService

    async def handle_inventory_action(self, intent: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            CHECK_STOCK_LEVELS: self.check_stock,
            CREATE_RECEIPT: self.create_receipt,
            UPDATE_STOCK_QUANTITIES: self.update_stock,
            ADD_NEW_ITEMS: self.add_item,
            UPDATE_ITEM: self.update_item,
            SEARCH_PRODUCTS: self.search_product,
            NORMAL_CONVERSATION: self.normal_conversation,
        }

        handler = handlers.get(intent.get("intent"))
        if not handler:
            return {"message": "No inventory action required"}

        return await handler(intent.get("parameters", {}))

    def _normalize_identifier(self, identifier: str | list[str]) -> str | list[str]:
        """Normalize SKU or barcode to a consistent format"""
        if isinstance(identifier, list):
            return [str(id).strip().upper() for id in identifier]
        return str(identifier).strip().upper()

    async def check_stock(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Checking stock with params: {params}")
        try:
            query_param = params.get("sku") or params.get("barcode") or params.get("product_name")
            if not query_param:
                return {
                    "action": "check_stock",
                    "status": "error",
                    "message": "No valid query parameter provided for stock check",
                }
            
            # Query Supabase for stock
            response = self.supabase_service.supabase.table(self.supabase_service.table_name).select(
                "id, title, quantity, reorder_point, price, sku"
            ).filter("sku", "eq", self._normalize_identifier(query_param)).execute()
            
            if response.status_code != 200 or not response.data:
                return {
                    "action": "check_stock",
                    "status": "success",
                    "message": "Không tìm thấy sản phẩm nào",
                    "items": [],
                }
            
            items = response.data
            formatted_items = self._format_stock_items(items)
            message = self._build_stock_message(formatted_items)

            return {
                "action": "check_stock",
                "status": "success",
                "message": message,
                "items": formatted_items,
            }

        except Exception as e:
            logger.error(f"Error checking stock: {str(e)}", exc_info=True)
            return {
                "action": "check_stock",
                "status": "error",
                "message": f"Lỗi kiểm tra tồn kho: {str(e)}",
            }

    async def search_product(self, intent_params: dict[str, Any]) -> dict[str, Any]:
        """
        Search products using Supabase based on intent parameters
        """
        try:
            query = intent_params.get("query", "")

            logger.info(f"==== Open AI {settings.OPENAI_API_KEY}")
            logger.info(f"==== Intent query {query}")
            llm_service = LLMService(
                db=self.db,
                api_key=settings.OPENAI_API_KEY,
                engine=settings.OPENAI_ENGINE,
            )

            # Parse the natural language query using LLM
            parsed_params = await llm_service.parse_product_query(query)
            logger.info(f"==== Parsed params { parsed_params }")

            if parsed_params.get("status") == "error":
                return {
                    "action": "search_product",
                    "status": "error",
                    "message": "Không thể xử lý yêu cầu tìm kiếm",
                    "items": [],
                }

            # Convert parsed parameters to SearchParams using the new factory method
            search_params = SearchParams.from_parsed_params(parsed_params["parameters"])

            # Perform vector search using Supabase
            search_result = await self.supabase_service.search_products(search_params)

            logger.info(f"==== Search result {search_result}")

            if not search_result.results:
                return {
                    "action": "search_product",
                    "status": "success",
                    "message": "Không tìm thấy sản phẩm nào phù hợp với yêu cầu của bạn",
                    "items": [],
                }

            # Format the results
            formatted_items = []
            for item in search_result.results:
                formatted_items.append(
                    {
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "category": item.get("category", ""),
                        "color_code": item.get("color_code", ""),
                        "price": f"{float(item.get('price', 0)):,.0f} VND",
                        "specifications": item.get("specifications", {}),
                        "status": item.get("status", ""),
                        "score": item.get("score", 0),
                    }
                )

            # Build response message
            message = "Kết quả tìm kiếm:\n\n"
            for item in formatted_items:
                message += f"- {item['title']}\n"
                message += f"  Mô tả: {item['description']}\n"
                message += f"  Danh mục: {item['category']}\n"
                message += f"  Màu sắc: {item['color_code']}\n"
                message += f"  Giá: {item['price']}\n"
                message += f"  Trạng thái: {item['status']}\n\n"

            return {
                "action": "search_product",
                "status": "success",
                "message": message,
                "items": formatted_items,
                "total": search_result.total,
                "page": search_result.page,
                "size": search_result.size,
            }

        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return {
                "action": "search_product",
                "status": "error",
                "message": f"Lỗi tìm kiếm sản phẩm: {str(e)}",
            }

    async def sync_products_to_supabase(self) -> dict[str, Any]:
        """
        Sync all products from database to Supabase
        """
        try:
            # Ensure the table is created before syncing
            await self.supabase_service.setup_table()
            # Fetch all items from the database
            statement = select(Item)
            items = self.db.exec(statement).all()

            if not items:
                return {"status": "error", "message": "No products found in database"}

            # Convert items to dictionary format
            products = []
            for item in items:
                try:
                    product = {
                        "title": item.title,
                        "description": item.description,
                        "category": item.category,
                        "color_code": item.color_code,
                        "price": float(item.price) if item.price else 0.0,
                        "specifications": item.specifications or {},
                        "tags": item.tags or [],
                        "status": item.status,
                        "sku": item.sku,
                        "quantity": item.quantity or 0,
                        "barcode": item.barcode,
                    }
                    products.append(product)
                except Exception as e:
                    logger.error(
                        f"Error converting item {getattr(item, 'id', 'unknown')}: {str(e)}"
                    )
                    continue

            # Index products into Supabase
            result = await self.supabase_service.index_products(products)

            return {
                "status": "success",
                "message": f"Synced {result['indexed']} products to Supabase",
                "failed": result["failed"],
            }

        except Exception as e:
            logger.error(f"Failed to sync products: {str(e)}", exc_info=True)
            return {"status": "error", "message": f"Failed to sync products: {str(e)}"}

    async def create_receipt(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Creating receipt with parameters: {params}")
        return {"action": "create_receipt", "status": "success", "params": params}

    async def update_stock(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Updating stock with parameters: {params}")
        return {"action": "update_stock", "status": "success", "params": params}

    async def add_item(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Adding new item with parameters: {params}")
        return {"action": "add_item", "status": "success", "params": params}

    async def update_item(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Updating item with parameters: {params}")
        return {"action": "update_item", "status": "success", "params": params}

    async def normal_conversation(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Payload {params}")
        return {"action": "normal_conversation", "status": "success", "params": params}