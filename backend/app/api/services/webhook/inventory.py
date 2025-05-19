from typing import Dict, Any
from app.api.services.webhook.search_utils import SearchUtils
from sqlmodel import Session, select
from app.models.item import Item
from app.api.constants.actions import (
    CHECK_STOCK_LEVELS,
    CREATE_RECEIPT,
    UPDATE_STOCK_QUANTITIES,
    ADD_NEW_ITEMS, 
    UPDATE_ITEM,
    SEARCH_PRODUCTS,
    NORMAL_CONVERSATION
)

class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    async def handle_inventory_action(
        self, 
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        handlers = {
            CHECK_STOCK_LEVELS: self.check_stock,
            CREATE_RECEIPT: self.create_receipt,
            UPDATE_STOCK_QUANTITIES: self.update_stock,
            ADD_NEW_ITEMS: self.add_item,
            UPDATE_ITEM: self.update_item,
            SEARCH_PRODUCTS: self.search_product,
            NORMAL_CONVERSATION: self.normal_conversation
        }
        
        handler = handlers.get(intent.get("intent"))
        if not handler:
            return {"message": "No inventory action required"}
            
        return await handler(intent.get("parameters", {}))

    async def check_stock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            statement = select(Item)
            
            if params.get("sku"):
                statement = statement.where(Item.sku == params["sku"])
            elif params.get("product_name"):
                statement = statement.where(Item.title.ilike(f"%{params['product_name']}%"))
            else:
                # Check for low stock products
                statement = statement.where(Item.quantity <= Item.reorder_point)
                
            items = self.db.exec(statement).all()
            
            if not items:
                return {
                    "action": "check_stock",
                    "status": "success",
                    "message": "Không tìm thấy sản phẩm nào",
                    "items": []
                }

            formatted_items = []
            for item in items:
                stock_status = "Còn hàng"
                if item.quantity == 0:
                    stock_status = "Hết hàng"
                elif item.quantity <= item.reorder_point:
                    stock_status = "Sắp hết hàng"

                formatted_items.append({
                    "title": item.title,
                    "quantity": item.quantity,
                    "status": stock_status,
                    "reorder_point": item.reorder_point,
                    "price": f"{item.price:,.0f} VND"
                })

            message = f"Thông tin tồn kho:\n\n"
            for item in formatted_items:
                message += f"- {item['title']}:\n"
                message += f"  Số lượng: {item['quantity']}\n"
                message += f"  Trạng thái: {item['status']}\n"
                message += f"  Giá: {item['price']}\n"

            return {
                "action": "check_stock",
                "status": "success",
                "message": message,
                "items": formatted_items
            }

        except Exception as e:
            return {
                "action": "check_stock",
                "status": "error",
                "message": f"Lỗi kiểm tra tồn kho: {str(e)}"
            }

    async def search_product(self, intent_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search products based on intent parameters
        """
        try:
            print(f"Search intent params {intent_params}")
            conditions = SearchUtils.build_search_conditions(intent_params)
            print(f"Condition: {conditions}")
            statement = SearchUtils.build_search_query(conditions)
            print(f"statement: { statement }")
            items = self.db.exec(statement).all()
            
            if not items:
                return {
                    "action": "search_product",
                    "status": "success",
                    "message": "Không tìm thấy sản phẩm nào phù hợp với yêu cầu của bạn",
                    "items": []
                }
            
            formatted_items = SearchUtils.format_items(items)
            message = SearchUtils.build_response_message(formatted_items)
            
            return {
                "action": "search_product",
                "status": "success",
                "message": message,
                "items": formatted_items
            }
            
        except Exception as e:
            return {
                "action": "search_product",
                "status": "error",
                "message": f"Lỗi tìm kiếm sản phẩm: {str(e)}"
            }

    async def create_receipt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Creating receipt with parameters: {params}")
        return {
            "action": "create_receipt",
            "status": "success",
            "params": params
        }

    async def update_stock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Updating stock with parameters: {params}")
        return {
            "action": "update_stock",
            "status": "success",
            "params": params
        }

    async def add_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Adding new item with parameters: {params}")
        return {
            "action": "add_item",
            "status": "success",
            "params": params
        }

    async def update_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Updating item with parameters: {params}")
        return {
            "action": "update_item",
            "status": "success",
            "params": params
        }
    
    async def normal_conversation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Payload {params}")
        return {
            "action": "normal_conversation",
            "status": "success",
            "params": params
        }