import os
import asyncio
import time
import re
import subprocess
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from yt_dlp import YoutubeDL
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# ================= ENV =================
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
SOURCE_CHAT = int(os.getenv("SOURCE_CHAT"))
TARGET_CHAT = int(os.getenv("TARGET_CHAT"))

DOWNLOAD_DIR = "downloads"
COOKIE_FILE = "cookies.txt"

# ================= APP =================
app = Client(
    "playlist_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION
)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= UTILS =================
def remove_file(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass

def get_video_info(path):
    try:
        parser = createParser(path)
        with parser:
            meta = extractMetadata(parser)
            duration = meta.get("duration").seconds if meta.has("duration") else 0
            width = meta.get("width") if meta.has("width") else 0
            height = meta.get("height") if meta.has("height") else 0
            return duration, width, height
    except:
        return 0, 0, 0

def prepare_telegram_thumb(input_thumb):
    if not input_thumb or not os.path.exists(input_thumb):
        return None

    output = "tg_thumb.jpg"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_thumb,
        "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
        "-frames:v", "1",
        "-q:v", "2",
        output
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(output) and os.path.getsize(output) <= 200 * 1024:
        return output
    return None

async def progress_log(current, total, title, start):
    diff = time.time() - start
    if round(diff % 5) == 0 or current == total:
        percent = current * 100 / total
        speed = current / (diff + 0.001)
        print(f"📤 {title[:30]} %{percent:.1f} {speed/1024:.1f} KB/s", end="\r")

# ================= CORE =================
async def process_playlist(url):
    extract_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "cookiefile": COOKIE_FILE,
    }

    download_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"}
        ],
        "cookiefile": COOKIE_FILE,
        "quiet": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
    }

    loop = asyncio.get_event_loop()

    with YoutubeDL(extract_opts) as ydl:
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
        entries = list(info["entries"]) if "entries" in info else [info]

    for i, entry in enumerate(entries, 1):
        if not entry:
            continue

        v_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"

        try:
            with YoutubeDL(download_opts) as ydl:
                print(f"\n📥 [{i}/{len(entries)}] İndiriliyor")
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(v_url, download=True))
                video_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp4"

            title = info.get("title", f"Video_{i}")

            thumb_candidates = [
                os.path.splitext(video_path)[0] + ".jpg",
                os.path.splitext(video_path)[0] + ".webp",
                os.path.splitext(video_path)[0] + ".png",
            ]

            raw_thumb = next((t for t in thumb_candidates if os.path.exists(t)), None)
            tg_thumb = prepare_telegram_thumb(raw_thumb)

            duration, width, height = get_video_info(video_path)
            start = time.time()

            await app.send_video(
                chat_id=TARGET_CHAT,
                video=video_path,
                thumb=tg_thumb,
                caption=title,
                duration=duration,
                width=width,
                height=height,
                progress=progress_log,
                progress_args=(title, start)
            )

            print(f"\n✅ Yüklendi: {title}")

            remove_file(video_path)
            remove_file(raw_thumb)
            remove_file(tg_thumb)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"\n❌ Video Hatası: {e}")

# ================= LISTENER =================
@app.on_message(filters.chat(SOURCE_CHAT) & filters.text)
async def listener(_, message):
    yt = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)\S+"
    m = re.search(yt, message.text)
    if m:
        asyncio.create_task(process_playlist(m.group()))

# ================= MAIN =================
async def main():
    await app.start()
    print("🚀 Bot aktif")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
