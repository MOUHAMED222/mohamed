# Colored by • 𝗠َِ𝗢َِ𝗛َِ𝗔َ | مــــووحــــا • (@mouhamed_ma)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تحميل الوسائط المتعددة – نسخة متطورة
- دعم Instagram Stories/Audio مع رسائل واضحة
- معالجة حجم الملفات
- جميع النصوص داخل blockquote
- أزرار مع إيموجي وتنسيق
"""
# ==========================================
# AUTO INSTALL + UPDATE EVERY 24 HOURS
# ==========================================

import sys
import subprocess
import os
import time


REQUIRED_PACKAGES = [
    "requests",
    "beautifulsoup4",
    "instaloader",
    "yt-dlp",
    "user-agent",
    "python-telegram-bot",
]

UPDATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".last_pip_update"
)


def install_and_update_packages():
    now = time.time()

    # تحديث مرة كل 24 ساعة
    if os.path.exists(UPDATE_FILE):
        try:
            last_update = float(
                open(UPDATE_FILE, "r").read().strip()
            )

            if now - last_update < 86400:
                return

        except Exception:
            pass

    print("🔄 Checking and updating Python packages...")

    for package in REQUIRED_PACKAGES:
        try:
            subprocess.check_call([
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                package,
                "--disable-pip-version-check",
            ])

            print(f"✅ {package}")

        except Exception as e:
            print(f"⚠️ Failed: {package} -> {e}")

    try:
        with open(UPDATE_FILE, "w") as f:
            f.write(str(now))
    except Exception:
        pass


install_and_update_packages()
# =============================================================================
# IMPORTS
# =============================================================================
import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional, List, Tuple

import requests
from bs4 import BeautifulSoup
import instaloader
import yt_dlp
from user_agent import generate_user_agent

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =============================================================================
# CONFIGURATION
# =============================================================================
TOKEN = "8942390497:AAFe2_cf4tg60NiZsbwZWptNDsBKLsCmRsg"
ADMIN_IDS = [6891530912]

CHANNEL_USERNAME = "@forzd9"
CHANNEL_USERNAME2 = "@Illegal_tools"

WELCOME_IMAGE = "https://c.top4top.io/p_38755a71h0.jpg"

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DB_NAME = "bot_database.db"
YOUTUBE_SEARCH_COUNT = 5
RETRY_LIMIT = 2
RETRY_DELAY = 1
MAX_FILE_SIZE_MB = 300

# =============================================================================
# قائمة أسماء السور
# =============================================================================
SURAH_NAMES = {
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة", "الأنعام", "الأعراف",
    "الأنفال", "التوبة", "يونس", "هود", "يوسف", "الرعد", "إبراهيم", "الحجر",
    "النحل", "الإسراء", "الكهف", "مريم", "طه", "الأنبياء", "الحج", "المؤمنون",
    "النور", "الفرقان", "الشعراء", "النمل", "القصص", "العنكبوت", "الروم",
    "لقمان", "السجدة", "الأحزاب", "سبأ", "فاطر", "يس", "الصافات", "ص",
    "الزمر", "غافر", "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية",
    "الأحقاف", "محمد", "الفتح", "الحجرات", "ق", "الذاريات", "الطور",
    "النجم", "القمر", "الرحمن", "الواقعة", "الحديد", "المجادلة", "الحشر",
    "الممتحنة", "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق",
    "التحريم", "الملك", "القلم", "الحاقة", "المعارج", "نوح", "الجن",
    "المزمل", "المدثر", "القيامة", "الإنسان", "المرسلات", "النبأ",
    "النازعات", "عبس", "التكوير", "الانفطار", "المطففين", "الانشقاق",
    "البروج", "الطارق", "الأعلى", "الغاشية", "الفجر", "البلد", "الشمس",
    "الليل", "الضحى", "الشرح", "التين", "العلق", "القدر", "البينة",
    "الزلزلة", "العاديات", "القارعة", "التكاثر", "العصر", "الهمزة",
    "الفيل", "قريش", "الماعون", "الكوثر", "الكافرون", "النصر", "المسد",
    "الإخلاص", "الفلق", "الناس"
}

# =============================================================================
# LOGGING
# =============================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE WITH AUTO-MIGRATION
# =============================================================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        date_joined TEXT,
        first_time INTEGER DEFAULT 1,
        banned INTEGER DEFAULT 0,
        language TEXT DEFAULT 'ar'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        maintenance_mode INTEGER DEFAULT 0,
        ban_list TEXT DEFAULT ''
    )''')
    # التحقق من الأعمدة المفقودة
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'first_time' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN first_time INTEGER DEFAULT 1")
    if 'banned' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
    if 'language' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ar'")
    if 'last_name' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    # التأكد من وجود صف في settings
    c.execute('SELECT count(*) FROM settings')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO settings (id, maintenance_mode, ban_list) VALUES (1, 0, "")')
    conn.commit()
    conn.close()
    logger.info("Database initialized and migrated successfully.")

def get_db():
    return sqlite3.connect(DB_NAME)

def add_user(user_data):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT first_time, banned FROM users WHERE user_id = ?", (user_data['id'],))
        existing = c.fetchone()
        if existing:
            c.execute('''UPDATE users SET
                        username = ?,
                        first_name = ?,
                        last_name = ?,
                        language = COALESCE(?, language)
                        WHERE user_id = ?''',
                      (user_data.get('username'),
                       user_data.get('first_name'),
                       user_data.get('last_name'),
                       user_data.get('language', 'ar'),
                       user_data['id']))
            first_time = existing[0]
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute('''INSERT INTO users
                        (user_id, username, first_name, last_name, date_joined, first_time, language)
                        VALUES (?, ?, ?, ?, ?, 1, ?)''',
                      (user_data['id'],
                       user_data.get('username'),
                       user_data.get('first_name'),
                       user_data.get('last_name'),
                       now,
                       user_data.get('language', 'ar')))
            first_time = 1
        conn.commit()
        return first_time
    except Exception as e:
        logger.error(f"DB add_user error: {e}")
        return 0
    finally:
        conn.close()

def get_all_users():
    conn = get_db()
    try:
        res = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
        return [row[0] for row in res]
    except Exception as e:
        logger.error(f"get_all_users error: {e}")
        return []
    finally:
        conn.close()

def get_user_count():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users WHERE banned = 0").fetchone()[0]
    except Exception as e:
        logger.error(f"get_user_count error: {e}")
        return 0
    finally:
        conn.close()

def get_banned_users():
    conn = get_db()
    try:
        res = conn.execute("SELECT user_id FROM users WHERE banned = 1").fetchall()
        return [row[0] for row in res]
    except Exception as e:
        logger.error(f"get_banned_users error: {e}")
        return []
    finally:
        conn.close()

def ban_user(user_id):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"ban_user error: {e}")
        return False
    finally:
        conn.close()

def unban_user(user_id):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"unban_user error: {e}")
        return False
    finally:
        conn.close()

def is_user_banned(user_id):
    conn = get_db()
    try:
        res = conn.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return res[0] == 1 if res else False
    except Exception as e:
        logger.error(f"is_user_banned error: {e}")
        return False
    finally:
        conn.close()

def get_user_stats():
    conn = get_db()
    try:
        active = conn.execute("SELECT COUNT(*) FROM users WHERE banned = 0").fetchone()[0]
        banned = conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
        new_today = conn.execute("SELECT COUNT(*) FROM users WHERE date(date_joined) = date('now')").fetchone()[0]
        first = conn.execute("SELECT date_joined FROM users ORDER BY date_joined LIMIT 1").fetchone()
        first_date = first[0] if first else "N/A"
        return {
            'active_users': active,
            'banned_users': banned,
            'total_users': active + banned,
            'new_today': new_today,
            'first_user_date': first_date
        }
    except Exception as e:
        logger.error(f"get_user_stats error: {e}")
        return None
    finally:
        conn.close()

def get_maintenance_mode():
    conn = get_db()
    try:
        val = conn.execute('SELECT maintenance_mode FROM settings WHERE id=1').fetchone()[0]
        return val == 1
    except:
        return False
    finally:
        conn.close()

def set_maintenance_mode(mode):
    conn = get_db()
    try:
        conn.execute('UPDATE settings SET maintenance_mode = ? WHERE id=1', (1 if mode else 0,))
        conn.commit()
    except Exception as e:
        logger.error(f"set_maintenance_mode error: {e}")
    finally:
        conn.close()

def get_ban_list():
    conn = get_db()
    try:
        ban_str = conn.execute('SELECT ban_list FROM settings WHERE id=1').fetchone()[0]
        if ban_str:
            return [int(x) for x in ban_str.split(',') if x.strip()]
        return []
    except:
        return []
    finally:
        conn.close()

def add_to_ban_list(user_id):
    conn = get_db()
    try:
        cur = conn.execute('SELECT ban_list FROM settings WHERE id=1')
        ban_str = cur.fetchone()[0] or ''
        ban_list = ban_str.split(',') if ban_str else []
        if str(user_id) not in ban_list:
            new_ban = ban_str + (',' if ban_str else '') + str(user_id)
            conn.execute('UPDATE settings SET ban_list = ? WHERE id=1', (new_ban,))
            conn.commit()
    except Exception as e:
        logger.error(f"add_to_ban_list error: {e}")
    finally:
        conn.close()

def remove_from_ban_list(user_id):
    conn = get_db()
    try:
        cur = conn.execute('SELECT ban_list FROM settings WHERE id=1')
        ban_str = cur.fetchone()[0] or ''
        ban_list = ban_str.split(',') if ban_str else []
        if str(user_id) in ban_list:
            ban_list.remove(str(user_id))
            new_ban = ','.join(ban_list)
            conn.execute('UPDATE settings SET ban_list = ? WHERE id=1', (new_ban,))
            conn.commit()
    except Exception as e:
        logger.error(f"remove_from_ban_list error: {e}")
    finally:
        conn.close()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def download_bytes(url, timeout=20):
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    return resp.content

def safe_filename_from_url(url, default):
    try:
        tail = urllib.parse.urlparse(url).path.split('/')[-1]
        if not tail:
            return default
        if '.' not in tail:
            return f"{tail}.bin"
        return tail
    except:
        return default

def is_youtube_url(url):
    return "youtube.com" in url.lower() or "youtu.be" in url.lower()

def is_instagram_url(url):
    return "instagram.com" in url.lower()

def get_instagram_type(url: str) -> str:
    if "/reels/audio/" in url or "/audio/" in url:
        return "audio"
    elif "/stories/" in url:
        return "story"
    elif "/reel/" in url:
        return "reel"
    elif "/p/" in url:
        return "post"
    elif "/tv/" in url:
        return "tv"
    else:
        return "unknown"

def is_tiktok_url(url):
    return "tiktok.com" in url.lower()

def is_pinterest_url(url):
    return "pinterest.com" in url.lower() or "pin.it" in url.lower()

def is_facebook_url(url):
    return "facebook.com" in url.lower() or "fb.watch" in url.lower()

def is_snapchat_url(url):
    return "snapchat.com" in url.lower()

def is_surah_name(text):
    cleaned = re.sub(r'[^\u0600-\u06FF\s]', '', text.strip())
    return cleaned in SURAH_NAMES

async def delete_file_async(filepath):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.debug(f"Deleted temp file: {filepath}")
    except Exception as e:
        logger.warning(f"Could not delete {filepath}: {e}")

def format_blockquote(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"

# =============================================================================
# YOUTUBE SEARCH (STABLE)
# =============================================================================
async def youtube_search(query: str, count: int = YOUTUBE_SEARCH_COUNT) -> List[Dict[str, Any]]:
    def _search():
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'no_check_certificate': True,
            'ignoreerrors': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_query = f"ytsearch{count}:{query}"
            try:
                info = ydl.extract_info(search_query, download=False)
            except Exception as e:
                logger.error(f"yt-dlp search error: {e}")
                return []
            entries = info.get('entries', [])
            results = []
            for entry in entries:
                if entry is None or not entry.get('webpage_url'):
                    continue
                results.append({
                    'title': entry.get('title', 'بدون عنوان'),
                    'url': entry.get('webpage_url', ''),
                    'duration': entry.get('duration', 0),
                    'uploader': entry.get('uploader', 'مجهول'),
                    'thumbnail': entry.get('thumbnail', ''),
                    'id': entry.get('id', ''),
                })
            return results

    for attempt in range(RETRY_LIMIT + 1):
        try:
            results = await asyncio.to_thread(_search)
            if results:
                return results
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"Search attempt {attempt+1} failed: {e}")
            if attempt == RETRY_LIMIT:
                return []
            await asyncio.sleep(RETRY_DELAY)
    return []

# =============================================================================
# YOUTUBE AUDIO DOWNLOAD (NO FFMPEG) - m4a
# =============================================================================
async def download_youtube_audio(video_url: str, output_path_template: str) -> Optional[str]:
    def _download():
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_path_template,
            'socket_timeout': 30,
            'no_check_certificate': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=True)
                filename = ydl.prepare_filename(info)
                if os.path.exists(filename):
                    return filename
                base = os.path.splitext(output_path_template)[0]
                dir_path = os.path.dirname(base)
                base_name = os.path.basename(base)
                for f in os.listdir(dir_path):
                    if f.startswith(base_name) and f.endswith(('.m4a', '.aac', '.opus')):
                        return os.path.join(dir_path, f)
                return None
            except Exception as e:
                logger.error(f"yt-dlp audio download error: {e}")
                return None

    for attempt in range(RETRY_LIMIT + 1):
        try:
            result = await asyncio.to_thread(_download)
            if result and os.path.exists(result):
                return result
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"Audio download attempt {attempt+1} failed: {e}")
            if attempt == RETRY_LIMIT:
                return None
            await asyncio.sleep(RETRY_DELAY)
    return None

# =============================================================================
# YOUTUBE VIDEO DOWNLOAD
# =============================================================================
async def download_youtube_video(video_url: str, output_path_template: str) -> Optional[str]:
    def _download():
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'outtmpl': output_path_template,
            'socket_timeout': 30,
            'no_check_certificate': True,
            'merge_output_format': 'mp4',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=True)
                filename = ydl.prepare_filename(info)
                if os.path.exists(filename):
                    return filename
                base = os.path.splitext(output_path_template)[0]
                dir_path = os.path.dirname(base)
                base_name = os.path.basename(base)
                for f in os.listdir(dir_path):
                    if f.startswith(base_name) and f.endswith('.mp4'):
                        return os.path.join(dir_path, f)
                return None
            except Exception as e:
                logger.error(f"yt-dlp video download error: {e}")
                return None

    for attempt in range(RETRY_LIMIT + 1):
        try:
            result = await asyncio.to_thread(_download)
            if result and os.path.exists(result):
                return result
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"Video download attempt {attempt+1} failed: {e}")
            if attempt == RETRY_LIMIT:
                return None
            await asyncio.sleep(RETRY_DELAY)
    return None

# =============================================================================
# PLATFORM-SPECIFIC DOWNLOADERS
# =============================================================================
async def handle_tiktok(update, context, url, loading_msg):
    chat_id = update.effective_chat.id
    try:
        data = {'q': url, 'lang': 'ar'}
        response = await asyncio.to_thread(
            requests.post,
            "https://tiksave.io/api/ajaxSearch",
            cookies={
                '__gads': 'ID=845d6f69a383b47d:T=1753115039:RT=1753777189:S=ALNI_MZ5mo4zUsj-FGlikaQuoQ4_swmsAw',
                '__gpi': 'UID=000010f3a3509093:T=1753115039:RT=1753777189:S=ALNI_MYygG_4blpkyQSIgGe4X14XjLOv_A',
                '__eoi': 'ID=f988b7216243e3f9:T=1753115039:RT=1753777189:S=AA-AfjaaFPzIIsO8HLZKRQPpo5H_',
                'FCNEC': '%5B%5B%22AKsRol_DFZW-z9Bos6qXwGfO8Q5J58PDhfHvyYmhEhiH_YoMOq4xyT_w_UAqYzh9EZDicGKtVO2YdT96aKCyE-6wO0HnG4tshKgcaw846Q46khC5rq-e0BMBYFBSXcTwPuhBnMw16CGjkEBIuJA9kx7kb17k5UHIZQ%3D%3D%22%5D%5D',
            },
            headers={
                'authority': 'tiksave.io',
                'accept': '*/*',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://tiksave.io',
                'referer': 'https://tiksave.io/ar',
                'user-agent': generate_user_agent(),
                'x-requested-with': 'XMLHttpRequest',
            },
            data=data,
            timeout=20
        )
        response.raise_for_status()
        json_data = response.json()
        html_content = json_data.get("data")
        if not html_content:
            raise ValueError("No data")
        soup = BeautifulSoup(html_content, 'html.parser')
        video_tag = soup.find('video')
        video_url = video_tag.get('data-src') if video_tag else None
        if video_url:
            await loading_msg.delete()
            await context.bot.send_video(chat_id, video_url, caption="✅ تم التحميل بأعلى دقة")
        else:
            raise ValueError("Video URL not found")
    except Exception as e:
        logger.error(f"TikTok error: {e}")
        await loading_msg.edit_text(format_blockquote("❌ فشل تحميل الفيديو من تيك توك."), parse_mode=ParseMode.HTML)

async def handle_pinterest(update, context, url, loading_msg):
    chat_id = update.effective_chat.id
    try:
        headers_img = {
            'authority': 'api.pinterestdl.io',
            'accept': '*/*',
            'origin': 'https://pinterestdl.io',
            'referer': 'https://pinterestdl.io/',
            'user-agent': generate_user_agent(),
        }
        resp = await asyncio.to_thread(
            requests.get,
            "https://api.pinterestdl.io/api/image",
            params={'url': url},
            headers=headers_img,
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            image_url = data.get('imageUrl')
            if image_url:
                content = await asyncio.to_thread(download_bytes, image_url, 25)
                filename = safe_filename_from_url(image_url, "pinterest.jpg")
                await loading_msg.delete()
                await context.bot.send_document(chat_id, document=BytesIO(content), filename=filename, caption="✅ تم التحميل بأعلى دقة")
                return
        data_form = {'url': url, 'token': '0d8a45597e998fd21242b74089fac11b70dd1499a2ba25ad3b6100238811eafd', 'hash': 'aHR0cHM6Ly9waW4uaXQvNmp0RVZPRkdz1024YWlvLWRs'}
        video_response = await asyncio.to_thread(
            requests.post,
            "https://everyweb.net/wp-json/aio-dl/video-data/",
            cookies={
                '_lscache_vary': 'cd11052a02ea53c97b30994ffef5a4b1',
                '_ga_7P1TVF9P7M': 'GS2.1.s1753736522$o1$g0$t1753736522$j60$l0$h0',
                '_ga': 'GA1.1.30758253.1753736522',
                'pll_language': 'ar',
                '__gads': 'ID=e510112a91dffb7c:T=1753736524:RT=1753736524:S=ALNI_MZ3sbceLB32rKNPnoWCLYi6ccl2Xg',
                '__gpi': 'UID=0000111a4db6b81c:T=1753736524:RT=1753736524:S=ALNI_Ma6vm88YHiW8LcyOlTWXlmafYoqTw',
                '__eoi': 'ID=c2055eef46b6fba0:T=1753736524:RT=1753736524:S=AA-Afjatkw_ngmHHvPIurkUp7l9N',
                'FCNEC': '%5B%5B%22AKsRol9AtNttuHht9OxvvFO9Ok96J2IaZLpQu-5py1E6tFSwu2yhdbdoM53f1SzURfR4XU24wRX_AdkxfZ_gu117p4Yr0dxw9EhKPsSc6C3ZPVOaVqfs4Gfe0yUGxrj0brm30K13UfO86KxL-lCngteOv-aGd8p9SA%3D%3D%22%5D%5D',
            },
            headers={
                'authority': 'everyweb.net',
                'accept': '*/*',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://everyweb.net',
                'referer': 'https://everyweb.net/pinterest/',
                'user-agent': generate_user_agent(),
            },
            data=data_form,
            timeout=20
        )
        if video_response.status_code == 200:
            jd = video_response.json()
            medias = jd.get('medias') or []
            if medias:
                candidate = None
                for m in medias:
                    if m.get('quality') in ('hd', '720', '1080', '4k'):
                        candidate = m
                        break
                if not candidate:
                    candidate = medias[0]
                video_url = candidate.get('url')
                if video_url:
                    await loading_msg.delete()
                    await context.bot.send_video(chat_id, video_url, caption="✅ تم التحميل بأعلى دقة")
                    return
        raise ValueError("No media")
    except Exception as e:
        logger.error(f"Pinterest error: {e}")
        await loading_msg.edit_text(format_blockquote("❌ فشل تحميل المحتوى من بينتريست."), parse_mode=ParseMode.HTML)

async def handle_facebook(update, context, url, loading_msg):
    chat_id = update.effective_chat.id
    try:
        data = {
            'k_exp': '1753825936',
            'k_token': '2ba09b483e6bd112275af34aa9fa4c2a9d53df34a934389b8086bcbffce0a515',
            'p': 'home',
            'q': url,
            'lang': 'ar',
            'v': 'v2',
            'w': '',
        }
        response = await asyncio.to_thread(
            requests.post,
            "https://fbdownloader.to/api/ajaxSearch",
            cookies={'fpestid': 'TQyMQylz-gvL1kHeSpoed1DZBd_-Y4YBDU4rVgQYEKy2H3fz6rzKpilTTsGNsyjM8XNppw'},
            headers={
                'authority': 'fbdownloader.to',
                'accept': '*/*',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://fbdownloader.to',
                'referer': 'https://fbdownloader.to/ar',
                'user-agent': generate_user_agent(),
                'x-requested-with': 'XMLHttpRequest',
            },
            data=data,
            timeout=20
        )
        response.raise_for_status()
        json_data = response.json()
        if json_data.get('status') != 'ok':
            raise ValueError("API error")
        soup = BeautifulSoup(json_data['data'], 'html.parser')
        video_url = None
        for quality in ['720p (HD)', '360p (SD)']:
            link = soup.find('a', {'title': f'Download {quality}'})
            if link and 'href' in link.attrs:
                video_url = link['href']
                break
        if not video_url:
            video_tag = soup.find('video')
            if video_tag and 'src' in video_tag.attrs:
                video_url = video_tag['src']
        if video_url:
            await loading_msg.delete()
            await context.bot.send_video(chat_id, video_url, caption="✅ تم التحميل بأعلى دقة")
        else:
            raise ValueError("No video URL")
    except Exception as e:
        logger.error(f"Facebook error: {e}")
        await loading_msg.edit_text(format_blockquote("❌ فشل تحميل الفيديو من فيسبوك."), parse_mode=ParseMode.HTML)

async def handle_snapchat(update, context, url, loading_msg):
    chat_id = update.effective_chat.id
    try:
        payload = {'file_name': url}
        r = await asyncio.to_thread(
            requests.post,
            "https://samrt-loader.com/kydwon/api/addfile",
            cookies={'myCookieConsent': 'true', 'PHPSESSID': 'lruvkc8ljl99ks5imuc3fsca9u'},
            headers={
                'authority': 'samrt-loader.com',
                'accept': 'application/json, text/plain, */*',
                'content-type': 'application/json',
                'origin': 'https://samrt-loader.com',
                'referer': 'https://samrt-loader.com/ar/snapchat',
                'user-agent': generate_user_agent(),
            },
            json=payload,
            timeout=20
        )
        jd = r.json()
        if jd.get('success') and 'files' in jd:
            video_url = None
            for f in jd['files']:
                if f.get('resolution_type') == 'mp4/hd' and f.get('file'):
                    video_url = f['file']
                    break
            if not video_url:
                for f in jd['files']:
                    if f.get('file'):
                        video_url = f['file']
                        break
            if video_url:
                await loading_msg.delete()
                await context.bot.send_video(chat_id, video_url, caption="✅ تم التحميل بأعلى دقة")
                return
        data = {'url': url, 'action': 'post'}
        response = await asyncio.to_thread(
            requests.post,
            "https://snapinsta.app/action.php",
            headers={
                'authority': 'snapinsta.app',
                'accept': '*/*',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://snapinsta.app',
                'referer': 'https://snapinsta.app/',
                'user-agent': generate_user_agent(),
            },
            data=data,
            timeout=20
        )
        response.raise_for_status()
        json_data = response.json()
        if json_data.get('status') == 'success' and 'url' in json_data:
            video_url = json_data['url']
            await loading_msg.delete()
            await context.bot.send_video(chat_id, video_url, caption="✅ تم التحميل بأعلى دقة")
            return
        raise ValueError("No video URL")
    except Exception as e:
        logger.error(f"Snapchat error: {e}")
        await loading_msg.edit_text(format_blockquote("❌ فشل تحميل المحتوى من سناب شات."), parse_mode=ParseMode.HTML)

# =============================================================================
# INSTAGRAM HANDLER (FULL SUPPORT)
# =============================================================================
async def handle_instagram(update, context, url, loading_msg):
    chat_id = update.effective_chat.id
    ig_type = get_instagram_type(url)

    await loading_msg.edit_text(
        format_blockquote(f"📥 جاري تحميل المحتوى من إنستغرام..."),
        parse_mode=ParseMode.HTML
    )

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(DOWNLOAD_DIR, 'instagram_%(id)s.%(ext)s'),
            'socket_timeout': 30,
            'no_check_certificate': True,
            'ignoreerrors': True,
        }
        if ig_type == 'audio':
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
        else:
            ydl_opts['format'] = 'best'

        def _dl_insta():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise ValueError("No info extracted")
                if 'entries' in info:
                    info = info['entries'][0]
                if info is None:
                    raise ValueError("No entry found")
                if ig_type == 'audio' or info.get('duration', 0) > 0 and info.get('ext') in ('m4a', 'aac', 'opus'):
                    ydl.download([url])
                    filename = ydl.prepare_filename(info)
                    if not os.path.exists(filename):
                        base = os.path.splitext(ydl_opts['outtmpl'])[0]
                        dir_path = os.path.dirname(base)
                        base_name = os.path.basename(base)
                        for f in os.listdir(dir_path):
                            if f.startswith(base_name) and f.endswith(('.m4a', '.aac', '.opus')):
                                filename = os.path.join(dir_path, f)
                                break
                    if filename and os.path.exists(filename):
                        return 'audio', filename, info
                    else:
                        raise ValueError("Audio file not found")
                elif info.get('duration', 0) > 0:
                    ydl.download([url])
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        return 'video', filename, info
                    else:
                        base = os.path.splitext(ydl_opts['outtmpl'])[0]
                        dir_path = os.path.dirname(base)
                        base_name = os.path.basename(base)
                        for f in os.listdir(dir_path):
                            if f.startswith(base_name) and f.endswith(('.mp4', '.mov')):
                                filename = os.path.join(dir_path, f)
                                break
                        if filename and os.path.exists(filename):
                            return 'video', filename, info
                        else:
                            raise ValueError("Video file not found")
                else:
                    img_url = info.get('url')
                    if not img_url:
                        raise ValueError("No image URL found")
                    content = download_bytes(img_url, 25)
                    filename = safe_filename_from_url(img_url, "instagram.jpg")
                    return 'image', content, filename

        result = None
        for attempt in range(RETRY_LIMIT + 1):
            try:
                result = await asyncio.to_thread(_dl_insta)
                if result:
                    break
            except Exception as e:
                logger.error(f"Instagram download attempt {attempt+1} failed: {e}")
                if "cookies" in str(e).lower() or "login" in str(e).lower():
                    await loading_msg.edit_text(
                        format_blockquote(
                            "🔐 هذا المحتوى يتطلب تسجيل دخول إلى إنستغرام.\n"
                            "📌 يرجى استخدام روابط عامة (غير خاصة) أو تحميل الفيديو يدوياً."
                        ),
                        parse_mode=ParseMode.HTML
                    )
                    return
                if attempt == RETRY_LIMIT:
                    raise
                await asyncio.sleep(RETRY_DELAY)

        if not result:
            raise ValueError("Download failed")

        await loading_msg.delete()

        if result[0] == 'audio':
            _, filename, info = result
            # التحقق من حجم الملف
            filesize = os.path.getsize(filename) / (1024*1024)
            if filesize > MAX_FILE_SIZE_MB:
                await context.bot.send_message(
                    chat_id,
                    format_blockquote(f"⚠️ الملف كبير جداً ({filesize:.1f} ميجابايت). الحد الأقصى هو {MAX_FILE_SIZE_MB} ميجابايت."),
                    parse_mode=ParseMode.HTML
                )
                await delete_file_async(filename)
                return
            title = info.get('title', 'صوت إنستغرام')
            uploader = info.get('uploader', 'مجهول')
            duration = info.get('duration')
            try:
                with open(filename, 'rb') as f:
                    await context.bot.send_audio(
                        chat_id,
                        audio=f,
                        title=title,
                        performer=uploader,
                        duration=duration
                    )
                await context.bot.send_message(
                    chat_id,
                    format_blockquote("✅ تم إرسال الصوت بنجاح."),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                await context.bot.send_message(
                    chat_id,
                    format_blockquote("❌ حدث خطأ أثناء إرسال الصوت."),
                    parse_mode=ParseMode.HTML
                )
            finally:
                await delete_file_async(filename)

        elif result[0] == 'video':
            _, filename, info = result
            filesize = os.path.getsize(filename) / (1024*1024)
            if filesize > MAX_FILE_SIZE_MB:
                await context.bot.send_message(
                    chat_id,
                    format_blockquote(f"⚠️ الملف كبير جداً ({filesize:.1f} ميجابايت). الحد الأقصى هو {MAX_FILE_SIZE_MB} ميجابايت."),
                    parse_mode=ParseMode.HTML
                )
                await delete_file_async(filename)
                return
            try:
                with open(filename, 'rb') as f:
                    await context.bot.send_video(
                        chat_id,
                        video=f,
                        caption="✅ تم التحميل بأعلى دقة",
                        width=info.get('width'),
                        height=info.get('height'),
                        duration=info.get('duration')
                    )
            except Exception as e:
                logger.error(f"Error sending video: {e}")
                await context.bot.send_message(
                    chat_id,
                    format_blockquote("❌ حدث خطأ أثناء إرسال الفيديو."),
                    parse_mode=ParseMode.HTML
                )
            finally:
                await delete_file_async(filename)

        elif result[0] == 'image':
            _, content, filename = result
            try:
                await context.bot.send_photo(
                    chat_id,
                    photo=BytesIO(content),
                    caption="✅ تم التحميل بأعلى دقة"
                )
            except Exception as e:
                logger.error(f"Error sending photo: {e}")
                await context.bot.send_message(
                    chat_id,
                    format_blockquote("❌ حدث خطأ أثناء إرسال الصورة."),
                    parse_mode=ParseMode.HTML
                )

    except Exception as e:
        logger.error(f"Instagram general error: {e}")
        # محاولة fallback باستخدام instaloader للقصص والمنشورات العامة
        if ig_type in ('story', 'reel', 'post'):
            try:
                await loading_msg.edit_text(
                    format_blockquote("🔄 جاري المحاولة بطريقة بديلة..."),
                    parse_mode=ParseMode.HTML
                )
                shortcode_match = re.search(r'/(?:reel|p|stories)/([^/?]+)', url)
                if shortcode_match:
                    shortcode = shortcode_match.group(1)
                    post = await asyncio.to_thread(
                        instaloader.Post.from_shortcode,
                        instaloader.Instaloader().context,
                        shortcode
                    )
                    if post.is_video:
                        await loading_msg.delete()
                        await context.bot.send_video(chat_id, post.video_url, caption="✅ تم التحميل بأعلى دقة")
                    else:
                        content = await asyncio.to_thread(download_bytes, post.url, 25)
                        filename = safe_filename_from_url(post.url, "instagram.jpg")
                        await loading_msg.delete()
                        await context.bot.send_photo(chat_id, photo=BytesIO(content), caption="✅ تم التحميل بأعلى دقة")
                    return
                else:
                    raise ValueError("No shortcode found")
            except Exception as e2:
                logger.error(f"Instagram fallback error: {e2}")
                await loading_msg.edit_text(
                    format_blockquote(
                        "⚠️ تعذر تحميل المحتوى من إنستغرام.\n"
                        "🔐 قد يكون المحتوى خاصاً أو الرابط غير صالح."
                    ),
                    parse_mode=ParseMode.HTML
                )
        else:
            error_msg = str(e)
            if "cookies" in error_msg.lower() or "login" in error_msg.lower():
                msg = "🔐 هذا المحتوى يتطلب تسجيل دخول إلى إنستغرام."
            elif "This video is not available" in error_msg:
                msg = "⚠️ الفيديو غير متاح حالياً."
            elif "Private" in error_msg or "private" in error_msg:
                msg = "🔐 هذا المحتوى خاص ولا يمكن الوصول إليه."
            elif "expired" in error_msg.lower():
                msg = "⏳ انتهت صلاحية هذا المحتوى."
            else:
                msg = f"⚠️ تعذر تحميل المحتوى: {error_msg[:100]}"
            await loading_msg.edit_text(
                format_blockquote(msg),
                parse_mode=ParseMode.HTML
            )

# =============================================================================
# YOUTUBE URL HANDLER
# =============================================================================
async def handle_youtube_url(update, context, url, loading_msg):
    chat_id = update.effective_chat.id
    keyboard = [
        [
            InlineKeyboardButton("❤️‍🩹تحميل صوت", callback_data=f"yt_audio_url_{url}", style="primary"),
            InlineKeyboardButton("💫تحميل فيديو", callback_data=f"yt_video_url_{url}", style="primary")
        ]
    ]
    await loading_msg.delete()
    await context.bot.send_message(
        chat_id,
        format_blockquote("🎧 اختر نوع التحميل:"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =============================================================================
# MESSAGE ROUTER
# =============================================================================
async def route_download(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    chat_id = update.effective_chat.id
    loading_msg = await context.bot.send_message(
        chat_id,
        format_blockquote("⏳ جاري معالجة طلبك..."),
        parse_mode=ParseMode.HTML
    )

    try:
        if is_youtube_url(text):
            await handle_youtube_url(update, context, text, loading_msg)
        elif is_instagram_url(text):
            await handle_instagram(update, context, text, loading_msg)
        elif is_tiktok_url(text):
            await handle_tiktok(update, context, text, loading_msg)
        elif is_pinterest_url(text):
            await handle_pinterest(update, context, text, loading_msg)
        elif is_facebook_url(text):
            await handle_facebook(update, context, text, loading_msg)
        elif is_snapchat_url(text):
            await handle_snapchat(update, context, text, loading_msg)
        else:
            await loading_msg.edit_text(
                format_blockquote("⏳ جاري محاولة التحميل..."),
                parse_mode=ParseMode.HTML
            )
            try:
                ydl_opts = {
                    'format': 'best',
                    'quiet': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, 'download_%(id)s.%(ext)s'),
                    'socket_timeout': 30,
                    'no_check_certificate': True,
                }
                def _dl_general():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(text, download=True)
                        filename = ydl.prepare_filename(info)
                        return filename, info
                filename, info = await asyncio.to_thread(_dl_general)
                await loading_msg.delete()
                with open(filename, 'rb') as f:
                    await context.bot.send_document(chat_id, document=f, caption="✅ تم التحميل")
                await delete_file_async(filename)
            except Exception as e:
                logger.error(f"General download error: {e}")
                await loading_msg.edit_text(
                    format_blockquote("❌ تعذر تحميل هذا المحتوى. تأكد من الرابط."),
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Route error: {e}")
        await loading_msg.edit_text(
            format_blockquote("⚠️ حدث خطأ أثناء المعالجة."),
            parse_mode=ParseMode.HTML
        )

# =============================================================================
# SUBSCRIPTION CHECK
# =============================================================================
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        for channel in (CHANNEL_USERNAME, CHANNEL_USERNAME2):
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ('member', 'administrator', 'creator'):
                return False
        return True
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

def subscription_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍃القناة الأولى", url=f"https://t.me/{CHANNEL_USERNAME[1:]}", style="primary"),
            InlineKeyboardButton("✅القناة الثانية", url=f"https://t.me/{CHANNEL_USERNAME2[1:]}", style="primary")
        ],
        [InlineKeyboardButton("😝تحقق من الاشتراك", callback_data='check_sub', style="primary")]
    ])

# =============================================================================
# WELCOME TEXT
# =============================================================================
def get_welcome_text() -> str:
    return (
        "🎬 <b>اليوتيوب :</b>\n\n"
        "<blockquote>"
        "🎵 أرسل اسم الأغنية أو الفيديو، وسأبحث عنه وأتيح لك تحميل الصوت أو الفيديو.\n"
        "📖 أو اكتب اسم سورة (مثل: الفاتحه) لأرسل لك تلاوتها.\n"
        "🔗 ويمكنك أيضاً إرسال رابط يوتيوب مباشرة."
        "</blockquote>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📸 <b>الانستا :</b>\n\n"
        "<blockquote>"
        "🔗 أرسل رابط الفيديو الذي تريد تحميله"
        "</blockquote>"
    )

# =============================================================================
# COMMAND HANDLERS
# =============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    chat_id = update.effective_chat.id
    user_id = user.id

    if is_user_banned(user_id) or user_id in get_ban_list():
        await update.message.reply_text(format_blockquote("⛔ تم حظرك من استخدام هذا البوت."), parse_mode=ParseMode.HTML)
        return

    add_user({
        'id': user_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'language': 'ar'
    })

    if not await check_subscription(update, context, user_id):
        msg = "⚠️ يجب الاشتراك في القنوات التالية أولاً:\n\n{ch1}\n{ch2}\n\nثم اضغط /start مرة أخرى."
        await update.message.reply_text(
            format_blockquote(msg.format(ch1=CHANNEL_USERNAME, ch2=CHANNEL_USERNAME2)),
            parse_mode=ParseMode.HTML,
            reply_markup=subscription_keyboard()
        )
        return

    if get_maintenance_mode() and user_id not in ADMIN_IDS:
        await update.message.reply_text(format_blockquote("🛠 البوت تحت الصيانة حالياً. حاول لاحقاً."), parse_mode=ParseMode.HTML)
        return

    if WELCOME_IMAGE:
        try:
            await context.bot.send_photo(
                chat_id,
                photo=WELCOME_IMAGE,
                caption=get_welcome_text(),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error sending welcome photo: {e}")
            await context.bot.send_message(
                chat_id,
                get_welcome_text(),
                parse_mode=ParseMode.HTML
            )
    else:
        await context.bot.send_message(
            chat_id,
            get_welcome_text(),
            parse_mode=ParseMode.HTML
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(format_blockquote("⛔ غير مصرح."), parse_mode=ParseMode.HTML)
        return

    stats = get_user_stats()
    text = (
        "♛ <b>لوحة الإدارة</b> ♛\n\n"
        f"👥 المستخدمين النشطين: {stats['active_users']}\n"
        f"🚫 المحظورين: {stats['banned_users']}\n"
        f"📊 الإجمالي: {stats['total_users']}\n"
        f"🆕 اليوم: {stats['new_today']}\n"
        f"📅 أول مستخدم: {stats['first_user_date']}\n"
        f"🔒 وضع الصيانة: {'مفعل' if get_maintenance_mode() else 'معطل'}"
    )

    keyboard = [
        [
            InlineKeyboardButton("📝إذاعة", callback_data="admin_broadcast", style="primary"),
            InlineKeyboardButton("🥹إحصائيات", callback_data="admin_stats", style="primary")
        ],
        [
            InlineKeyboardButton("✨قفل البوت", callback_data="admin_lock", style="primary"),
            InlineKeyboardButton("💞فتح البوت", callback_data="admin_unlock", style="primary")
        ],
        [
            InlineKeyboardButton("❌حظر مستخدم", callback_data="admin_ban", style="primary"),
            InlineKeyboardButton("🎹إلغاء حظر", callback_data="admin_unban", style="primary")
        ],
    ]
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =============================================================================
# MESSAGE HANDLER (text)
# =============================================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user or not update.message:
        return

    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # التحقق من الحظر
    if is_user_banned(user.id) or user.id in get_ban_list():
        await update.message.reply_text(
            format_blockquote("⛔ تم حظرك."),
            parse_mode=ParseMode.HTML
        )
        return

    # وضع الصيانة
    if get_maintenance_mode() and user.id not in ADMIN_IDS:
        await update.message.reply_text(
            format_blockquote("🛠 البوت تحت الصيانة."),
            parse_mode=ParseMode.HTML
        )
        return

    if not text:
        return

    # معالجة الروابط
    if text.startswith(("http://", "https://")):
        await route_download(update, context, text)
        return

    # تجهيز البحث
    query = text

    if is_surah_name(query):
        query = f"تلاوة سورة {query}"

    # رسالة الانتظار
    loading_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=format_blockquote("🔎 جاري البحث عن طلبك..."),
        parse_mode=ParseMode.HTML
    )

    try:
        # البحث
        results = await youtube_search(
            query,
            YOUTUBE_SEARCH_COUNT
        )

        # لا توجد نتائج
        if not results:
            await loading_msg.edit_text(
                format_blockquote(
                    "🔎 لم يتم العثور على نتائج، حاول باسم آخر."
                ),
                parse_mode=ParseMode.HTML
            )
            return

        # حفظ النتائج
        context.user_data["search_results"] = results
        context.user_data["search_query"] = query

        # إنشاء الأزرار
        buttons = []

        for idx, res in enumerate(results):
            title = str(
                res.get("title", "بدون عنوان")
            )[:50]

            duration = res.get("duration")

            if duration:
                try:
                    duration = int(duration)
                    dur_str = (
                        f"{duration // 60:02d}:"
                        f"{duration % 60:02d}"
                    )
                except (ValueError, TypeError):
                    dur_str = "غير معروف"
            else:
                dur_str = "غير معروف"

            button_text = (
                f"🎵 {idx + 1}. {title} ⏱ {dur_str}"
            )

            buttons.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"yt_result_{idx}",
                    style="primary"
                )
            ])

        # حذف رسالة البحث
        try:
            await loading_msg.delete()
        except Exception:
            pass

        # إرسال النتائج
        await context.bot.send_message(
            chat_id=chat_id,
            text=format_blockquote(
                f"🎵 <b>نتائج البحث عن:</b>\n"
                f"╰─ <code>{query}</code>\n\n"
                f"📌 <b>اختر أحد الخيارات:</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logging.exception(
            "حدث خطأ أثناء البحث: %s",
            e
        )

        try:
            await loading_msg.edit_text(
                format_blockquote(
                    "❌ حدث خطأ أثناء البحث، حاول مرة أخرى لاحقًا."
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

# =============================================================================
# CALLBACK HANDLER
# =============================================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    admin_actions = {
        'admin_broadcast': ('broadcast', "📣 أرسل رسالة البث (نص، صورة، فيديو، ملف):"),
        'admin_stats': ('stats', None),
        'admin_lock': ('lock', None),
        'admin_unlock': ('unlock', None),
        'admin_ban': ('ban', "🚫 أرسل ID المستخدم لحظره:"),
        'admin_unban': ('unban', "✅ أرسل ID المستخدم لإلغاء الحظر:"),
    }

    if data in admin_actions:
        if user_id not in ADMIN_IDS:
            await query.answer("⛔ غير مصرح", show_alert=True)
            return
        action, reply_msg = admin_actions[data]
        if action == 'broadcast':
            context.user_data['awaiting_action'] = 'broadcast'
            await query.message.reply_text(format_blockquote(reply_msg), parse_mode=ParseMode.HTML)
        elif action == 'stats':
            stats = get_user_stats()
            text = (
                f"📊 الإحصائيات:\n"
                f"👥 نشطين: {stats['active_users']}\n"
                f"🚫 محظورين: {stats['banned_users']}\n"
                f"📊 إجمالي: {stats['total_users']}\n"
                f"🆕 جدد اليوم: {stats['new_today']}\n"
                f"📅 أول مستخدم: {stats['first_user_date']}"
            )
            await query.edit_message_text(format_blockquote(text), parse_mode=ParseMode.HTML, reply_markup=query.message.reply_markup)
        elif action == 'lock':
            set_maintenance_mode(True)
            await query.answer("🔒 تم قفل البوت (وضع الصيانة)")
            await admin_command(update, context)
        elif action == 'unlock':
            set_maintenance_mode(False)
            await query.answer("🔓 تم فتح البوت")
            await admin_command(update, context)
        elif action in ('ban', 'unban'):
            context.user_data['awaiting_action'] = action
            await query.message.reply_text(format_blockquote(reply_msg), parse_mode=ParseMode.HTML)
        return

    if data == 'check_sub':
        if await check_subscription(update, context, user_id):
            await query.edit_message_text(
                format_blockquote("✅ تم التحقق من الاشتراك! اضغط /start للمتابعة."),
                parse_mode=ParseMode.HTML
            )
        else:
            await query.answer("❌ لم تشترك بعد.", show_alert=True)
        return

    if data.startswith('yt_result_'):
        idx = int(data.split('_')[2])
        results = context.user_data.get('search_results', [])
        if idx >= len(results):
            await query.edit_message_text(
                format_blockquote("⚠️ انتهت صلاحية هذه النتيجة، الرجاء إجراء بحث جديد."),
                parse_mode=ParseMode.HTML
            )
            return
        selected = results[idx]
        context.user_data['selected_video'] = selected
        keyboard = [
            [
                InlineKeyboardButton("🎹تحميل صوت", callback_data="yt_audio", style="primary"),
                InlineKeyboardButton("✨تحميل فيديو", callback_data="yt_video", style="primary")
            ]
        ]
        await query.edit_message_text(
            format_blockquote(f"🎵 <b>{selected['title']}</b>\n\n🎧 اختر نوع التحميل:"),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data in ('yt_audio', 'yt_video'):
        selected = context.user_data.get('selected_video')
        if not selected:
            await query.edit_message_text(
                format_blockquote("⚠️ لم يتم اختيار فيديو. ابدأ بحثاً جديداً."),
                parse_mode=ParseMode.HTML
            )
            return

        video_url = selected['url']
        await query.edit_message_text(
            format_blockquote("⏳ جاري التحميل... قد يستغرق بعض الوقت."),
            parse_mode=ParseMode.HTML
        )

        if data == 'yt_audio':
            output_template = os.path.join(DOWNLOAD_DIR, f"audio_{int(time.time())}.%(ext)s")
            filepath = await download_youtube_audio(video_url, output_template)
            if filepath:
                filesize = os.path.getsize(filepath) / (1024*1024)
                if filesize > MAX_FILE_SIZE_MB:
                    await query.edit_message_text(
                        format_blockquote(f"⚠️ الملف كبير جداً ({filesize:.1f} ميجابايت). الحد الأقصى هو {MAX_FILE_SIZE_MB} ميجابايت."),
                        parse_mode=ParseMode.HTML
                    )
                    await delete_file_async(filepath)
                    return
                try:
                    with open(filepath, 'rb') as f:
                        await context.bot.send_audio(
                            chat_id,
                            audio=f,
                            title=selected.get('title', 'صوت'),
                            performer=selected.get('uploader', 'مجهول'),
                            duration=selected.get('duration')
                        )
                    await query.edit_message_text(
                        format_blockquote("✅ تم إرسال الصوت بنجاح."),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Error sending audio: {e}")
                    await query.edit_message_text(
                        format_blockquote("❌ حدث خطأ أثناء إرسال الصوت."),
                        parse_mode=ParseMode.HTML
                    )
                finally:
                    await delete_file_async(filepath)
            else:
                await query.edit_message_text(
                    format_blockquote("❌ تعذر تحميل الصوت."),
                    parse_mode=ParseMode.HTML
                )
        elif data == 'yt_video':
            output_template = os.path.join(DOWNLOAD_DIR, f"video_{int(time.time())}.%(ext)s")
            filepath = await download_youtube_video(video_url, output_template)
            if filepath:
                filesize = os.path.getsize(filepath) / (1024*1024)
                if filesize > MAX_FILE_SIZE_MB:
                    await query.edit_message_text(
                        format_blockquote(f"⚠️ الملف كبير جداً ({filesize:.1f} ميجابايت). الحد الأقصى هو {MAX_FILE_SIZE_MB} ميجابايت."),
                        parse_mode=ParseMode.HTML
                    )
                    await delete_file_async(filepath)
                    return
                try:
                    with open(filepath, 'rb') as f:
                        await context.bot.send_video(
                            chat_id,
                            video=f,
                            caption=f"🎬 {selected.get('title', 'فيديو')}",
                            supports_streaming=True
                        )
                    await query.edit_message_text(
                        format_blockquote("✅ تم إرسال الفيديو بنجاح."),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Error sending video: {e}")
                    await query.edit_message_text(
                        format_blockquote("❌ حدث خطأ أثناء إرسال الفيديو."),
                        parse_mode=ParseMode.HTML
                    )
                finally:
                    await delete_file_async(filepath)
            else:
                await query.edit_message_text(
                    format_blockquote("❌ تعذر تحميل الفيديو."),
                    parse_mode=ParseMode.HTML
                )
        return

    if data.startswith('yt_audio_url_') or data.startswith('yt_video_url_'):
        parts = data.split('_', 3)
        if len(parts) < 4:
            await query.edit_message_text(
                format_blockquote("❌ رابط غير صالح."),
                parse_mode=ParseMode.HTML
            )
            return
        url = parts[3]
        await query.edit_message_text(
            format_blockquote("⏳ جاري التحميل..."),
            parse_mode=ParseMode.HTML
        )
        if data.startswith('yt_audio_url_'):
            output_template = os.path.join(DOWNLOAD_DIR, f"audio_{int(time.time())}.%(ext)s")
            filepath = await download_youtube_audio(url, output_template)
            if filepath:
                filesize = os.path.getsize(filepath) / (1024*1024)
                if filesize > MAX_FILE_SIZE_MB:
                    await query.edit_message_text(
                        format_blockquote(f"⚠️ الملف كبير جداً ({filesize:.1f} ميجابايت). الحد الأقصى هو {MAX_FILE_SIZE_MB} ميجابايت."),
                        parse_mode=ParseMode.HTML
                    )
                    await delete_file_async(filepath)
                    return
                try:
                    with open(filepath, 'rb') as f:
                        await context.bot.send_audio(chat_id, audio=f)
                    await query.edit_message_text(
                        format_blockquote("✅ تم إرسال الصوت."),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Error sending audio: {e}")
                    await query.edit_message_text(
                        format_blockquote("❌ حدث خطأ أثناء إرسال الصوت."),
                        parse_mode=ParseMode.HTML
                    )
                finally:
                    await delete_file_async(filepath)
            else:
                await query.edit_message_text(
                    format_blockquote("❌ تعذر تحميل الصوت."),
                    parse_mode=ParseMode.HTML
                )
        else:
            output_template = os.path.join(DOWNLOAD_DIR, f"video_{int(time.time())}.%(ext)s")
            filepath = await download_youtube_video(url, output_template)
            if filepath:
                filesize = os.path.getsize(filepath) / (1024*1024)
                if filesize > MAX_FILE_SIZE_MB:
                    await query.edit_message_text(
                        format_blockquote(f"⚠️ الملف كبير جداً ({filesize:.1f} ميجابايت). الحد الأقصى هو {MAX_FILE_SIZE_MB} ميجابايت."),
                        parse_mode=ParseMode.HTML
                    )
                    await delete_file_async(filepath)
                    return
                try:
                    with open(filepath, 'rb') as f:
                        await context.bot.send_video(chat_id, video=f, supports_streaming=True)
                    await query.edit_message_text(
                        format_blockquote("✅ تم إرسال الفيديو."),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"Error sending video: {e}")
                    await query.edit_message_text(
                        format_blockquote("❌ حدث خطأ أثناء إرسال الفيديو."),
                        parse_mode=ParseMode.HTML
                    )
                finally:
                    await delete_file_async(filepath)
            else:
                await query.edit_message_text(
                    format_blockquote("❌ تعذر تحميل الفيديو."),
                    parse_mode=ParseMode.HTML
                )
        return

    await query.edit_message_text(
        format_blockquote("❌ خيار غير معروف."),
        parse_mode=ParseMode.HTML
    )

# =============================================================================
# BROADCAST HANDLER (admin)
# =============================================================================
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id not in ADMIN_IDS:
        return
    if context.user_data.get('awaiting_action') != 'broadcast':
        return

    msg = update.message
    users = get_all_users()
    success = 0
    fail = 0
    status_msg = await msg.reply_text(format_blockquote("📢 جاري البث..."), parse_mode=ParseMode.HTML)

    for uid in users:
        try:
            if msg.photo:
                await context.bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                await context.bot.send_video(uid, msg.video.file_id, caption=msg.caption)
            elif msg.document:
                await context.bot.send_document(uid, msg.document.file_id, caption=msg.caption)
            elif msg.text:
                await context.bot.send_message(uid, msg.text)
            else:
                await msg.forward(uid)
            success += 1
        except Exception as e:
            logger.warning(f"Broadcast failed to {uid}: {e}")
            fail += 1
        await asyncio.sleep(0.05)
    await status_msg.edit_text(
        format_blockquote(f"✅ تم البث.\nنجاح: {success}\nفشل: {fail}"),
        parse_mode=ParseMode.HTML
    )
    context.user_data['awaiting_action'] = None

# =============================================================================
# ADMIN BAN/UNBAN HANDLERS
# =============================================================================
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id not in ADMIN_IDS:
        return
    action = context.user_data.get('awaiting_action')
    if action not in ('ban', 'unban'):
        return

    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text(format_blockquote("❌ يرجى إرسال ID رقمي."), parse_mode=ParseMode.HTML)
        return
    target = int(text)
    if target in ADMIN_IDS:
        await update.message.reply_text(format_blockquote("❌ لا يمكن حظر/إلغاء حظر الأدمن."), parse_mode=ParseMode.HTML)
        return

    if action == 'ban':
        ban_user(target)
        add_to_ban_list(target)
        await update.message.reply_text(format_blockquote(f"✅ تم حظر المستخدم {target}."), parse_mode=ParseMode.HTML)
    else:
        unban_user(target)
        remove_from_ban_list(target)
        await update.message.reply_text(format_blockquote(f"✅ تم إلغاء حظر المستخدم {target}."), parse_mode=ParseMode.HTML)
    context.user_data['awaiting_action'] = None

# =============================================================================
# ERROR HANDLER
# =============================================================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_user is None:
        return
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                update.effective_chat.id,
                format_blockquote("⚠️ حدث خطأ داخلي. حاول لاحقاً."),
                parse_mode=ParseMode.HTML
            )
    except:
        pass

# =============================================================================
# MAIN
# =============================================================================
def main():
    init_db()

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('admin', admin_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_broadcast_message))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^\d+$'), handle_admin_input))

    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_error_handler(error_handler)

    logger.info("Bot started successfully.")
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)