#MOHA
#!/usr/bin/env python3
import asyncio
import logging
import sqlite3
import time
import json
import re
import sys
import tempfile
import os
import html
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from collections import defaultdict
from io import BytesIO

import psutil
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
    User,
    Chat,
    ChatMember,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

BOT_TOKEN = "8698315055:AAE_fGFuWRojmmYGBAQUHR7vl2XZcHrBVn8"

ADMIN_ID = 6891530912

DEFAULT_FORCED_CHANNELS = ["forzd9", "mouhamed_maa", "mouhamed_maaaa", "Illegal_tools"]

def load_emojis_from_json(filepath: str = "emoji_export.json") -> Dict[str, str]:
    extra_emojis = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data.get('emojis', []):
                    emoji = item.get('emoji', '').strip()
                    cid = item.get('custom_emoji_id')
                    if emoji and cid and emoji not in extra_emojis:
                        extra_emojis[emoji] = cid
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to load emojis from {filepath}: {e}")
    return extra_emojis

CUSTOM_EMOJIS = {
    "👍": "5942913575658985039",
    "🗓": "5257977213772400201",
    "📱": "5987892959968761865",
    "🧧": "5327765312731378129",
    "🌟": "5855044871269651123",
    "📣": "5859264006623072192",
    "🪪": "5863838791038407008",
    "🤒": "5875017993909440887",
    "🤒2": "5875005555684152921",
    "🔶": "5938190352878931973",
    "👑": "5857263604130123563",
    "😂": "5857226886454711367",
    "🚫": "6086741365998227951",
}

EXTRA_EMOJIS = load_emojis_from_json()
for emoji, cid in EXTRA_EMOJIS.items():
    if emoji not in CUSTOM_EMOJIS:
        CUSTOM_EMOJIS[emoji] = cid

def get_custom_emoji_html(emoji: str) -> str:
    if emoji in CUSTOM_EMOJIS:
        return f"<tg-emoji emoji-id='{CUSTOM_EMOJIS[emoji]}'>{emoji}</tg-emoji>"
    return emoji

def get_custom_emoji_html_by_id(custom_emoji_id: str, fallback: str = "🙂") -> str:
    return f"<tg-emoji emoji-id='{custom_emoji_id}'>{fallback}</tg-emoji>"

def utf16_len(s: str) -> int:
    """Return the length of the string in UTF-16 code units (needed for Telegram entity offsets)."""
    return len(s.encode('utf-16-le')) // 2


# ---------------------------------------------------------------------------
# Global bot-message custom emoji theme
# ---------------------------------------------------------------------------
# Use only IDs that already exist in CUSTOM_EMOJIS / emoji_export.json.
# When a visual emoji has no dedicated ID in the user's collection, map it to
# the closest available custom emoji instead of inventing an ID.
MESSAGE_EMOJI_ALIASES = {
    "✅": "👍",
    "☑️": "👍",
    "❌": "🚫",
    "⛔": "🚫",
    "🚫": "🚫",
    "⚠️": "🔶",
    "⚠": "🔶",
    "📢": "📣",
    "📣": "📣",
    "📥": "📱",
    "📤": "📱",
    "📱": "📱",
    "📝": "🧧",
    "📋": "📣",
    "📂": "🧧",
    "📦": "🧧",
    "📨": "📱",
    "🪪": "🪪",
    "👤": "🪪",
    "👥": "🪪",
    "👑": "👑",
    "🌟": "🌟",
    "⭐": "🌟",
    "🔥": "🌟",
    "💡": "🌟",
    "😂": "😂",
    "👍": "👍",
    "🗓️": "🗓",
    "🗓": "🗓",
    "⏰": "🗓",
    "⏱️": "🗓",
    "🔍": "🌟",
    "🔎": "🌟",
    "🔶": "🔶",
    "➕": "👍",
    "➖": "🚫",
    "✏️": "🧧",
    "🗑️": "🚫",
    "🛡️": "🔶",
    "🔄": "🗓",
    "🛠️": "🔶",
    "⚙️": "🔶",
    "📄": "🧧",
    "🖼️": "📱",
    "📭": "🧧",
    "📌": "📣",
    "📞": "📱",
    "🚀": "🌟",
    "❤️": "😂",
    "❤️": "😂",
    "❤": "😂",
    "🙂": "👍",
    "😊": "👍",
    "🥳": "🌟",
    "🤒": "🤒",
}

