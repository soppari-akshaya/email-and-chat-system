
from flask import (
    render_template, redirect, url_for, flash,
    abort, request
)
from flask_login import login_required, current_user
from extensions import db
from auth_module.models import User
from chat_module import chat_bp
from chat_module.models import (
    Conversation,
    ConversationMember,
    ChatMessage
)


def is_member(conversation_id, user_id):
    return ConversationMember.query.filter_by(
        conversation_id=conversation_id,
        user_id=user_id
    ).first() is not None


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

    conversations = [
        item.conversation for item in memberships
    ]

    return render_template(
        "chat/index.html",
        users=users,
        conversations=conversations
    )


@chat_bp.route("/user/<int:user_id>")
@login_required
def private_chat(user_id):
    other_user = User.query.filter_by(
        id=user_id,
        is_active=True
    ).first_or_404()

    if other_user.id == current_user.id:
        abort(400)

    conversation = None

    my_memberships = ConversationMember.query.filter_by(
        user_id=current_user.id
    ).all()

    for membership in my_memberships:
        candidate = membership.conversation

        if candidate.is_group:
            continue

        member_ids = {
            member.user_id for member in candidate.members
        }

        if member_ids == {current_user.id, other_user.id}:
            conversation = candidate
            break

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
        messages=messages
    )


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

    return render_template(
        "chat/conversation.html",
        conversation=conversation,
        other_user=None,
        chat_title=conversation.name or "Group Chat",
        messages=messages
    )
