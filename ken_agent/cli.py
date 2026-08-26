import os
import sys
import json
import time
import asyncio
import argparse
import subprocess

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
DEFAULT_SERVER_URL = "wss://api.haiphongdeveloper.com/ws/hermes-relay"

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

async def run_command_on_system(command):
    try:
        if sys.platform == "win32":
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe", "-NoProfile", "-Command", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        elif sys.platform == "darwin":
            if command.startswith("osascript:") or command.startswith("apple:"):
                script = command.split(":", 1)[1].strip()
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    executable="/bin/zsh"
                )
        else:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                executable="/bin/bash"
            )

        stdout, stderr = await proc.communicate()
        out = stdout.decode('utf-8', errors='ignore').strip()
        err = stderr.decode('utf-8', errors='ignore').strip()

        if proc.returncode == 0:
            return out if out else "✅ Lệnh thực thi thành công (Không có output)."
        else:
            return f"⚠️ Lỗi (Mã {proc.returncode}):\n{err if err else out}"
    except Exception as e:
        return f"❌ Lỗi thực thi hệ thống: {str(e)}"

async def handle_agent_task(prompt):
    prompt_strip = prompt.strip()
    prompt_lower = prompt_strip.lower()

    if prompt_lower.startswith("cmd:") or prompt_lower.startswith("run:"):
        cmd = prompt_strip.split(":", 1)[1].strip()
        return await run_command_on_system(cmd)

    if sys.platform == "darwin" and prompt_lower.startswith("open:"):
        app = prompt_strip.split(":", 1)[1].strip()
        return await run_command_on_system(f"open -a '{app}'")

    if sys.platform == "darwin" and prompt_lower.startswith("notify:"):
        msg = prompt_strip.split(":", 1)[1].strip()
        return await run_command_on_system(f'osascript -e \'display notification "{msg}" with title "KEN AGENT"\'')

    return await run_command_on_system(prompt_strip)

