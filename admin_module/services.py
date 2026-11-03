import os
from extensions import db
from auth_module.models import User
from email_module.models import Email, EmailAttachment
from chat_module.models import Conversation, ChatMessage
from notification_module.models import Notification


def get_dir_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total += os.path.getsize(fp)
    return total


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def get_system_stats(upload_folder):
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    inactive_users = total_users - active_users
    admin_users = User.query.filter_by(role="admin").count()

    total_emails = Email.query.count()
    inbox_emails = Email.query.filter_by(folder="inbox").count()
    sent_emails = Email.query.filter_by(folder="sent").count()
    draft_emails = Email.query.filter_by(folder="drafts").count()
    trash_emails = Email.query.filter_by(folder="trash").count()
    total_email_attachments = EmailAttachment.query.count()

    total_conversations = Conversation.query.count()
    group_conversations = Conversation.query.filter_by(is_group=True).count()
    direct_conversations = total_conversations - group_conversations
    total_messages = ChatMessage.query.count()
    total_notifications = Notification.query.count()

    # Storage calculation
    email_att_size = get_dir_size(os.path.join(upload_folder, "email_attachments"))
    chat_att_size = get_dir_size(os.path.join(upload_folder, "chat_attachments"))
    profile_size = get_dir_size(os.path.join(upload_folder, "profiles"))
    total_storage = email_att_size + chat_att_size + profile_size

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "inactive": inactive_users,
            "admins": admin_users
        },
        "emails": {
            "total": total_emails,
            "inbox": inbox_emails,
            "sent": sent_emails,
            "drafts": draft_emails,
            "trash": trash_emails,
            "attachments": total_email_attachments
        },
        "chats": {
            "total": total_conversations,
            "groups": group_conversations,
            "direct": direct_conversations,
            "messages": total_messages
        },
        "notifications": total_notifications,
        "storage": {
            "total_bytes": total_storage,
            "total_formatted": format_bytes(total_storage),
            "email_attachments": format_bytes(email_att_size),
            "chat_attachments": format_bytes(chat_att_size),
            "profiles": format_bytes(profile_size)
        }
    }

