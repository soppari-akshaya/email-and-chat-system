# ConnectHub - Real-Time Email & Chat Platform

ConnectHub is a full-featured communication platform built with Flask, SQLAlchemy, Flask-SocketIO, Bootstrap 5, Firebase Authentication, and native Web Notifications.

---

## Features

- **Email Workspace**:
  - Inbox, Starred, Important, Sent, Drafts, and Trash folders.
  - Case-insensitive recipient lookup by username or email.
  - Multi-file attachments with file-type verification and download capabilities.
  - Live unread badges and instant delivery notifications.

- **Real-Time Chat**:
  - One-to-one private conversations and team group chats.
  - Real-time WebSocket messaging via Flask-SocketIO.
  - Message replies, inline edits, and deletions.
  - Read receipts (Sent, Delivered, Seen / double blue checks).
  - Online/offline presence indicators.
  - Chat transcripts export.

- **Authentication & Security**:
  - Standard email and password authentication with Werkzeug password hashing.
  - **Forgot Password** via Firebase Authentication password reset emails.
  - **Continue with Google** via Firebase Auth popup and verified ID token authentication.
  - Flask-Login session management and Flask-WTF CSRF protection.
  - Rate limiting with Flask-Limiter.

- **Real Windows Desktop Notifications**:
  - Native Windows Action Center desktop toast notifications.
  - Service Worker background push notifications using VAPID keys and `pywebpush`.
  - Notification suppression when active on the conversation tab.
  - Per-user notification preference settings in profile (desktop, email, 1-to-1 chat, group chat, sound).

- **Administrative Dashboard**:
  - User management (activation, role changes, password resets).
  - System-wide email and chat oversight.

---

## Project Structure

```text
email-and-chat-system/
├── admin_module/             # Admin dashboard routes and controllers
├── auth_module/              # Authentication routes, models, forms, and Firebase service
│   ├── firebase_service.py   # Firebase Admin SDK & Google token validation
│   ├── forms.py              # Login, registration, profile forms
│   ├── models.py             # User and UserProfile models
│   └── routes.py             # Auth endpoints (/login, /register, /forgot-password, etc.)
├── chat_module/              # Real-time chat blueprints and WebSocket events
│   ├── events.py             # Socket.IO event handlers
│   ├── models.py             # Conversation, ConversationMember, ChatMessage models
│   └── routes.py             # Chat controllers and attachment endpoints
├── email_module/             # Email workspace blueprints and models
│   ├── models.py             # Email and EmailAttachment models
│   ├── routes.py             # Inbox, sent, drafts, compose routes
│   └── services.py           # Email creation, delivery, and notification dispatch
├── notification_module/      # Web Push and notification models
│   ├── models.py             # Notification and PushSubscription models
│   ├── routes.py             # Push subscription and test endpoints
│   └── webpush_service.py    # VAPID handling and pywebpush dispatcher
├── static/                   # Static assets (CSS, JS, icons, service worker)
│   ├── css/                  # App styling
│   ├── icons/                # Notification and app badge icons
│   ├── js/                   # notifications.js and client scripts
│   └── sw.js                 # Service worker for background push delivery
├── templates/                # Jinja2 HTML templates
│   ├── admin/                # Admin templates
│   ├── auth/                 # Login, register, profile, forgot-password templates
│   ├── chat/                 # Conversation and chat index templates
│   ├── email/                # Inbox, compose, view templates
│   └── base.html             # Master layout with navbar, sidebar, socket listener
├── tests/                    # Automated Pytest suite
├── app.py                    # Application factory, routes, and main entrypoint
├── config.py                 # Application configuration & environment settings
├── extensions.py             # Initialized Flask extension instances
├── Procfile                  # Render / Heroku production WSGI entrypoint
├── render.yaml               # Render infrastructure-as-code specification
└── requirements.txt          # Production Python dependencies
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+
- SQLite (included) or PostgreSQL

### 2. Installation
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in credentials:
```bash
cp .env.example .env
```

### 4. Running the Development Server
```bash
python app.py
```
Visit `http://localhost:5000` in your browser. Default administrator credentials:
- **Email**: `admin@connecthub.com`
- **Password**: `AdminPass123!`

### 5. Running the Tests
```bash
pytest -v -p no:flask
```

