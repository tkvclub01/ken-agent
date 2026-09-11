import os
import sys
import json
import time
import asyncio
import argparse
import subprocess
import sqlite3
import uuid
import mimetypes
import base64
import threading
import webbrowser
import shutil
import platform
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

try:
    import websockets
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "websockets"])
        import websockets
    except Exception:
        pass

APP_DIR = os.path.expanduser("~/.ken-agent")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
DEFAULT_SERVER_URL = "wss://ken.haiphongdeveloper.com/ws/ken-hub"
AUTH_PATH = os.path.join(APP_DIR, "auth.json")
HUB_URL = "https://ken.haiphongdeveloper.com"
HUB_WS_URL = "wss://ken.haiphongdeveloper.com/ws/ken-hub"
CURRENT_VERSION = "2.5.0"

# --- ZERO-TOKEN 1-CLICK DEVICE AUTHENTICATION ---
def load_device_auth():
    if os.path.exists(AUTH_PATH):
        try:
            with open(AUTH_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("device_id") and data.get("device_token"):
                    return data
        except Exception:
            pass
    return None

def save_device_auth(data):
    try:
        with open(AUTH_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Lỗi lưu auth.json: {e}")

def ensure_device_auth():
    auth_data = load_device_auth()
    if auth_data:
        return auth_data

    import platform
    device_id = "dev_" + uuid.uuid4().hex[:12]
    device_token = "kdtk_" + uuid.uuid4().hex + uuid.uuid4().hex
    device_name = platform.node() or "Máy tính cá nhân"

    req_payload = json.dumps({
        "deviceId": device_id,
        "deviceName": device_name,
        "platform": sys.platform,
        "deviceToken": device_token
    }).encode("utf-8")

    pair_req = urllib.request.Request(
        f"{HUB_URL}/api/device/request-pairing",
        data=req_payload,
        headers={"Content-Type": "application/json", "User-Agent": "ken-agent-cli"}
    )

    try:
        with urllib.request.urlopen(pair_req, timeout=10) as resp:
            pair_res = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ Không thể kết nối tới Cloud Web Hub ({HUB_URL}): {e}")
        sys.exit(1)

    code = pair_res.get("code")
    pair_url = pair_res.get("pair_url", f"{HUB_URL}/#/pair?code={code}")

    print("\n" + "═" * 76)
    print(" 🚀 KEN AGENT - XÁC THỰC THIẾT BỊ 1-CLICK (ZERO-TOKEN)")
    print("═" * 76)
    print(f" 💻 Thiết bị    : \033[1;37m{device_name}\033[0m ({sys.platform.upper()})")
    print(f" 🔑 Mã ghép đôi : [ \033[1;32m{code}\033[0m ]")
    print(f" 🌐 Đang tự động mở trình duyệt web để liên kết với tài khoản của bạn...")
    print(f" 👉 Hoặc mở link: \033[1;36m{pair_url}\033[0m")
    print("═" * 76)
    print(" ⏳ Đang chờ bạn bấm xác nhận trên trình duyệt web...")

    try:
        webbrowser.open(pair_url)
    except Exception:
        pass

    poll_url = f"{HUB_URL}/api/device/check-pair?code={code}&device_token={device_token}"
    poll_req = urllib.request.Request(poll_url, headers={"User-Agent": "ken-agent-cli"})

    while True:
        try:
            time.sleep(2)
            with urllib.request.urlopen(poll_req, timeout=5) as resp:
                poll_res = json.loads(resp.read().decode("utf-8"))
                if poll_res.get("paired"):
                    auth_data = {
                        "device_id": device_id,
                        "device_token": device_token,
                        "device_name": device_name,
                        "user_id": poll_res.get("user_id"),
                        "user_email": poll_res.get("user_email"),
                        "user_name": poll_res.get("user_name")
                    }
                    save_device_auth(auth_data)
                    print(f"\n🎉 [GHÉP ĐÔI THÀNH CÔNG] Đã liên kết với tài khoản: \033[1;32m{auth_data['user_email']}\033[0m!\n")
                    return auth_data
        except KeyboardInterrupt:
            print("\n👋 Đã hủy ghép đôi thiết bị.")
            sys.exit(0)
        except Exception:
            pass

# --- LOCAL DATABASE & MEDIA STORAGE ---
DB_PATH = os.path.join(APP_DIR, "chat_history.sqlite3")
MEDIA_DIR = os.path.join(APP_DIR, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
LOCAL_WEB_PORT = 18765
_local_web_server_started = False

def get_local_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_local_db():
    conn = get_local_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            media_json TEXT,
            created_at TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    conn.close()

def ensure_web_ui_html():
    """Bảo đảm file web_ui.html có mặt tại ~/.ken-agent/web_ui.html để phục vụ Web Chat cục bộ"""
    html_path = os.path.join(APP_DIR, "web_ui.html")
    if not os.path.exists(html_path):
        # 1. Thử lấy từ thư mục cùng cấp với file cli.py
        current_dir_html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_ui.html")
        if os.path.exists(current_dir_html):
            try:
                import shutil
                shutil.copy2(current_dir_html, html_path)
                return html_path
            except Exception:
                pass
        # 2. Tải trực tiếp từ Hub Server
        try:
            req = urllib.request.Request("https://api.haiphongdeveloper.com/web_ui.html", headers={"User-Agent": "ken-agent-cli"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                with open(html_path, "wb") as f:
                    f.write(resp.read())
        except Exception:
            pass
    return html_path

# --- AUTONOMOUS AI AGENT CORE (HERMES PARITY) ---
LOCAL_AGENT_SYSTEM_PROMPT = f"""You are KEN AGENT (Senior Lead AI Engineer, Hermes Parity).
You run locally on the user's computer ({platform.system()} {platform.release()}).
You communicate clearly, knowledgeably, and directly in Vietnamese with Markdown formatting.
You possess full autonomous capabilities to control and inspect this local computer via your tools.

AUTONOMOUS EXECUTION RULES:
1. ALWAYS use the provided tools to FINISH THE JOB autonomously. NEVER tell the user to run commands manually.
2. For system status (disk space, RAM, CPU, OS, processes, hardware, network, files): ALWAYS call 'execute_shell' or 'system_info' to retrieve REAL system stats.
   - For disk space: call 'execute_shell' with 'df -h' on Linux/macOS or 'wmic logicaldisk get caption,freespace,size' on Windows, or call 'system_info'.
   - For RAM: call 'execute_shell' with 'free -m' on Linux or 'vm_stat' on macOS, or call 'system_info'.
3. For file operations: use 'read_file', 'write_file', or 'execute_shell'.
4. For pure questions or conversation without OS action (e.g. 'Python là gì?', 'Chào bạn'): answer directly WITHOUT calling tools.
5. Synthesize tool results into concise, polite, senior-level responses in Vietnamese with Markdown formatting.
"""

LOCAL_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Thực thi câu lệnh terminal shell / powershell trên máy tính cục bộ của người dùng",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Câu lệnh shell (ví dụ: df -h, free -m, ps aux, cat ...)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Lấy thông tin tổng quan hệ thống máy tính (HĐH, CPU, RAM, Ổ cứng, Uptime)",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Đọc nội dung một file văn bản từ máy tính cục bộ",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Đường dẫn tuyệt đối hoặc tương đối tới file cần đọc"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Tạo mới hoặc ghi nội dung vào một file trên máy tính",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Đường dẫn file cần ghi"},
                    "content": {"type": "string", "description": "Nội dung cần ghi"}
                },
                "required": ["path", "content"]
            }
        }
    }
]

