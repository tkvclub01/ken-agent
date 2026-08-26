# 🚀 KEN AGENT - Trợ Lý AI Tự Hành Điều Khiển Máy Tính Đa Nền Tảng

[![PyPI version](https://img.shields.io/pypi/v/ken-agent.svg?color=emerald)](https://pypi.org/project/ken-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Telegram Bot](https://img.shields.io/badge/Telegram%20Bot-@eto__codex__bot-cyan.svg)](https://t.me/eto_codex_bot)
[![Ecosystem](https://img.shields.io/badge/Hub-api.haiphongdeveloper.com-blueviolet)](https://api.haiphongdeveloper.com)

**KEN AGENT** là nền tảng Trợ lý AI Tự hành (Autonomous Agent) thế hệ mới, cho phép điều khiển máy tính từ xa qua ngôn ngữ tự nhiên tiếng Việt trên **Telegram Bot** (`@eto_codex_bot`), **Zalo OA** và **WhatsApp**. Tích hợp kiến trúc **Hermes Agent** với khả năng **tự thực thi trọn vẹn (Finishing The Job)**, **tự học kỹ năng (Auto-Skills)**, **quản lý đa phiên (Multi-Sessions)** và **ví Lúa tự động**.

---

## 🌟 Điểm Nổi Bật

- 🍎 **macOS Native:** MenuBar Status Item tròn xanh trực quan, LaunchAgent chạy ngầm độc lập với Terminal.
- 🐧 **Linux First-class:** Tối ưu hóa 100% thuần Python cho Debian, Ubuntu, CentOS, Arch, tích hợp `systemd user service`.
- 🪟 **Windows Native:** Chạy ngầm qua `pythonw` không hiện cửa sổ đen CMD, tích hợp System Tray khay Taskbar.
- 🤖 **100% Autonomous (Tự Hành):** Tự động sinh mã, cài đặt gói phụ thuộc, tự chạy ngầm và tạo thành phẩm thực tế (.obj 3D, quét dự án, chỉnh sửa code).
- 🧠 **Hermes Auto-Skill Engine:** Tự động đúc kết quy trình sau mỗi tác vụ thành công và tái sử dụng ở các lần tiếp theo.
- 📂 **Multi-Session Management:** Hỗ trợ lệnh `/new`, `/sessions`, `/resume <id>` chuyển đổi và khôi phục ngữ cảnh tức thì.
- 💰 **Ví Lúa & VietQR Tự Động:** Nạp tiền tự động qua SePay (`/wallet`, `/nap`), cước phí minh bạch pay-as-you-go.

---

## ⚡ Cài Đặt Tự Động 1 Dòng Lệnh (1-Click Installer)

Hệ thống tự động kiểm tra, cài Python (nếu thiếu) và thiết lập ứng dụng chạy ngầm:

### 🍎 Dành cho macOS (Apple Silicon M-Series & Intel)
```bash
curl -sSL https://api.haiphongdeveloper.com/install-macos.sh | bash
```

### 🐧 Dành cho Linux (Debian, Ubuntu, CentOS, Arch)
```bash
curl -sSL https://api.haiphongdeveloper.com/install-linux.sh | bash
```

### 🪟 Dành cho Windows (PowerShell)
```powershell
irm https://api.haiphongdeveloper.com/install.ps1 | iex
```

---

## 📦 Cài Đặt Qua PyPI

Nếu máy tính của bạn đã có sẵn môi trường Python:
```bash
pip install --upgrade ken-agent
```

---

## 🚀 Khởi Chạy & Sử Dụng

### 1. Khởi động Agent
```bash
ken-agent
```
*(Màn hình sẽ hiển thị **Mã Ghép Đôi** ví dụ: `5T8-B4E` kèm link QR kết nối)*

### 2. Ghép đôi trên Telegram
Mở Telegram bot **[@eto_codex_bot](https://t.me/eto_codex_bot)** và gửi:
```text
/pair 5T8-B4E
```

### 3. Cập nhật phiên bản mới nhất
```bash
ken-agent update
```

---

## 📋 Danh Sách Lệnh Quản Trị Trên Telegram

| Lệnh | Mô tả |
| :--- | :--- |
| **`/wallet`** hoặc **`/nap`** | Xem số dư Ví Lúa & nhận mã VietQR nạp tiền tự động |
| **`/sessions`** | Xem danh sách các phiên làm việc và chủ đề gần đây |
| **`/resume <id>`** | Quay lại phiên làm việc cũ để tiếp tục câu chuyện |
| **`/new`** | Mở một phiên làm việc mới toanh |
| **`/skills`** | Xem danh sách các kỹ năng KEN AGENT đã tự học được |

---

## 🛡️ Bản Quyền & Bảo Mật

Phát triển và bảo trợ bởi **HPD Ecosystem (Hải Phòng Developer)**  
Website: [https://api.haiphongdeveloper.com](https://api.haiphongdeveloper.com)
