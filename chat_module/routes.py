import os
import uuid
from datetime import datetime, timezone, timedelta

from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    abort,
    request,
    current_app,
    send_file,
    Response,
    jsonify
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from extensions import db, socketio
from auth_module.models import User
from notification_module.models import Notification
from chat_module import chat_bp
from chat_module.models import (
    Conversation,
    ConversationMember,
    ChatMessage,
    ChatMessageReceipt
)

IST = timezone(timedelta(hours=5, minutes=30))

# --------------------------------------------------
# ATTACHMENT SETTINGS
# --------------------------------------------------

MAX_ATTACHMENT_SIZE = 15 * 1024 * 1024  # 15 MB

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp",
    "pdf", "doc", "docx", "txt",
    "xls", "xlsx", "ppt", "pptx", "csv", "zip"
}


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def is_member(conversation_id, user_id):
    return ConversationMember.query.filter_by(
        conversation_id=conversation_id,
        user_id=user_id
    ).first() is not None


def get_upload_folder():
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "chat_attachments")
    os.makedirs(folder, exist_ok=True)
    return folder


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def notify_conversation_members(conversation_id, event_name, payload):
    members = ConversationMember.query.filter_by(
        conversation_id=conversation_id
    ).all()

    for member in members:
        socketio.emit(
            event_name,
            payload,
            to=f"user_{member.user_id}"
        )


def broadcast_attachment_message(message):
    conversation_id = message.conversation_id

    reply_data = None
    if message.reply_to:
        reply_data = {
            "id": message.reply_to.id,
            "sender_name": message.reply_to.sender.username if message.reply_to.sender else "User",
            "content": "This message was deleted." if message.reply_to.is_deleted else (message.reply_to.content or message.reply_to.attachment_name or "Attachment")
        }

    message_data = {
        "id": message.id,
        "conversation_id": conversation_id,
        "sender_id": current_user.id,
        "sender_name": current_user.username,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "status": message.get_status_for_sender(),
        "delivery_status": message.get_status_for_sender(),
        "is_edited": False,
        "is_deleted": False,
        "has_attachment": True,
        "attachment_name": message.attachment_name,
        "attachment_mimetype": message.attachment_mimetype,
        "attachment_size": message.attachment_size,
        "reply_to": reply_data,
        "attachment_url": url_for(
            "chat.download_attachment",
            message_id=message.id
        )
    }

    # Send the attachment message to everyone in the chat conversation room.
    socketio.emit(
        "new_message",
        message_data,
        to=f"conversation_{conversation_id}"
    )

    # Deliver to each member's private room
    members = ConversationMember.query.filter_by(conversation_id=conversation_id).all()
    for member in members:
        socketio.emit(
            "new_message",
            message_data,
            to=f"user_{member.user_id}"
        )

        if member.user_id != current_user.id:
            socketio.emit(
                "new_notification",
                {
                    "message": f"{current_user.username} sent an attachment: {message.attachment_name}",
                    "conversation_id": conversation_id,
                    "type": "chat",
                    "link": f"/chat/conversation/{conversation_id}"
                },
                to=f"user_{member.user_id}"
            )

            try:
                from email_module.models import Email
                unread_emails = Email.query.filter_by(recipient_id=member.user_id, folder="inbox", is_read=False).count()
                unread_notifs = Notification.query.filter_by(recipient_id=member.user_id, is_read=False).count()
                socketio.emit(
                    "update_unread_counts",
                    {
                        "unread_emails": unread_emails,
                        "unread_notifications": unread_notifs
                    },
                    to=f"user_{member.user_id}"
                )
            except Exception:
                pass

    # Update conversation ordering for all members.
    notify_conversation_members(
        conversation_id,
        "conversation_list_update",
        {
            "conversation_id": conversation_id,
            "last_message_at": message.created_at.isoformat(),
            "last_message": f"📎 {message.attachment_name}",
            "sender_id": current_user.id,
            "sender_name": current_user.username
        }
    )


# --------------------------------------------------
# CHAT INDEX
# --------------------------------------------------

