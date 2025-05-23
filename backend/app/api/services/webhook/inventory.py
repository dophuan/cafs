from decimal import Decimal
import logging
from typing import Any
from sqlalchemy import text
from sqlmodel import Session
from app.api.constants.actions import (
    ADD_NEW_ITEMS, CHECK_STOCK_LEVELS, CREATE_RECEIPT,
    NORMAL_CONVERSATION, SEARCH_PRODUCTS, UPDATE_ITEM,
    UPDATE_STOCK_QUANTITIES,
)
from app.api.services.vector_search.vector_search import VectorSearchService
from app.models.search_params import SearchParams, SearchResult

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.vector_service = VectorSearchService(db)

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

    def _build_stock_query_text(self, params: dict[str, Any]) -> str:
        """Build search query text based on parameters"""
        if params.get("skus"):
            return f"SKU: {' '.join(self._normalize_identifier(params['skus']))}"
        elif params.get("sku"):
            return f"SKU: {self._normalize_identifier(params['sku'])}"
        elif params.get("barcodes"):
            return f"Barcode: {' '.join(self._normalize_identifier(params['barcodes']))}"
        elif params.get("barcode"):
            return f"Barcode: {self._normalize_identifier(params['barcode'])}"
        elif params.get("product_name"):
            return params["product_name"]
        return ""

    def _format_search_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format items for search response"""
        formatted_items = []
        for item in items:
            formatted_items.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "category": item.get("category", ""),
                "color_code": item.get("color_code", ""),
                "price": f"{int(float(item.get('price', 0))):,} VND",
                "specifications": item.get("specifications", {}),
                "status": item.get("status", ""),
                "similarity": item.get("similarity", 0),
            })
        return formatted_items

    async def sync_products_embeddings(self, products: list[dict[str, Any]] = None) -> dict[str, Any]:
        """Update embeddings for all products"""
        try:
            if products is None:
                stmt = text("""
                    SELECT 
                        id, owner_id, title, description, sku, category, 
                        price, quantity, dimensions, color_code, specifications, 
                        tags, status, unit, barcode, supplier_id, reorder_point, 
                        max_stock, created_at, updated_at
                    FROM item
                """)
                result = self.db.execute(stmt)
                products = [dict(zip([
                    'id', 'owner_id', 'title', 'description', 'sku', 'category',
                    'price', 'quantity', 'dimensions', 'color_code', 'specifications',
                    'tags', 'status', 'unit', 'barcode', 'supplier_id', 'reorder_point',
                    'max_stock', 'created_at', 'updated_at'
                ], row)) for row in result]

            logger.info(f"Found {len(products)} items in database")
            
            success_count = 0
            failed_count = 0

            for product in products:
                try:
                    content_parts = [
                        str(product.get('title', '')),
                        str(product.get('description', '')),
                        str(product.get('category', '')),
                    ]
                    
                    tags = product.get('tags', [])
                    if isinstance(tags, list):
                        content_parts.append(' '.join(str(tag) for tag in tags))
                    
                    content = ' '.join(filter(None, content_parts))
                    
                    embedding = await self.vector_service.get_embedding(content)
                    vector_string = ','.join(str(x) for x in embedding)

                    stmt = text(f"""
                        UPDATE public.item 
                        SET embedding = '[{vector_string}]'::vector
                        WHERE id = '{product['id']}'::uuid
                    """)
                    
                    self.db.execute(stmt)
                    self.db.commit()
                    success_count += 1
                    logger.info(f"Successfully updated embedding for product {product['id']}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to update embedding for product {product['id']}: {str(e)}")
                    self.db.rollback()
                    continue

            return {
                "status": "success",
                "message": f"Updated embeddings for {success_count} products, {failed_count} failed",
                "success_count": success_count,
                "failed_count": failed_count
            }
                    
        except Exception as e:
            logger.error(f"Error in sync_products_embeddings: {str(e)}")
            self.db.rollback()
            raise

    async def check_stock(self, params: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Checking stock with params: {params}")
        try:
            query_text = self._build_stock_query_text(params)
            search_params = SearchParams(
                query=query_text,
                page=1,
                size=100
            )

            search_result = await self.vector_service.search_products(search_params)

            if not search_result.results:
                return {
                    "action": "check_stock",
                    "status": "success",
                    "message": "Không tìm thấy sản phẩm nào",
                    "items": [],
                }

            formatted_items = self._format_stock_items(search_result.results)
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

    async def search_products(self, search_params: SearchParams) -> SearchResult:
        """Search products using vector similarity"""
        try:
            # Generate embedding for search query
            query_embedding = await self.get_embedding(search_params.query)

            # Build the search query
            stmt = text("""
            SELECT 
                i.id,
                i.title,
                i.description,
                i.price,
                i.category,
                i.status,
                1 - (i.embedding <=> CAST(:query_embedding AS vector(1536))) as similarity
            FROM public.item i
            WHERE 1 - (i.embedding <=> CAST(:query_embedding AS vector(1536))) > :similarity_threshold
            ORDER BY similarity DESC
            LIMIT :max_results
            """)
            
            params = {
                "query_embedding": f"[{','.join(str(x) for x in query_embedding)}]",
                "similarity_threshold": 0.7,
                "max_results": search_params.size
            }

            # Execute search
            results = self.db.execute(stmt, params).fetchall()
            
            total = len(results)
            
            return SearchResult(
                total=total,
                page=search_params.page,
                size=search_params.size,
                results=[dict(row) for row in results]
            )

        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return SearchResult(
                total=0,
                page=search_params.page,
                size=search_params.size,
                results=[]
            )

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
        logger.info(f"Normal conversation with parameters: {params}")
        return {"action": "normal_conversation", "status": "success", "params": params}
    
    def _format_price(self, price: Any) -> str:
        """Format price to VND string"""
        try:
            if isinstance(price, Decimal):
                price = int(float(price))
            elif isinstance(price, float):
                price = int(price)
            elif isinstance(price, str):
                price = int(float(price))
            return f"{price:,} VND"
        except (ValueError, TypeError):
            return "0 VND"

    def _format_stock_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format items for stock check response"""
        formatted_items = []
        for item in items:
            quantity = int(item.get("quantity", 0))
            reorder_point = int(item.get("reorder_point", 0)) if item.get("reorder_point") else 0

            stock_status = "Còn hàng"
            if quantity == 0:
                stock_status = "Hết hàng"
            elif quantity <= reorder_point:
                stock_status = "Sắp hết hàng"

            formatted_items.append({
                "title": item.get("title", ""),
                "quantity": quantity,
                "status": stock_status,
                "reorder_point": reorder_point,
                "price": self._format_price(item.get('price')),
                "sku": item.get("sku", ""),
            })
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

    def _build_search_message(self, items: list[dict[str, Any]]) -> str:
        """Build search response message"""
        message = "Kết quả tìm kiếm:\n\n"
        for item in items:
            message += f"- {item['title']}\n"
            message += f"  Mô tả: {item['description']}\n"
            message += f"  Danh mục: {item['category']}\n"
            message += f"  Màu sắc: {item['color_code']}\n"
            message += f"  Giá: {item['price']}\n"
            message += f"  Trạng thái: {item['status']}\n\n"
        return message