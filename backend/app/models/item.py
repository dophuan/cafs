import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Dict, List

from sqlmodel import Field, Relationship, SQLModel, Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy import String, Numeric

if TYPE_CHECKING:
    from .user import User

class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=50, index=True)
    category: str | None = Field(default=None, max_length=100, index=True)
    price: float | None = Field(default=None, sa_column=Column(Numeric(10, 2)))
    quantity: int | None = Field(default=0)
    dimensions: Dict | None = Field(default=None, sa_column=Column(JSONB))
    color_code: str | None = Field(default=None, max_length=50, index=True)
    specifications: Dict | None = Field(default=None, sa_column=Column(JSONB))
    tags: List[str] | None = Field(default=None, sa_column=Column(ARRAY(String)))
    status: str = Field(default="active", max_length=20)  # active, discontinued, out_of_stock
    unit: str | None = Field(default=None, max_length=20)  # pcs, kg, m, etc.
    barcode: str | None = Field(default=None, max_length=100)
    supplier_id: str | None = Field(default=None, max_length=100)
    reorder_point: int | None = Field(default=None)
    max_stock: int | None = Field(default=None)

class ItemCreate(ItemBase):
    pass

class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    price: float | None = None
    quantity: int | None = None
    dimensions: Dict | None = None
    color_code: str | None = Field(default=None, max_length=50)
    specifications: Dict | None = None
    tags: List[str] | None = None
    status: str | None = Field(default=None, max_length=20)
    unit: str | None = Field(default=None, max_length=20)
    barcode: str | None = Field(default=None, max_length=100)
    supplier_id: str | None = Field(default=None, max_length=100)
    reorder_point: int | None = None
    max_stock: int | None = None

class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: Optional["User"] = Relationship(back_populates="items")
    
    # Audit fields
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=datetime.utcnow)
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int

# Additional models for specific operations

class ItemStock(SQLModel):
    id: uuid.UUID
    title: str
    sku: str | None
    quantity: int
    reorder_point: int | None
    max_stock: int | None
    status: str

class ItemSearch(SQLModel):
    category: str | None = None
    color_code: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    tags: List[str] | None = None
    status: str | None = None
    dimensions: Dict | None = None
    specifications: Dict | None = None

class ItemStockAdjustment(SQLModel):
    id: uuid.UUID
    adjustment_type: str  # increase, decrease
    quantity: int
    reason: str | None = None
    reference_number: str | None = None

class ItemSupplierInfo(SQLModel):
    id: uuid.UUID
    supplier_id: str
    supplier_sku: str | None = None
    supplier_price: float | None = None
    lead_time_days: int | None = None
    minimum_order_quantity: int | None = None
    
class ItemWithInventoryStatus(ItemPublic):
    stock_status: str  # in_stock, low_stock, out_of_stock
    days_until_reorder: int | None = None
    last_restock_date: datetime | None = None
    average_daily_sales: float | None = None