def execute_local_tool(name: str, args: dict, cwd: str | None = None) -> str:
    working_dir = None
    if cwd:
        try:
            expanded = os.path.abspath(os.path.expanduser(cwd))
            os.makedirs(expanded, exist_ok=True)
            working_dir = expanded
        except Exception:
            working_dir = None

    if name == "execute_shell":
        cmd = args.get("command", "").strip()
        if not cmd:
            return "Lỗi: Không có câu lệnh được cung cấp."
        try:
            out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=35, cwd=working_dir).strip()
            return out or "(Thực thi thành công, không có output)"
        except subprocess.CalledProcessError as e:
            return f"Lỗi (Mã {e.returncode}):\n{e.output}"
        except Exception as e:
            return f"Lỗi thực thi: {str(e)}"

    elif name == "system_info":
        try:
            uname = platform.uname()
            disk = shutil.disk_usage('/')
            total_gb = round(disk.total / (1024**3), 2)
            used_gb = round(disk.used / (1024**3), 2)
            free_gb = round(disk.free / (1024**3), 2)
            mem_info = "N/A"
            if os.path.exists('/proc/meminfo'):
                with open('/proc/meminfo') as f:
                    lines = f.readlines()
                mem = {l.split(':')[0]: int(l.split(':')[1].strip().split()[0]) for l in lines if ':' in l}
                t_ram = round(mem.get('MemTotal', 0) / (1024**2), 2)
                a_ram = round(mem.get('MemAvailable', 0) / (1024**2), 2)
                u_ram = round(t_ram - a_ram, 2)
                mem_info = f"{t_ram} GB (Đã dùng {u_ram} GB, Còn trống {a_ram} GB)"
            return json.dumps({
                "os": f"{uname.system} {uname.release} ({uname.machine})",
                "node": uname.node,
                "disk_root": f"{total_gb} GB tổng, {used_gb} GB đã dùng, {free_gb} GB còn trống ({round(used_gb/total_gb*100, 1)}%)",
                "ram": mem_info,
                "python": platform.python_version()
            }, ensure_ascii=False)
        except Exception as e:
            return f"Lỗi system_info: {str(e)}"

    elif name == "read_file":
        raw_path = os.path.expanduser(args.get("path", ""))
        if working_dir and not os.path.isabs(raw_path):
            path = os.path.join(working_dir, raw_path)
        else:
            path = raw_path
        if not os.path.exists(path):
            return f"Lỗi: File '{path}' không tồn tại."
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(15000)
            return content
        except Exception as e:
            return f"Lỗi đọc file: {str(e)}"

    elif name == "write_file":
        raw_path = os.path.expanduser(args.get("path", ""))
        if working_dir and not os.path.isabs(raw_path):
            path = os.path.join(working_dir, raw_path)
        else:
            path = raw_path
        content = args.get("content", "")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Đã ghi file thành công: {path} ({len(content)} ký tự)"
        except Exception as e:
            return f"Lỗi ghi file: {str(e)}"

    return f"Lỗi: Không tìm thấy công cụ '{name}'"

