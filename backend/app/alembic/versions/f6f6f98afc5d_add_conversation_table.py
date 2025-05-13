"""Add conversation table

Revision ID: f6f6f98afc5d
Revises: 1a31ce608336
Create Date: 2025-05-03 20:23:48.537663

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = 'f6f6f98afc5d'
down_revision = '1a31ce608336'
branch_labels = None
depends_on = None


def upgrade():
    # Add extension for UUID support
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    op.create_table(
        'llm_conversations',
        sa.Column('id', UUID(), primary_key=True, server_default=sa.text('uuid_generate_v4()')),  # Changed to uuid_generate_v4()
        sa.Column('user_id', UUID(), nullable=False, comment='Reference to user.id but not enforced by FK'),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('file_urls', JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb"), 
                  comment='Array of file URLs stored in cloud storage'),
        sa.Column('messages', JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('metadata', JSONB(), nullable=True),
    )
    op.create_index('idx_llm_conversations_user_id', 'llm_conversations', ['user_id'])

def downgrade():
    op.drop_table('llm_conversations')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')