@chat_bp.route("/")
@login_required
def index():
    users = User.query.filter(
        User.id != current_user.id,
        User.is_active.is_(True)
    ).order_by(User.username).all()

    memberships = ConversationMember.query.filter_by(
        user_id=current_user.id
    ).all()

    all_convs = [
        item.conversation for item in memberships if item.conversation is not None
    ]

    # Show recently active conversations first.
    all_convs.sort(
        key=lambda c: (
            c.last_message_at
            or c.created_at
        ),
        reverse=True
    )

    # Deduplicate 1-on-1 conversations for the same partner
    conversations = []
    seen_partners = set()
    for conv in all_convs:
        if conv.is_group:
            conversations.append(conv)
        else:
            partner_id = next((m.user_id for m in conv.members if m.user_id != current_user.id), None)
            if partner_id is not None:
                if partner_id in seen_partners:
                    continue
                seen_partners.add(partner_id)
            conversations.append(conv)

    return render_template(
        "chat/index.html",
        users=users,
        conversations=conversations
    )


# --------------------------------------------------
# PRIVATE CHAT
# --------------------------------------------------

@chat_bp.route("/user/<int:user_id>")
@login_required
def private_chat(user_id):
    other_user = User.query.filter(
        User.id == user_id,
        User.is_active.is_(True)
    ).first_or_404()

    if other_user.id == current_user.id:
        abort(400)

    conversation = None

    my_memberships = ConversationMember.query.filter_by(
        user_id=current_user.id
    ).all()

    candidates = []
    for membership in my_memberships:
        candidate = membership.conversation
        if candidate and not candidate.is_group:
            member_ids = {
                member.user_id for member in candidate.members
            }
            if member_ids == {current_user.id, other_user.id}:
                candidates.append(candidate)

    if candidates:
        candidates.sort(key=lambda c: (len(c.messages), c.last_message_at or c.created_at), reverse=True)
        conversation = candidates[0]

    # Create a new private conversation if one does not exist.
    if conversation is None:
        conversation = Conversation(is_group=False)
        db.session.add(conversation)
        db.session.flush()

        db.session.add_all([
            ConversationMember(
                conversation_id=conversation.id,
                user_id=current_user.id
            ),
            ConversationMember(
                conversation_id=conversation.id,
                user_id=other_user.id
            )
        ])
        db.session.commit()

    messages = ChatMessage.query.filter_by(
        conversation_id=conversation.id
    ).order_by(ChatMessage.created_at.asc()).all()

    return render_template(
        "chat/conversation.html",
        conversation=conversation,
        other_user=other_user,
        chat_title=other_user.username,
        messages=messages,
        all_users=[]
    )


# --------------------------------------------------
# CREATE GROUP
# --------------------------------------------------

@chat_bp.route("/create-group", methods=["POST"])
@login_required
def create_group():
    group_name = request.form.get("group_name", "").strip()
    selected_ids = request.form.getlist("members")

    if not group_name:
        flash("Please enter a group name.", "warning")
        return redirect(url_for("chat.index"))

    if len(group_name) > 100:
        flash("Group name must be under 100 characters.", "warning")
        return redirect(url_for("chat.index"))

    try:
        member_ids = {int(value) for value in selected_ids}
    except (TypeError, ValueError):
        flash("Invalid group member selection.", "danger")
        return redirect(url_for("chat.index"))

    member_ids.add(current_user.id)

    users = User.query.filter(
        User.id.in_(member_ids),
        User.is_active.is_(True)
    ).all()

    if len(users) != len(member_ids) or len(member_ids) < 2:
        flash("Select at least one other active user.", "warning")
        return redirect(url_for("chat.index"))

    conversation = Conversation(
        is_group=True,
        name=group_name
    )

    db.session.add(conversation)
    db.session.flush()

    for user in users:
        db.session.add(
            ConversationMember(
                conversation_id=conversation.id,
                user_id=user.id
            )
        )

    db.session.commit()
    flash("Group created successfully.", "success")

    return redirect(
        url_for("chat.group_chat", conversation_id=conversation.id)
    )