def run_local_agent_loop(prompt: str, past_rows: list | None = None, token: str | None = None, device_token: str | None = None, max_steps: int = 5, cwd: str | None = None) -> str:
    """
    Vòng lặp Autonomous AI Agent (Hermes Parity) chạy cục bộ trên máy.
    Tự động suy luận, gọi công cụ terminal/file và tổng hợp câu trả lời hoàn chỉnh.
    """
    auth_info = load_device_auth()
    if not token and auth_info:
        token = auth_info.get("device_token") or auth_info.get("api_token", "")
    if not device_token and auth_info:
        device_token = auth_info.get("device_token", "")
    if not token:
        cfg = load_config()
        token = cfg.get("token", "")

    if not token:
        return "⚠️ **Chưa đăng nhập tài khoản!**\n\nThiết bị chưa được liên kết với tài khoản. Vui lòng mở https://ken.haiphongdeveloper.com để ghép đôi hoặc chạy lệnh `ken-agent`."

    messages = [
        {"role": "system", "content": LOCAL_AGENT_SYSTEM_PROMPT}
    ]
    if past_rows:
        for r in past_rows[-8:]:
            messages.append({"role": r["role"], "content": r["content"]})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "ken-agent-local-client"
    }
    if device_token:
        headers["x-device-token"] = device_token

    api_url = "https://api.haiphongdeveloper.com/v1/chat/completions"

    for step in range(max_steps):
        req_body = {
            "model": "ken-ai-helper",
            "messages": messages,
            "tools": LOCAL_AGENT_TOOLS,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": 2500
        }
        req = urllib.request.Request(
            api_url,
            data=json.dumps(req_body).encode("utf-8"),
            headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            if he.code == 402:
                return "⚠️ **Số dư Ví Lúa không đủ để xử lý tác vụ!**\n\n👉 Vui lòng quét mã VietQR tại https://api.haiphongdeveloper.com để nạp thêm Lúa."
            return f"⚠️ Lỗi máy chủ AI ({he.code}): {he.reason}"
        except Exception as e:
            return f"⚠️ Lỗi khi kết nối tới AI Hub: {str(e)}"

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls")

        # Nếu mô hình không gọi tool nữa, trả về kết quả tổng hợp
        if not tool_calls:
            return msg.get("content", "").strip() or "✅ Đã thực hiện xong yêu cầu."

        # Thêm phản hồi của assistant vào danh sách messages
        messages.append(msg)

        # Thực thi các tool call
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name", "")
            try:
                fn_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except Exception:
                fn_args = {}
            tool_output = execute_local_tool(fn_name, fn_args, cwd=cwd)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{fn_name}"),
                "name": fn_name,
                "content": str(tool_output)
            })

    return "⚠️ Đã đạt giới hạn số bước suy luận (5 bước). Vui lòng thử lại với yêu cầu cụ thể hơn."

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class LocalChatHandler(BaseHTTPRequestHandler):
    server_token = None

    def log_message(self, format, *args):
        # Tắt log stdout ồn ào của HTTP server trong console
        pass

    def do_HEAD(self):
        self.do_GET()

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Phục vụ giao diện Web UI HTML
        if path in ["/", "/index.html"]:
            html_file = ensure_web_ui_html()
            if os.path.exists(html_file):
                with open(html_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"web_ui.html not found")
                return

        # 2. Phục vụ Media cục bộ (Chỉ đọc từ ~/.ken-agent/media/, bảo mật chống path traversal)
        if path.startswith("/media/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 3:
                session_id, filename = parts[1], parts[2]
                safe_media_path = os.path.abspath(os.path.join(MEDIA_DIR, session_id, filename))
                if not safe_media_path.startswith(os.path.abspath(MEDIA_DIR)):
                    self.send_response(403)
                    self.end_headers()
                    return

                if os.path.exists(safe_media_path) and os.path.isfile(safe_media_path):
                    mime, _ = mimetypes.guess_type(safe_media_path)
                    mime = mime or "application/octet-stream"
                    with open(safe_media_path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_response(404)
            self.end_headers()
            return

        # 3. API Kiểm tra trạng thái Daemon
        if path == "/api/status":
            auth_info = load_device_auth()
            token = self.server_token or os.environ.get("KEN_AGENT_TOKEN", "")
            if not token and auth_info:
                token = auth_info.get("device_token") or auth_info.get("api_token", "")
            if not token:
                cfg = load_config()
                token = cfg.get("token", "")

            display_name = "Chưa Đăng Nhập"
            if auth_info:
                display_name = auth_info.get("user_name") or auth_info.get("user_email") or "KEN AGENT User"
            elif token:
                display_name = "KEN AGENT User"

            self._send_json({
                "ok": True,
                "token_name": display_name,
                "token_configured": bool(token or auth_info),
                "user_email": auth_info.get("user_email") if auth_info else "",
                "device_name": auth_info.get("device_name") if auth_info else "",
                "port": LOCAL_WEB_PORT,
                "version": CURRENT_VERSION
            })
            return

        # 4. API Lấy danh sách các phiên trò chuyện
        if path == "/api/sessions":
            conn = get_local_db()
            rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
            sessions = [dict(r) for r in rows]
            conn.close()
            self._send_json({"ok": True, "sessions": sessions})
            return

        # 5. API Lấy lịch sử tin nhắn của một phiên
        if path.startswith("/api/sessions/") and path.endswith("/messages"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                sess_id = parts[2]
                conn = get_local_db()
                rows = conn.execute("SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC", (sess_id,)).fetchall()
                messages = [dict(r) for r in rows]
                conn.close()
                self._send_json({"ok": True, "messages": messages})
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            body = {}

        # 1. Tạo phiên trò chuyện mới
        if path == "/api/sessions":
            title = body.get("title", "Phiên Trò Chuyện Mới").strip() or "Phiên Trò Chuyện Mới"
            sess_id = "sess_" + uuid.uuid4().hex[:12]
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn = get_local_db()
            conn.execute("INSERT INTO sessions(id, title, created_at, updated_at) VALUES(?, ?, ?, ?)", (sess_id, title, now, now))
            conn.commit()
            conn.close()
            self._send_json({"ok": True, "session": {"id": sess_id, "title": title, "created_at": now, "updated_at": now}})
            return

        # 2. Upload Media Cục Bộ (Lưu vào ~/.ken-agent/media/<session_id>/, Không gửi lên Cloud)
        if path == "/api/upload_media":
            sess_id = body.get("session_id", "default")
            raw_filename = body.get("filename", "upload.bin")
            safe_name = os.path.basename(raw_filename).replace(" ", "_")
            data_b64 = body.get("data", "")
            mime = body.get("mime_type", "application/octet-stream")

            sess_media_dir = os.path.join(MEDIA_DIR, sess_id)
            os.makedirs(sess_media_dir, exist_ok=True)
            file_path = os.path.join(sess_media_dir, safe_name)

            try:
                if "," in data_b64:
                    data_b64 = data_b64.split(",", 1)[1]
                file_bytes = base64.b64decode(data_b64)
                with open(file_path, "wb") as f:
                    f.write(file_bytes)
                
                self._send_json({
                    "ok": True,
                    "file": {
                        "filename": safe_name,
                        "url": f"/media/{sess_id}/{safe_name}",
                        "mime_type": mime,
                        "size": len(file_bytes)
                    }
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        # 3. Trò chuyện với KEN AGENT
        if path == "/api/chat":
            sess_id = body.get("session_id")
            prompt = body.get("prompt", "").strip()
            media = body.get("media", [])

            if not sess_id or (not prompt and not media):
                self._send_json({"ok": False, "error": "Thiếu prompt hoặc session_id"}, status=400)
                return

            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            msg_id = "msg_" + uuid.uuid4().hex[:12]
            media_json = json.dumps(media) if media else None

            conn = get_local_db()
            # Ghi tin nhắn người dùng vào SQLite cục bộ
            conn.execute("INSERT INTO messages(id, session_id, role, content, media_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                         (msg_id, sess_id, "user", prompt, media_json, now))
            conn.commit()

            # Lấy ngữ cảnh các tin nhắn gần nhất
            past_rows = conn.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY created_at ASC LIMIT 15", (sess_id,)).fetchall()
            
            # Nếu người dùng gõ lệnh shell trực tiếp ($ cmd hoặc ! cmd)
            if prompt.startswith("$ ") or prompt.startswith("! "):
                cmd = prompt[2:].strip()
                try:
                    res_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=30).strip()
                    res_output = res_output or "✅ Lệnh đã thực thi thành công (Không có output)."
                except subprocess.CalledProcessError as e:
                    res_output = f"⚠️ Lỗi thực thi (Mã {e.returncode}):\n{e.output}"
                except Exception as e:
                    res_output = f"❌ Lỗi: {str(e)}"
                assistant_reply = f"💻 **Kết quả thực thi lệnh cục bộ:**\n```bash\n{res_output}\n```"
            else:
                # Kích hoạt Autonomous Hermes Agent Loop
                auth_info = load_device_auth()
                token = self.server_token or os.environ.get("KEN_AGENT_TOKEN", "")
                dev_tok = auth_info.get("device_token") if auth_info else None
                assistant_reply = run_local_agent_loop(prompt, past_rows, token=token, device_token=dev_tok)

            # Ghi tin nhắn phản hồi của Assistant vào SQLite cục bộ
            asst_msg_id = "msg_" + uuid.uuid4().hex[:12]
            asst_now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute("INSERT INTO messages(id, session_id, role, content, media_json, created_at) VALUES(?, ?, ?, ?, NULL, ?)",
                         (asst_msg_id, sess_id, "assistant", assistant_reply, asst_now))

            # Tự động cập nhật tiêu đề nếu vẫn đang để mặc định
            current_sess = conn.execute("SELECT title FROM sessions WHERE id=?", (sess_id,)).fetchone()
            if current_sess and current_sess["title"] == "Phiên Trò Chuyện Mới" and prompt:
                new_title = prompt[:28] + ("..." if len(prompt) > 28 else "")
                conn.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (new_title, asst_now, sess_id))
            else:
                conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (asst_now, sess_id))

            conn.commit()
            conn.close()

            self._send_json({"ok": True, "response": assistant_reply, "session_id": sess_id})
            return

        self.send_response(404)
        self.end_headers()

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}

        # Đổi tên phiên
        if path.startswith("/api/sessions/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                sess_id = parts[2]
                new_title = body.get("title", "").strip()
                if new_title:
                    conn = get_local_db()
                    conn.execute("UPDATE sessions SET title=? WHERE id=?", (new_title, sess_id))
                    conn.commit()
                    conn.close()
                    self._send_json({"ok": True})
                    return
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Xóa sạch tin nhắn trong phiên
        if path.startswith("/api/sessions/") and path.endswith("/messages"):
            parts = path.strip("/").split("/")
            if len(parts) == 4:
                sess_id = parts[2]
                conn = get_local_db()
                conn.execute("DELETE FROM messages WHERE session_id=?", (sess_id,))
                conn.commit()
                conn.close()
                self._send_json({"ok": True})
                return

        # Xóa toàn bộ phiên trò chuyện
        if path.startswith("/api/sessions/"):
            parts = path.strip("/").split("/")
            if len(parts) == 3:
                sess_id = parts[2]
                conn = get_local_db()
                conn.execute("DELETE FROM messages WHERE session_id=?", (sess_id,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sess_id,))
                conn.commit()
                conn.close()
                # Xóa thư mục media của session nếu có
                sess_media_dir = os.path.join(MEDIA_DIR, sess_id)
                if os.path.exists(sess_media_dir):
                    try:
                        import shutil
                        shutil.rmtree(sess_media_dir)
                    except Exception:
                        pass
                self._send_json({"ok": True})
                return

        self.send_response(404)
        self.end_headers()

def start_local_web_chat_server(token=None):
    """Khởi động Local Web Chat Server trong luồng nền (Zero-dependency, Python stdlib)"""
    global _local_web_server_started, LOCAL_WEB_PORT
    if _local_web_server_started:
        return
    _local_web_server_started = True

    init_local_db()
    ensure_web_ui_html()
    if not token:
        auth_info = load_device_auth()
        if auth_info:
            token = auth_info.get("device_token") or auth_info.get("api_token")
    LocalChatHandler.server_token = token

    def _worker():
        global LOCAL_WEB_PORT
        for port in range(18765, 18780):
            try:
                server = ThreadedHTTPServer(("127.0.0.1", port), LocalChatHandler)
                LOCAL_WEB_PORT = port
                print(f"🌐 [LOCAL CHAT] Giao diện Web Chat cục bộ đang chạy tại: http://127.0.0.1:{LOCAL_WEB_PORT}")
                server.serve_forever()
                break
            except OSError:
                continue

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def parse_version(v_str):
    """Chuyển chuỗi version thành tuple số để so sánh chính xác: (2, 3, 4) > (2, 3, 2)"""
    try:
        import re
        nums = [int(n) for n in re.findall(r'\d+', str(v_str))]
        return tuple(nums)
    except Exception:
        return (0, 0, 0)

def check_for_updates():
    """Kiểm tra phiên bản mới nhất từ PyPI trong nền và thông báo CHỈ KHI latest > CURRENT_VERSION"""
    try:
        import urllib.request
        req = urllib.request.Request("https://pypi.org/pypi/ken-agent/json", headers={"User-Agent": "ken-agent-cli"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("info", {}).get("version")
            if latest and parse_version(latest) > parse_version(CURRENT_VERSION):
                print("\n" + "!" * 68)
                print(f" 🚀 ĐÃ CÓ BẢN CẬP NHẬT MỚI: v{latest} (Phiên bản của bạn: v{CURRENT_VERSION})")
                print(" 👉 Hãy gõ lệnh sau để nâng cấp ngay:")
                print("    \033[1;32mken-agent update\033[0m")
                print("!" * 68 + "\n")
    except Exception:
        pass

def perform_update():
    """Thực hiện cập nhật ken-agent lên phiên bản mới nhất trực tiếp từ Hub Server"""
    print("\n" + "=" * 60)
    print(" ⚡ ĐANG CẬP NHẬT KEN AGENT...")
    print("=" * 60)
    try:
        if sys.platform == "win32":
            cmd = 'powershell -Command "irm https://api.haiphongdeveloper.com/install.ps1 | iex"'
        else:
            cmd = 'curl -sSL https://api.haiphongdeveloper.com/install.sh | bash'
        print(f"📦 Đang tải và đồng bộ bản phát hành mới nhất từ api.haiphongdeveloper.com...")
        subprocess.check_call(cmd, shell=True)
        print("\n🎉 CẬP NHẬT HOÀN TẤT! Hãy khởi chạy lại: ken-agent\n")
    except Exception as e:
        print(f"❌ Cập nhật thất bại: {e}")
        print("💡 Bạn có thể thử chạy lại: curl -sSL https://api.haiphongdeveloper.com/install.sh | bash\n")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"server_url": DEFAULT_SERVER_URL, "token": "", "device_name": "My-Computer"}

def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Đã lưu cấu hình tại: {CONFIG_FILE}")

async def run_command_on_system(command, cwd=None):
    try:
        working_dir = None
        if cwd:
            try:
                expanded = os.path.abspath(os.path.expanduser(cwd))
                os.makedirs(expanded, exist_ok=True)
                working_dir = expanded
            except Exception:
                working_dir = None

        # Chuẩn hóa executable Python cho đa nền tảng (Windows, macOS, Linux)
        venv_py = sys.executable
        if sys.platform == "win32":
            for prefix in ["~/.ken-agent/venv/bin/python", "$HOME/.ken-agent/venv/bin/python", "%USERPROFILE%\\.ken-agent\\venv\\Scripts\\python.exe"]:
                if command.startswith(prefix):
                    command = f'& "{venv_py}"' + command[len(prefix):]
                    break
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe", "-NoProfile", "-Command", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )
        elif sys.platform == "darwin":
            for prefix in ["~/.ken-agent/venv/bin/python", "$HOME/.ken-agent/venv/bin/python"]:
                if command.startswith(prefix):
                    command = f'"{venv_py}"' + command[len(prefix):]
                    break
            if command.startswith("osascript:") or command.startswith("apple:"):
                script = command.split(":", 1)[1].strip()
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                    executable="/bin/zsh"
                )
        else:
            for prefix in ["~/.ken-agent/venv/bin/python", "$HOME/.ken-agent/venv/bin/python"]:
                if command.startswith(prefix):
                    command = f'"{venv_py}"' + command[len(prefix):]
                    break
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                executable="/bin/bash"
            )

        stdout, stderr = await proc.communicate()
        out = stdout.decode('utf-8', errors='ignore').strip()
        err = stderr.decode('utf-8', errors='ignore').strip()

        # Nếu có output chuẩn thì ưu tiên trả về out (kể cả exitcode != 0 do warning/pipe)
        if out:
            return out
        elif err:
            return f"⚠️ Lỗi (Mã {proc.returncode}):\n{err}"
        elif proc.returncode == 0:
            return "✅ Lệnh thực thi thành công (Không có output)."
        else:
            return f"⚠️ Lỗi thực thi (Mã {proc.returncode})"
    except Exception as e:
        return f"❌ Lỗi thực thi hệ thống: {str(e)}"

async def handle_agent_task(prompt, ai_plan=None, cwd=None):
    prompt_strip = prompt.strip()
    
    # 1. Nếu Hub đã có AI Planner phân tích sẵn
    if ai_plan and isinstance(ai_plan, dict):
        cmd = ai_plan.get("command") or ai_plan.get("cmd")
        if cmd:
            res = await run_command_on_system(cmd, cwd=cwd)
            return f"💻 Kết quả thực thi:\n```\n{res}\n```"

    prompt_lower = prompt_strip.lower()

    # 2. Xử lý câu chào hỏi tự nhiên
    if prompt_lower in ["alo", "alo ken", "hi", "hello", "xin chào", "ken ơi", "hey"]:
        uname = "macOS" if sys.platform == "darwin" else ("Windows" if sys.platform == "win32" else "Linux")
        return f"👋 Chào bạn! KEN AGENT đang sẵn sàng trên thiết bị ({uname}).\nBạn cứ ra lệnh bằng tiếng Việt tự nhiên nhé (Ví dụ: 'dung lượng ổ cứng trên máy', 'kiểm tra RAM', 'tạo file script'...)!"

    # 3. Lệnh shell trực tiếp ($ cmd hoặc ! cmd)
    if prompt_strip.startswith("$ ") or prompt_strip.startswith("! "):
        cmd = prompt_strip[2:].strip()
        res = await run_command_on_system(cmd, cwd=cwd)
        return f"💻 **Kết quả thực thi lệnh:**\n```bash\n{res}\n```"

    # 4. Ngôn ngữ tự nhiên: Chạy Local Autonomous Agent Loop (Hermes Parity)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: run_local_agent_loop(prompt_strip, cwd=cwd))

async def send_heartbeat_loop(ws):
    """Gửi heartbeat định kỳ 15s để giữ kết nối WSS luôn sống (chống timeout bởi proxy/Nginx)"""
    while True:
        try:
            await asyncio.sleep(15)
            if ws.closed:
                break
            await ws.send(json.dumps({"type": "HEARTBEAT", "timestamp": time.time()}))
        except Exception:
            break

async def start_relay_loop(auth_data, server_url=None):
    check_for_updates()
    
    device_id = auth_data["device_id"]
    device_token = auth_data["device_token"]
    user_email = auth_data.get("user_email", "User")
    device_name = auth_data.get("device_name", "PC")

    ws_url = f"{HUB_WS_URL}?device_id={device_id}&device_token={device_token}"

    # Khởi động Local Web Chat Server song song trong luồng nền
    start_local_web_chat_server()

    print("\n" + "═" * 76)
    print(" 🚀 KEN AGENT - TRỢ LÝ AI ĐIỀU KHIỂN TỰ HÀNH (HPD Web Hub)")
    print(f" 🌐 Cloud Hub: {HUB_URL}")
    print(f" 👤 Tài khoản: \033[1;32m{user_email}\033[0m")
    print(f" 💻 Thiết bị : \033[1;37m{device_name}\033[0m ({device_id})")
    print(f" 💬 Local Web Chat: http://127.0.0.1:{LOCAL_WEB_PORT}")
    print("═" * 76)

    retry_count = 0
    while True:
        try:
            print(f"\n🔄 Đang kết nối tới Cloud Web Hub...")
            async with websockets.connect(ws_url) as ws:
                retry_count = 0
                print(f"⚡ [ONLINE] Đã kết nối thành công tới Web Hub: {HUB_URL}\n")

                # Chạy task heartbeat ngầm giữ kết nối
                hb_task = asyncio.create_task(send_heartbeat_loop(ws))

                async for message in ws:
                    try:
                        data = json.loads(message)
                    except Exception:
                        continue

                    msg_type = data.get("type")

                    if msg_type == "INIT_SUCCESS":
                        print("┌" + "─" * 74 + "┐")
                        print(f"│  ⚡ SẴN SÀNG NHẬN LỆNH ĐIỀU KHIỂN TỪ XA                                    │")
                        print(f"│  👉 Bạn có thể mở điện thoại hoặc trình duyệt bất kỳ tại:                  │")
                        print(f"│     \033[1;36m{HUB_URL}\033[0m                                     │")
                        print("└" + "─" * 74 + "┘\n")

                    elif msg_type == "EXECUTE_TASK":
                        task_id = data.get("task_id")
                        prompt = data.get("prompt", "")
                        command = data.get("command") or (data.get("ai_plan") or {}).get("command")
                        cwd = data.get("cwd")
                        media = data.get("media", [])

                        print(f"\n📥 [LỆNH TỪ XA]: {command or prompt} (cwd: {cwd or 'default'})")

                        if command:
                            output = await run_command_on_system(command, cwd=cwd)
                        else:
                            output = await handle_agent_task(prompt, cwd=cwd)

                        print(f"📤 [KẾT QUẢ]: {output[:120]}..." if len(output) > 120 else f"📤 [KẾT QUẢ]: {output}")

                        await ws.send(json.dumps({
                            "type": "TASK_COMPLETED",
                            "task_id": task_id,
                            "response": output,
                            "is_error": False
                        }))

                    elif msg_type == "UNPAIRED":
                        print("\n⚠️ Thiết bị đã bị hủy ghép đôi khỏi tài khoản trên Web Hub.")
                        if os.path.exists(AUTH_PATH):
                            try:
                                os.remove(AUTH_PATH)
                            except Exception:
                                pass
                        sys.exit(0)

        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 401:
                print("\n❌ Lỗi: Mã xác thực thiết bị không hợp lệ hoặc đã bị hủy ghép đôi!")
                if os.path.exists(AUTH_PATH):
                    try:
                        os.remove(AUTH_PATH)
                    except Exception:
                        pass
                sys.exit(1)
            print(f"⚠️ Lỗi kết nối HTTP {e.status_code}. Thử lại sau 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            retry_count += 1
            wait_time = min(retry_count * 2, 15)
            print(f"⚠️ Mất kết nối tới Cloud Hub ({str(e)}). Tự động kết nối lại sau {wait_time}s...")
            await asyncio.sleep(wait_time)

def create_tray_icon_image(connected=True):
    """Tạo biểu tượng Robot Ken siêu nét với định dạng RGBA chuẩn (Cyberpunk Robot Face)"""
    from PIL import Image, ImageDraw
    size = 64
    img = Image.new('RGBA', (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    scale = size / 128.0

    # 1. Anten trên đầu
    draw.line((64*scale, 28*scale, 64*scale, 10*scale), fill=(0, 229, 255, 255), width=max(1, int(4*scale)))
    draw.ellipse((58*scale, 6*scale, 70*scale, 18*scale), fill=(0, 255, 136, 255), outline=(0, 229, 255, 255), width=max(1, int(2*scale)))

    # 2. Đầu Robot bo góc
    draw.rounded_rectangle((24*scale, 28*scale, 104*scale, 98*scale), radius=int(18*scale), fill=(20, 28, 45, 255), outline=(0, 229, 255, 255), width=max(1, int(4*scale)))

    # 3. Tai Robot 2 bên
    draw.rounded_rectangle((14*scale, 50*scale, 24*scale, 76*scale), radius=int(4*scale), fill=(0, 229, 255, 255))
    draw.rounded_rectangle((104*scale, 50*scale, 114*scale, 76*scale), radius=int(4*scale), fill=(0, 229, 255, 255))

    # 4. Kính Màn hình Neon
    draw.rounded_rectangle((34*scale, 42*scale, 94*scale, 84*scale), radius=int(10*scale), fill=(10, 15, 25, 255), outline=(0, 255, 136, 255), width=max(1, int(2*scale)))

    # 5. Mắt Robot (Xanh Neon rực sáng khi online, đỏ khi mất mạng)
    eye_color = (0, 255, 136, 255) if connected else (255, 82, 82, 255)
    draw.ellipse((44*scale, 54*scale, 58*scale, 68*scale), fill=eye_color)
    draw.ellipse((70*scale, 54*scale, 84*scale, 68*scale), fill=eye_color)

    # 6. Miệng cười Robot
    draw.line((54*scale, 76*scale, 74*scale, 76*scale), fill=(0, 229, 255, 255), width=max(1, int(3*scale)))

    return img

def run_macos_native_statusbar(auth_data, server_url=None):
    """Khởi chạy native NSStatusItem bằng PyObjC Cocoa trên macOS với text emoji indicator trực tiếp"""
    try:
        import objc
        from AppKit import (
            NSApplication, NSApp, NSStatusBar, NSVariableStatusItemLength,
            NSMenu, NSMenuItem, NSApplicationActivationPolicyAccessory
        )
        from Foundation import NSObject
        import threading
        import webbrowser

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        status_bar = NSStatusBar.systemStatusBar()
        # Tạo Status Item với độ dài tự co giãn theo nội dung
        status_item = status_bar.statusItemWithLength_(-1) # -1 = NSVariableStatusItemLength

        # Lưu biến toàn cục tránh Garbage Collector giải phóng bộ nhớ
        global _global_status_item, _global_delegate
        _global_status_item = status_item

        button = status_item.button()
        if button:
            button.setTitle_("🟢 KEN AGENT")
            button.setToolTip_("KEN AGENT - Đang online kết nối Telegram")
        else:
            # Fallback nếu macOS cũ không có button()
            status_item.setTitle_("🟢 KEN AGENT")

        menu = NSMenu.alloc().init()

        item_title = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("⚡ KEN AGENT: Đang chạy ngầm", None, "")
        item_title.setEnabled_(False)
        menu.addItem_(item_title)

        class MenuDelegate(NSObject):
            def openHub_(self, sender):
                webbrowser.open("https://ken.haiphongdeveloper.com")
            def openChat_(self, sender):
                webbrowser.open(f"http://127.0.0.1:{LOCAL_WEB_PORT}")
            def openDash_(self, sender):
                webbrowser.open("https://ken.haiphongdeveloper.com")
            def quitApp_(self, sender):
                os._exit(0)

        delegate = MenuDelegate.alloc().init()
        _global_delegate = delegate

        item_hub = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("🌐 Mở Web Hub Điều Khiển (ken.haiphongdeveloper.com)", "openHub:", "")
        item_hub.setTarget_(delegate)
        menu.addItem_(item_hub)

        item_chat = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("💬 Mở Web Chat Cục Bộ (localhost)", "openChat:", "")
        item_chat.setTarget_(delegate)
        menu.addItem_(item_chat)

        item_dash = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("🪙 Quản lý Ví Lúa & Thiết Bị", "openDash:", "")
        item_dash.setTarget_(delegate)
        menu.addItem_(item_dash)

        menu.addItem_(NSMenuItem.separatorItem())

        item_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("❌ Thoát KEN AGENT", "quitApp:", "")
        item_quit.setTarget_(delegate)
        menu.addItem_(item_quit)

        status_item.setMenu_(menu)

        # Chạy WSS Relay Loop trong luồng nền
        def relay_worker():
            asyncio.run(start_relay_loop(auth_data, server_url))

        t = threading.Thread(target=relay_worker, daemon=True)
        t.start()

        print("⚡ [MENUBAR] Đã kích hoạt biểu tượng '🟢 KEN AGENT' trên thanh MenuBar macOS.")
        app.run()
    except Exception as e:
        print(f"⚠️ Lỗi khởi chạy Native MenuBar ({e}). Chuyển sang chạy nền...")
        asyncio.run(start_relay_loop(auth_data, server_url))

def run_linux_appindicator_tray(auth_data, server_url=None):
    """Khởi chạy native Ayatana / AppIndicator System Tray cho Debian/Ubuntu/GNOME"""
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3 as appindicator
        except Exception:
            gi.require_version('AppIndicator3', '0.1')
            from gi.repository import AppIndicator3 as appindicator

        import threading
        import webbrowser

        # Lưu ảnh icon tạm thời
        icon_path = os.path.join(APP_DIR, "tray_icon.png")
        try:
            img = create_tray_icon_image(True)
            img.save(icon_path, "PNG")
        except Exception:
            pass

        # Khởi tạo AppIndicator với icon theme path chuẩn xác
        theme_path = os.path.expanduser("~/.local/share/icons/hicolor/48x48/apps")
        indicator = appindicator.Indicator.new_with_path(
            "ken_agent_indicator",
            "ken-agent",
            appindicator.IndicatorCategory.APPLICATION_STATUS,
            theme_path
        )
        indicator.set_icon_theme_path(theme_path)
        indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        indicator.set_title("KEN AGENT")

        user_email = auth_data.get("user_email", "User")

        # Xây dựng Menu ngữ cảnh
        menu = Gtk.Menu()

        item_status = Gtk.MenuItem(label=f"⚡ KEN AGENT: Online ({user_email})")
        item_status.set_sensitive(False)
        menu.append(item_status)

        item_hub = Gtk.MenuItem(label="🌐 Mở Web Hub Điều Khiển (ken.haiphongdeveloper.com)")
        item_hub.connect("activate", lambda w: webbrowser.open("https://ken.haiphongdeveloper.com"))
        menu.append(item_hub)

        item_chat = Gtk.MenuItem(label="💬 Mở Web Chat Cục Bộ (localhost)")
        item_chat.connect("activate", lambda w: webbrowser.open(f"http://127.0.0.1:{LOCAL_WEB_PORT}"))
        menu.append(item_chat)

        item_dash = Gtk.MenuItem(label="🪙 Quản lý Ví Lúa & Thiết Bị")
        item_dash.connect("activate", lambda w: webbrowser.open("https://ken.haiphongdeveloper.com"))
        menu.append(item_dash)

        sep = Gtk.SeparatorMenuItem()
        menu.append(sep)

        item_quit = Gtk.MenuItem(label="❌ Thoát KEN AGENT")
        item_quit.connect("activate", lambda w: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        indicator.set_menu(menu)

        print("⚡ [TRAY] Đã kích hoạt biểu tượng KEN AGENT trên thanh Taskbar/System Tray Linux.")

        # Chạy WSS Relay Loop trong luồng nền
        def relay_worker():
            asyncio.run(start_relay_loop(auth_data, server_url))

        t = threading.Thread(target=relay_worker, daemon=True)
        t.start()

        # Chạy GTK Main Loop trên main thread
        Gtk.main()
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo AppIndicator ({e}). Chuyển sang chạy nền...")
        asyncio.run(start_relay_loop(auth_data, server_url))

def run_tray_icon(auth_data, server_url=None):
    """Chạy System Tray Icon đa nền tảng: macOS (Cocoa Native), Linux (Ayatana AppIndicator / DBusMenu), Windows (Pystray)"""
    if sys.platform == "darwin":
        run_macos_native_statusbar(auth_data, server_url)
        return

    if sys.platform.startswith("linux"):
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            run_linux_appindicator_tray(auth_data, server_url)
            return
    try:
        import pystray
        import threading
        import webbrowser
        from PIL import Image

        icon_path = os.path.join(APP_DIR, "tray_icon.png")
        if os.path.exists(icon_path):
            icon_img = Image.open(icon_path)
        else:
            icon_img = create_tray_icon_image(True)

        def on_open_hub(icon, item):
            webbrowser.open("https://ken.haiphongdeveloper.com")

        def on_open_chat(icon, item):
            webbrowser.open(f"http://127.0.0.1:{LOCAL_WEB_PORT}")

        def on_quit(icon, item):
            icon.stop()
            os._exit(0)

        def on_open_dashboard(icon, item):
            webbrowser.open("https://ken.haiphongdeveloper.com")

        user_email = auth_data.get("user_email", "User")
        menu = pystray.Menu(
            pystray.MenuItem(f"⚡ KEN AGENT: Online ({user_email})", None, enabled=False),
            pystray.MenuItem("🌐 Mở Web Hub Điều Khiển", on_open_hub),
            pystray.MenuItem("💬 Mở Web Chat Cục Bộ", on_open_chat),
            pystray.MenuItem("🪙 Quản lý Ví Lúa & Thiết Bị", on_open_dashboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Thoát KEN AGENT", on_quit)
        )

        icon = pystray.Icon("ken_agent", icon_img, "KEN AGENT - Web Hub Runner", menu)

        print("⚡ [TRAY] Đã kích hoạt biểu tượng Robot KEN AGENT trên khay hệ thống (System Tray).")

        def relay_worker():
            asyncio.run(start_relay_loop(auth_data, server_url))

        t = threading.Thread(target=relay_worker, daemon=True)
        t.start()

        icon.run()
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo System Tray ({e}). Chuyển sang chạy nền...")
        asyncio.run(start_relay_loop(auth_data, server_url))

def main():
    parser = argparse.ArgumentParser(
        prog="ken-agent",
        description="🚀 KEN AGENT CLI - Trợ lý AI tự hành điều khiển máy tính từ xa qua Web Hub (HPD Ecosystem)",
        epilog="""Ví dụ sử dụng:
  ken-agent                          Khởi chạy nhanh (tự động ghép đôi 1-Click qua Web Hub)
  ken-agent chat                     Mở giao diện Web Chat cục bộ tại localhost:18765
  ken-agent unpair                   Hủy ghép đôi và đăng xuất thiết bị
  ken-agent update                   Cập nhật KEN AGENT lên phiên bản mới nhất
  ken-agent uninstall                Gỡ cài đặt hoàn toàn KEN AGENT khỏi máy
  ken-agent -v                       Xem phiên bản hiện tại

Trung tâm điều khiển từ xa:
  • Web Hub   : https://ken.haiphongdeveloper.com (Điều khiển mọi lúc mọi nơi)
  • Local Chat: http://127.0.0.1:18765
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="action", help="Lệnh thao tác bổ sung")

    subparsers.add_parser("start", help="Khởi động KEN AGENT Runner")
    subparsers.add_parser("update", help="Cập nhật KEN AGENT lên phiên bản mới nhất từ PyPI")
    subparsers.add_parser("unpair", help="Hủy ghép đôi thiết bị khỏi Web Hub")

    cfg_parser = subparsers.add_parser("config", help="Cấu hình Server URL")
    cfg_parser.add_argument("--server", "-s", type=str, help="Lưu Relay Server URL")
    cfg_parser.add_argument("--show", action="store_true", help="Hiển thị cấu hình hiện tại")

    uninst_parser = subparsers.add_parser("uninstall", help="Gỡ cài đặt và dọn dẹp sạch sẽ KEN AGENT")
    uninst_parser.add_argument("-y", "--yes", action="store_true", help="Tự động đồng ý gỡ cài đặt mà không cần xác nhận")

    subparsers.add_parser("chat", help="Mở giao diện Web Chat cục bộ trong trình duyệt")

    parser.add_argument("--cli", action="store_true", help="Chạy ở chế độ dòng lệnh Terminal (mặc định mở service ngầm / Tray)")
    parser.add_argument("--chat", action="store_true", help="Mở giao diện Web Chat cục bộ")
    parser.add_argument("--daemon", action="store_true", help="Khởi chạy chạy ngầm hoàn toàn")
    parser.add_argument("--start", action="store_true", help="Khởi động service chạy ngầm (macOS/Linux)")
    parser.add_argument("--stop", action="store_true", help="Dừng service chạy ngầm")
    parser.add_argument("--status", action="store_true", help="Kiểm tra trạng thái service")
    parser.add_argument("--version", "-v", action="version", version=f"KEN AGENT v{CURRENT_VERSION} (HPD Ecosystem 2026)")

    args = parser.parse_args()
    config = load_config()

    if getattr(args, "stop", False):
        if sys.platform == "darwin":
            plist = os.path.expanduser("~/Library/LaunchAgents/com.haiphongdeveloper.ken-agent.plist")
            subprocess.run(["launchctl", "unload", plist], capture_output=True)
            subprocess.run(["pkill", "-f", "ken_agent"], capture_output=True)
            print("🛑 Đã dừng service KEN AGENT trên macOS.")
        else:
            subprocess.run(["pkill", "-f", "ken_agent"], capture_output=True)
            print("🛑 Đã dừng tiến trình KEN AGENT.")
        return

    if getattr(args, "start", False):
        if sys.platform == "darwin":
            plist = os.path.expanduser("~/Library/LaunchAgents/com.haiphongdeveloper.ken-agent.plist")
            if os.path.exists(plist):
                subprocess.run(["launchctl", "load", "-w", plist], capture_output=True)
                subprocess.run(["launchctl", "start", "com.haiphongdeveloper.ken-agent"], capture_output=True)
                print("🚀 Đã khởi động background service com.haiphongdeveloper.ken-agent trên macOS!")
                return
        log_file = os.path.expanduser("~/.ken-agent/agent.log")
        with open(log_file, "a") as out:
            subprocess.Popen([sys.executable, "-m", "ken_agent", "--cli"], stdout=out, stderr=out, start_new_session=True)
        print(f"🚀 KEN AGENT đã được chạy ngầm. Xem log tại: {log_file}")
        return

    if getattr(args, "status", False):
        res = subprocess.run(["pgrep", "-f", "ken_agent"], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"🟢 KEN AGENT đang CHẠY NGẦM (PIDs: {res.stdout.strip()})")
        else:
            print("🔴 KEN AGENT hiện KHÔNG chạy.")
        return

    if args.action == "update":
        perform_update()
        return

    if args.action == "unpair":
        if os.path.exists(AUTH_PATH):
            try:
                os.remove(AUTH_PATH)
                print("✅ Đã hủy ghép đôi thiết bị này khỏi tài khoản Web Hub.")
                print("👉 Lần tới khi chạy, KEN AGENT sẽ tự động mở liên kết với tài khoản mới.")
            except Exception as e:
                print(f"⚠️ Lỗi xóa auth: {e}")
        else:
            print("ℹ️ Thiết bị này hiện chưa ghép đôi với tài khoản nào.")
        return

    if args.action == "chat" or getattr(args, "chat", False):
        start_local_web_chat_server()
        webbrowser.open(f"http://127.0.0.1:{LOCAL_WEB_PORT}")
        print(f"💬 Đã mở Web Chat Cục Bộ tại: http://127.0.0.1:{LOCAL_WEB_PORT}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Đã thoát Web Chat.")
        return

    if args.action == "uninstall":
        print("\n" + "=" * 60)
        print(" 🗑️ GỠ CÀI ĐẶT KEN AGENT")
        print("=" * 60)
        if not getattr(args, "yes", False):
            confirm = input("⚠️ Bạn có chắc chắn muốn gỡ cài đặt KEN AGENT khỏi máy? (y/N): ").strip().lower()
            if confirm not in ("y", "yes"):
                print("❌ Đã hủy thao tác gỡ cài đặt.")
                return

        import shutil
        app_dir = os.path.expanduser("~/.ken-agent")
        bin_file = os.path.expanduser("~/.local/bin/ken-agent")

        if os.path.exists(bin_file):
            try:
                os.remove(bin_file)
                print(f"✅ Đã xóa file thực thi: {bin_file}")
            except Exception as e:
                print(f"⚠️ Không thể xóa {bin_file}: {e}")

        if os.path.exists(app_dir):
            try:
                shutil.rmtree(app_dir)
                print(f"✅ Đã xóa thư mục dữ liệu & venv: {app_dir}")
            except Exception as e:
                print(f"⚠️ Không thể xóa {app_dir}: {e}")

        print("\n🎉 ĐÃ GỠ CÀI ĐẶT KEN AGENT THÀNH CÔNG!")
        print("Cảm ơn bạn đã sử dụng dịch vụ của https://ken.haiphongdeveloper.com\n")
        return

    if args.action == "config":
        if args.show:
            print("\n📋 CẤU HÌNH KEN AGENT HIỆN TẠI:")
            print(f"  • File cấu hình : {CONFIG_FILE}")
            print(f"  • Web Hub URL   : {HUB_URL}")
            auth_info = load_device_auth()
            if auth_info:
                print(f"  • Tài khoản     : {auth_info.get('user_email')} ({auth_info.get('user_id')})")
                print(f"  • Thiết bị      : {auth_info.get('device_name')} ({auth_info.get('device_id')})")
            else:
                print("  • Thiết bị      : (Chưa ghép đôi)")
            return
        if getattr(args, "server", None):
            config["server_url"] = args.server.strip()
            save_config(config)
        return

    # Xác thực thiết bị 1-Click (Zero-Token UX)
    auth_data = ensure_device_auth()
    server_url = getattr(args, "server", None) or HUB_WS_URL

    is_cli = getattr(args, "cli", False)
    if is_cli or os.environ.get("SSH_TTY") or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")):
        try:
            asyncio.run(start_relay_loop(auth_data, server_url))
        except KeyboardInterrupt:
            print("\n👋 Đã dừng KEN AGENT.")
    else:
        try:
            run_tray_icon(auth_data, server_url)
        except Exception:
            asyncio.run(start_relay_loop(auth_data, server_url))

if __name__ == "__main__":
    main()
