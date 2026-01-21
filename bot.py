import os
import asyncio
import time
import re
import gc
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

DOWNLOAD_DIR = os.path.abspath("downloads")
COOKIE_FILE = os.path.abspath("cookies.txt")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Client(
    "playlist_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION
)

def remove_file_with_retry(path, retries=5, delay=2):
    if not path or not os.path.exists(path):
        return True

    for _ in range(retries):
        try:
            os.remove(path)
            print(f"[SILINDI] {path}")
            return True
        except PermissionError:
            gc.collect()
            time.sleep(delay)
        except Exception:
            break
    return False

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
    except Exception:
        return 0, 0, 0

async def progress_log(current, total, video_title, start_time):
    now = time.time()
    diff = now - start_time

    if total == 0:
        return

    if int(diff) % 5 == 0 or current == total:
        percent = (current * 100) / total
        speed = current / (diff + 0.001)
        print(
            f"[YUKLENIYOR] {video_title[:30]} "
            f"%{percent:.1f} - {speed / 1024:.1f} KB/s",
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
        "format": (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=720][ext=mp4]/best"
        ),
        "merge_output_format": "mp4",
        "writethumbnail": True,
        "restrictfilenames": False,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg"}
        ],
        "quiet": True,
        "no_warnings": True,
        "cookiefile": COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
    }

    loop = asyncio.get_running_loop()

    try:
        with YoutubeDL(extract_opts) as ydl:
            print(f"\nANALIZ: {url}")
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=False)
            )

        entries = list(info.get("entries", [info]))
        total_videos = len(entries)
        print(f"BULUNAN VIDEO: {total_videos}")

        for index, entry in enumerate(entries, 1):
            if not entry:
                continue

            video_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"

            try:
                with YoutubeDL(download_opts) as ydl_dl:
                    print(f"\n[{index}/{total_videos}] INDIRILIYOR")
                    video_info = await loop.run_in_executor(
                        None, lambda: ydl_dl.extract_info(video_url, download=True)
                    )

                video_path = ydl_dl.prepare_filename(video_info)
                if not os.path.exists(video_path):
                    video_path = os.path.splitext(video_path)[0] + ".mp4"

                title = video_info.get("title", f"Video_{index}")
                thumb_path = os.path.splitext(video_path)[0] + ".jpg"

                if not os.path.exists(video_path):
                    continue

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
                    progress_args=(title, start_time),
                )

                print(f"TAMAMLANDI: {title}")

                remove_file_with_retry(video_path)
                remove_file_with_retry(thumb_path)

            except FloodWait as e:
                print(f"FLOODWAIT: {e.value} saniye")
                await asyncio.sleep(e.value)

            except Exception as e:
                print(f"HATA: {e}")

    except Exception as e:
        print(f"KRITIK HATA: {e}")

@app.on_message(filters.chat(SOURCE_CHAT) & filters.text)
async def listener(_, message):
    yt_regex = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)\S+"
    match = re.search(yt_regex, message.text)
    if match:
        asyncio.create_task(process_playlist(match.group()))

async def main():
    await app.start()
    print("BOT AKTIF")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