async def start_relay_loop(token, server_url):
    full_url = f"{server_url}?token={token}"
    
    print("\n" + "=" * 65)
    print(" 🚀 KEN AGENT - TRỢ LÝ AI ĐIỀU KHIỂN TỰ HÀNH (PyPI CLI)")
    print(f" 🌐 Relay Server: {server_url}")
    print(f" 🔑 Token: {token[:8]}...{token[-4:] if len(token) > 12 else ''}")
    print(f" 💻 Hệ điều hành: {sys.platform.upper()}")
    print("=" * 65)

    retry_count = 0
    while True:
        try:
            print(f"\n🔄 Đang kết nối tới Relay Server...")
            async with websockets.connect(full_url, ping_interval=20, ping_timeout=20) as ws:
                retry_count = 0
                print("⚡ [ONLINE] Đã kết nối thành công tới KEN AGENT Hub!\n")

                async for message in ws:
                    try:
                        data = json.loads(message)
                    except Exception:
                        continue

                    msg_type = data.get("type")

                    if msg_type == "INIT_SUCCESS":
                        name = data.get("name", "Khách hàng")
                        code = data.get("pairing_code")
                        paired = data.get("paired_channels", [])

                        print("┌" + "─" * 63 + "┐")
                        print(f"│  👤 Tài khoản: {name:<46} │")
                        if code:
                            print(f"│  👉 MÃ GHÉP ĐÔI CỦA BẠN: [ \033[1;32m{code}\033[0m ]                       │")
                            print("│  📌 Mở Telegram/Zalo và nhắn: /pair " + f"{code:<27} │")
                        else:
                            print(f"│  ✅ Trạng thái: Đã kết nối với {len(paired)} kênh chat.               │")
                            for p in paired:
                                print(f"│     • {p.get('platform').upper()}: {p.get('user_name')} ({p.get('user_channel_id')})")
                        print("└" + "─" * 63 + "┘")

                    elif msg_type == "PAIR_SUCCESS":
                        print(f"\n🎉 [GHÉP ĐÔI THÀNH CÔNG] Đã liên kết với {data.get('platform').upper()}: {data.get('user_name')}!")

                    elif msg_type == "EXECUTE_TASK":
                        task_id = data.get("task_id")
                        platform = data.get("platform")
                        user_channel_id = data.get("user_channel_id")
                        prompt = data.get("prompt")
                        sender = data.get("sender", {})

                        print(f"\n📥 [NHẬN TÁC VỤ] [{platform.upper()}] {sender.get('user_name', 'User')}: {prompt}")

                        output = await handle_agent_task(prompt)
                        print(f"📤 [KẾT QUẢ]: {output[:120]}..." if len(output) > 120 else f"📤 [KẾT QUẢ]: {output}")

                        await ws.send(json.dumps({
                            "type": "TASK_RESPONSE",
                            "task_id": task_id,
                            "platform": platform,
                            "user_channel_id": user_channel_id,
                            "text": output
                        }))

        except websockets.exceptions.InvalidStatusCode as e:
            if e.status_code == 401:
                print("\n❌ Lỗi: Token không hợp lệ hoặc đã hết hạn!")
                print("👉 Vui lòng kiểm tra lại Token tại https://api.haiphongdeveloper.com")
                sys.exit(1)
            print(f"⚠️ Lỗi kết nối HTTP {e.status_code}. Thử lại sau 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            retry_count += 1
            wait_time = min(retry_count * 2, 10)
            print(f"⚠️ Mất kết nối ({str(e)}). Tự động kết nối lại sau {wait_time}s...")
            await asyncio.sleep(wait_time)

def main():
    parser = argparse.ArgumentParser(
        prog="ken-agent",
        description="KEN AGENT CLI - Trợ lý AI tự hành điều khiển máy tính qua Telegram/Zalo"
    )
    subparsers = parser.add_subparsers(dest="action", help="Lệnh thao tác")

    start_parser = subparsers.add_parser("start", help="Khởi động KEN AGENT Runner")
    start_parser.add_argument("--token", "-t", type=str, help="API Token tài khoản của bạn")
    start_parser.add_argument("--server", "-s", type=str, help="URL Relay Server")

    cfg_parser = subparsers.add_parser("config", help="Cấu hình Token hoặc Server URL")
    cfg_parser.add_argument("--token", "-t", type=str, help="Lưu Token tài khoản")
    cfg_parser.add_argument("--server", "-s", type=str, help="Lưu Relay Server URL")
    cfg_parser.add_argument("--show", action="store_true", help="Hiển thị cấu hình hiện tại")

    parser.add_argument("--token", "-t", type=str, help="API Token để chạy nhanh")
    parser.add_argument("--version", "-v", action="version", version="KEN AGENT v2.0.0 (HPD Ecosystem 2026)")

    args = parser.parse_args()
    config = load_config()

    if args.action == "config":
        if args.show:
            print("\n📋 CẤU HÌNH KEN AGENT HIỆN TẠI:")
            print(f"  • File cấu hình : {CONFIG_FILE}")
            print(f"  • Server URL    : {config.get('server_url', DEFAULT_SERVER_URL)}")
            tok = config.get('token', '')
            print(f"  • Token         : {tok[:8]}...{tok[-4:] if len(tok) > 12 else ''}" if tok else "  • Token         : (Chưa cấu hình)")
            return
        if args.token:
            config["token"] = args.token.strip()
        if args.server:
            config["server_url"] = args.server.strip()
        save_config(config)
        return

    token = args.token or getattr(args, "token", None) or config.get("token", "")
    server_url = getattr(args, "server", None) or config.get("server_url", DEFAULT_SERVER_URL)

    if not token or token == "YOUR_CLIENT_TOKEN_HERE":
        print("\n" + "=" * 60)
        print(" ⚡ CHÀO MỪNG BẠN ĐẾN VỚI KEN AGENT")
        print("=" * 60)
        print("👉 Chưa tìm thấy API Token trên máy của bạn.")
        print("📌 Hãy nhập API Token từ https://api.haiphongdeveloper.com để bắt đầu:\n")
        try:
            token_input = input("🔑 Nhập API Token: ").strip()
            if token_input:
                config["token"] = token_input
                save_config(config)
                token = token_input
            else:
                print("❌ Không có Token được nhập. Hủy khởi động.")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Đã thoát.")
            sys.exit(0)

    try:
        asyncio.run(start_relay_loop(token, server_url))
    except KeyboardInterrupt:
        print("\n👋 Đã dừng KEN AGENT.")

if __name__ == "__main__":
    main()
