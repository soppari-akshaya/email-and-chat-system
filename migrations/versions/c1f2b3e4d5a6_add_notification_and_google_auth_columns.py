"""Add notification preferences, desktop notifications, google_id and missing schema columns

Revision ID: c1f2b3e4d5a6
Revises: eaac4b6a587a
Create Date: 2026-11-03 19:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = 'c1f2b3e4d5a6'
down_revision = 'eaac4b6a587a'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names())

    # 1. user_profiles columns
    if 'user_profiles' in existing_tables:
        profile_cols = {col['name'] for col in inspector.get_columns('user_profiles')}

        if 'desktop_notifications_enabled' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('desktop_notifications_enabled', sa.Boolean(), server_default=sa.true(), nullable=True)
            )

        if 'email_notifications_enabled' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('email_notifications_enabled', sa.Boolean(), server_default=sa.true(), nullable=True)
            )

        if 'private_chat_notifications_enabled' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('private_chat_notifications_enabled', sa.Boolean(), server_default=sa.true(), nullable=True)
            )

        if 'group_chat_notifications_enabled' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('group_chat_notifications_enabled', sa.Boolean(), server_default=sa.true(), nullable=True)
            )

        if 'sound_enabled' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('sound_enabled', sa.Boolean(), server_default=sa.true(), nullable=True)
            )

        if 'google_id' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('google_id', sa.String(128), nullable=True)
            )

        if 'notification_preferences' not in profile_cols:
            op.add_column(
                'user_profiles',
                sa.Column('notification_preferences', sa.String(255), server_default="email,chat,sound", nullable=True)
            )

        existing_indexes = {idx['name'] for idx in inspector.get_indexes('user_profiles')}
        if 'ix_user_profiles_google_id' not in existing_indexes:
            op.create_index('ix_user_profiles_google_id', 'user_profiles', ['google_id'], unique=False)

    # 2. emails columns
    if 'emails' in existing_tables:
        email_cols = {col['name'] for col in inspector.get_columns('emails')}
        if 'label' not in email_cols:
            op.add_column('emails', sa.Column('label', sa.String(50), nullable=True))

    # 3. chat_messages columns
    if 'chat_messages' in existing_tables:
        msg_cols = {col['name'] for col in inspector.get_columns('chat_messages')}
        if 'reply_to_id' not in msg_cols:
            op.add_column('chat_messages', sa.Column('reply_to_id', sa.Integer(), nullable=True))

    # 4. email_attachments columns
    if 'email_attachments' in existing_tables:
        att_cols = {col['name'] for col in inspector.get_columns('email_attachments')}
        if 'mimetype' not in att_cols:
            op.add_column(
                'email_attachments',
                sa.Column('mimetype', sa.String(150), server_default="application/octet-stream", nullable=True)
            )

    # 5. push_subscriptions table
    if 'push_subscriptions' not in existing_tables:
        op.create_table(
            'push_subscriptions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('endpoint', sa.Text(), nullable=False),
            sa.Column('p256dh', sa.String(255), nullable=False),
            sa.Column('auth', sa.String(255), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
        )
        op.create_index('ix_push_subscriptions_endpoint', 'push_subscriptions', ['endpoint'], unique=True)
        op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'], unique=False)


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names())

    if 'push_subscriptions' in existing_tables:
        op.drop_table('push_subscriptions')

    if 'email_attachments' in existing_tables:
        att_cols = {col['name'] for col in inspector.get_columns('email_attachments')}
        if 'mimetype' in att_cols:
            op.drop_column('email_attachments', 'mimetype')

    if 'chat_messages' in existing_tables:
        msg_cols = {col['name'] for col in inspector.get_columns('chat_messages')}
        if 'reply_to_id' in msg_cols:
            op.drop_column('chat_messages', 'reply_to_id')

    if 'emails' in existing_tables:
        email_cols = {col['name'] for col in inspector.get_columns('emails')}
        if 'label' in email_cols:
            op.drop_column('emails', 'label')

    if 'user_profiles' in existing_tables:
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('user_profiles')}
        if 'ix_user_profiles_google_id' in existing_indexes:
            op.drop_index('ix_user_profiles_google_id', table_name='user_profiles')

        profile_cols = {col['name'] for col in inspector.get_columns('user_profiles')}
        for col_name in [
            'notification_preferences',
            'google_id',
            'sound_enabled',
            'group_chat_notifications_enabled',
            'private_chat_notifications_enabled',
            'email_notifications_enabled',
            'desktop_notifications_enabled'
        ]:
            if col_name in profile_cols:
                op.drop_column('user_profiles', col_name)

