import os
import asyncio
import time
import re
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from yt_dlp import YoutubeDL
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# .env dosyasını yükle
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
STRING_SESSION = os.getenv("STRING_SESSION")
SOURCE_CHAT = int(os.getenv("SOURCE_CHAT"))
TARGET_CHAT = int(os.getenv("TARGET_CHAT"))

DOWNLOAD_DIR = "downloads"
COOKIE_FILE = "cookies.txt"

app = Client(
    "playlist_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION
)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Ubuntu için basit silme
def remove_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            print(f"[🗑️] Silindi: {path}")
    except Exception as e:
        print(f"[❌] Silinemedi: {path} -> {e}")

def get_video_info(file_path):
    try:
        if not os.path.exists(file_path):
            return 0, 0, 0

        parser = createParser(file_path)
        if not parser:
            return 0, 0, 0

        with parser:
            metadata = extractMetadata(parser)
            if not metadata:
                return 0, 0, 0

            duration = metadata.get("duration").seconds if metadata.has("duration") else 0
            width = metadata.get("width") if metadata.has("width") else 0
            height = metadata.get("height") if metadata.has("height") else 0

            return duration, width, height
    except:
        return 0, 0, 0

async def progress_log(current, total, video_title, start_time):
    now = time.time()
    diff = now - start_time
    if round(diff % 5) == 0 or current == total:
        percentage = (current * 100) / total
        speed = current / (diff + 0.0001)
        print(
            f"📤 [YÜKLENİYOR] {video_title[:30]} | %{percentage:.1f} | {speed/1024:.1f} KB/s",
            end="\r"
        )

async def process_playlist(url):
    extract_opts = {
        "extract_flat": "in_playlist",
        "lazy_playlist": True,
        "quiet": True,
        "no_warnings": True,
        "cookiefile": COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    }

    download_opts = {
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "writethumbnail": True,
        "restrictfilenames": False,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "cookiefile": COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    }

    try:
        loop = asyncio.get_event_loop()

        with YoutubeDL(extract_opts) as ydl:
            print(f"\n🔍 Analiz Ediliyor: {url}")
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            entries = list(info["entries"]) if "entries" in info else [info]
            print(f"✅ {len(entries)} video bulundu.")

        for index, entry in enumerate(entries, 1):
            if not entry:
                continue

            v_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"

            try:
                with YoutubeDL(download_opts) as ydl_dl:
                    print(f"\n📥 [{index}/{len(entries)}] İndiriliyor...")
                    video_info = await loop.run_in_executor(
                        None, lambda: ydl_dl.extract_info(v_url, download=True)
                    )

                    video_path = ydl_dl.prepare_filename(video_info)
                    if not os.path.exists(video_path):
                        video_path = video_path.rsplit(".", 1)[0] + ".mp4"

                    title = video_info.get("title", f"Video_{index}")
                    thumb_path = os.path.splitext(video_path)[0] + ".jpg"

                    if os.path.exists(video_path):
                        duration, width, height = get_video_info(video_path)
                        start_time = time.time()

                        await app.send_video(
                            chat_id=TARGET_CHAT,
                            video=video_path,
                            thumb=thumb_path if os.path.exists(thumb_path) else None,
                            duration=duration,
                            width=width,
                            height=height,
                            caption=title,
                            progress=progress_log,
                            progress_args=(title, start_time)
                        )

                        print(f"\n✅ Yüklendi: {title}")

                        remove_file(video_path)
                        remove_file(thumb_path)

            except FloodWait as e:
                print(f"\n⚠️ FloodWait: {e.value} saniye bekleniyor...")
                await asyncio.sleep(e.value)

            except Exception as e:
                print(f"\n❌ Video Hatası: {e}")

    except Exception as e:
        print(f"\n💥 Kritik Hata: {e}")

@app.on_message(filters.chat(SOURCE_CHAT) & filters.text)
async def listener(client, message):
    yt_regex = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)\S+"
    match = re.search(yt_regex, message.text)
    if match:
        asyncio.create_task(process_playlist(match.group()))

async def main():
    await app.start()
    print("🚀 Bot Ubuntu üzerinde aktif!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
