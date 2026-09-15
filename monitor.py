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

def get_channel_videos(channel_url, max_per_tab=3):
    """Quét cả tab Shorts và Videos để không bao giờ bỏ sót video hoặc short mới"""
    clean_url = channel_url.rstrip('/')
    urls_to_scan = []

    if clean_url.endswith('/shorts') or clean_url.endswith('/videos'):
        urls_to_scan.append(clean_url)
    else:
        # YouTube phân tách Shorts và Video dài ở 2 tab riêng biệt
        urls_to_scan.append(f"{clean_url}/shorts")
        urls_to_scan.append(f"{clean_url}/videos")

    found_videos = []
    seen_ids = set()

    for target_url in urls_to_scan:
        cmd = [
            'yt-dlp',
            '--flat-playlist',
            '--playlist-end', str(max_per_tab),
            '--print', '%(id)s|%(title)s|%(url)s',
            '--compat-options', 'no-youtube-unavailable-videos',
            target_url
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40)
            if p.returncode == 0:
                for line in p.stdout.splitlines():
                    line = line.strip()
                    if '|' in line and line.count('|') >= 2:
                        parts = line.split('|', 2)
                        v_id = parts[0].strip()
                        v_title = parts[1].strip()
                        v_url = parts[2].strip()

                        if v_id and len(v_id) > 2 and "WARNING" not in v_id and v_id not in seen_ids:
                            seen_ids.add(v_id)
                            if not v_url.startswith("http"):
                                if "/shorts" in target_url:
                                    v_url = f"https://www.youtube.com/shorts/{v_id}"
                                else:
                                    v_url = f"https://www.youtube.com/watch?v={v_id}"
                            found_videos.append({
                                "id": v_id,
                                "title": v_title,
                                "url": v_url,
                                "is_short": ("/shorts" in target_url or "/shorts/" in v_url)
                            })
        except Exception as e:
            print(f"[ERROR] Lỗi quét URL {target_url}: {e}")

    return found_videos

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
        videos = get_channel_videos(url, max_per_tab=3)
        if not videos:
            print(f"[WARN] Không lấy được video nào từ {name}")
            continue

        seen_list = seen_data.get(url, [])

        # Lần đầu tiên theo dõi kênh: Ghi nhận các video hiện tại để làm mốc, không báo dồn dập
        if not seen_list:
            top_ids = [v["id"] for v in videos]
            print(f"[INIT] Kênh mới '{name}': Ghi nhận {len(top_ids)} video làm mốc ban đầu.")
            seen_data[url] = top_ids
            changes_made = True
            continue

        # Kiểm tra xem có video / short mới nào không
        new_videos_found = []
        for v in videos:
            if v["id"] not in seen_list:
                new_videos_found.append(v)

        if new_videos_found:
            for v in reversed(new_videos_found): # Gửi từ cũ hơn đến mới nhất
                v_id = v["id"]
                v_title = v["title"]
                v_url = v["url"]
                tag = "🎬 [SHORTS MỚI]" if v["is_short"] else "📹 [VIDEO MỚI]"

                print(f"[FOUND] Phát hiện {tag} từ '{name}': {v_title}")
                safe_title = html.escape(v_title)
                safe_name = html.escape(name)

                msg = (
                    f"🔔 <b>{tag}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📺 <b>Kênh:</b> {safe_name}\n"
                    f"📝 <b>Tiêu đề:</b> {safe_title}\n"
                    f"🔗 <b>Xem ngay:</b> <a href=\"{v_url}\">{v_url}</a>\n"
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
            print(f"[OK] '{name}' chưa có video hay Shorts mới.")

    if changes_made:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_data, f, ensure_ascii=False, indent=2)

    print("=== HOÀN TẤT CHU KỲ QUÉT ===")

if __name__ == "__main__":
    main()
