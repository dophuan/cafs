"""add_zalo_conversations_table

Revision ID: 54dd7c143889
Revises: d4215e84a6b8
Create Date: 2025-05-17 14:45:36.628065

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = '54dd7c143889'
down_revision = 'd4215e84a6b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'zalo_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=False),
        sa.Column('group_id', sa.String(), nullable=True),
        sa.Column('sender_id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=True),
        sa.Column('file_url', sa.String(), nullable=True),
        sa.Column('file_name', sa.String(), nullable=True),
        sa.Column('file_type', sa.String(), nullable=True),
        sa.Column('sticker_id', sa.String(), nullable=True),
        sa.Column('sticker_url', sa.String(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('llm_analysis', JSONB(), nullable=True),
        sa.Column('raw_payload', JSONB(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_zalo_conversations_conversation_id'), 'zalo_conversations', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_zalo_conversations_group_id'), 'zalo_conversations', ['group_id'], unique=False)
    op.create_index(op.f('ix_zalo_conversations_sender_id'), 'zalo_conversations', ['sender_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_zalo_conversations_sender_id'), table_name='zalo_conversations')
    op.drop_index(op.f('ix_zalo_conversations_group_id'), table_name='zalo_conversations')
    op.drop_index(op.f('ix_zalo_conversations_conversation_id'), table_name='zalo_conversations')
    op.drop_table('zalo_conversations')
