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
CURRENT_VERSION = "2.3.18"

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

async def handle_agent_task(prompt, ai_plan=None):
    prompt_strip = prompt.strip()
    
    # 1. Nếu Hub đã có AI Planner phân tích sẵn
    if ai_plan and isinstance(ai_plan, dict):
        plan_type = ai_plan.get("type")
        cmd = ai_plan.get("command", "")
        reply = ai_plan.get("friendly_reply", "")
        
        if plan_type == "open" and cmd:
            if sys.platform == "darwin":
                await run_command_on_system(f"open -a '{cmd}'")
            elif sys.platform == "win32":
                await run_command_on_system(f"Start-Process '{cmd}'")
            else:
                await run_command_on_system(f"xdg-open '{cmd}' &")
            return reply if reply else f"✅ Đã mở ứng dụng {cmd}."

        if plan_type == "notify" and cmd:
            if sys.platform == "darwin":
                await run_command_on_system(f'osascript -e \'display notification "{cmd}" with title "KEN AGENT"\'')
            elif sys.platform == "win32":
                await run_command_on_system(f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms"); [Windows.Forms.MessageBox]::Show("{cmd}", "KEN AGENT")')
            else:
                await run_command_on_system(f'notify-send "KEN AGENT" "{cmd}"')
            return reply if reply else f"✅ Đã gửi thông báo: {cmd}"

        if plan_type == "dialog" and cmd:
            if sys.platform == "darwin":
                await run_command_on_system(f'osascript -e \'display dialog "{cmd}" with title "KEN AGENT"\'')
            elif sys.platform == "win32":
                await run_command_on_system(f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms"); [Windows.Forms.MessageBox]::Show("{cmd}", "KEN AGENT")')
            return reply if reply else f"✅ Đã hiện hộp thoại: {cmd}"

        if plan_type == "shell" and cmd:
            res = await run_command_on_system(cmd)
            return f"💻 Kết quả thực thi:\n```\n{res}\n```"

    prompt_lower = prompt_strip.lower()

    # 2. Xử lý câu chào hỏi tự nhiên
    if prompt_lower in ["alo", "alo ken", "hi", "hello", "xin chào", "ken ơi", "hey"]:
        uname = "macOS" if sys.platform == "darwin" else ("Windows" if sys.platform == "win32" else "Linux")
        return f"👋 Chào bạn! KEN AGENT đang sẵn sàng trên thiết bị ({uname}).\nBạn cứ ra lệnh bằng tiếng Việt tự nhiên nhé (Ví dụ: 'mở Safari', 'hiện thông báo chào mừng', 'xem dung lượng ổ cứng'...)!"

    # 3. Lệnh mở ứng dụng tiếng Việt tự nhiên
    if sys.platform == "darwin" and (prompt_lower.startswith("mở ") or prompt_lower.startswith("mo ") or prompt_lower.startswith("bật ")):
        app = prompt_strip.split(" ", 1)[1].strip()
        await run_command_on_system(f"open -a '{app}'")
        return f"✅ Đang mở ứng dụng {app} trên Mac của bạn."

    # 4. Mặc định chạy lệnh hệ thống
    return await run_command_on_system(prompt_strip)

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
            async with websockets.connect(full_url) as ws:
                retry_count = 0
                print("⚡ [ONLINE] Đã kết nối thành công tới KEN AGENT Hub!\n")

                # Chạy task heartbeat ngầm giữ kết nối
                hb_task = asyncio.create_task(send_heartbeat_loop(ws))

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
                            tele_link = f"https://t.me/eto_codex_bot?start=pair_{code}"

                            print(f"│  👉 MÃ GHÉP ĐÔI CỦA BẠN: [ \033[1;32m{code}\033[0m ]                                              │")
                            print("├" + "─" * 78 + "┤")
                            print("│  📲 QUÉT MÃ QR DƯỚI ĐÂY BẰNG CAMERA ĐIỆN THOẠI ĐỂ GHÉP ĐÔI TỰ ĐỘNG:          │")
                            print("└" + "─" * 78 + "┘")

                            # Tải và hiển thị mã QR Telegram duy nhất siêu nét
                            try:
                                import urllib.request
                                req = urllib.request.Request(f"https://qrenco.de/{tele_link}", headers={"User-Agent": "curl/7.68.0"})
                                with urllib.request.urlopen(req, timeout=3) as resp:
                                    lines = resp.read().decode("utf-8").strip().split("\n")
                                    print("\n   \033[1;36m[ 📱 TELEGRAM BOT (1-Click Tự Động Kết Nối) ]\033[0m")
                                    print(f"   👉 Quét mã bằng Camera điện thoại để mở bot @eto_codex_bot:")
                                    for line in lines:
                                        print("   " + line)
                                    print()
                            except Exception:
                                pass

                            print("┌" + "─" * 78 + "┐")
                            print("│  💬 HOẶC BẤM ĐƯỜNG LINK TRỰC TIẾP ĐỂ GHÉP ĐÔI:                             │")
                            print(f"│  • Telegram : \033[1;36m{tele_link}\033[0m │")
                            print(f"│  • Cú pháp  : Gửi tin nhắn \033[1;33m/start pair_{code}\033[0m vào Telegram Bot                 │")
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
                        ai_plan = data.get("ai_plan")
                        sender = data.get("sender", {})

                        print(f"\n📥 [NHẬN TÁC VỤ] [{platform.upper()}] {sender.get('user_name', 'User')}: {prompt}")

                        output = await handle_agent_task(prompt, ai_plan=ai_plan)
                        print(f"📤 [KẾT QUẢ]: {output[:120]}..." if len(output) > 120 else f"📤 [KẾT QUẢ]: {output}")

                        await ws.send(json.dumps({
                            "type": "TASK_RESPONSE",
                            "task_id": task_id,
                            "platform": platform,
                            "user_channel_id": user_channel_id,
                            "prompt": prompt,
                            "ai_plan": ai_plan,
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

def run_macos_native_statusbar(token, server_url):
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
            def openBot_(self, sender):
                webbrowser.open("https://t.me/eto_codex_bot")
            def openDash_(self, sender):
                webbrowser.open("https://api.haiphongdeveloper.com")
            def quitApp_(self, sender):
                os._exit(0)

        delegate = MenuDelegate.alloc().init()
        _global_delegate = delegate

        item_bot = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("📱 Mở Telegram Bot (@eto_codex_bot)", "openBot:", "")
        item_bot.setTarget_(delegate)
        menu.addItem_(item_bot)

        item_dash = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("🌐 Quản lý Ví Lúa & Token", "openDash:", "")
        item_dash.setTarget_(delegate)
        menu.addItem_(item_dash)

        menu.addItem_(NSMenuItem.separatorItem())

        item_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("❌ Thoát KEN AGENT", "quitApp:", "")
        item_quit.setTarget_(delegate)
        menu.addItem_(item_quit)

        status_item.setMenu_(menu)

        # Chạy WSS Relay Loop trong luồng nền
        def relay_worker():
            asyncio.run(start_relay_loop(token, server_url))

        t = threading.Thread(target=relay_worker, daemon=True)
        t.start()

        print("⚡ [MENUBAR] Đã kích hoạt biểu tượng '🟢 KEN AGENT' trên thanh MenuBar macOS.")
        app.run()
    except Exception as e:
        print(f"⚠️ Lỗi khởi chạy Native MenuBar ({e}). Chuyển sang chạy nền...")
        asyncio.run(start_relay_loop(token, server_url))

def run_linux_appindicator_tray(token, server_url):
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

        # Tự động nạp Icon Robot Ken siêu nét vào hicolor icon theme
        icon_name = "ken-agent"
        theme_path = os.path.expanduser("~/.local/share/icons/hicolor")

        indicator = appindicator.Indicator.new_with_path(
            "ken_agent_indicator",
            "ken-agent",
            appindicator.IndicatorCategory.APPLICATION_STATUS,
            os.path.join(theme_path, "48x48/apps")
        )
        indicator.set_icon_theme_path(os.path.join(theme_path, "48x48/apps"))
        indicator.set_icon_full("ken-agent", "KEN AGENT")
        indicator.set_status(appindicator.IndicatorStatus.ACTIVE)

        menu = Gtk.Menu()

        item_status = Gtk.MenuItem(label="⚡ KEN AGENT: Đang chạy ngầm")
        item_status.set_sensitive(False)
        menu.append(item_status)

        item_bot = Gtk.MenuItem(label="📱 Mở Telegram Bot (@eto_codex_bot)")
        item_bot.connect("activate", lambda w: webbrowser.open("https://t.me/eto_codex_bot"))
        menu.append(item_bot)

        item_dash = Gtk.MenuItem(label="🌐 Quản lý Ví Lúa & Token")
        item_dash.connect("activate", lambda w: webbrowser.open("https://api.haiphongdeveloper.com"))
        menu.append(item_dash)

        item_sep = Gtk.SeparatorMenuItem()
        menu.append(item_sep)

        item_quit = Gtk.MenuItem(label="❌ Thoát KEN AGENT")
        item_quit.connect("activate", lambda w: os._exit(0))
        menu.append(item_quit)

        menu.show_all()
        indicator.set_menu(menu)

        print("⚡ [TRAY] Đã kích hoạt biểu tượng KEN AGENT trên thanh Taskbar/System Tray Linux.")

        # Chạy WSS Relay Loop trong luồng nền
        def relay_worker():
            asyncio.run(start_relay_loop(token, server_url))

        t = threading.Thread(target=relay_worker, daemon=True)
        t.start()

        # Chạy GTK Main Loop trên main thread
        Gtk.main()
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo AppIndicator ({e}). Chuyển sang chạy nền...")
        asyncio.run(start_relay_loop(token, server_url))

def run_tray_icon(token, server_url):
    """Chạy System Tray Icon đa nền tảng: macOS (Cocoa Native), Linux & Windows (Pystray Native Menu)"""
    if sys.platform == "darwin":
        run_macos_native_statusbar(token, server_url)
        return

    # Windows & Linux: Sử dụng pystray với cơ chế native menu tương tác 100% khi click chuột
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

        def on_quit(icon, item):
            icon.stop()
            os._exit(0)

        def on_open_dashboard(icon, item):
            webbrowser.open("https://api.haiphongdeveloper.com")

        def on_open_bot(icon, item):
            webbrowser.open("https://t.me/eto_codex_bot")

        # Cấu hình Menu tương tác đầy đủ với Default Action khi click đúp / click chuột trái
        menu = pystray.Menu(
            pystray.MenuItem("⚡ KEN AGENT: Đang Online", None, enabled=False),
            pystray.MenuItem("📱 Mở Telegram Bot (@eto_codex_bot)", on_open_bot, default=True),
            pystray.MenuItem("🌐 Quản lý Ví Lúa & Token", on_open_dashboard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Thoát KEN AGENT", on_quit)
        )

        icon = pystray.Icon("ken_agent", icon_img, "KEN AGENT - AI Runner (HPD)", menu)

        print("⚡ [TRAY] Đã kích hoạt biểu tượng Robot KEN AGENT trên khay hệ thống (System Tray).")

        # Chạy WSS Relay Loop trong luồng nền
        def relay_worker():
            asyncio.run(start_relay_loop(token, server_url))

        t = threading.Thread(target=relay_worker, daemon=True)
        t.start()

        # Chạy EventLoop của System Tray trên Main Thread
        icon.run()
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo System Tray ({e}). Chuyển sang chạy nền...")
        asyncio.run(start_relay_loop(token, server_url))

def main():
    parser = argparse.ArgumentParser(
        prog="ken-agent",
        description="🚀 KEN AGENT CLI - Trợ lý AI tự hành điều khiển máy tính qua Telegram (HPD Ecosystem)",
        epilog="""Ví dụ sử dụng:
  ken-agent                          Khởi chạy nhanh (sử dụng Token đã lưu hoặc hỏi nhập Token)
  ken-agent -t eto_tk_xxx            Khởi chạy trực tiếp với API Token
  ken-agent update                   Cập nhật KEN AGENT lên phiên bản mới nhất
  ken-agent config -t eto_tk_xxx     Lưu vĩnh viễn API Token vào máy
  ken-agent config --show            Xem cấu hình hiện tại
  ken-agent uninstall                Gỡ cài đặt hoàn toàn KEN AGENT khỏi máy
  ken-agent -v                       Xem phiên bản hiện tại

Kênh điều khiển & Ghép đôi:
  • Telegram Bot : https://t.me/eto_codex_bot (1-Click Tự Động Kết Nối)
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

    is_cli = getattr(args, "cli", False)
    # Nếu chỉ định --cli hoặc môi trường không có UI/Desktop (SSH / Headless Linux server)
    if is_cli or os.environ.get("SSH_TTY") or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")):
        try:
            asyncio.run(start_relay_loop(token, server_url))
        except KeyboardInterrupt:
            print("\n👋 Đã dừng KEN AGENT.")
    else:
        # Mặc định khởi chạy Tray Icon trên thanh MenuBar macOS hoặc Taskbar Windows / Linux
        try:
            run_tray_icon(token, server_url)
        except Exception:
            asyncio.run(start_relay_loop(token, server_url))

if __name__ == "__main__":
    main()
