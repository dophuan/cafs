from typing import Dict, Any
from sqlmodel import Session, select
from app.models.item import Item

class InventoryService:
    def __init__(self, db: Session):
        self.db = db

    async def handle_inventory_action(
        self, 
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        handlers = {
            "Checking stock levels": self.check_stock,
            "Creating a receipt": self.create_receipt,
            "Updating stock quantities": self.update_stock,
            "Adding new items": self.add_item,
            "Updating stock quantities": self.update_item,
            "Searching for products": self.search_product
        }
        
        handler = handlers.get(intent.get("intent"))
        if not handler:
            return {"message": "No inventory action required"}
            
        return await handler(intent.get("parameters", {}))

    async def check_stock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        statement = select(Item)
        
        if params.get("sku"):
            statement = statement.where(Item.sku == params["sku"])
        elif params.get("title"):
            statement = statement.where(Item.title.ilike(f"%{params['title']}%"))
            
        items = self.db.exec(statement).all()
        return {"items": [item.model_dump() for item in items]}

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

    async def search_product(self, params: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Searching products with parameters: {params}")
        return {
            "action": "search_product",
            "status": "success",
            "params": params
        }