# --------------------------------------------------
# GROUP CHAT
# --------------------------------------------------

@chat_bp.route("/group/<int:conversation_id>")
@login_required
def group_chat(conversation_id):
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        is_group=True
    ).first_or_404()

    if not is_member(conversation.id, current_user.id):
        abort(403)

    messages = ChatMessage.query.filter_by(
        conversation_id=conversation.id
    ).order_by(ChatMessage.created_at.asc()).all()

    # Get existing member IDs
    existing_member_ids = {m.user_id for m in conversation.members}
    available_users = User.query.filter(
        User.is_active == True,
        ~User.id.in_(existing_member_ids)
    ).order_by(User.username).all()

    return render_template(
        "chat/conversation.html",
        conversation=conversation,
        other_user=None,
        chat_title=conversation.name or "Group Chat",
        messages=messages,
        available_users=available_users
    )


# --------------------------------------------------
# ADD MEMBER TO GROUP
# --------------------------------------------------

@chat_bp.route("/group/<int:conversation_id>/add-member", methods=["POST"])
@login_required
def add_group_member(conversation_id):
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        is_group=True
    ).first_or_404()

    if not is_member(conversation.id, current_user.id):
        abort(403)

    user_id = request.form.get("user_id", type=int)
    if not user_id:
        flash("Please select a user to add.", "warning")
        return redirect(url_for("chat.group_chat", conversation_id=conversation.id))

    user_to_add = User.query.filter_by(id=user_id, is_active=True).first()
    if not user_to_add:
        flash("User not found or inactive.", "danger")
        return redirect(url_for("chat.group_chat", conversation_id=conversation.id))

    if is_member(conversation.id, user_to_add.id):
        flash("User is already a member of this group.", "info")
        return redirect(url_for("chat.group_chat", conversation_id=conversation.id))

    new_member = ConversationMember(
        conversation_id=conversation.id,
        user_id=user_to_add.id
    )
    db.session.add(new_member)

    # Add system notification message
    sys_msg = ChatMessage(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        content=f"{current_user.username} added {user_to_add.username} to the group."
    )
    db.session.add(sys_msg)
    db.session.commit()

    socketio.emit(
        "new_message",
        {
            "id": sys_msg.id,
            "conversation_id": conversation.id,
            "sender_id": current_user.id,
            "sender_name": "System",
            "content": sys_msg.content,
            "created_at": sys_msg.created_at.isoformat(),
            "status": "sent",
            "is_edited": False,
            "is_deleted": False,
            "has_attachment": False,
            "reply_to": None
        },
        to=f"conversation_{conversation.id}"
    )

    flash(f"{user_to_add.username} has been added to the group.", "success")
    return redirect(url_for("chat.group_chat", conversation_id=conversation.id))


# --------------------------------------------------
# REMOVE MEMBER FROM GROUP / LEAVE GROUP
# --------------------------------------------------

@chat_bp.route("/group/<int:conversation_id>/remove-member", methods=["POST"])
@login_required
def remove_group_member(conversation_id):
    conversation = Conversation.query.filter_by(
        id=conversation_id,
        is_group=True
    ).first_or_404()

    if not is_member(conversation.id, current_user.id):
        abort(403)

    user_id = request.form.get("user_id", type=int)
    if not user_id:
        abort(400)

    member_to_remove = ConversationMember.query.filter_by(
        conversation_id=conversation.id,
        user_id=user_id
    ).first()

    if not member_to_remove:
        flash("Member not found in this group.", "warning")
        return redirect(url_for("chat.group_chat", conversation_id=conversation.id))

    removed_username = member_to_remove.user.username if member_to_remove.user else "User"

    db.session.delete(member_to_remove)

    sys_msg = ChatMessage(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        content=f"{current_user.username} removed {removed_username} from the group." if user_id != current_user.id else f"{removed_username} left the group."
    )
    db.session.add(sys_msg)
    db.session.commit()

    socketio.emit(
        "new_message",
        {
            "id": sys_msg.id,
            "conversation_id": conversation.id,
            "sender_id": current_user.id,
            "sender_name": "System",
            "content": sys_msg.content,
            "created_at": sys_msg.created_at.isoformat(),
            "status": "sent",
            "is_edited": False,
            "is_deleted": False,
            "has_attachment": False,
            "reply_to": None
        },
        to=f"conversation_{conversation.id}"
    )

    if user_id == current_user.id:
        flash("You have left the group.", "info")
        return redirect(url_for("chat.index"))

    flash(f"{removed_username} was removed from the group.", "success")
    return redirect(url_for("chat.group_chat", conversation_id=conversation.id))


