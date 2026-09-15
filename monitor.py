import os
import json
import subprocess
import html
import time
import urllib.request

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

CHANNELS_FILE = "channels.json"
SEEN_FILE = "seen_videos.json"

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID!")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "GitHubActions-Monitor/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True
    except Exception as e:
        print(f"[ERROR] Lỗi gửi Telegram: {e}")
        return False

def get_latest_video(channel_url):
    """Lấy 1 video mới nhất từ kênh bằng yt-dlp"""
    cmd = [
        'yt-dlp',
        '--flat-playlist',
        '--playlist-end', '1',
        '--print', '%(id)s|%(title)s|%(url)s',
        '--compat-options', 'no-youtube-unavailable-videos',
        channel_url
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
        if p.returncode == 0:
            for line in p.stdout.splitlines():
                line = line.strip()
                if '|' in line and line.count('|') >= 2:
                    parts = line.split('|', 2)
                    v_id = parts[0].strip()
                    v_title = parts[1].strip()
                    v_url = parts[2].strip()
                    if not v_url.startswith("http"):
                        v_url = f"https://www.youtube.com/watch?v={v_id}"
                    return {"id": v_id, "title": v_title, "url": v_url}
        else:
            print(f"[WARN] yt-dlp trả về mã lỗi: {p.returncode}. Stderr: {p.stderr.strip()[:100]}")
    except Exception as e:
        print(f"[ERROR] Lỗi quét {channel_url}: {e}")
    return None

def main():
    print(f"=== BẮT ĐẦU QUÉT YOUTUBE ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    if not os.path.exists(CHANNELS_FILE):
        print(f"[ERROR] Không tìm thấy file {CHANNELS_FILE}!")
        return

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        channels = json.load(f)

    seen_data = {}
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                seen_data = json.load(f)
        except Exception:
            seen_data = {}

    changes_made = False

    for ch in channels:
        name = ch.get("name", "Kênh YouTube")
        url = ch.get("url")

        if not url:
            continue

        print(f"[*] Đang quét kênh: {name} ({url})...")
        video = get_latest_video(url)
        if not video:
            print(f"[WARN] Không lấy được video của {name}")
            continue

        v_id = video["id"]
        v_title = video["title"]
        v_url = video["url"]

        seen_list = seen_data.get(url, [])

        # Lần đầu tiên thêm kênh: Lưu mốc video hiện tại, không spam thông báo
        if not seen_list:
            print(f"[INIT] Kênh mới '{name}': Ghi nhận video mốc '{v_title}' (ID: {v_id}).")
            seen_data[url] = [v_id]
            changes_made = True
            continue

        # Nếu video mới nhất chưa có trong danh sách đã xem -> Có video mới!
        if v_id not in seen_list:
            print(f"[FOUND] Phát hiện video mới từ '{name}': {v_title}")
            safe_title = html.escape(v_title)
            safe_name = html.escape(name)

            msg = (
                f"🔔 <b>[YOUTUBE MONITOR] PHÁT HIỆN VIDEO MỚI!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📺 <b>Kênh:</b> {safe_name}\n"
                f"🎬 <b>Tiêu đề:</b> {safe_title}\n"
                f"🔗 <b>Xem video:</b> <a href=\"{v_url}\">{v_url}</a>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )

            print(f"[NOTIFY] Đang gửi Telegram...")
            if send_telegram(msg):
                print(" -> Gửi thành công!")
            else:
                print(" -> Gửi thất bại!")

            seen_data[url].append(v_id)
            changes_made = True
            time.sleep(1)
        else:
            print(f"[OK] '{name}' chưa có video mới.")

    if changes_made:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_data, f, ensure_ascii=False, indent=2)

    print("=== HOÀN TẤT CHU KỲ QUÉT ===")

if __name__ == "__main__":
    main()
