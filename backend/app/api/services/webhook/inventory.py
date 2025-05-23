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
from app.api.services.elasticsearch.elasticsearch import ElasticSearchService
from app.core.config import settings
from app.models.item import Item
from app.models.search_params import SearchParams

logger = logging.getLogger(__name__)


class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.es_service = ElasticSearchService()

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

    def _build_stock_query(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build Elasticsearch query based on parameters"""
        query_types = {
            "skus": lambda skus: {
                "bool": {
                    "should": [
                        {"match": {"sku": sku}}
                        for sku in self._normalize_identifier(skus)
                    ],
                    "minimum_should_match": 1,
                }
            },
            "sku": lambda sku: {"match": {"sku": self._normalize_identifier(sku)}},
            "barcodes": lambda barcodes: {
                "bool": {
                    "should": [
                        {"match": {"barcode": barcode}}
                        for barcode in self._normalize_identifier(barcodes)
                    ],
                    "minimum_should_match": 1,
                }
            },
            "barcode": lambda barcode: {
                "match": {"barcode": self._normalize_identifier(barcode)}
            },
            "product_name": lambda name: {
                "match": {"title": {"query": name, "analyzer": "vietnamese_analyzer"}}
            },
        }

        # Get the first available query parameter and its value
        query_param = next((k for k in query_types.keys() if params.get(k)), None)

        # Use the matching query builder or default to low stock query
        query_builder = query_types.get(
            query_param, lambda _: {"range": {"quantity": {"lte": "reorder_point"}}}
        )

        return {"query": query_builder(params.get(query_param, [])), "size": 100}

    def _format_stock_items(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format Elasticsearch hits into stock items"""
        formatted_items = []
        for hit in hits:
            source = hit["_source"]
            quantity = int(source.get("quantity", 0))
            reorder_point = int(source.get("reorder_point", 0))

            stock_status = "Còn hàng"
            if quantity == 0:
                stock_status = "Hết hàng"
            elif quantity <= reorder_point:
                stock_status = "Sắp hết hàng"

            formatted_items.append(
                {
                    "title": source.get("title", ""),
                    "quantity": quantity,
                    "status": stock_status,
                    "reorder_point": reorder_point,
                    "price": f"{float(source.get('price', 0)):,.0f} VND",
                    "sku": source.get("sku", ""),
                }
            )
        return formatted_items

    def _build_stock_message(self, items: list[dict[str, Any]]) -> str:
        """Build response message from formatted items"""
        message = "Thông tin tồn kho:\n\n"
        for item in items:
            message += f"- {item['title']}:\n"
            message += f"  Số lượng: {item['quantity']}\n"
            message += f"  Trạng thái: {item['status']}\n"
            message += f"  Giá: {item['price']}\n"
            message += f"  SKU: {item['sku']}\n"
        return message

    async def check_stock(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Checking stock with params: {params}")
        try:
            query = self._build_stock_query(params)
            logger.info(f"Executing query: {query}")

            response = self.es_service.client.search(
                index=self.es_service.index_name, body=query
            )
            logger.info(f"Search response: {response}")

            hits = response.get("hits", {}).get("hits", [])
            logger.info(f"Found {len(hits)} hits")

            if not hits:
                return {
                    "action": "check_stock",
                    "status": "success",
                    "message": "Không tìm thấy sản phẩm nào",
                    "items": [],
                }

            formatted_items = self._format_stock_items(hits)
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
        Search products using Elasticsearch based on intent parameters
        """
        try:
            query = intent_params.get("query", "")
            llm_service = LLMService(
                db=self.db,
                api_key=settings.OPENAI_API_KEY,
                engine=settings.OPENAI_ENGINE,
            )

            # Parse the natural language query using LLM
            parsed_params = await llm_service.parse_product_query(query)

            if parsed_params.get("status") == "error":
                return {
                    "action": "search_product",
                    "status": "error",
                    "message": "Không thể xử lý yêu cầu tìm kiếm",
                    "items": [],
                }

            # Convert parsed parameters to SearchParams using the new factory method
            search_params = SearchParams.from_parsed_params(parsed_params["parameters"])
            print(f"====== Search params: {search_params}")

            # Perform search using Elasticsearch
            search_result = await self.es_service.search_products(search_params)

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
            return {
                "action": "search_product",
                "status": "error",
                "message": f"Lỗi tìm kiếm sản phẩm: {str(e)}",
            }

    async def sync_products_to_elasticsearch(self) -> dict[str, Any]:
        """
        Sync all products from database to Elasticsearch
        """
        try:
            # Add debug logging for query
            statement = select(Item)

            # Get items and log raw results
            items = self.db.exec(statement).all()
            logger.info(f"Found {len(items)} items in database")

            if not items:
                logger.error("No items found in database!")
                # Let's check if the table exists and has the right schema
                try:
                    # Try to get one item to verify table structure
                    test_item = self.db.exec(select(Item).limit(1)).first()
                    logger.info(f"Test query result: {test_item}")
                except Exception as table_error:
                    logger.error(f"Table check error: {str(table_error)}")
                return {"status": "error", "message": "No products found in database"}
            # Convert items to dictionary format
            products = []
            for item in items:
                try:
                    product = {
                        "id": str(item.id),
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
                        "dimensions": item.dimensions or {},
                        "unit": item.unit,
                        "barcode": item.barcode,
                        "supplier_id": item.supplier_id,
                        "owner_id": str(item.owner_id),
                    }
                    products.append(product)
                except Exception as e:
                    logger.error(
                        f"Error converting item {getattr(item, 'id', 'unknown')}: {str(e)}"
                    )
                    continue

            logger.info(f"Converting {len(products)} products for indexing")
            if products:
                logger.info(f"Sample product for indexing: {products[0]}")

            # Setup Elasticsearch index
            await self.es_service.setup_index()

            # Index products
            result = await self.es_service.index_products(products)

            # Verify indexing
            count = self.es_service.client.count(index=self.es_service.index_name)
            logger.info(f"After indexing: {count['count']} documents in index")

            return {
                "status": "success",
                "message": f"Synced {result['indexed']} products to Elasticsearch",
                "failed": result["failed"],
                "total_in_index": count["count"],
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