# --------------------------------------------------
# UPLOAD ATTACHMENT
# --------------------------------------------------

@chat_bp.route("/conversation/<int:conversation_id>/upload", methods=["POST"])
@login_required
def upload_attachment(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)

    if not is_member(conversation_id, current_user.id):
        abort(403)

    uploaded_file = request.files.get("attachment")
    reply_to_id = request.form.get("reply_to_id", type=int)

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a file.", "warning")
        return redirect(request.referrer or url_for("chat.index"))

    original_name = secure_filename(uploaded_file.filename)
    if not original_name or not allowed_file(original_name):
        flash("This file type is not supported.", "danger")
        return redirect(request.referrer or url_for("chat.index"))

    file_data = uploaded_file.read(MAX_ATTACHMENT_SIZE + 1)
    if not file_data:
        flash("The selected file is empty.", "warning")
        return redirect(request.referrer or url_for("chat.index"))

    if len(file_data) > MAX_ATTACHMENT_SIZE:
        flash("File size must not exceed 15 MB.", "danger")
        return redirect(request.referrer or url_for("chat.index"))

    extension = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{extension}"

    upload_folder = get_upload_folder()
    file_path = os.path.join(upload_folder, stored_name)

    try:
        with open(file_path, "wb") as output_file:
            output_file.write(file_data)

        mimetype = uploaded_file.mimetype or "application/octet-stream"

        message = ChatMessage(
            conversation_id=conversation_id,
            sender_id=current_user.id,
            content="",
            attachment_name=original_name,
            attachment_path=stored_name,
            attachment_mimetype=mimetype,
            attachment_size=len(file_data),
            reply_to_id=reply_to_id
        )

        db.session.add(message)
        db.session.flush()

        members = ConversationMember.query.filter_by(
            conversation_id=conversation_id
        ).all()

        from chat_module.events import active_users
        now = utc_now()
        delivered_count = 0
        for member in members:
            if member.user_id == current_user.id:
                continue

            is_online = member.user_id in active_users
            deliv_time = now if is_online else None
            if is_online:
                delivered_count += 1

            db.session.add(
                ChatMessageReceipt(
                    message_id=message.id,
                    recipient_id=member.user_id,
                    delivered_at=deliv_time
                )
            )

            db.session.add(
                Notification(
                    recipient_id=member.user_id,
                    sender_id=current_user.id,
                    conversation_id=conversation_id,
                    message=f"{current_user.username} shared {original_name} with you."
                )
            )

        if delivered_count > 0:
            message.delivered_at = now
            message.delivery_status = "delivered"
        else:
            message.delivery_status = "sent"

        conversation.last_message_at = message.created_at
        db.session.commit()

        broadcast_attachment_message(message)
        flash("File shared successfully.", "success")

    except Exception:
        db.session.rollback()
        if os.path.exists(file_path):
            os.remove(file_path)

        current_app.logger.exception("Attachment upload failed")
        flash("Unable to upload the file. Please try again.", "danger")

    if conversation.is_group:
        return redirect(url_for("chat.group_chat", conversation_id=conversation_id))

    return redirect(request.referrer or url_for("chat.index"))


# --------------------------------------------------
# DOWNLOAD ATTACHMENT
# --------------------------------------------------

