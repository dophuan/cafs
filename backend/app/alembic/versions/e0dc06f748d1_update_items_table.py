"""update_items_table

Revision ID: e0dc06f748d1
Revises: 54dd7c143889
Create Date: 2025-05-17 15:41:03.403047

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'e0dc06f748d1'
down_revision = '54dd7c143889'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('item', sa.Column('sku', sa.String(50), nullable=True))
    op.add_column('item', sa.Column('category', sa.String(100), nullable=True))
    op.add_column('item', sa.Column('price', sa.Numeric(10, 2), nullable=True))
    op.add_column('item', sa.Column('quantity', sa.Integer(), nullable=True))
    op.add_column('item', sa.Column('dimensions', postgresql.JSONB(), nullable=True))
    op.add_column('item', sa.Column('color_code', sa.String(50), nullable=True))
    op.add_column('item', sa.Column('specifications', postgresql.JSONB(), nullable=True))
    op.add_column('item', sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('item', sa.Column('status', sa.String(20), nullable=False, server_default='active'))
    op.add_column('item', sa.Column('unit', sa.String(20), nullable=True))
    op.add_column('item', sa.Column('barcode', sa.String(100), nullable=True))
    op.add_column('item', sa.Column('supplier_id', sa.String(100), nullable=True))
    op.add_column('item', sa.Column('reorder_point', sa.Integer(), nullable=True))
    op.add_column('item', sa.Column('max_stock', sa.Integer(), nullable=True))
    op.add_column('item', sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.add_column('item', sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')))
    
    # Create indexes
    op.create_index(op.f('ix_item_sku'), 'item', ['sku'], unique=True)
    op.create_index(op.f('ix_item_category'), 'item', ['category'], unique=False)
    op.create_index(op.f('ix_item_color_code'), 'item', ['color_code'], unique=False)
    op.create_index(op.f('ix_item_status'), 'item', ['status'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_item_status'), table_name='item')
    op.drop_index(op.f('ix_item_color_code'), table_name='item')
    op.drop_index(op.f('ix_item_category'), table_name='item')
    op.drop_index(op.f('ix_item_sku'), table_name='item')
    
    op.drop_column('item', 'updated_at')
    op.drop_column('item', 'created_at')
    op.drop_column('item', 'max_stock')
    op.drop_column('item', 'reorder_point')
    op.drop_column('item', 'supplier_id')
    op.drop_column('item', 'barcode')
    op.drop_column('item', 'unit')
    op.drop_column('item', 'status')
    op.drop_column('item', 'tags')
    op.drop_column('item', 'specifications')
    op.drop_column('item', 'color_code')
    op.drop_column('item', 'dimensions')
    op.drop_column('item', 'quantity')
    op.drop_column('item', 'price')
    op.drop_column('item', 'category')
    op.drop_column('item', 'sku')