# Sort longest-first so variants like ✏️ are handled before base symbols.
_MESSAGE_EMOJI_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(MESSAGE_EMOJI_ALIASES, key=len, reverse=True))
)
_TG_EMOJI_BLOCK = re.compile(r"<tg-emoji\b[^>]*>.*?</tg-emoji>", re.DOTALL | re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")


def _replace_message_emojis_outside_tags(text: str) -> str:
    """Convert normal visual emojis in bot HTML to Telegram custom emoji tags.

    Existing <tg-emoji> blocks are protected so we never nest/alter their
    real custom emoji entities.
    """
    if not text:
        return text

    protected = []

    def protect(m):
        protected.append(m.group(0))
        return f"\x00TGEMOJI{len(protected)-1}\x00"

    text = _TG_EMOJI_BLOCK.sub(protect, text)

    def convert_segment(segment: str) -> str:
        # Never rewrite HTML tag names/attributes.
        parts = _HTML_TAG.split(segment)
        tags = _HTML_TAG.findall(segment)
        out_parts = []
        for i, part in enumerate(parts):
            out_parts.append(_MESSAGE_EMOJI_PATTERN.sub(
                lambda m: get_custom_emoji_html(
                    MESSAGE_EMOJI_ALIASES[m.group(0)]
                ),
                part,
            ))
            if i < len(tags):
                out_parts.append(tags[i])
        return ''.join(out_parts)

    text = convert_segment(text)

    for i, block in enumerate(protected):
        text = text.replace(f"\x00TGEMOJI{i}\x00", block)
    return text


def customize_bot_html(text: str) -> str:
    """Apply the custom-emoji visual theme to every bot-authored HTML message."""
    return _replace_message_emojis_outside_tags(text)


def strip_visual_emojis(text: str) -> str:
    """CallbackQuery.answer has no HTML parse mode; avoid regular emoji there."""
    if not text:
        return text
    return _MESSAGE_EMOJI_PATTERN.sub('', text)

# Mapping for button icons (custom emoji IDs)
BUTTON_ICONS = {
    "extract": CUSTOM_EMOJIS.get("📱", ""),
    "extract_pack": CUSTOM_EMOJIS.get("🧧", ""),
    "list_emojis": CUSTOM_EMOJIS.get("📣", ""),
    "create_message": CUSTOM_EMOJIS.get("👑", ""),
    "search": CUSTOM_EMOJIS.get("🌟", ""),
    "categories": CUSTOM_EMOJIS.get("🔶", ""),
    "most_used": CUSTOM_EMOJIS.get("🤒2", ""),
    "favorites": CUSTOM_EMOJIS.get("🌟", ""),
    "stats": CUSTOM_EMOJIS.get("📣", ""),
    "help": CUSTOM_EMOJIS.get("😂", ""),
    "support": CUSTOM_EMOJIS.get("👍", ""),
    "admin_panel": CUSTOM_EMOJIS.get("👑", ""),
    "admin_stats": CUSTOM_EMOJIS.get("📣", ""),
    "admin_users": CUSTOM_EMOJIS.get("🪪", ""),
    "admin_broadcast": CUSTOM_EMOJIS.get("📣", ""),
    "admin_send": CUSTOM_EMOJIS.get("📱", ""),
    "admin_emojis": CUSTOM_EMOJIS.get("🔶", ""),
    "admin_categories": CUSTOM_EMOJIS.get("🔶", ""),
    "admin_admins": CUSTOM_EMOJIS.get("👑", ""),
    "admin_settings": CUSTOM_EMOJIS.get("🔶", ""),
    "admin_logs": CUSTOM_EMOJIS.get("🗓", ""),
    "admin_backup": CUSTOM_EMOJIS.get("🧧", ""),
    "admin_restore": CUSTOM_EMOJIS.get("🔶", ""),
    "admin_export": CUSTOM_EMOJIS.get("📱", ""),
    "admin_import": CUSTOM_EMOJIS.get("📱", ""),
    "admin_system": CUSTOM_EMOJIS.get("🔶", ""),
    "admin_restart": CUSTOM_EMOJIS.get("🔶", ""),
    "admin_change_photo": CUSTOM_EMOJIS.get("📱", ""),
    "admin_change_name": CUSTOM_EMOJIS.get("👑", ""),
    "admin_change_description": CUSTOM_EMOJIS.get("📣", ""),
    "admin_change_short_description": CUSTOM_EMOJIS.get("📣", ""),
    "back": CUSTOM_EMOJIS.get("🚫", ""),
    "check_sub": CUSTOM_EMOJIS.get("✅", ""),
    "edit_draft": CUSTOM_EMOJIS.get("✏️", ""),
    "publish_channel": CUSTOM_EMOJIS.get("📢", ""),
    "publish_now": CUSTOM_EMOJIS.get("📢", ""),
    "delay_post": CUSTOM_EMOJIS.get("⏰", ""),
    "back_publish": CUSTOM_EMOJIS.get("🔙", ""),
    "noop": "",
    "admin_add_emoji": CUSTOM_EMOJIS.get("➕", ""),
    "admin_edit_emoji": CUSTOM_EMOJIS.get("✏️", ""),
    "admin_delete_emoji": CUSTOM_EMOJIS.get("🗑️", ""),
    "admin_search_emoji": CUSTOM_EMOJIS.get("🔍", ""),
    "admin_add_category": CUSTOM_EMOJIS.get("➕", ""),
    "admin_edit_category": CUSTOM_EMOJIS.get("✏️", ""),
    "admin_delete_category": CUSTOM_EMOJIS.get("🗑️", ""),
    "admin_add_admin": CUSTOM_EMOJIS.get("➕", ""),
    "admin_remove_admin": CUSTOM_EMOJIS.get("➖", ""),
    "admin_forced_channels": CUSTOM_EMOJIS.get("📢", ""),
    "admin_spam_settings": CUSTOM_EMOJIS.get("🛡️", ""),
    "user_emoji_list": CUSTOM_EMOJIS.get("📋", ""),
    "main": CUSTOM_EMOJIS.get("🔙", ""),
}

def button_with_icon(text: str, callback_data: str, style: str = "primary") -> InlineKeyboardButton:
    # Telegram button colors: keep the design limited to primary/success/danger.
    style = style if style in {"primary", "success", "danger"} else "primary"
    icon_id = BUTTON_ICONS.get(callback_data, "")
    return InlineKeyboardButton(
        text,
        callback_data=callback_data,
        style=style,
        icon_custom_emoji_id=icon_id if icon_id else None
    )

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

class SpamProtection:
    def __init__(self, limit: int = 1000, interval: int = 60):
        self.limit = limit
        self.interval = interval
        self.user_actions = defaultdict(list)

    def check_and_update(self, user_id: int) -> bool:
        now = time.time()
        self.user_actions[user_id] = [t for t in self.user_actions[user_id] if now - t < self.interval]
        if len(self.user_actions[user_id]) >= self.limit:
            return False
        self.user_actions[user_id].append(now)
        return True

class Database:
    def __init__(self, db_path: str = "emoji_bot.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_admin INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0,
                    joined_date TEXT,
                    last_active TEXT
                )
            """)
            try:
                cur.execute("ALTER TABLE users ADD COLUMN notified INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            cur.execute("""
                CREATE TABLE IF NOT EXISTS emojis (
                    custom_emoji_id TEXT PRIMARY KEY,
                    emoji TEXT NOT NULL,
                    category TEXT DEFAULT 'أخرى',
                    added_by INTEGER,
                    date_added TEXT,
                    last_used TEXT,
                    use_count INTEGER DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER,
                    custom_emoji_id TEXT,
                    added_date TEXT,
                    PRIMARY KEY (user_id, custom_emoji_id),
                    FOREIGN KEY (custom_emoji_id) REFERENCES emojis(custom_emoji_id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('forced_channels', ?)", (json.dumps(DEFAULT_FORCED_CHANNELS),))
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('spam_limit', '5')")
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('spam_interval', '60')")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT,
                    target_id INTEGER,
                    details TEXT,
                    timestamp TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_emojis (
                    user_id INTEGER,
                    custom_emoji_id TEXT,
                    emoji TEXT NOT NULL,
                    source_pack TEXT,
                    added_date TEXT,
                    PRIMARY KEY (user_id, custom_emoji_id),
                    FOREIGN KEY (custom_emoji_id) REFERENCES emojis(custom_emoji_id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS emoji_packs (
                    user_id INTEGER,
                    set_name TEXT,
                    title TEXT,
                    added_date TEXT,
                    PRIMARY KEY (user_id, set_name)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pack_emojis (
                    user_id INTEGER,
                    set_name TEXT,
                    custom_emoji_id TEXT,
                    emoji TEXT NOT NULL,
                    position INTEGER,
                    PRIMARY KEY (user_id, set_name, custom_emoji_id),
                    FOREIGN KEY (custom_emoji_id) REFERENCES emojis(custom_emoji_id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_channels (
                    user_id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    title TEXT,
                    username TEXT,
                    active INTEGER DEFAULT 1,
                    added_date TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    entities_json TEXT,  -- JSON array of {offset, length, custom_emoji_id}
                    send_at REAL NOT NULL,
                    created_at TEXT,
                    status TEXT DEFAULT 'pending'
                )
            """)
            # Add entities_json column if not exists
            try:
                cur.execute("ALTER TABLE scheduled_posts ADD COLUMN entities_json TEXT")
            except sqlite3.OperationalError:
                pass

            cur.execute("CREATE INDEX IF NOT EXISTS idx_emojis_category ON emojis(category)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_emojis_use_count ON emojis(use_count DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_emojis_last_used ON emojis(last_used DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)")
            conn.commit()

    def get_or_create_user(self, user: User):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, joined_date, last_active, notified)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    last_active = excluded.last_active
            """, (
                user.id,
                user.username,
                user.first_name,
                user.last_name,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            conn.commit()
            cur.execute("SELECT notified FROM users WHERE user_id = ?", (user.id,))
            row = cur.fetchone()
            if row and row[0] == 0:
                cur.execute("UPDATE users SET notified = 1 WHERE user_id = ?", (user.id,))
                conn.commit()
                return True
            return False

    def is_user_blocked(self, user_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return row is not None and row[0] == 1

    def block_user(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
            conn.commit()

    def unblock_user(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
            conn.commit()

    def get_all_users(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM users ORDER BY user_id")
            return [dict(row) for row in cur.fetchall()]

    def get_user_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]

    def get_admin_ids(self) -> List[int]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users WHERE is_admin = 1")
            return [row[0] for row in cur.fetchall()]

    def set_admin(self, user_id: int, is_admin: bool = True):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (1 if is_admin else 0, user_id))
            conn.commit()

    def save_emoji(self, custom_emoji_id: str, emoji: str, added_by: int, category: str = 'أخرى'):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT custom_emoji_id FROM emojis WHERE custom_emoji_id = ?", (custom_emoji_id,))
            if cur.fetchone() is None:
                cur.execute("""
                    INSERT INTO emojis (custom_emoji_id, emoji, category, added_by, date_added, last_used, use_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (custom_emoji_id, emoji, category, added_by, datetime.now().isoformat(), datetime.now().isoformat()))
            else:
                cur.execute("""
                    UPDATE emojis
                    SET use_count = use_count + 1,
                        last_used = ?
                    WHERE custom_emoji_id = ?
                """, (datetime.now().isoformat(), custom_emoji_id))
            conn.commit()

    def link_emoji_to_user(self, user_id: int, custom_emoji_id: str, emoji: str, source_pack: str = None):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_emojis (user_id, custom_emoji_id, emoji, source_pack, added_date)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, custom_emoji_id) DO UPDATE SET
                    emoji = excluded.emoji,
                    source_pack = COALESCE(excluded.source_pack, user_emojis.source_pack)
            """, (user_id, custom_emoji_id, emoji or "▫️", source_pack, datetime.now().isoformat()))
            conn.commit()

    def save_pack(self, user_id: int, set_name: str, title: str, items: List[Tuple[str, str]]) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            now = datetime.now().isoformat()
            cur.execute("""
                INSERT INTO emoji_packs (user_id, set_name, title, added_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, set_name) DO UPDATE SET
                    title = excluded.title,
                    added_date = excluded.added_date
            """, (user_id, set_name, title, now))
            cur.execute("DELETE FROM pack_emojis WHERE user_id = ? AND set_name = ?", (user_id, set_name))
            for pos, (cid, emoji) in enumerate(items, 1):
                cur.execute("""
                    INSERT OR REPLACE INTO pack_emojis
                    (user_id, set_name, custom_emoji_id, emoji, position)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, set_name, cid, emoji or "▫️", pos))
                cur.execute("SELECT custom_emoji_id FROM emojis WHERE custom_emoji_id = ?", (cid,))
                if cur.fetchone() is None:
                    cur.execute("""
                        INSERT INTO emojis (custom_emoji_id, emoji, category, added_by, date_added, last_used, use_count)
                        VALUES (?, ?, 'حزم', ?, ?, ?, 1)
                    """, (cid, emoji or "▫️", user_id, now, now))
                else:
                    cur.execute("UPDATE emojis SET use_count = use_count + 1, last_used = ? WHERE custom_emoji_id = ?", (now, cid))
                cur.execute("""
                    INSERT INTO user_emojis (user_id, custom_emoji_id, emoji, source_pack, added_date)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, custom_emoji_id) DO UPDATE SET
                        emoji = excluded.emoji,
                        source_pack = excluded.source_pack
                """, (user_id, cid, emoji or "▫️", set_name, now))
            conn.commit()
            return len(items)

    def get_user_emojis(self, user_id: int, limit: int = 15, offset: int = 0) -> Tuple[List[Dict], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            total = cur.execute("SELECT COUNT(*) FROM user_emojis WHERE user_id = ?", (user_id,)).fetchone()[0]
            cur.execute("""
                SELECT ue.*, e.use_count, e.category
                FROM user_emojis ue
                LEFT JOIN emojis e ON e.custom_emoji_id = ue.custom_emoji_id
                WHERE ue.user_id = ?
                ORDER BY ue.added_date ASC, ue.custom_emoji_id ASC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
            return [dict(row) for row in cur.fetchall()], total

    def get_all_user_emojis(self, user_id: int) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT ue.*, e.use_count, e.category
                FROM user_emojis ue
                LEFT JOIN emojis e ON e.custom_emoji_id = ue.custom_emoji_id
                WHERE ue.user_id = ?
                ORDER BY ue.added_date ASC, ue.custom_emoji_id ASC
            """, (user_id,))
            return [dict(row) for row in cur.fetchall()]

    def save_channel(self, user_id: int, chat_id: int, title: str, username: str = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_channels (user_id, chat_id, title, username, active, added_date)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    title=excluded.title,
                    username=excluded.username,
                    active=1,
                    added_date=excluded.added_date
            """, (user_id, chat_id, title, username, datetime.now().isoformat()))
            conn.commit()

    def get_channel(self, user_id: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM user_channels WHERE user_id = ? AND active = 1", (user_id,)).fetchone()
            return dict(row) if row else None

    def save_scheduled_post(self, user_id: int, chat_id: int, text: str, entities: List[Dict], send_at: float) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            entities_json = json.dumps(entities) if entities else None
            cur.execute("""
                INSERT INTO scheduled_posts (user_id, chat_id, text, entities_json, send_at, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (user_id, chat_id, text, entities_json, send_at, datetime.now().isoformat()))
            conn.commit()
            return cur.lastrowid

    def mark_scheduled_done(self, post_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE scheduled_posts SET status='sent' WHERE id=?", (post_id,))
            conn.commit()

    def get_pending_scheduled_posts(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM scheduled_posts
                WHERE status = 'pending'
                ORDER BY send_at ASC
            """)
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get('entities_json'):
                    try:
                        d['entities'] = json.loads(d['entities_json'])
                    except:
                        d['entities'] = []
                else:
                    d['entities'] = []
                result.append(d)
            return result

    def get_emoji(self, custom_emoji_id: str) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM emojis WHERE custom_emoji_id = ?", (custom_emoji_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_emojis(self, limit: int = 10, offset: int = 0) -> Tuple[List[Dict], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM emojis")
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT * FROM emojis
                ORDER BY date_added DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [dict(row) for row in cur.fetchall()], total

    def get_most_used(self, limit: int = 10) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM emojis
                ORDER BY use_count DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]

    def search_emojis(self, query: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM emojis
                WHERE emoji LIKE ? OR custom_emoji_id LIKE ? OR category LIKE ?
                ORDER BY use_count DESC
            """, (f"%{query}%", f"%{query}%", f"%{query}%"))
            return [dict(row) for row in cur.fetchall()]

    def get_emojis_by_category(self, category: str, limit: int = 10, offset: int = 0) -> Tuple[List[Dict], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM emojis WHERE category = ?", (category,))
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT * FROM emojis
                WHERE category = ?
                ORDER BY date_added DESC
                LIMIT ? OFFSET ?
            """, (category, limit, offset))
            return [dict(row) for row in cur.fetchall()], total

    def update_emoji_category(self, custom_emoji_id: str, new_category: str):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE emojis SET category = ? WHERE custom_emoji_id = ?", (new_category, custom_emoji_id))
            conn.commit()

    def delete_emoji(self, custom_emoji_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM emojis WHERE custom_emoji_id = ?", (custom_emoji_id,))
            conn.commit()

    def add_favorite(self, user_id: int, custom_emoji_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO favorites (user_id, custom_emoji_id, added_date) VALUES (?, ?, ?)",
                            (user_id, custom_emoji_id, datetime.now().isoformat()))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def remove_favorite(self, user_id: int, custom_emoji_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM favorites WHERE user_id = ? AND custom_emoji_id = ?",
                        (user_id, custom_emoji_id))
            conn.commit()

    def get_favorites(self, user_id: int, limit: int = 10, offset: int = 0) -> Tuple[List[Dict], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (user_id,))
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT e.*
                FROM favorites f
                JOIN emojis e ON f.custom_emoji_id = e.custom_emoji_id
                WHERE f.user_id = ?
                ORDER BY f.added_date DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
            return [dict(row) for row in cur.fetchall()], total

    def is_favorite(self, user_id: int, custom_emoji_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM favorites WHERE user_id = ? AND custom_emoji_id = ?",
                        (user_id, custom_emoji_id))
            return cur.fetchone() is not None

    def get_forced_channels(self) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = 'forced_channels'")
            row = cur.fetchone()
            if row:
                return json.loads(row[0])
            return DEFAULT_FORCED_CHANNELS

    def set_forced_channels(self, channels: List[str]):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE settings SET value = ? WHERE key = 'forced_channels'", (json.dumps(channels),))
            conn.commit()

    def get_spam_settings(self) -> Tuple[int, int]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key = 'spam_limit'")
            limit_row = cur.fetchone()
            cur.execute("SELECT value FROM settings WHERE key = 'spam_interval'")
            interval_row = cur.fetchone()
            limit = int(limit_row[0]) if limit_row else 5
            interval = int(interval_row[0]) if interval_row else 60
            return limit, interval

    def set_spam_limit(self, limit: int):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE settings SET value = ? WHERE key = 'spam_limit'", (str(limit),))
            conn.commit()

    def set_spam_interval(self, interval: int):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE settings SET value = ? WHERE key = 'spam_interval'", (str(interval),))
            conn.commit()

    def add_admin_log(self, admin_id: int, action: str, target_id: int = None, details: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (admin_id, action, target_id, details, datetime.now().isoformat()))
            conn.commit()

    def get_admin_logs(self, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM admin_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]

    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            total_users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_emojis = cur.execute("SELECT COUNT(*) FROM emojis").fetchone()[0]
            total_favs = cur.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
            total_uses = cur.execute("SELECT SUM(use_count) FROM emojis").fetchone()[0] or 0
            cur.execute("SELECT category, COUNT(*) FROM emojis GROUP BY category")
            categories = cur.fetchall()
            return {
                "total_users": total_users,
                "total_emojis": total_emojis,
                "total_favorites": total_favs,
                "total_uses": total_uses,
                "categories": categories,
            }

def format_emoji_card(emoji_data: Dict, is_fav: bool = False) -> str:
    emoji = emoji_data['emoji']
    cid = emoji_data['custom_emoji_id']
    cat = emoji_data.get('category', 'أخرى')
    added = emoji_data.get('date_added', 'غير معروف')[:10]
    last = emoji_data.get('last_used', 'غير معروف')[:10]
    uses = emoji_data.get('use_count', 0)
    fav_star = "⭐" if is_fav else ""
    # Use custom emoji tag for display
    emoji_display = get_custom_emoji_html_by_id(cid, emoji)
    return f"""<blockquote>
<strong>الإيموجي:</strong> {emoji_display} {fav_star}
<strong>المعرف:</strong> <code>{cid}</code>
<strong>التصنيف:</strong> {cat}
<strong>أُضيف:</strong> {added}
<strong>آخر استخدام:</strong> {last}
<strong>عدد الاستخدامات:</strong> {uses}
</blockquote>"""

def generate_emoji_codes(cid: str, emoji: str = "😊") -> Tuple[str, str, str, str]:
    html_code = f"<tg-emoji emoji-id='{cid}'>\n</tg-emoji>"
    button_code = f", icon_custom_emoji_id=\"{cid}\""
    php_map = f"=> '{cid}',"
    json_code = json.dumps({"custom_emoji_id": cid, "emoji": emoji}, indent=2)
    return html_code, button_code, php_map, json_code

def build_codes_text(cid: str, emoji: str = "😊") -> str:
    html_code, button_code, php_map, json_code = generate_emoji_codes(cid, emoji)
    return f"""<blockquote>
<strong>Original:</strong> {emoji}
<strong>Custom Emoji ID:</strong> <code>{cid}</code>

<strong>Text Code (HTML):</strong>
<pre>{html_code}</pre>

<strong>Button Code:</strong>
<pre>{button_code}</pre>

<strong>PHP Map:</strong>
<pre>{php_map}</pre>

<strong>JSON:</strong>
<pre>{json_code}</pre>
</blockquote>"""

def build_rows(buttons: List[InlineKeyboardButton], cols: int = 2) -> List[List[InlineKeyboardButton]]:
    return [buttons[i:i+cols] for i in range(0, len(buttons), cols)]

def get_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        button_with_icon("استخراج ID", "extract", "primary"),
        button_with_icon("استخراج حزمة", "extract_pack", "primary"),
        button_with_icon("إنشاء رسالة", "create_message", "success"),
        button_with_icon("قائمة الإيموجيات", "list_emojis", "primary"),
        button_with_icon("بحث", "search", "primary"),
        button_with_icon("تصنيفات", "categories", "primary"),
        button_with_icon("الأكثر استخداماً", "most_used", "primary"),
        button_with_icon("المفضلة", "favorites", "primary"),
        button_with_icon("الإحصائيات", "stats", "primary"),
        button_with_icon("المساعدة", "help", "primary"),
        button_with_icon("الدعم", "support", "primary"),
    ]
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        button_with_icon("إحصائيات كاملة", "admin_stats", "primary"),
        button_with_icon("إدارة المستخدمين", "admin_users", "primary"),
        button_with_icon("إذاعة", "admin_broadcast", "primary"),
        button_with_icon("إرسال لمستخدم", "admin_send", "primary"),
        button_with_icon("إدارة الإيموجيات", "admin_emojis", "primary"),
        button_with_icon("إدارة التصنيفات", "admin_categories", "primary"),
        button_with_icon("إدارة الأدمنز", "admin_admins", "primary"),
        button_with_icon("الإعدادات", "admin_settings", "primary"),
        button_with_icon("السجلات", "admin_logs", "primary"),
        button_with_icon("نسخ احتياطي", "admin_backup", "primary"),
        button_with_icon("استعادة", "admin_restore", "primary"),
        button_with_icon("تصدير البيانات", "admin_export", "primary"),
        button_with_icon("استيراد البيانات", "admin_import", "primary"),
        button_with_icon("معلومات النظام", "admin_system", "primary"),
        button_with_icon("إعادة التشغيل", "admin_restart", "danger"),
        button_with_icon("تغيير صورة البوت", "admin_change_photo", "primary"),
        button_with_icon("تغيير اسم البوت", "admin_change_name", "primary"),
        button_with_icon("تغيير وصف البوت", "admin_change_description", "primary"),
        button_with_icon("تغيير البايو", "admin_change_short_description", "primary"),
        button_with_icon("رجوع", "main", "primary"),
    ]
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_category_keyboard() -> InlineKeyboardMarkup:
    categories = ["وجوه", "قلوب", "تيجان", "شارات", "رموز", "أسهم", "حيوانات", "طعام", "أخرى"]
    buttons = [button_with_icon(f"{cat}", f"cat_{cat}", "primary") for cat in categories]
    buttons.append(button_with_icon("رجوع", "main", "primary"))
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_admin_users_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        button_with_icon("حظر مستخدم", "admin_block_user", "danger"),
        button_with_icon("فك حظر مستخدم", "admin_unblock_user", "success"),
        button_with_icon("قائمة المستخدمين", "admin_list_users", "primary"),
        button_with_icon("رجوع", "admin_panel", "primary"),
    ]
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_admin_emojis_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        button_with_icon("إضافة إيموجي", "admin_add_emoji", "success"),
        button_with_icon("تعديل إيموجي", "admin_edit_emoji", "primary"),
        button_with_icon("حذف إيموجي", "admin_delete_emoji", "danger"),
        button_with_icon("بحث إيموجي", "admin_search_emoji", "primary"),
        button_with_icon("رجوع", "admin_panel", "primary"),
    ]
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_admin_categories_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        button_with_icon("إضافة تصنيف", "admin_add_category", "success"),
        button_with_icon("تعديل تصنيف", "admin_edit_category", "primary"),
        button_with_icon("حذف تصنيف", "admin_delete_category", "danger"),
        button_with_icon("رجوع", "admin_panel", "primary"),
    ]
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_admin_settings_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        button_with_icon("إدارة القنوات الإجبارية", "admin_forced_channels", "primary"),
        button_with_icon("ضبط الحماية من التكرار", "admin_spam_settings", "primary"),
        button_with_icon("رجوع", "admin_panel", "primary"),
    ]
    rows = build_rows(buttons, 2)
    return InlineKeyboardMarkup(rows)

def get_pagination_keyboard(page: int, total_pages: int, callback_prefix: str, extra_data: str = "") -> InlineKeyboardMarkup:
    buttons = []
    if page > 0:
        buttons.append(button_with_icon("السابق", f"{callback_prefix}_{page-1}_{extra_data}", "primary"))
    buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop", style="primary"))
    if page < total_pages - 1:
        buttons.append(button_with_icon("التالي", f"{callback_prefix}_{page+1}_{extra_data}", "primary"))
    return InlineKeyboardMarkup([buttons, [button_with_icon("رجوع", "main", "primary")]])

class EmojiBot:
    def __init__(self, application: Application, db: Database):
        self.app = application
        self.db = db
        self.spam = SpamProtection()
        self._register_handlers()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("admin", self.admin_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        callbacks = [
            "main", "extract", "extract_pack", "create_message",
            "user_emoji_list", "user_emoji_list_\\d+",
            "pack_page_\\d+", "edit_draft", "publish_channel",
            "publish_now", "delay_post", "back_publish", "cancel_flow",
            "list_emojis",
            "list_emojis_\\d+",
            "list_emojis_\\d+_.*",
            "search",
            "categories", "cat_.*", "most_used",
            "favorites",
            "fav_\\d+",
            "fav_\\d+_.*",
            "stats", "help", "code_.*", "add_fav_.*", "rem_fav_.*", "emoji_detail_.*",
            "admin_panel", "admin_stats", "admin_users", "admin_block_user",
            "admin_unblock_user", "admin_list_users", "admin_broadcast", "admin_send",
            "admin_emojis", "admin_add_emoji", "admin_edit_emoji", "admin_delete_emoji",
            "admin_search_emoji", "admin_categories", "admin_add_category",
            "admin_edit_category", "admin_delete_category", "admin_admins",
            "admin_add_admin", "admin_remove_admin",
            "admin_settings", "admin_forced_channels", "admin_spam_settings",
            "admin_logs", "admin_backup", "admin_restore", "admin_export",
            "admin_import", "admin_system", "admin_restart", "noop", "check_sub",
            "support",
            "admin_change_photo", "admin_change_name", "admin_change_description", "admin_change_short_description"
        ]
        for pattern in callbacks:
            self.app.add_handler(CallbackQueryHandler(self.handle_callback, pattern=f"^{pattern}$"))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return
        is_new = self.db.get_or_create_user(user)
        
        if is_new:
            await self._notify_admin_new_user(update, context)

        welcome_text = self._get_welcome_text(user)
        main_kb = get_main_keyboard()
        keyboard = list(main_kb.inline_keyboard)
        if user.id == ADMIN_ID:
            keyboard.append([button_with_icon("لوحة الأدمن", "admin_panel", "primary")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if not await self._check_forced_subscription(update, context):
            return

        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                await update.message.reply_photo(
                    photo=file_id,
                    caption=welcome_text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                await self._reply_html(update.message, 
                    welcome_text,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send welcome with photo: {e}")
            await self._reply_html(update.message, 
                welcome_text,
                reply_markup=reply_markup
            )

    def _get_welcome_text(self, user: User) -> str:
        welcome = f"""<blockquote>
{get_custom_emoji_html('👑')} <b>مرحباً بك في بوت استخراج الإيموجيات المميزة!</b>
{get_custom_emoji_html('🌟')} يمكنك استخدام البوت لاستخراج ومعرفة معرفات الإيموجيات المميزة.

{get_custom_emoji_html('📱')} <b>المطور:</b> @mouhamed_ma
{get_custom_emoji_html('📣')} <b>القنوات المطلوبة:</b>
{chr(10).join([f'• @{ch}' for ch in self.db.get_forced_channels()])}

{get_custom_emoji_html('😂')} استخدم الأزرار أدناه للبدء.
</blockquote>"""
        return welcome

    async def _notify_admin_new_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        photo_file_id = None
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0:
                photo_file_id = photos.photos[0][-1].file_id
        except Exception as e:
            logger.error(f"Failed to get user photo: {e}")

        text = f"""<blockquote>
{get_custom_emoji_html('📣')} <b>مستخدم جديد دخل البوت!</b>

{get_custom_emoji_html('🪪')} <b>الاسم:</b> {user.first_name} {user.last_name or ''}
{get_custom_emoji_html('📱')} <b>اليوزر:</b> @{user.username if user.username else 'لا يوجد'}
{get_custom_emoji_html('🗓')} <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{get_custom_emoji_html('🔶')} <b>المعرف:</b> <code>{user.id}</code>
</blockquote>"""
        try:
            if photo_file_id:
                await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file_id, caption=customize_bot_html(text), parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=ADMIN_ID, text=customize_bot_html(text), parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to send new user notification: {e}")

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            await self._reply_text(update.message, "⛔ غير مصرح لك.")
            return
        await self._send_admin_panel(update, context)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return
        self.db.get_or_create_user(user)

        if user.id != ADMIN_ID and not await self._check_forced_subscription(update, context):
            return

        if user.id != ADMIN_ID and not self.spam.check_and_update(user.id):
            await self._reply_text(update.message, "🚫 تم تجاوز حد الرسائل. الرجاء الانتظار.")
            return

        if self.db.is_user_blocked(user.id) and user.id != ADMIN_ID:
            await self._reply_text(update.message, "⛔ أنت محظور من استخدام البوت.")
            return

        message = update.message
        if not message:
            return

        # استقبال رسالة محولة من قناة أثناء تفعيل قناة النشر
        if context.user_data.get('user_flow') == 'awaiting_channel_forward':
            if await self._process_channel_forward(update, context):
                return

        # استخراج حزمة من رابط addemoji حتى لو لم يضغط المستخدم الزر
        if message.text and 't.me/addemoji/' in message.text:
            pack_name = self._extract_pack_name(message.text)
            if pack_name:
                await self._extract_emoji_pack(update, context, pack_name)
                return

        if not message.text:
            return

        if context.user_data.get('search_state') == 'awaiting_search':
            query = message.text
            context.user_data.pop('search_state')
            await self._perform_search(update, context, query)
            return

        # تدفقات المستخدم الجديدة
        if context.user_data.get('user_flow'):
            handled = await self._process_user_text_flow(update, context)
            if handled:
                return

        # تحويل الرسائل التي تحتوي أرقام الإيموجيات تلقائياً بدون أي أزرار
        # إذا كان لدى المستخدم إيموجيات محفوظة.
        if re.search(r'(?<!\w)[0-9٠-٩]+(?!\w)', message.text) and self.db.get_all_user_emojis(user.id):
            await self._convert_and_send_message(update, context, message.text.strip())
            return

        if self._is_admin(update) and context.user_data.get('admin_action'):
            await self._process_admin_text(update, context)
            return

        custom_emojis = []
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntity.CUSTOM_EMOJI:
                    cid = entity.custom_emoji_id
                    emoji_text = message.text[entity.offset:entity.offset+entity.length] if entity.length else ""
                    custom_emojis.append((emoji_text, cid))

        if not custom_emojis:
            await self._reply_html(update.message, 
                "<blockquote>⚠️ لم يتم العثور على أي إيموجي مميز في الرسالة.\n"
                "يرجى إرسال إيموجي Telegram المميز فقط، أو رابط حزمة /addemoji.</blockquote>"
            )
            return

        saved = []
        for emoji_text, cid in custom_emojis:
            self.db.save_emoji(cid, emoji_text, user.id, 'أخرى')
            self.db.link_emoji_to_user(user.id, cid, emoji_text)
            saved.append((emoji_text, cid))

        if len(saved) == 1:
            emoji_text, cid = saved[0]
            await self._show_emoji_card(update, context, cid, emoji_text)
        else:
            lines = []
            for i, (emoji_text, cid) in enumerate(saved, 1):
                emoji_display = get_custom_emoji_html_by_id(cid, emoji_text)
                lines.append(f"{i}. {emoji_display} – <code>{cid}</code>")
            text = "<blockquote>تم استخراج الإيموجيات التالية:\n" + "\n".join(lines) + \
                   "\n\nاضغط على أحدها للحصول على التفاصيل.</blockquote>"
            keyboard = []
            for emoji_text, cid in saved:
                keyboard.append([InlineKeyboardButton(
                    f"{emoji_text} {cid[:6]}...", callback_data=f"emoji_detail_{cid}")])
            keyboard.append([button_with_icon("رجوع", "main", "primary")])
            await self._reply_html(update.message, text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_admin(update):
            return
        if context.user_data.get('admin_action') == 'change_photo':
            photo_file = await update.message.photo[-1].get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                await photo_file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            try:
                with open(tmp_path, 'rb') as f:
                    await context.bot.set_my_photo(photo=InputFile(f))
                await self._reply_html(update.message, "<blockquote>✅ تم تغيير صورة البوت بنجاح.</blockquote>")
                self.db.add_admin_log(update.effective_user.id, 'change_photo', details="Changed bot photo")
            except Exception as e:
                await self._reply_html(update.message, f"<blockquote>❌ فشل تغيير الصورة: {e}</blockquote>")
            finally:
                os.unlink(tmp_path)
            context.user_data.pop('admin_action', None)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await self._answer_query(query, )

        user = update.effective_user
        if not user:
            return
        self.db.get_or_create_user(user)

        if user.id != ADMIN_ID and not await self._check_forced_subscription(update, context):
            return

        if user.id != ADMIN_ID and not self.spam.check_and_update(user.id):
            await self._edit_query_text(query, "🚫 تم تجاوز حد الطلبات. الرجاء الانتظار.")
            return

        if self.db.is_user_blocked(user.id) and user.id != ADMIN_ID:
            await self._edit_query_text(query, "⛔ أنت محظور.")
            return

        data = query.data
        if data == "main":
            await self._send_main_menu(update, context)
        elif data == "extract":
            await self._send_extract_instruction(update, context)
        elif data == "extract_pack":
            await self._prompt_pack_url(update, context)
        elif data == "create_message":
            await self._show_create_message_menu(update, context)
        elif data == "user_emoji_list":
            await self._list_user_emojis(update, context, 0)
        elif data.startswith("user_emoji_list_"):
            try:
                await self._list_user_emojis(update, context, int(data.rsplit("_", 1)[1]))
            except ValueError:
                pass
        elif data.startswith("pack_page_"):
            try:
                await self._show_pack_page(update, context, int(data.rsplit("_", 1)[1]))
            except ValueError:
                pass
        elif data == "edit_draft":
            await self._prompt_message_edit(update, context)
        elif data == "publish_channel":
            await self._prompt_channel_activation(update, context)
        elif data == "publish_now":
            await self._publish_now(update, context)
        elif data == "delay_post":
            await self._prompt_delay(update, context)
        elif data == "back_publish":
            await self._show_publish_options(update, context)
        elif data == "cancel_flow":
            context.user_data.pop('user_flow', None)
            await self._send_main_menu(update, context)
        elif data == "list_emojis":
            await self._list_emojis(update, context, page=0)
        elif data.startswith("list_emojis_"):
            parts = data.split("_")
            if len(parts) >= 3:
                try:
                    page = int(parts[2])
                    await self._list_emojis(update, context, page=page)
                except ValueError:
                    pass
        elif data == "search":
            await self._search_prompt(update, context)
        elif data == "categories":
            await self._show_categories(update, context)
        elif data.startswith("cat_"):
            category = data[4:]
            await self._list_by_category(update, context, category, page=0)
        elif data == "most_used":
            await self._show_most_used(update, context)
        elif data == "favorites":
            await self._list_favorites(update, context, page=0)
        elif data.startswith("fav_"):
            parts = data.split("_")
            if len(parts) >= 2:
                try:
                    page = int(parts[1])
                    await self._list_favorites(update, context, page=page)
                except ValueError:
                    pass
        elif data == "stats":
            await self._show_stats(update, context)
        elif data == "help":
            await self._show_help(update, context)
        elif data.startswith("code_"):
            parts = data.split("_")
            if len(parts) == 3:
                code_type = parts[1]
                cid = parts[2]
                await self._show_code(update, context, cid, code_type)
        elif data.startswith("emoji_detail_"):
            cid = data.split("_")[2]
            emoji_data = self.db.get_emoji(cid)
            if emoji_data:
                await self._show_emoji_card(update, context, cid, emoji_data['emoji'])
            else:
                await self._edit_query_text(query, "⚠️ لم يتم العثور على الإيموجي.")
        elif data.startswith("add_fav_"):
            cid = data.split("_")[2]
            if self.db.add_favorite(user.id, cid):
                await self._answer_query(query, "✅ تمت الإضافة إلى المفضلة.")
                await self._refresh_current_view(update, context)
            else:
                await self._answer_query(query, "⚠️ موجود بالفعل في المفضلة.")
        elif data.startswith("rem_fav_"):
            cid = data.split("_")[2]
            self.db.remove_favorite(user.id, cid)
            await self._answer_query(query, "❌ تمت الإزالة من المفضلة.")
            await self._refresh_current_view(update, context)
        elif data == "admin_panel":
            await self._send_admin_panel(update, context)
        elif data == "admin_stats":
            await self._admin_stats(update, context)
        elif data == "admin_users":
            await self._admin_users_menu(update, context)
        elif data == "admin_block_user":
            await self._admin_block_user_prompt(update, context)
        elif data == "admin_unblock_user":
            await self._admin_unblock_user_prompt(update, context)
        elif data == "admin_list_users":
            await self._admin_list_users(update, context)
        elif data == "admin_broadcast":
            await self._admin_broadcast_prompt(update, context)
        elif data == "admin_send":
            await self._admin_send_prompt(update, context)
        elif data == "admin_emojis":
            await self._admin_emojis_menu(update, context)
        elif data == "admin_add_emoji":
            await self._admin_add_emoji_prompt(update, context)
        elif data == "admin_edit_emoji":
            await self._admin_edit_emoji_prompt(update, context)
        elif data == "admin_delete_emoji":
            await self._admin_delete_emoji_prompt(update, context)
        elif data == "admin_search_emoji":
            await self._admin_search_emoji_prompt(update, context)
        elif data == "admin_categories":
            await self._admin_categories_menu(update, context)
        elif data == "admin_add_category":
            await self._admin_add_category_prompt(update, context)
        elif data == "admin_edit_category":
            await self._admin_edit_category_prompt(update, context)
        elif data == "admin_delete_category":
            await self._admin_delete_category_prompt(update, context)
        elif data == "admin_admins":
            await self._admin_admins_menu(update, context)
        elif data == "admin_add_admin":
            await self._admin_add_admin_prompt(update, context)
        elif data == "admin_remove_admin":
            await self._admin_remove_admin_prompt(update, context)
        elif data == "admin_settings":
            await self._admin_settings_menu(update, context)
        elif data == "admin_forced_channels":
            await self._admin_forced_channels_prompt(update, context)
        elif data == "admin_spam_settings":
            await self._admin_spam_settings_prompt(update, context)
        elif data == "admin_logs":
            await self._admin_logs(update, context)
        elif data == "admin_backup":
            await self._admin_backup(update, context)
        elif data == "admin_restore":
            await self._admin_restore_prompt(update, context)
        elif data == "admin_export":
            await self._admin_export(update, context)
        elif data == "admin_import":
            await self._admin_import_prompt(update, context)
        elif data == "admin_system":
            await self._admin_system(update, context)
        elif data == "admin_restart":
            await self._admin_restart(update, context)
        elif data == "check_sub":
            await self._check_sub_callback(update, context)
        elif data == "support":
            await self._show_support(update, context)
        elif data == "admin_change_photo":
            await self._admin_change_photo_prompt(update, context)
        elif data == "admin_change_name":
            await self._admin_change_name_prompt(update, context)
        elif data == "admin_change_description":
            await self._admin_change_description_prompt(update, context)
        elif data == "admin_change_short_description":
            await self._admin_change_short_description_prompt(update, context)
        elif data == "noop":
            pass

    @staticmethod
    def _extract_pack_name(value: str) -> Optional[str]:
        m = re.search(r'(?:https?://)?t\.me/addemoji/([A-Za-z0-9_]+)', value)
        return m.group(1) if m else None

    async def _prompt_pack_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['user_flow'] = 'awaiting_pack_url'
        text = "<blockquote>📦 أرسل رابط حزمة الإيموجي المميز، مثال:\n<code>https://t.me/addemoji/Mahsum_EMOJI_by_fStikBot</code></blockquote>"
        kb = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, kb)

    async def _extract_emoji_pack(self, update: Update, context: ContextTypes.DEFAULT_TYPE, pack_name: str):
        user = update.effective_user
        try:
            pack = await context.bot.get_sticker_set(pack_name)
        except Exception as e:
            logger.exception("Failed to fetch emoji pack")
            await self._reply_html(update.message, 
                f"<blockquote>❌ تعذر جلب الحزمة.\n<code>{html.escape(str(e))}</code></blockquote>"
            )
            context.user_data.pop('user_flow', None)
            return

        if getattr(pack, 'sticker_type', None) != 'custom_emoji':
            await self._reply_html(update.message, "<blockquote>⚠️ الرابط لا يشير إلى حزمة Custom Emoji.</blockquote>")
            context.user_data.pop('user_flow', None)
            return

        items = []
        for sticker in getattr(pack, 'stickers', []) or []:
            cid = getattr(sticker, 'custom_emoji_id', None)
            if cid:
                items.append((cid, getattr(sticker, 'emoji', None) or "▫️"))

        if not items:
            await self._reply_html(update.message, "<blockquote>📭 الحزمة لا تحتوي على إيموجيات مميزة قابلة للاستخراج.</blockquote>")
            context.user_data.pop('user_flow', None)
            return

        count = self.db.save_pack(user.id, pack.name, pack.title, items)
        context.user_data['current_pack'] = {
            'name': pack.name, 'title': pack.title, 'items': items
        }
        context.user_data['user_flow'] = None
        await self._reply_html(update.message, 
            f"<blockquote>✅ تم استخراج الحزمة بنجاح!\n"
            f"📦 <b>{html.escape(pack.title)}</b>\n"
            f"🔢 عدد الإيموجيات: <b>{count}</b>\n\n"
            "سيتم عرضها على صفحات، 15 إيموجي في كل صفحة.</blockquote>"
        )
        await self._show_pack_page(update, context, 0)

    async def _show_pack_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
        current = context.user_data.get('current_pack')
        if not current:
            await self._reply_or_edit(update, context, "<blockquote>⚠️ لا توجد حزمة مفتوحة حالياً.</blockquote>")
            return
        items = current['items']
        per_page = 15
        total_pages = (len(items) + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        start = page * per_page
        current_page = items[start:start+per_page]
        lines = []
        for i, (cid, emoji) in enumerate(current_page, 1):
            emoji_display = get_custom_emoji_html_by_id(cid, emoji or "▫️")
            lines.append(f"{start+i}. {emoji_display} — <code>{cid}</code>")
        text = f"<blockquote>📦 <b>{html.escape(current['title'])}</b>\n\n" + \
               "\n".join(lines) + f"\n\nالصفحة {page+1}/{total_pages}</blockquote>"
        nav = []
        if page > 0:
            nav.append(button_with_icon("السابق", f"pack_page_{page-1}", "primary"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop", style="primary"))
        if page < total_pages - 1:
            nav.append(button_with_icon("التالي", f"pack_page_{page+1}", "primary"))
        kb = [nav, [button_with_icon("إنشاء رسالة", "create_message", "success")],
              [button_with_icon("رجوع", "main", "primary")]]
        await self._reply_or_edit(update, context, text, InlineKeyboardMarkup(kb))

    async def _show_create_message_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = "<blockquote>📝 <b>إنشاء رسالة</b>\n\nاختر ما تريد فعله:</blockquote>"
        kb = InlineKeyboardMarkup([
            [button_with_icon("قائمة الإيموجي", "user_emoji_list", "primary")],
            [button_with_icon("تعديل رسالة", "edit_draft", "primary")],
            [button_with_icon("رجوع", "main", "primary")]
        ])
        await self._reply_or_edit(update, context, text, kb)

    async def _list_user_emojis(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        user = update.effective_user
        emojis, total = self.db.get_user_emojis(user.id, 15, page * 15)
        if not emojis:
            await self._reply_or_edit(
                update, context,
                "<blockquote>📭 لا توجد إيموجيات محفوظة لك حالياً.\nأرسل إيموجياً مميزاً أو استخرج حزمة أولاً.</blockquote>",
                InlineKeyboardMarkup([[button_with_icon("رجوع", "create_message", "primary")]])
            )
            return
        total_pages = (total + 14) // 15
        start = page * 15 + 1
        lines = []
        for i, item in enumerate(emojis, start):
            emoji_display = get_custom_emoji_html_by_id(item['custom_emoji_id'], item['emoji'] or "▫️")
            pack = f" • 📦 {html.escape(item['source_pack'])}" if item.get('source_pack') else ""
            lines.append(f"{i}. {emoji_display} — <code>{item['custom_emoji_id']}</code>{pack}")
        text = "<blockquote>📋 <b>قائمة إيموجياتك</b>\n\n" + "\n".join(lines) + \
               f"\n\nالترقيم هنا هو نفسه الذي ستستخدمه داخل الرسالة.\nالصفحة {page+1}/{total_pages}</blockquote>"
        nav = []
        if page > 0:
            nav.append(button_with_icon("السابق", f"user_emoji_list_{page-1}", "primary"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop", style="primary"))
        if page < total_pages - 1:
            nav.append(button_with_icon("التالي", f"user_emoji_list_{page+1}", "primary"))
        kb = [nav, [button_with_icon("تعديل رسالة", "edit_draft", "primary")],
              [button_with_icon("رجوع", "create_message", "primary")]]
        await self._reply_or_edit(update, context, text, InlineKeyboardMarkup(kb))

    async def _prompt_message_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.db.get_all_user_emojis(update.effective_user.id):
            await self._reply_or_edit(
                update, context,
                "<blockquote>⚠️ لا توجد إيموجيات محفوظة لك. استخرج حزمة أو أرسل إيموجيات أولاً.</blockquote>",
                InlineKeyboardMarkup([[button_with_icon("رجوع", "create_message", "primary")]])
            )
            return
        context.user_data['user_flow'] = 'awaiting_draft_text'
        text = (
            "<blockquote>✏️ أرسل الرسالة التي تريد تحويلها.\n\n"
            "استخدم الأرقام 1، 2، 3... مكان الإيموجيات.\n"
            "مثال: <code>هذا نص 1 ثم هذا 2</code>\n\n"
            "سيتم استبدال الأرقام المطابقة تلقائياً بالإيموجيات من قائمتك.</blockquote>"
        )
        kb = InlineKeyboardMarkup([[button_with_icon("إلغاء", "create_message", "primary")]])
        await self._reply_or_edit(update, context, text, kb)

    async def _process_user_text_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        flow = context.user_data.get('user_flow')
        text = update.message.text.strip()

        if flow == 'awaiting_pack_url':
            pack_name = self._extract_pack_name(text)
            if not pack_name:
                await self._reply_html(update.message, "<blockquote>⚠️ الرابط غير صحيح. أرسل رابط t.me/addemoji/... صالحاً.</blockquote>")
                return True
            await self._extract_emoji_pack(update, context, pack_name)
            return True

        if flow == 'awaiting_draft_text':
            await self._convert_and_send_message(update, context, text)
            return True

        if flow == 'awaiting_channel_forward':
            # forwarded message is handled earlier in handle_message
            return False

        if flow == 'awaiting_delay':
            if not text.isdigit():
                await self._reply_html(update.message, "<blockquote>⚠️ أرسل عدد الدقائق كرقم، مثال: <code>30</code>.</blockquote>")
                return True
            minutes = int(text)
            if minutes < 1 or minutes > 10080:
                await self._reply_html(update.message, "<blockquote>⚠️ أدخل مدة بين 1 دقيقة و7 أيام.</blockquote>")
                return True
            await self._schedule_post(update, context, minutes)
            return True

        return False

    @staticmethod
    def _normalize_number(s: str) -> int:
        trans = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        return int(s.translate(trans))

    async def _convert_and_send_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, source: str) -> None:
        """
        تحويل أرقام الإيموجيات إلى Custom Emoji وعرض الرسالة فقط بدون أزرار،
        ثم إرسال تعليمات النشر عبر @chelpbot أسفلها.
        """
        user = update.effective_user
        plain_text, entities, html_preview, error = self._replace_numbers_with_emojis(user.id, source)
        context.user_data['user_flow'] = None

        if error:
            await self._reply_html(update.message, f"<blockquote>⚠️ {html.escape(error)}</blockquote>")
            return

        if not entities:
            await self._reply_html(update.message, 
                "<blockquote>⚠️ لم أجد أي رقم مرتبط بإيموجي مميز في الرسالة.\n"
                "استخدم الأرقام الموجودة في قائمة الإيموجيات المحفوظة لديك.</blockquote>"
            )
            return

        # الرسالة المحولة نفسها فقط — بدون أي أزرار أو إضافات.
        await self._reply_html(update.message, html_preview)

        instructions = (
            "<blockquote>"
            "إذا كنت تريد نشر الرسالة في القناة قم برفع البوت هاذا الى قناتك @chelpbot "
            "ثم ادخل البوت نفسه اضغط إنشاء منشور ثم التالي ثم قم بتوجيه الرسالة من البوت الحالي "
            "الى البوت هاذا @chelpbot ( الرسالة التي تحتوي على ايموجي مميز ) بدون اخفاء اسم المرسل "
            "ثم اضغط زر بدون ازرار ثم ارسال المنشور ثم اختر القناة التي رفعت فيها البوت ادمن ثم اضغط تأكيد الإرسال"
            "</blockquote>"
        )
        await self._reply_html(update.message, instructions)

    def _replace_numbers_with_emojis(self, user_id: int, source: str) -> Tuple[str, List[Dict], str, Optional[str]]:
        """
        Replaces numbers in the source text with custom emojis from the user's list.
        Returns:
          plain_text: the final text with fallback emojis (for entities)
          entities: list of dicts with 'offset', 'length', 'custom_emoji_id' (UTF-16 offsets)
          html_preview: HTML string with <tg-emoji> tags (for preview only)
          error: error message if any
        """
        items = self.db.get_all_user_emojis(user_id)
        if not items:
            return source, [], source, "لا توجد إيموجيات محفوظة لك."

        # We'll build plain_text and also track the positions of replacements for entity creation.
        # We'll also build html_preview by inserting tg-emoji tags.
        pattern = re.compile(r'(?<!\w)([0-9٠-٩]+)(?!\w)')
        pos = 0
        plain_parts = []
        html_parts = []
        # Store (start_index_in_plain, end_index_in_plain, custom_emoji_id) for each replacement
        replacements = []
        current_plain_len = 0

        for match in pattern.finditer(source):
            # Add text before match
            before = source[pos:match.start()]
            plain_parts.append(before)
            html_parts.append(html.escape(before))
            current_plain_len += len(before)

            # Number
            num_str = match.group(1)
            n = self._normalize_number(num_str)
            if 1 <= n <= len(items):
                item = items[n-1]
                cid = item['custom_emoji_id']
                fallback = item['emoji'] or "▫️"
                # Add fallback to plain text
                plain_parts.append(fallback)
                start_index = current_plain_len
                end_index = current_plain_len + len(fallback)
                replacements.append((start_index, end_index, cid))
                current_plain_len += len(fallback)
                # HTML: use tg-emoji tag
                html_parts.append(f"<tg-emoji emoji-id='{cid}'>{fallback}</tg-emoji>")
            else:
                # number not mapped, keep as is (escaped)
                plain_parts.append(num_str)
                html_parts.append(html.escape(num_str))
                current_plain_len += len(num_str)
            pos = match.end()

        # Add remaining text
        if pos < len(source):
            remainder = source[pos:]
            plain_parts.append(remainder)
            html_parts.append(html.escape(remainder))

        plain_text = ''.join(plain_parts)
        html_preview = ''.join(html_parts)

        # Build entities with UTF-16 offsets
        entities = []
        for start_index, end_index, cid in replacements:
            # Calculate UTF-16 offsets for the slice
            offset = utf16_len(plain_text[:start_index])
            length = utf16_len(plain_text[start_index:end_index])
            entities.append({
                'offset': offset,
                'length': length,
                'custom_emoji_id': cid
            })

        return plain_text, entities, html_preview, None

    def _publish_keyboard(self):
        return InlineKeyboardMarkup([
            [button_with_icon("النشر في القناة", "publish_channel", "success")],
            [button_with_icon("رجوع", "create_message", "primary")]
        ])

    async def _prompt_channel_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['user_flow'] = 'awaiting_channel_forward'
        text = (
            "<blockquote>📢 <b>تفعيل قناة النشر</b>\n\n"
            "1) أضف البوت إلى القناة كـ <b>مشرف</b> مع كامل الصلاحيات اللازمة للنشر.\n"
            "2) بعد ذلك قم بتحويل أي رسالة من نفس القناة إلى البوت.\n\n"
            "سيقوم البوت بفحص الصلاحيات وتفعيل القناة تلقائياً.</blockquote>"
        )
        kb = InlineKeyboardMarkup([[button_with_icon("رجوع", "back_publish", "primary")]])
        await self._reply_or_edit(update, context, text, kb)

    async def _process_channel_forward(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        msg = update.message
        origin = getattr(msg, 'forward_origin', None)
        chat = None
        if origin and getattr(origin, 'chat', None):
            chat = origin.chat
        elif getattr(msg, 'forward_from_chat', None):
            chat = msg.forward_from_chat

        if not chat or getattr(chat, 'type', None) != 'channel':
            await self._reply_html(msg, "<blockquote>⚠️ لم أتعرف على رسالة قناة. أرسل رسالة محولة مباشرة من القناة المطلوبة.</blockquote>")
            return True

        bot_user = await context.bot.get_me()
        try:
            member = await context.bot.get_chat_member(chat.id, bot_user.id)
        except Exception as e:
            await self._reply_html(msg, 
                f"<blockquote>❌ لم أستطع التحقق من صلاحيات البوت في القناة.\n"
                f"تأكد من إضافة البوت كـمشرف ثم أعد تحويل الرسالة.\n\n"
                f"<code>{html.escape(str(e))}</code></blockquote>"
            )
            return True

        missing = []
        status = getattr(member, 'status', '')
        if status not in ('administrator', 'creator'):
            missing.append("صلاحية مشرف")
        elif status == 'administrator':
            required_rights = [
                ('can_post_messages', 'نشر الرسائل'),
                ('can_edit_messages', 'تعديل الرسائل'),
                ('can_delete_messages', 'حذف الرسائل'),
                ('can_change_info', 'تغيير معلومات القناة'),
                ('can_invite_users', 'دعوة المستخدمين'),
                ('can_promote_members', 'إضافة/تعديل المشرفين'),
            ]
            for attr, label in required_rights:
                if hasattr(member, attr) and getattr(member, attr) is False:
                    missing.append(label)
        if missing:
            await self._reply_html(msg, 
                "<blockquote>❌ البوت غير جاهز للنشر.\n"
                "المطلوب: رفع البوت مشرفاً ومنحه صلاحية إرسال الرسائل على الأقل.\n\n"
                + "\n".join(f"• {x}" for x in missing) + "</blockquote>"
            )
            return True

        username = getattr(chat, 'username', None)
        title = getattr(chat, 'title', None) or username or str(chat.id)
        self.db.save_channel(update.effective_user.id, chat.id, title, username)
        context.user_data['channel_id'] = chat.id
        context.user_data['user_flow'] = None
        await self._reply_html(msg, 
            f"<blockquote>✅ تم تفعيل قناة النشر:\n📢 <b>{html.escape(title)}</b>\n\n"
            "القناة جاهزة لنشر رسالتك.</blockquote>",
            reply_markup=self._publish_options_keyboard()
        )
        return True

    def _publish_options_keyboard(self):
        return InlineKeyboardMarkup([
            [button_with_icon("النشر الآن", "publish_now", "success")],
            [button_with_icon("تعديل الرسالة", "edit_draft", "primary")],
            [button_with_icon("تأجيل", "delay_post", "primary")],
            [button_with_icon("رجوع", "back_publish", "primary")]
        ])

    async def _show_publish_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get('draft'):
            await self._show_create_message_menu(update, context)
            return
        channel = self.db.get_channel(update.effective_user.id)
        if not channel:
            await self._prompt_channel_activation(update, context)
            return
        await self._reply_or_edit(
            update, context,
            f"<blockquote>📢 القناة: <b>{html.escape(channel['title'] or str(channel['chat_id']))}</b>\n\nاختر الإجراء:</blockquote>",
            self._publish_options_keyboard()
        )

    async def _publish_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        channel = self.db.get_channel(update.effective_user.id)
        draft = context.user_data.get('draft')
        if not channel or not draft:
            await self._show_publish_options(update, context)
            return
        try:
            # Publish the exact HTML preview containing <tg-emoji> tags.
            # This avoids UTF-16 entity offset issues and preserves Custom Emoji.
            html_text = draft.get('html_preview')
            if not html_text:
                # Backward compatibility for old drafts that may not have html_preview.
                html_text = html.escape(draft.get('text', ''))

            await context.bot.send_message(
                chat_id=channel['chat_id'],
                text=html_text,
                parse_mode='HTML'
            )
            await self._answer_query(update.callback_query, "✅ تم النشر.")
            await self._reply_or_edit(update, context, "<blockquote>✅ تم نشر الرسالة في القناة بنجاح بالإيموجيات المميزة.</blockquote>",
                                      InlineKeyboardMarkup([[button_with_icon("الرئيسية", "main", "primary")]]))
        except Exception as e:
            await self._answer_query(update.callback_query, )
            await self._reply_or_edit(update, context, f"<blockquote>❌ فشل النشر:\n<code>{html.escape(str(e))}</code></blockquote>",
                                      self._publish_options_keyboard())

    async def _prompt_delay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.db.get_channel(update.effective_user.id):
            await self._prompt_channel_activation(update, context)
            return
        context.user_data['user_flow'] = 'awaiting_delay'
        text = "<blockquote>⏰ أرسل عدد الدقائق التي تريد تأجيل الرسالة لها.\nمثال: <code>30</code> = بعد 30 دقيقة.</blockquote>"
        kb = InlineKeyboardMarkup([[button_with_icon("رجوع", "back_publish", "primary")]])
        await self._reply_or_edit(update, context, text, kb)

    async def _schedule_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE, minutes: int):
        channel = self.db.get_channel(update.effective_user.id)
        draft = context.user_data.get('draft')
        if not channel or not draft:
            await self._reply_html(update.message, "<blockquote>⚠️ لا توجد قناة أو رسالة جاهزة.</blockquote>")
            context.user_data['user_flow'] = None
            return

        send_at = time.time() + minutes * 60
        # Store the HTML version so scheduled posts preserve Custom Emoji exactly.
        html_text = draft.get('html_preview') or html.escape(draft.get('text', ''))
        post_id = self.db.save_scheduled_post(
            update.effective_user.id,
            channel['chat_id'],
            html_text,
            [],
            send_at
        )
        context.user_data['user_flow'] = None

        post = {
            'id': post_id,
            'chat_id': channel['chat_id'],
            'text': html_text,
            'entities': [],
            'send_at': send_at,
        }
        asyncio.create_task(self._run_scheduled_post(post))
        await self._reply_html(update.message, 
            f"<blockquote>✅ تم جدولة الرسالة.\n"
            f"📢 القناة: <b>{html.escape(channel['title'] or str(channel['chat_id']))}</b>\n"
            f"⏰ النشر بعد: <b>{minutes} دقيقة</b></blockquote>",
            reply_markup=InlineKeyboardMarkup([[button_with_icon("الرئيسية", "main", "primary")]])
        )

    async def _send_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        main_kb = get_main_keyboard()
        keyboard = list(main_kb.inline_keyboard)
        if update.effective_user and update.effective_user.id == ADMIN_ID:
            keyboard.append([button_with_icon("لوحة الأدمن", "admin_panel", "primary")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "<blockquote>اختر أحد الخيارات أدناه للاستمرار.</blockquote>"
        await self._reply_or_edit(update, context, text, reply_markup)

    async def _send_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        keyboard = get_admin_main_keyboard()
        text = "<blockquote>🛠️ لوحة التحكم الإدارية</blockquote>"
        await self._reply_or_edit(update, context, text, keyboard)

    async def _send_extract_instruction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = f"<blockquote>📥 أرسل إيموجي Telegram المميز (Custom Emoji) وسأقوم باستخراج معرفه.\nيمكنك إرسال عدة إيموجيات في رسالة واحدة.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _show_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = f"""<blockquote>
📞 <b>الدعم والمساعدة</b>

للتواصل مع المطور:
{get_custom_emoji_html('📱')} <b>المطور:</b> @mouhamed_ma

{get_custom_emoji_html('🌟')} يمكنك مراسلتي لأي استفسار أو اقتراح.
{get_custom_emoji_html('😂')} شكراً لاستخدامك البوت!
</blockquote>"""
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_change_photo_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'change_photo'
        text = "<blockquote>🖼️ أرسل الصورة الجديدة للبوت.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_change_name_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'change_name'
        text = "<blockquote>✏️ أرسل الاسم الجديد للبوت.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_change_description_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'change_description'
        text = "<blockquote>📝 أرسل الوصف الجديد للبوت (سيظهر في صفحة البوت).</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_change_short_description_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'change_short_description'
        text = "<blockquote>📄 أرسل البايو الجديد (الوصف القصير) للبوت.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _list_emojis(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
        limit = 10
        offset = page * limit
        emojis, total = self.db.get_all_emojis(limit, offset)
        if not emojis:
            text = "<blockquote>📭 لا توجد إيموجيات مسجلة بعد.</blockquote>"
            keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
            await self._reply_or_edit(update, context, text, keyboard)
            return
        total_pages = (total + limit - 1) // limit
        lines = []
        for idx, emoji in enumerate(emojis, start=offset+1):
            emoji_display = get_custom_emoji_html_by_id(emoji['custom_emoji_id'], emoji['emoji'] or "▫️")
            lines.append(f"{idx}. {emoji_display} – <code>{emoji['custom_emoji_id']}</code>")
        text = "<blockquote>📋 قائمة الإيموجيات:\n" + "\n".join(lines) + f"\n\nالصفحة {page+1}/{total_pages}</blockquote>"
        keyboard = get_pagination_keyboard(page, total_pages, "list_emojis")
        await self._reply_or_edit(update, context, text, keyboard)

    async def _list_by_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE, category: str, page: int = 0) -> None:
        limit = 10
        offset = page * limit
        emojis, total = self.db.get_emojis_by_category(category, limit, offset)
        if not emojis:
            text = f"<blockquote>📭 لا توجد إيموجيات في تصنيف '{category}'.</blockquote>"
            keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "categories", "primary")]])
            await self._reply_or_edit(update, context, text, keyboard)
            return
        total_pages = (total + limit - 1) // limit
        lines = []
        for idx, emoji in enumerate(emojis, start=offset+1):
            emoji_display = get_custom_emoji_html_by_id(emoji['custom_emoji_id'], emoji['emoji'] or "▫️")
            lines.append(f"{idx}. {emoji_display} – <code>{emoji['custom_emoji_id']}</code>")
        text = f"<blockquote>📂 تصنيف '{category}':\n" + "\n".join(lines) + f"\n\nالصفحة {page+1}/{total_pages}</blockquote>"
        keyboard = get_pagination_keyboard(page, total_pages, f"cat_{category}")
        await self._reply_or_edit(update, context, text, keyboard)

    async def _show_most_used(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        emojis = self.db.get_most_used(10)
        if not emojis:
            text = "<blockquote>📭 لا توجد إيموجيات مسجلة.</blockquote>"
            keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
            await self._reply_or_edit(update, context, text, keyboard)
            return
        lines = []
        for idx, emoji in enumerate(emojis, 1):
            emoji_display = get_custom_emoji_html_by_id(emoji['custom_emoji_id'], emoji['emoji'] or "▫️")
            lines.append(f"{idx}. {emoji_display} – استخدام: {emoji['use_count']} – <code>{emoji['custom_emoji_id']}</code>")
        text = "<blockquote>🔥 الأكثر استخداماً:\n" + "\n".join(lines) + "</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _list_favorites(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
        user = update.effective_user
        if not user:
            return
        limit = 10
        offset = page * limit
        emojis, total = self.db.get_favorites(user.id, limit, offset)
        if not emojis:
            text = "<blockquote>⭐ ليس لديك إيموجيات مفضلة حالياً.</blockquote>"
            keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
            await self._reply_or_edit(update, context, text, keyboard)
            return
        total_pages = (total + limit - 1) // limit
        lines = []
        for idx, emoji in enumerate(emojis, start=offset+1):
            emoji_display = get_custom_emoji_html_by_id(emoji['custom_emoji_id'], emoji['emoji'] or "▫️")
            lines.append(f"{idx}. {emoji_display} – <code>{emoji['custom_emoji_id']}</code>")
        text = "<blockquote>⭐ المفضلة:\n" + "\n".join(lines) + f"\n\nالصفحة {page+1}/{total_pages}</blockquote>"
        keyboard = get_pagination_keyboard(page, total_pages, "fav")
        await self._reply_or_edit(update, context, text, keyboard)

    async def _show_emoji_card(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cid: str, emoji_text: str) -> None:
        emoji_data = self.db.get_emoji(cid)
        if not emoji_data:
            emoji_data = {'emoji': emoji_text, 'custom_emoji_id': cid, 'category': 'أخرى',
                          'date_added': 'الآن', 'last_used': 'الآن', 'use_count': 0}
        user = update.effective_user
        is_fav = self.db.is_favorite(user.id, cid) if user else False

        card_text = format_emoji_card(emoji_data, is_fav)
        codes_text = build_codes_text(cid, emoji_text)
        full_text = card_text + "\n" + codes_text

        fav_button_text = "إزالة من المفضلة" if is_fav else "إضافة إلى المفضلة"
        fav_callback = f"rem_fav_{cid}" if is_fav else f"add_fav_{cid}"

        code_buttons = [
            button_with_icon("HTML", f"code_html_{cid}", "primary"),
            button_with_icon("Button Code", f"code_button_{cid}", "primary"),
            button_with_icon("PHP Map", f"code_php_{cid}", "primary"),
            button_with_icon("JSON", f"code_json_{cid}", "primary"),
        ]
        code_rows = build_rows(code_buttons, 2)
        keyboard = code_rows + [
            [button_with_icon(fav_button_text, fav_callback, "primary")],
            [button_with_icon("رجوع", "main", "primary")],
        ]
        await self._reply_or_edit(update, context, full_text, InlineKeyboardMarkup(keyboard))

    async def _show_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cid: str, code_type: str) -> None:
        emoji_data = self.db.get_emoji(cid)
        emoji = emoji_data['emoji'] if emoji_data else "😊"
        html_code, button_code, php_map, json_code = generate_emoji_codes(cid, emoji)
        if code_type == "html":
            code_text = html_code
            label = "HTML"
        elif code_type == "button":
            code_text = button_code
            label = "Button Code"
        elif code_type == "php":
            code_text = php_map
            label = "PHP Map"
        elif code_type == "json":
            code_text = json_code
            label = "JSON"
        else:
            await self._answer_query(update.callback_query, "نوع غير معروف.")
            return
        text = f"<blockquote><strong>{label}</strong>\n<pre>{code_text}</pre></blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", f"emoji_detail_{cid}", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _search_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data['search_state'] = 'awaiting_search'
        text = "<blockquote>🔍 أرسل نص البحث (إيموجي، معرف، أو رقم الترتيب).</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _perform_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
        if query.isdigit():
            index = int(query)
            if index < 1:
                await self._reply_or_edit(update, context, "<blockquote>⚠️ الرقم يجب أن يكون أكبر من 0.</blockquote>")
                return
            emojis, total = self.db.get_all_emojis(limit=1, offset=index-1)
            if not emojis:
                await self._reply_or_edit(update, context, f"<blockquote>⚠️ لا يوجد إيموجي برقم {index}.</blockquote>")
                return
            emoji_data = emojis[0]
            await self._show_emoji_card(update, context, emoji_data['custom_emoji_id'], emoji_data['emoji'])
            return

        results = self.db.search_emojis(query)
        if not results:
            text = f"<blockquote>🔍 لا توجد نتائج للبحث عن '{query}'.</blockquote>"
            keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
            await self._reply_or_edit(update, context, text, keyboard)
            return
        lines = []
        for idx, emoji in enumerate(results[:20], 1):
            emoji_display = get_custom_emoji_html_by_id(emoji['custom_emoji_id'], emoji['emoji'] or "▫️")
            lines.append(f"{idx}. {emoji_display} – <code>{emoji['custom_emoji_id']}</code>")
        more = "\n... (يوجد المزيد)" if len(results) > 20 else ""
        text = f"<blockquote>🔍 نتائج البحث عن '{query}':\n" + "\n".join(lines) + more + "</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _show_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = "<blockquote>📂 اختر تصنيفاً لعرض الإيموجيات:</blockquote>"
        keyboard = get_category_keyboard()
        await self._reply_or_edit(update, context, text, keyboard)

    async def _show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        stats = self.db.get_stats()
        text = f"""<blockquote>
📊 الإحصائيات:
👥 المستخدمون: {stats['total_users']}
📝 الإيموجيات: {stats['total_emojis']}
⭐ المفضلة: {stats['total_favorites']}
👆 إجمالي الاستخدامات: {stats['total_uses']}

التصنيفات:
{chr(10).join([f"- {cat}: {cnt}" for cat, cnt in stats['categories']])}
</blockquote>"""
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = f"""<blockquote>
❓ <strong>مساعدة البوت</strong>

يمكنك استخدام البوت لاستخراج ومعرفة معرفات الإيموجيات المميزة.

<strong>الأوامر:</strong>
/start - القائمة الرئيسية
/admin - لوحة الأدمن (للمسؤولين فقط)

<strong>الاستخدام:</strong>
- أرسل إيموجي مميز لاستخراج معرفه.
- استخدم الأزرار لتصفح الإيموجيات المحفوظة والبحث والتصنيفات.
- يمكنك إضافة الإيموجيات إلى المفضلة.
- في البحث، يمكنك إدخال رقم لعرض الإيموجي بذاك الترتيب.

<strong>ملاحظة:</strong>
البوت يحفظ كل الإيموجيات التي يتم إرسالها مع عدد الاستخدامات والتواريخ.
</blockquote>"""
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "main", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    def _is_admin(self, update: Update) -> bool:
        user = update.effective_user
        return user and user.id == ADMIN_ID

    async def _admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        stats = self.db.get_stats()
        text = f"""<blockquote>
📊 <strong>إحصائيات كاملة</strong>
👥 المستخدمون: {stats['total_users']}
📝 الإيموجيات: {stats['total_emojis']}
⭐ المفضلة: {stats['total_favorites']}
👆 إجمالي الاستخدامات: {stats['total_uses']}

<strong>التصنيفات:</strong>
{chr(10).join([f"- {cat}: {cnt}" for cat, cnt in stats['categories']])}
</blockquote>"""
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_users_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        keyboard = get_admin_users_keyboard()
        text = "<blockquote>👥 إدارة المستخدمين</blockquote>"
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_block_user_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'block_user'
        text = "<blockquote>🚫 أرسل معرف المستخدم (user_id) لحظره.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_users", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_unblock_user_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'unblock_user'
        text = "<blockquote>✅ أرسل معرف المستخدم لفك حظره.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_users", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        users = self.db.get_all_users()
        if not users:
            text = "<blockquote>لا يوجد مستخدمون.</blockquote>"
        else:
            lines = []
            for u in users[:20]:
                status = "🚫" if u['is_blocked'] else "✅"
                admin = "👑" if u['is_admin'] else ""
                lines.append(f"{status} {admin} {u['first_name']} (@{u['username']}) ID: {u['user_id']}")
            more = "\n... (يوجد المزيد)" if len(users) > 20 else ""
            text = "<blockquote>👥 قائمة المستخدمين:\n" + "\n".join(lines) + more + "</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_users", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_broadcast_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'broadcast'
        text = "<blockquote>📢 أرسل الرسالة التي تريد إذاعتها لجميع المستخدمين.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_send_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'send_to_user'
        text = "<blockquote>📨 أرسل معرف المستخدم أولاً، ثم في الرسالة التالية أرسل النص.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_emojis_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        keyboard = get_admin_emojis_keyboard()
        text = "<blockquote>📝 إدارة الإيموجيات</blockquote>"
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_add_emoji_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'add_emoji'
        text = "<blockquote>➕ أرسل الإيموجي المميز (كرمز) ثم تصنيفه (اختياري). مثال: 😊 وجوه</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_emojis", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_edit_emoji_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'edit_emoji'
        text = "<blockquote>✏️ أرسل معرف الإيموجي ثم التصنيف الجديد مفصولاً بمسافة.\nمثال: 5857263604130123563 قلوب</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_emojis", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_delete_emoji_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'delete_emoji'
        text = "<blockquote>🗑️ أرسل معرف الإيموجي المراد حذفه.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_emojis", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_search_emoji_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'admin_search_emoji'
        text = "<blockquote>🔍 أرسل نص البحث (إيموجي أو معرف).</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_emojis", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_categories_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        keyboard = get_admin_categories_keyboard()
        text = "<blockquote>📂 إدارة التصنيفات</blockquote>"
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_add_category_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'add_category'
        text = "<blockquote>➕ أرسل اسم التصنيف الجديد.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_categories", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_edit_category_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'edit_category'
        text = "<blockquote>✏️ أرسل التصنيف القديم والجديد مفصولاً بفاصلة.\nمثال: وجوه,وجوه جديدة</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_categories", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_delete_category_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'delete_category'
        text = "<blockquote>🗑️ أرسل اسم التصنيف المراد حذفه.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_categories", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_admins_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        text = "<blockquote>👤 إدارة الأدمنز\n(يمكنك إضافة أو إزالة صلاحيات الأدمن عبر معرف المستخدم)</blockquote>"
        keyboard = [
            [button_with_icon("إضافة أدمن", "admin_add_admin", "success")],
            [button_with_icon("إزالة أدمن", "admin_remove_admin", "danger")],
            [button_with_icon("رجوع", "admin_panel", "primary")],
        ]
        await self._reply_or_edit(update, context, text, InlineKeyboardMarkup(keyboard))

    async def _admin_add_admin_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'add_admin'
        text = "<blockquote>➕ أرسل معرف المستخدم لإضافته كأدمن.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_admins", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_remove_admin_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'remove_admin'
        text = "<blockquote>➖ أرسل معرف المستخدم لإزالة صلاحيات الأدمن.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_admins", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        keyboard = get_admin_settings_keyboard()
        text = "<blockquote>⚙️ الإعدادات</blockquote>"
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_forced_channels_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        channels = self.db.get_forced_channels()
        current = "\n".join([f"- @{ch}" for ch in channels]) if channels else "لا توجد قنوات إجبارية"
        context.user_data['admin_action'] = 'forced_channels'
        text = f"<blockquote>📢 إدارة القنوات الإجبارية\nالحالية:\n{current}\n\nأرسل قائمة المعرفات مفصولة بمسافات (مثل: @channel1 @channel2).</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_settings", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_spam_settings_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        limit, interval = self.db.get_spam_settings()
        context.user_data['admin_action'] = 'spam_settings'
        text = f"<blockquote>🛡️ إعدادات الحماية من التكرار\nالحد الأقصى: {limit} رسالة لكل {interval} ثانية.\nأرسل القيم الجديدة كـ 'الحد الفاصل' (مثال: 10 30).</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_settings", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        logs = self.db.get_admin_logs(50)
        if not logs:
            text = "<blockquote>لا توجد سجلات.</blockquote>"
        else:
            lines = []
            for log in logs[:20]:
                lines.append(f"{log['timestamp'][:16]} - {log['admin_id']} - {log['action']}")
            more = "\n... (يوجد المزيد)" if len(logs) > 20 else ""
            text = "<blockquote>📜 السجلات:\n" + "\n".join(lines) + more + "</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        try:
            with open(self.db.db_path, 'rb') as f:
                await update.callback_query.message.reply_document(document=f, filename="emoji_bot_backup.db")
            await self._reply_or_edit(update, context, "✅ تم إنشاء النسخة الاحتياطية.")
        except Exception as e:
            await self._reply_or_edit(update, context, f"❌ فشل النسخ الاحتياطي: {e}")

    async def _admin_restore_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'restore'
        text = "<blockquote>🔄 أرسل ملف قاعدة البيانات (ملف .db) لاستعادته.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        emojis, _ = self.db.get_all_emojis(limit=1000000, offset=0)
        data = {"emojis": emojis, "export_date": datetime.now().isoformat()}
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        try:
            bio = BytesIO(json_str.encode('utf-8'))
            bio.name = "emoji_export.json"
            await update.callback_query.message.reply_document(document=bio, filename="emoji_export.json")
            await self._reply_or_edit(update, context, "✅ تم تصدير البيانات.")
        except Exception as e:
            await self._reply_or_edit(update, context, f"❌ فشل التصدير: {e}")

    async def _admin_import_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        context.user_data['admin_action'] = 'import'
        text = "<blockquote>📥 أرسل ملف JSON للاستيراد.</blockquote>"
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        uptime = time.time() - psutil.boot_time()
        uptime_str = str(timedelta(seconds=int(uptime)))
        text = f"""<blockquote>
💻 <strong>معلومات النظام</strong>
وحدة المعالجة المركزية: {cpu}%
الذاكرة: {mem.used/1024**3:.2f}GB / {mem.total/1024**3:.2f}GB
التخزين: {disk.used/1024**3:.2f}GB / {disk.total/1024**3:.2f}GB
وقت التشغيل: {uptime_str}
</blockquote>"""
        keyboard = InlineKeyboardMarkup([[button_with_icon("رجوع", "admin_panel", "primary")]])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _admin_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        await self._reply_or_edit(update, context, "🔄 جارٍ إعادة التشغيل...")
        sys.exit(0)

    async def _check_forced_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        channels = self.db.get_forced_channels()
        if not channels:
            return True
        user_id = update.effective_user.id
        for channel in channels:
            try:
                chat = await context.bot.get_chat(channel)
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ("member", "administrator", "creator"):
                    await self._prompt_subscription(update, context, channels)
                    return False
            except Exception as e:
                logger.error(f"Failed to check subscription for {channel}: {e}")
        return True

    async def _prompt_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE, channels: List[str]) -> None:
        lines = [f"- @{ch}" for ch in channels]
        text = f"""<blockquote>
⚠️ يجب الاشتراك في القنوات التالية لاستخدام البوت:
{chr(10).join(lines)}
اضغط على زر التحقق بعد الاشتراك.
</blockquote>"""
        keyboard = InlineKeyboardMarkup([
            [button_with_icon("تحقق من الاشتراك", "check_sub", "primary")],
            [button_with_icon("رجوع", "main", "primary")]
        ])
        await self._reply_or_edit(update, context, text, keyboard)

    async def _check_sub_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await self._answer_query(query, )
        if await self._check_forced_subscription(update, context):
            await self._send_main_menu(update, context)
        else:
            await self._edit_query_text(query, "<blockquote>⚠️ لا تزال غير مشترك. يرجى الاشتراك ثم التحقق مرة أخرى.</blockquote>",
                                         reply_markup=InlineKeyboardMarkup([
                                             [button_with_icon("تحقق مرة أخرى", "check_sub", "primary")],
                                             [button_with_icon("رجوع", "main", "primary")]
                                         ]))

    async def _process_admin_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_admin(update):
            return
        action = context.user_data.get('admin_action')
        text = update.message.text.strip()
        if not action:
            return

        if action == 'block_user':
            try:
                user_id = int(text)
                self.db.block_user(user_id)
                self.db.add_admin_log(update.effective_user.id, 'block_user', user_id, f"Blocked user {user_id}")
                await self._reply_html(update.message, "<blockquote>✅ تم حظر المستخدم.</blockquote>")
            except ValueError:
                await self._reply_html(update.message, "<blockquote>⚠️ معرف غير صحيح.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'unblock_user':
            try:
                user_id = int(text)
                self.db.unblock_user(user_id)
                self.db.add_admin_log(update.effective_user.id, 'unblock_user', user_id, f"Unblocked user {user_id}")
                await self._reply_html(update.message, "<blockquote>✅ تم فك الحظر.</blockquote>")
            except ValueError:
                await self._reply_html(update.message, "<blockquote>⚠️ معرف غير صحيح.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'broadcast':
            users = self.db.get_all_users()
            sent = 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u['user_id'], text=customize_bot_html(text), parse_mode='HTML')
                    sent += 1
                except:
                    pass
            self.db.add_admin_log(update.effective_user.id, 'broadcast', details=f"Sent to {sent} users")
            await self._reply_html(update.message, f"<blockquote>📢 تم الإذاعة إلى {sent} مستخدم.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'send_to_user':
            if 'send_target' not in context.user_data:
                try:
                    target_id = int(text)
                    context.user_data['send_target'] = target_id
                    await self._reply_html(update.message, "<blockquote>📨 الآن أرسل النص الذي تريد إرساله.</blockquote>")
                except ValueError:
                    await self._reply_html(update.message, "<blockquote>⚠️ معرف غير صحيح.</blockquote>")
                    context.user_data.pop('admin_action', None)
            else:
                target_id = context.user_data.pop('send_target')
                try:
                    await context.bot.send_message(chat_id=target_id, text=customize_bot_html(text), parse_mode='HTML')
                    self.db.add_admin_log(update.effective_user.id, 'send_to_user', target_id, f"Sent message")
                    await self._reply_html(update.message, "<blockquote>✅ تم الإرسال.</blockquote>")
                except Exception as e:
                    await self._reply_html(update.message, f"<blockquote>❌ فشل الإرسال: {e}</blockquote>")
                context.user_data.pop('admin_action', None)

        elif action == 'add_emoji':
            await self._reply_html(update.message, "<blockquote>⚠️ استخدم إرسال الإيموجي مباشرة للاستخراج.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'edit_emoji':
            parts = text.split()
            if len(parts) < 2:
                await self._reply_html(update.message, "<blockquote>⚠️ أرسل المعرف والتصنيف الجديد.</blockquote>")
                return
            cid = parts[0]
            new_cat = ' '.join(parts[1:])
            emoji_data = self.db.get_emoji(cid)
            if emoji_data:
                self.db.update_emoji_category(cid, new_cat)
                self.db.add_admin_log(update.effective_user.id, 'edit_emoji', details=f"Updated {cid} to {new_cat}")
                await self._reply_html(update.message, "<blockquote>✅ تم التعديل.</blockquote>")
            else:
                await self._reply_html(update.message, "<blockquote>⚠️ المعرف غير موجود.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'delete_emoji':
            cid = text
            emoji_data = self.db.get_emoji(cid)
            if emoji_data:
                self.db.delete_emoji(cid)
                self.db.add_admin_log(update.effective_user.id, 'delete_emoji', details=f"Deleted {cid}")
                await self._reply_html(update.message, "<blockquote>🗑️ تم الحذف.</blockquote>")
            else:
                await self._reply_html(update.message, "<blockquote>⚠️ المعرف غير موجود.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'admin_search_emoji':
            results = self.db.search_emojis(text)
            if not results:
                await self._reply_html(update.message, "<blockquote>🔍 لا توجد نتائج.</blockquote>")
            else:
                lines = []
                for emoji in results[:10]:
                    emoji_display = get_custom_emoji_html_by_id(emoji['custom_emoji_id'], emoji['emoji'] or "▫️")
                    lines.append(f"{emoji_display} – <code>{emoji['custom_emoji_id']}</code> - تصنيف: {emoji['category']}")
                more = "\n... (يوجد المزيد)" if len(results) > 10 else ""
                await self._reply_html(update.message, "<blockquote>🔍 نتائج البحث:\n" + "\n".join(lines) + more + "</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'add_category':
            await self._reply_html(update.message, "<blockquote>✅ تمت إضافة التصنيف (يمكن استخدامه عند إضافة إيموجيات).</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'edit_category':
            parts = text.split(',')
            if len(parts) != 2:
                await self._reply_html(update.message, "<blockquote>⚠️ أرسل التصنيف القديم والجديد مفصولاً بفاصلة.</blockquote>")
                return
            old_cat = parts[0].strip()
            new_cat = parts[1].strip()
            with sqlite3.connect(self.db.db_path) as conn:
                cur = conn.cursor()
                cur.execute("UPDATE emojis SET category = ? WHERE category = ?", (new_cat, old_cat))
                conn.commit()
            self.db.add_admin_log(update.effective_user.id, 'edit_category', details=f"Renamed {old_cat} to {new_cat}")
            await self._reply_html(update.message, "<blockquote>✅ تم التعديل.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'delete_category':
            cat = text.strip()
            with sqlite3.connect(self.db.db_path) as conn:
                cur = conn.cursor()
                cur.execute("UPDATE emojis SET category = 'أخرى' WHERE category = ?", (cat,))
                conn.commit()
            self.db.add_admin_log(update.effective_user.id, 'delete_category', details=f"Deleted category {cat}")
            await self._reply_html(update.message, "<blockquote>✅ تم حذف التصنيف (تم نقل الإيموجيات إلى 'أخرى').</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'add_admin':
            try:
                user_id = int(text)
                self.db.set_admin(user_id, True)
                self.db.add_admin_log(update.effective_user.id, 'add_admin', user_id, f"Added admin {user_id}")
                await self._reply_html(update.message, "<blockquote>✅ تمت إضافة الأدمن.</blockquote>")
            except ValueError:
                await self._reply_html(update.message, "<blockquote>⚠️ معرف غير صحيح.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'remove_admin':
            try:
                user_id = int(text)
                if user_id == ADMIN_ID:
                    await self._reply_html(update.message, "<blockquote>⚠️ لا يمكن إزالة الأدمن الرئيسي.</blockquote>")
                else:
                    self.db.set_admin(user_id, False)
                    self.db.add_admin_log(update.effective_user.id, 'remove_admin', user_id, f"Removed admin {user_id}")
                    await self._reply_html(update.message, "<blockquote>✅ تمت إزالة الأدمن.</blockquote>")
            except ValueError:
                await self._reply_html(update.message, "<blockquote>⚠️ معرف غير صحيح.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'forced_channels':
            channels = text.split()
            clean = [ch.lstrip('@') for ch in channels]
            self.db.set_forced_channels(clean)
            self.db.add_admin_log(update.effective_user.id, 'forced_channels', details=f"Set channels: {clean}")
            await self._reply_html(update.message, "<blockquote>✅ تم تحديث القنوات الإجبارية.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'spam_settings':
            parts = text.split()
            if len(parts) != 2:
                await self._reply_html(update.message, "<blockquote>⚠️ أرسل قيمتين: الحد والفاصل (مثال: 10 30).</blockquote>")
                return
            try:
                limit = int(parts[0])
                interval = int(parts[1])
                self.db.set_spam_limit(limit)
                self.db.set_spam_interval(interval)
                self.db.add_admin_log(update.effective_user.id, 'spam_settings', details=f"Set limit={limit}, interval={interval}")
                await self._reply_html(update.message, "<blockquote>✅ تم تحديث الإعدادات.</blockquote>")
            except ValueError:
                await self._reply_html(update.message, "<blockquote>⚠️ القيم يجب أن تكون أرقاماً.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'restore':
            if update.message.document:
                file = await update.message.document.get_file()
                await file.download_to_drive(self.db.db_path)
                self.db.add_admin_log(update.effective_user.id, 'restore', details="Restored database")
                await self._reply_html(update.message, "<blockquote>✅ تمت الاستعادة.</blockquote>")
            else:
                await self._reply_html(update.message, "<blockquote>⚠️ يرجى إرسال ملف قاعدة البيانات.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'import':
            if update.message.document:
                file = await update.message.document.get_file()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
                    await file.download_to_drive(tmp.name)
                    with open(tmp.name, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    emojis = data.get('emojis', [])
                    for item in emojis:
                        cid = item.get('custom_emoji_id')
                        emoji = item.get('emoji')
                        category = item.get('category', 'أخرى')
                        if cid and emoji:
                            self.db.save_emoji(cid, emoji, ADMIN_ID, category)
                    self.db.add_admin_log(update.effective_user.id, 'import', details=f"Imported {len(emojis)} emojis")
                    await self._reply_html(update.message, f"<blockquote>✅ تم استيراد {len(emojis)} إيموجي.</blockquote>")
            else:
                await self._reply_html(update.message, "<blockquote>⚠️ يرجى إرسال ملف JSON.</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'change_name':
            try:
                await context.bot.set_my_name(text)
                self.db.add_admin_log(update.effective_user.id, 'change_name', details=f"New name: {text}")
                await self._reply_html(update.message, "<blockquote>✅ تم تغيير اسم البوت بنجاح.</blockquote>")
            except Exception as e:
                await self._reply_html(update.message, f"<blockquote>❌ فشل تغيير الاسم: {e}</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'change_description':
            try:
                await context.bot.set_my_description(text)
                self.db.add_admin_log(update.effective_user.id, 'change_description', details=f"New description: {text[:50]}...")
                await self._reply_html(update.message, "<blockquote>✅ تم تغيير وصف البوت بنجاح.</blockquote>")
            except Exception as e:
                await self._reply_html(update.message, f"<blockquote>❌ فشل تغيير الوصف: {e}</blockquote>")
            context.user_data.pop('admin_action', None)

        elif action == 'change_short_description':
            try:
                await context.bot.set_my_short_description(text)
                self.db.add_admin_log(update.effective_user.id, 'change_short_description', details=f"New short description: {text[:50]}...")
                await self._reply_html(update.message, "<blockquote>✅ تم تغيير البايو بنجاح.</blockquote>")
            except Exception as e:
                await self._reply_html(update.message, f"<blockquote>❌ فشل تغيير البايو: {e}</blockquote>")
            context.user_data.pop('admin_action', None)

        else:
            context.user_data.pop('admin_action', None)

    async def _restore_scheduled_posts(self):
        pending = self.db.get_pending_scheduled_posts()
        for post in pending:
            asyncio.create_task(self._run_scheduled_post(post))
        if pending:
            logger.info("Restored %s pending scheduled post(s).", len(pending))

    async def _run_scheduled_post(self, post: Dict):
        delay = max(0, float(post['send_at']) - time.time())
        await asyncio.sleep(delay)
        try:
            # New scheduled posts contain ready-to-send HTML with <tg-emoji> tags.
            # Keep backward compatibility with old DB records that stored entities.
            if post.get('entities'):
                entities = [MessageEntity(
                    type=MessageEntity.CUSTOM_EMOJI,
                    offset=e['offset'],
                    length=e['length'],
                    custom_emoji_id=e['custom_emoji_id']
                ) for e in post['entities']]
                await self.app.bot.send_message(
                    chat_id=post['chat_id'],
                    text=post['text'],
                    entities=entities
                )
            else:
                await self.app.bot.send_message(
                    chat_id=post['chat_id'],
                    text=post['text'],
                    parse_mode='HTML'
                )
            self.db.mark_scheduled_done(post['id'])
            logger.info("Scheduled post %s published", post['id'])
        except Exception:
            logger.exception("Scheduled post %s failed", post['id'])

    async def _reply_or_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                             text: str, keyboard: InlineKeyboardMarkup = None,
                             parse_mode: str = 'HTML') -> None:
        query = update.callback_query
        if query:
            if query.message:
                if query.message.photo or query.message.document or query.message.video or query.message.animation:
                    try:
                        await self._edit_query_caption(query, 
                            caption=text,
                            reply_markup=keyboard,
                            parse_mode=parse_mode
                        )
                        return
                    except Exception as e:
                        logger.warning(f"Failed to edit caption, falling back to edit_text: {e}")
                try:
                    await self._edit_query_text(query, text, reply_markup=keyboard, parse_mode=parse_mode)
                except Exception as e:
                    logger.error(f"Failed to edit message: {e}")
                    await self._reply_text(query.message, text, reply_markup=keyboard, parse_mode=parse_mode)
            else:
                pass
        else:
            if update.message:
                await self._reply_text(update.message, text, reply_markup=keyboard, parse_mode=parse_mode)
            else:
                logger.warning("No message or query to reply.")

    async def _reply_html(self, message, text, **kwargs):
        kwargs.setdefault('parse_mode', 'HTML')
        return await message.reply_text(customize_bot_html(text), **kwargs)

    async def _reply_text(self, message, text, **kwargs):
        # Send through HTML so custom emoji tags render in the same way as all
        # other bot-authored messages.
        kwargs.setdefault('parse_mode', 'HTML')
        return await message.reply_text(customize_bot_html(html.escape(text) if '<' not in text else text), **kwargs)

    async def _edit_query_text(self, query, text, **kwargs):
        kwargs.setdefault('parse_mode', 'HTML')
        return await query.edit_message_text(customize_bot_html(text), **kwargs)

    async def _edit_query_caption(self, query, caption, **kwargs):
        kwargs.setdefault('parse_mode', 'HTML')
        return await query.edit_message_caption(caption=customize_bot_html(caption), **kwargs)

    async def _answer_query(self, query, text=None, **kwargs):
        if text:
            text = strip_visual_emojis(text)
        return await query.answer(text=text, **kwargs)

    async def _refresh_current_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_main_menu(update, context)

def main() -> None:
    db = Database()
    bot_holder = {}

    async def post_init(application: Application) -> None:
        bot = bot_holder.get('bot')
        if bot:
            await bot._restore_scheduled_posts()

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    bot = EmojiBot(application, db)
    bot_holder['bot'] = bot
    logger.info("موحا يسلم عليك🥹❤️")
    application.run_polling()

if __name__ == "__main__":
    main()