"""Add chat attachments and message controls

Revision ID: eaac4b6a587a
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = 'eaac4b6a587a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Check existing chat_messages columns
    message_columns = {
        column['name']
        for column in inspector.get_columns('chat_messages')
    }

    # Add attachment columns only if missing
    if 'attachment_name' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column('attachment_name', sa.String(255), nullable=True)
        )

    if 'attachment_path' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column('attachment_path', sa.String(500), nullable=True)
        )

    if 'attachment_mimetype' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column('attachment_mimetype', sa.String(150), nullable=True)
        )

    if 'attachment_size' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column('attachment_size', sa.Integer(), nullable=True)
        )

    if 'is_edited' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column(
                'is_edited',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false()
            )
        )

    if 'edited_at' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True)
        )

    if 'is_deleted' not in message_columns:
        op.add_column(
            'chat_messages',
            sa.Column(
                'is_deleted',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false()
            )
        )

    # Check existing conversations columns
    conversation_columns = {
        column['name']
        for column in inspector.get_columns('conversations')
    }

    if 'last_message_at' not in conversation_columns:
        op.add_column(
            'conversations',
            sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True)
        )

    # Create index only if missing
    existing_indexes = {
        index['name']
        for index in sa.inspect(connection).get_indexes('conversations')
    }

    if 'ix_conversations_last_message_at' not in existing_indexes:
        op.create_index(
            'ix_conversations_last_message_at',
            'conversations',
            ['last_message_at'],
            unique=False
        )


def downgrade():
    op.drop_index(
        'ix_conversations_last_message_at',
        table_name='conversations'
    )
    op.drop_column('conversations', 'last_message_at')

    op.drop_column('chat_messages', 'is_deleted')
    op.drop_column('chat_messages', 'edited_at')
    op.drop_column('chat_messages', 'is_edited')
    op.drop_column('chat_messages', 'attachment_size')
    op.drop_column('chat_messages', 'attachment_mimetype')
    op.drop_column('chat_messages', 'attachment_path')
    op.drop_column('chat_messages', 'attachment_name')