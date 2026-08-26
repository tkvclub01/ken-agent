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
CURRENT_VERSION = "2.1.0"

def check_for_updates():
    """Kiểm tra phiên bản mới nhất từ PyPI trong nền và thông báo"""
    try:
        import urllib.request
        req = urllib.request.Request("https://pypi.org/pypi/ken-agent/json", headers={"User-Agent": "ken-agent-cli"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("info", {}).get("version")
            if latest and latest != CURRENT_VERSION:
                print("\n" + "!" * 68)
                print(f" 🚀 ĐÃ CÓ BẢN CẬP NHẬT MỚI: v{latest} (Phiên bản của bạn: v{CURRENT_VERSION})")
                print(" 👉 Hãy gõ lệnh sau để nâng cấp ngay:")
                print("    \033[1;32mken-agent update\033[0m")
                print("!" * 68 + "\n")
    except Exception:
        pass

def perform_update():
    """Thực hiện cập nhật ken-agent lên phiên bản mới nhất"""
    print("\n" + "=" * 60)
    print(" ⚡ ĐANG CẬP NHẬT KEN AGENT...")
    print("=" * 60)
    try:
        venv_pip = os.path.expanduser("~/.ken-agent/venv/bin/pip")
        if sys.platform == "win32":
            venv_pip = os.path.expanduser("~/.ken-agent/venv/Scripts/pip.exe")

        pip_cmd = venv_pip if os.path.exists(venv_pip) else f'"{sys.executable}" -m pip'
        cmd = f'{pip_cmd} install --upgrade ken-agent'
        print(f"📦 Đang tải và cài đặt bản mới nhất từ PyPI...")
        subprocess.check_call(cmd, shell=True)
        print("\n🎉 CẬP NHẬT THÀNH CÔNG! Hãy khởi chạy lại: ken-agent\n")
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
    check_for_updates()
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

                        print("┌" + "─" * 78 + "┐")
                        print(f"│  👤 Tài khoản: {name:<61} │")
                        if code:
                            tele_link = f"https://t.me/eto_otp_bot?start=pair_{code}"
                            zalo_link = "https://zalo.me/717382562076019145"

                            print(f"│  👉 MÃ GHÉP ĐÔI CỦA BẠN: [ \033[1;32m{code}\033[0m ]                                              │")
                            print("├" + "─" * 78 + "┤")
                            print("│  📲 QUÉT MÃ QR BẰNG CAMERA ĐIỆN THOẠI ĐỂ KẾT NỐI TỰ ĐỘNG:                   │")
                            print("└" + "─" * 78 + "┘")

                            # Tải và hiển thị lần lượt từng mã QR (Dọc) để chống dính và điện thoại quét dễ nhất
                            try:
                                import urllib.request
                                def print_single_qr(title, url, note):
                                    req = urllib.request.Request(f"https://qrenco.de/{url}", headers={"User-Agent": "curl/7.68.0"})
                                    with urllib.request.urlopen(req, timeout=3) as resp:
                                        lines = resp.read().decode("utf-8").strip().split("\n")
                                        print(f"\n   {title}")
                                        print(f"   {note}")
                                        for line in lines:
                                            print("   " + line)
                                        print()

                                print_single_qr(
                                    "\033[1;36m[ 📱 MÃ QR 1: TELEGRAM BOT (1-Click Ghép Đôi) ]\033[0m",
                                    tele_link,
                                    f"👉 Quét bằng Camera để tự động kết nối với @eto_otp_bot"
                                )

                                print_single_qr(
                                    "\033[1;34m[ 💬 MÃ QR 2: ZALO BOT KEN AI EDU ]\033[0m",
                                    zalo_link,
                                    f"👉 Quét bằng App Zalo và gửi cú pháp: /pair {code}"
                                )
                            except Exception:
                                pass

                            print("┌" + "─" * 78 + "┐")
                            print("│  💬 HOẶC KẾT NỐI BẰNG ĐƯỜNG LINK & CÚ PHÁP:                                │")
                            print(f"│  • Telegram : \033[1;36m{tele_link}\033[0m (1-Click Tự Ghép Đôi) │")
                            print(f"│  • Zalo Bot : \033[1;34m{zalo_link}\033[0m ➔ Gửi tin nhắn: \033[1;33m/pair {code}\033[0m            │")
                            print(f"│  • WhatsApp : Gửi tin nhắn: \033[1;33m/pair {code}\033[0m tới Hotline hỗ trợ                 │")
                        else:
                            print(f"│  ✅ Trạng thái: Đã kết nối với {len(paired)} kênh chat.                              │")
                            for p in paired:
                                print(f"│     • {p.get('platform').upper()}: {p.get('user_name')} ({p.get('user_channel_id')})")
                        print("└" + "─" * 78 + "┘\n")

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
        description="🚀 KEN AGENT CLI - Trợ lý AI tự hành điều khiển máy tính qua Telegram & Zalo (HPD Ecosystem)",
        epilog="""Ví dụ sử dụng:
  ken-agent                          Khởi chạy nhanh (sử dụng Token đã lưu hoặc hỏi nhập Token)
  ken-agent -t eto_tk_xxx            Khởi chạy trực tiếp với API Token
  ken-agent update                   Cập nhật KEN AGENT lên phiên bản mới nhất
  ken-agent config -t eto_tk_xxx     Lưu vĩnh viễn API Token vào máy
  ken-agent config --show            Xem cấu hình hiện tại
  ken-agent uninstall                Gỡ cài đặt hoàn toàn KEN AGENT khỏi máy
  ken-agent -v                       Xem phiên bản hiện tại

Kênh hỗ trợ & Ghép đôi:
  • Telegram Bot : https://t.me/eto_otp_bot
  • Zalo Bot     : https://zalo.me/717382562076019145
  • Dashboard    : https://api.haiphongdeveloper.com
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="action", help="Lệnh thao tác bổ sung")

    start_parser = subparsers.add_parser("start", help="Khởi động KEN AGENT Runner")
    start_parser.add_argument("--token", "-t", type=str, help="API Token tài khoản của bạn")
    start_parser.add_argument("--server", "-s", type=str, help="URL Relay Server")

    subparsers.add_parser("update", help="Cập nhật KEN AGENT lên phiên bản mới nhất từ PyPI")

    cfg_parser = subparsers.add_parser("config", help="Cấu hình Token hoặc Server URL")
    cfg_parser.add_argument("--token", "-t", type=str, help="Lưu API Token tài khoản vào máy")
    cfg_parser.add_argument("--server", "-s", type=str, help="Lưu Relay Server URL")
    cfg_parser.add_argument("--show", action="store_true", help="Hiển thị cấu hình và Token hiện tại")

    uninst_parser = subparsers.add_parser("uninstall", help="Gỡ cài đặt và dọn dẹp sạch sẽ KEN AGENT")
    uninst_parser.add_argument("-y", "--yes", action="store_true", help="Tự động đồng ý gỡ cài đặt mà không cần xác nhận")

    parser.add_argument("--token", "-t", type=str, help="API Token để khởi chạy ngay")
    parser.add_argument("--version", "-v", action="version", version=f"KEN AGENT v{CURRENT_VERSION} (HPD Ecosystem 2026)")

    args = parser.parse_args()
    config = load_config()

    if args.action == "update":
        perform_update()
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
        print("Cảm ơn bạn đã sử dụng dịch vụ của https://api.haiphongdeveloper.com\n")
        return

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