@chat_bp.route("/attachment/<int:message_id>/download")
@login_required
def download_attachment(message_id):
    message = ChatMessage.query.get_or_404(message_id)

    if not is_member(message.conversation_id, current_user.id):
        abort(403)

    if not message.attachment_path:
        abort(404)

    upload_folder = get_upload_folder()
    stored_name = os.path.basename(message.attachment_path)
    file_path = os.path.join(upload_folder, stored_name)

    if not os.path.isfile(file_path):
        abort(404)

    inline = request.args.get("inline") == "1"
    mimetype = message.attachment_mimetype or "application/octet-stream"
    display_inline = inline and mimetype.startswith("image/")

    return send_file(
        file_path,
        as_attachment=not display_inline,
        download_name=message.attachment_name or "attachment",
        mimetype=mimetype
    )


# --------------------------------------------------
# DOWNLOAD CONVERSATION TRANSCRIPT
# --------------------------------------------------

@chat_bp.route("/conversation/<int:conversation_id>/download")
@login_required
def download_transcript(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)

    if not is_member(conversation_id, current_user.id):
        abort(403)

    messages = ChatMessage.query.filter_by(
        conversation_id=conversation_id
    ).order_by(ChatMessage.created_at.asc()).all()

    if conversation.is_group:
        title = conversation.name or "Group Chat"
    else:
        other_member = ConversationMember.query.filter(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != current_user.id
        ).first()

        title = (
            other_member.user.username
            if other_member and other_member.user
            else "Private Chat"
        )

    lines = [
        f"Conversation: {title}",
        f"Downloaded by: {current_user.username}",
        f"Downloaded at: {utc_now().astimezone(IST).strftime('%d-%m-%Y %I:%M %p')} IST",
        "=" * 60,
        ""
    ]

    for message in messages:
        timestamp = message.created_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(IST)

        sender_name = message.sender.username if message.sender else "Unknown User"
        time_text = timestamp.strftime("%d-%m-%Y %I:%M %p IST")

        lines.append(f"[{time_text}] {sender_name}:")

        if message.is_deleted:
            lines.append("This message was deleted.")
        elif message.content:
            lines.append(message.content)

        if message.attachment_name:
            lines.append(f"Attachment: {message.attachment_name}")

        if message.is_edited:
            lines.append("(Edited)")

        lines.append("")

    transcript = "\n".join(lines)
    filename = f"chat_transcript_{conversation_id}.txt"

    return Response(
        transcript,
        mimetype="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# --------------------------------------------------
# VIEW CONVERSATION BY ID (ROUTER / REDIRECTOR)
# --------------------------------------------------

@chat_bp.route("/conversation/<int:conversation_id>")
@login_required
def view_conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)

    if not is_member(conversation_id, current_user.id):
        abort(403)

    if conversation.is_group:
        return redirect(url_for("chat.group_chat", conversation_id=conversation.id))

    other_member = ConversationMember.query.filter(
        ConversationMember.conversation_id == conversation.id,
        ConversationMember.user_id != current_user.id
    ).first()

    if other_member:
        return redirect(url_for("chat.private_chat", user_id=other_member.user_id))

    return redirect(url_for("chat.index"))


# --------------------------------------------------
# CLEAR CONVERSATION CHAT
# --------------------------------------------------

@chat_bp.route("/conversation/<int:conversation_id>/clear", methods=["POST"])
@login_required
def clear_chat(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)

    if not is_member(conversation_id, current_user.id):
        abort(403)

    messages = ChatMessage.query.filter_by(conversation_id=conversation_id).all()
    for msg in messages:
        if msg.attachment_path and os.path.exists(msg.attachment_path):
            try:
                os.remove(msg.attachment_path)
            except OSError:
                pass
        db.session.delete(msg)

    conversation.last_message_at = utc_now()
    db.session.commit()

    from extensions import socketio
    socketio.emit(
        "chat_cleared",
        {"conversation_id": conversation_id, "cleared_by": current_user.username},
        to=f"conversation_{conversation_id}"
    )

    flash("Chat history has been cleared.", "info")
    return redirect(url_for("chat.view_conversation", conversation_id=conversation_id))

