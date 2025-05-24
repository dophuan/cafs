from fastapi import APIRouter, Depends, HTTPException
from app.api.services.webhook.inventory import InventoryService
from app.api.constants.actions import SEARCH_PRODUCTS
from sqlmodel import Session
from typing import Optional
from pydantic import BaseModel

from app.api.deps import get_db

router = APIRouter(prefix="/inventory", tags=["inventory"])

class SearchQuery(BaseModel):
    query: str

class StockQuery(BaseModel):
    sku: Optional[str] = None
    barcode: Optional[str] = None
    product_name: Optional[str] = None

@router.post("/check-stock")
async def check_stock(
    query: StockQuery,
    db: Session = Depends(get_db)
) -> dict:
    """
    Check stock levels for products by SKU, barcode, or product name
    """
    try:
        inventory_service = InventoryService(db)
        result = await inventory_service.handle_inventory_action({
            "intent": "check_stock",
            "parameters": query.model_dump(exclude_none=True)
        })
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
            
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search")
async def search_products(
    query: SearchQuery,
    db: Session = Depends(get_db)
) -> dict:
    """
    Search products using natural language query
    """
    try:
        inventory_service = InventoryService(db)
        result = await inventory_service.handle_inventory_action({
            "intent": SEARCH_PRODUCTS,
            "parameters": {"query": query.query}
        })
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
            
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Optional: Add a GET endpoint for simpler stock checks
@router.get("/stock/{sku}")
async def get_stock_by_sku(
    sku: str,
    db: Session = Depends(get_db)
) -> dict:
    """
    Check stock levels for a product by SKU
    """
    try:
        inventory_service = InventoryService(db)
        result = await inventory_service.handle_inventory_action({
            "intent": "check_stock",
            "parameters": {"sku": sku}
        })
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
            
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))