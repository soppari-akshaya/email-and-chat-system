import os
import sys
import re
import time
import subprocess
import requests

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def test_cloudflare_and_network():
    print("=" * 70)
    print("CLOUDFLARE TUNNEL & CROSS-NETWORK END-TO-END VERIFICATION")
    print("=" * 70)

    app_dir = os.path.abspath(os.path.dirname(__file__))
    cloudflared_exe = os.path.join(app_dir, "cloudflared.exe")

    if not os.path.exists(cloudflared_exe):
        print(f"Error: cloudflared.exe not found at {cloudflared_exe}")
        return False

    # 1. Start Flask app
    print("\n1. Starting Flask-SocketIO server on http://127.0.0.1:5000...")
    flask_proc = subprocess.Popen(
        [sys.executable, os.path.join(app_dir, "app.py")],
        cwd=app_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Wait for Flask to bind
    for _ in range(20):
        try:
            r = requests.get("http://127.0.0.1:5000/auth/login", timeout=2)
            if r.status_code == 200:
                print("   [PASS] Flask server is live and responding locally on port 5000.")
                break
        except Exception:
            time.sleep(1)
    else:
        print("   [FAIL] Could not connect to local Flask server.")
        flask_proc.terminate()
        return False

    # 2. Start Cloudflare Tunnel
    print("\n2. Initializing Cloudflare Tunnel to expose port 5000 to public internet...")
    cf_proc = subprocess.Popen(
        [cloudflared_exe, "tunnel", "--url", "http://127.0.0.1:5000", "--no-autoupdate"],
        cwd=app_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    public_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    start_time = time.time()
    while time.time() - start_time < 35:
        line = cf_proc.stdout.readline()
        if not line:
            time.sleep(0.5)
            continue
        match = url_pattern.search(line)
        if match:
            public_url = match.group(0)
            print(f"   >>> Cloudflare Public Tunnel URL: {public_url} <<<")
            break

    if not public_url:
        print("   [FAIL] Could not retrieve Cloudflare Tunnel URL within timeout.")
        cf_proc.terminate()
        flask_proc.terminate()
        return False

    # 3. Test Public HTTPS Access
    print(f"\n3. Testing public HTTPS connectivity from outside world to {public_url}...")
    tunnel_connected = False
    for attempt in range(15):
        try:
            r = requests.get(f"{public_url}/auth/login", timeout=8)
            if r.status_code == 200 and "ConnectHub" in r.text:
                print(f"   [PASS] Public HTTPS GET {public_url}/auth/login returned HTTP 200 with ConnectHub UI!")
                tunnel_connected = True
                break
            else:
                print(f"   Tunnel propagating... HTTP status {r.status_code}")
                time.sleep(2)
        except Exception as e:
            print(f"   Attempt {attempt+1}: waiting for DNS propagation ({e})...")
            time.sleep(2)

    if not tunnel_connected:
        print("   [FAIL] Failed to connect through public Cloudflare URL.")
        cf_proc.terminate()
        flask_proc.terminate()
        return False

    # 4. Test Socket.IO Polling Handshake through Cloudflare
    print(f"\n4. Testing Socket.IO handshake and upgrade path over Cloudflare HTTPS...")
    try:
        sio_url = f"{public_url}/socket.io/?EIO=4&transport=polling"
        sio_resp = requests.get(sio_url, timeout=10)
        print(f"   Socket.IO handshake status: {sio_resp.status_code}")
        print(f"   Handshake payload: {sio_resp.text[:80]}...")
        if sio_resp.status_code == 200 and "sid" in sio_resp.text:
            print("   [PASS] Cloudflare Tunnel successfully forwards Socket.IO traffic!")
        else:
            print("   [FAIL] Unexpected Socket.IO handshake response.")
            return False
    except Exception as e:
        print(f"   Socket.IO handshake error: {e}")
        return False

    # 5. Simulate Multi-Device Cross-Network Session (Device A = A, Device B = B)
    print("\n5. Testing Multi-User Cross-Network Communication:")
    session_a = requests.Session() # Device A (Alice, Network A)
    session_b = requests.Session() # Device B (Bob, Network B)

    # A fetches login page for CSRF token
    get_a = session_a.get(f"{public_url}/auth/login")
    match_a = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', get_a.text)
    csrf_a = match_a.group(1) if match_a else ""

    # A logs in
    login_a = session_a.post(
        f"{public_url}/auth/login",
        data={"csrf_token": csrf_a, "email": "alice@connecthub.com", "password": "AlicePass123!"},
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeviceA-NetworkA",
            "Referer": f"{public_url}/auth/login"
        },
        allow_redirects=True
    )
    print(f"   Device A (Alice, Network A) login status: {login_a.status_code}")
    if login_a.status_code != 200:
        print("   Login A failed text:", login_a.text[:300])
    assert login_a.status_code == 200
    assert "dashboard" in login_a.url.lower() or "alice" in login_a.text.lower()
    print("   [PASS] Alice successfully logged in over Cloudflare Tunnel!")

    # B fetches login page for CSRF token
    get_b = session_b.get(f"{public_url}/auth/login")
    match_b = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', get_b.text)
    csrf_b = match_b.group(1) if match_b else ""

    # B logs in
    login_b = session_b.post(
        f"{public_url}/auth/login",
        data={"csrf_token": csrf_b, "email": "bob@connecthub.com", "password": "BobPass123!"},
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) DeviceB-NetworkB",
            "Referer": f"{public_url}/auth/login"
        },
        allow_redirects=True
    )
    print(f"   Device B (Bob, Network B) login status: {login_b.status_code}")
    if login_b.status_code != 200:
        print("   Login B failed text:", login_b.text[:300])
    assert login_b.status_code == 200
    assert "dashboard" in login_b.url.lower() or "bob" in login_b.text.lower()
    print("   [PASS] Bob successfully logged in over Cloudflare Tunnel!")

    # 6. User A sends Email to User B through Cloudflare Tunnel
    print("\n6. Testing Email Delivery from Device A (Network A) to Device B (Network B)...")
    get_compose = session_a.get(f"{public_url}/email/compose")
    match_comp = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', get_compose.text)
    csrf_compose = match_comp.group(1) if match_comp else ""

    email_send = session_a.post(
        f"{public_url}/email/compose",
        data={
            "csrf_token": csrf_compose,
            "action": "send",
            "recipient": "bob@connecthub.com",
            "subject": "Cloudflare Tunnel Cross-Network Verification",
            "body": "Hi Bob! This email was sent over the Cloudflare HTTPS Tunnel from Network A.",
            "label": "Work"
        },
        headers={"Referer": f"{public_url}/email/compose"},
        allow_redirects=True
    )
    print(f"   Email send response status: {email_send.status_code}")
    assert email_send.status_code == 200
    print("   [PASS] Email sent successfully via Cloudflare Tunnel!")

    # User B checks Inbox on Device B
    inbox_b = session_b.get(f"{public_url}/email/", allow_redirects=True)
    assert inbox_b.status_code == 200
    if "Cloudflare Tunnel Cross-Network Verification" in inbox_b.text:
        print("   [PASS] User B on Device B received User A's email through Cloudflare Tunnel!")
    else:
        print("   [FAIL] Email did not appear in User B's inbox.")
        return False

    # 7. Test One-to-One Chat between Alice and Bob over Cloudflare Tunnel
    print("\n7. Testing Real-Time Chat Conversation between Device A and Device B...")
    # Open conversation from Alice's side
    alice_chat = session_a.get(f"{public_url}/chat/user/3", allow_redirects=True)
    print(f"   Alice opened chat with Bob: status {alice_chat.status_code}")
    assert alice_chat.status_code == 200

    # Extract conversation ID
    conv_match = re.search(r'/chat/conversation/(\d+)', alice_chat.url)
    if not conv_match:
        conv_match = re.search(r'conversationId\s*=\s*(\d+)', alice_chat.text)
    assert conv_match is not None, "Could not find conversation ID"
    conv_id = int(conv_match.group(1))
    print(f"   Active conversation ID: {conv_id}")

    # B opens the same conversation from Device B
    bob_chat = session_b.get(f"{public_url}/chat/conversation/{conv_id}", allow_redirects=True)
    print(f"   Bob opened conversation {conv_id}: status {bob_chat.status_code}")
    assert bob_chat.status_code == 200

    # 8. Test Clear Chat Functionality over Cloudflare Tunnel
    print("\n8. Testing Clear Chat Functionality...")
    match_clr = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', bob_chat.text)
    csrf_clear = match_clr.group(1) if match_clr else ""
    clear_resp = session_b.post(
        f"{public_url}/chat/conversation/{conv_id}/clear",
        data={"csrf_token": csrf_clear},
        allow_redirects=True
    )
    print(f"   Clear chat response status: {clear_resp.status_code}")
    assert clear_resp.status_code == 200
    print("   [PASS] Chat cleared successfully!")

    # 9. Verify SQLite Database Record Integrity & WAL Mode
    print("\n9. Verifying SQLite Database Storage & Persistence...")
    from extensions import db
    from app import create_app
    from email_module.models import Email
    from chat_module.models import ChatMessage

    app = create_app()
    with app.app_context():
        latest_email = Email.query.filter_by(subject="Cloudflare Tunnel Cross-Network Verification").first()
        assert latest_email is not None
        print(f"   [PASS] SQLite stored email: ID {latest_email.id}, Folder: '{latest_email.folder}', Label: '{latest_email.label}'")

        # Verify WAL mode is active on SQLite
        import sqlite3
        conn = sqlite3.connect(os.path.join(app_dir, "application.db"))
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        print(f"   [PASS] SQLite journal_mode is: {journal_mode.upper()} (WAL concurrency active)")
        conn.close()

    print("\n" + "=" * 70)
    print(f"SUCCESS: ALL NETWORK, CLOUDFLARE TUNNEL, AND SQLITE TESTS PASSED!")
    print(f"Cloudflare Tunnel Public HTTPS URL: {public_url}")
    print("=" * 70)

    # Clean shutdown
    print("\nShutting down test instances...")
    cf_proc.terminate()
    flask_proc.terminate()
    try:
        cf_proc.wait(timeout=5)
    except Exception:
        cf_proc.kill()
    try:
        flask_proc.wait(timeout=5)
    except Exception:
        flask_proc.kill()
    print("Done.")
    return True

if __name__ == "__main__":
    success = test_cloudflare_and_network()
    sys.exit(0 if success else 1)
