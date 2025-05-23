from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Float, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Column, DateTime, Field, Relationship, SQLModel
from app.db.custom_types import VECTOR

if TYPE_CHECKING:
    from .user import User


class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=50, index=True)
    category: str | None = Field(default=None, max_length=100, index=True)
    price: float | None = Field(default=None, sa_column=Column(Numeric(10, 2)))
    quantity: int | None = Field(default=0)
    dimensions: dict | None = Field(default=None, sa_column=Column(JSONB))
    color_code: str | None = Field(default=None, max_length=50, index=True)
    specifications: dict | None = Field(default=None, sa_column=Column(JSONB))
    tags: list[str] | None = Field(default=None, sa_column=Column(ARRAY(String)))
    status: str = Field(
        default="active", max_length=20
    )  # active, discontinued, out_of_stock
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
    dimensions: dict | None = None
    color_code: str | None = Field(default=None, max_length=50)
    specifications: dict | None = None
    tags: list[str] | None = None
    status: str | None = Field(default=None, max_length=20)
    unit: str | None = Field(default=None, max_length=20)
    barcode: str | None = Field(default=None, max_length=100)
    supplier_id: str | None = Field(default=None, max_length=100)
    reorder_point: int | None = None
    max_stock: int | None = None


class Item(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(foreign_key="user.id", nullable=False)
    title: str
    description: str | None = None
    sku: str | None = Field(default=None, sa_column=Column(String(50), index=True))
    category: str | None = Field(
        default=None, sa_column=Column(String(100), index=True)
    )
    price: float | None = Field(default=None, sa_column=Column(Float))
    quantity: int | None = Field(default=None, sa_column=Column(Integer))
    dimensions: dict | None = Field(default=None, sa_column=Column(JSONB))
    color_code: str | None = Field(
        default=None, sa_column=Column(String(50), index=True)
    )
    specifications: dict | None = Field(default=None, sa_column=Column(JSONB))
    tags: list[str] | None = Field(default=None, sa_column=Column(ARRAY(String)))
    status: str = Field(default="active", sa_column=Column(String(20), index=True))
    unit: str | None = Field(default=None, sa_column=Column(String(20)))
    barcode: str | None = Field(default=None, sa_column=Column(String(100)))
    supplier_id: str | None = Field(default=None, sa_column=Column(String(100)))
    reorder_point: int | None = Field(default=None, sa_column=Column(Integer))
    max_stock: int | None = Field(default=None, sa_column=Column(Integer))
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=text("now()")
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=text("now()")
        )
    )
    owner: Optional["User"] = Relationship(back_populates="items")
    embedding: Optional[List[float]] = Field(
        default=None,
        sa_column=Column(VECTOR(1536))
    )

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: int(float(v)),
            UUID: lambda v: str(v)
        }


class ItemPublic(ItemBase):
    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Additional models for specific operations


class ItemStock(SQLModel):
    id: UUID
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
    tags: list[str] | None = None
    status: str | None = None
    dimensions: dict | None = None
    specifications: dict | None = None


class ItemStockAdjustment(SQLModel):
    id: UUID
    adjustment_type: str  # increase, decrease
    quantity: int
    reason: str | None = None
    reference_number: str | None = None


class ItemSupplierInfo(SQLModel):
    id: UUID
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
