# ==============================
# 📦 AUTO INSTALL DEPENDENCIES
# ==============================
import sys
import subprocess

packages = {
    "psutil": "psutil",
    "telegram": "python-telegram-bot",
    "requests": "requests",
    "bs4": "beautifulsoup4",
    "telebot": "pyTelegramBotAPI",
}

for module, package in packages.items():
    try:
        __import__(module)
    except ImportError:
        print(f"📦 Installing {package}...")
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            package
        ])

print("✅ All required libraries are installed.")

# ==============================
# 🔽 YOUR CODE STARTS HERE
# ==============================

import os
import json
import html
import logging
import threading
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, BotCommand

# ============================================================
# الإعدادات الأساسية
# ============================================================
# ضع التوكن في متغير البيئة BOT_TOKEN بدل كتابة التوكن داخل الملف.
TOKEN = "8931647420:AAEPE6R5Mo8UtfsryAZAMzGHPDht-t5TzTU"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود. ضع توكن البوت في متغير البيئة BOT_TOKEN.")

DATA_FILE = "user_data.json"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# الإيموجيات المخصصة الموجودة في ملفك
# ============================================================
CUSTOM_EMOJIS = {
    # تم تغيير بعض الإيموجيات إلى IDs أجمل من ملف الإيموجيات الذي أرسلته.
    "⚡️": "5812295584303816243",  # 🫶
    "❗️": "5812299217846150320",  # 🛑
    "❓": "5812384820839325207",  # 😱
    "⚠️": "5812299217846150320",  # 🛑
    "💬": "5812125177181379867",  # 💬
    "⬆️": "5812434487841136061",  # ➡️
    "⬇️": "5812080754334636324",  # ⬇️
    "✅": "5811998303847455806",  # 👍
    "⭐️": "5812160881244510987",  # 💠
    "💎": "5812136915327002202",  # 💠 مختلف
    "🔜": "5812434487841136061",  # ➡️
    "🆕": "5811923854884346134",  # 🔅
    "🔗": "5812329368516566132",  # 🔐
    "👎": "5811912181163235280",  # ☹️
    "💲": "5812160881244510987",  # 💠
    "❌": "5812074170149771271",  # ❌
    "💡": "5811943852252077435",  # 💡
    "🔄": "5812274891151383429",  # 🔄
    "🏆": "5812160881244510987",  # 💠
    "💰": "5812160881244510987",  # 💠
    "🎁": "5812160881244510987",  # 💠
    "🆔": "5812358239286729700",  # 🧠
    "👤": "5811905206136347060",  # 🤳
    "📋": "5812236940820356899",  # 🧭
    "📝": "5812253678307910739",  # 🖋
    "🌐": "5812393814500843141",  # 🌐
    "👨‍💻": "5812358239286729700",  # 🧠
    "🖼": "5323379047315555501",  # 📱/صورة
    "🇸🇦": "5224698145010624573",
    "🇬🇧": "5224518800061245598",
}

# ============================================================
# تقدير تاريخ إنشاء الحساب من Telegram ID
# ============================================================
# هذه نقاط مرجعية عامة منشورة في مشاريع تقدير عمر حسابات Telegram.
# يتم إجراء interpolation بينها للحصول على يوم/شهر/سنة تقريبية.
# Telegram لا يرسل تاريخ التسجيل الرسمي عبر Bot API، لذلك النتيجة تقديرية.
ACCOUNT_DATE_ANCHORS = [
    (2768409, "2013-11-01"),
    (7679610, "2013-12-31"),
    (11538514, "2014-02-01"),
    (38015510, "2014-03-01"),
    (46145305, "2014-05-15"),
    (54845238, "2014-09-20"),
    (63263518, "2014-10-27"),
    (101260938, "2015-03-06"),
    (116812045, "2015-07-23"),
    (130029930, "2015-09-03"),
    (133909606, "2015-10-07"),
    (157242073, "2015-11-06"),
    (181783990, "2016-04-10"),
    (222021233, "2016-06-08"),
    (278941742, "2016-09-10"),
    (285253072, "2016-10-18"),
    (294851037, "2016-11-19"),
    (297621225, "2016-12-16"),
    (328594461, "2017-01-28"),
    (337808429, "2017-02-21"),
    (369669043, "2017-03-31"),
    (400169472, "2017-07-31"),
    (805158066, "2019-07-15"),
    (1974255900, "2021-10-12"),
    (5031711230, "2021-12-06"),
    (5070164216, "2022-01-19"),
    (5149590651, "2022-01-22"),
    (5177789190, "2022-01-24"),
    (5288930461, "2022-01-27"),
    (5396515972, "2022-04-21"),
    (5505809357, "2022-05-27"),
    (5598262640, "2022-06-11"),
    (5721138769, "2022-09-23"),
    (5931294587, "2022-11-19"),
    (5983753471, "2022-12-23"),
    (6271031786, "2023-02-12"),
    (6277658932, "2023-03-17"),
    (6326011828, "2023-07-07"),
    (6523424924, "2023-08-02"),
    (6684986493, "2023-09-25"),
    (6829119388, "2023-12-02"),
    (7002435197, "2024-04-06"),
    (7104310277, "2024-04-19"),
    (7242296450, "2024-05-29"),
    (7254607307, "2024-06-10"),
    (7293965553, "2024-06-16"),
    (7409259451, "2024-06-20"),
    (7458668365, "2024-08-02"),
    (7832006200, "2024-09-19"),
    (8173852075, "2025-02-21"),
    (8238766847, "2025-07-31"),
    (8343786378, "2025-08-08"),
    (8461579295, "2025-09-11"),
    (8559682245, "2025-11-11"),
    # نقطة نهاية تقديرية مؤقتة لتغطية المعرفات الأحدث من آخر عينة منشورة.
    (12000000000, "2026-08-19"),
]

ARABIC_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}

def estimate_account_creation_date(user_id: int):
    """إرجاع تاريخ تسجيل تقريبي من Telegram ID باستخدام interpolation خطي."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None

    points = sorted((int(pid), datetime.strptime(date, "%Y-%m-%d")) for pid, date in ACCOUNT_DATE_ANCHORS)

    if uid <= points[0][0]:
        estimated = points[0][1]
    elif uid >= points[-1][0]:
        estimated = points[-1][1]
    else:
        for (x0, d0), (x1, d1) in zip(points, points[1:]):
            if x0 <= uid <= x1:
                ratio = (uid - x0) / (x1 - x0)
                estimated = d0 + (d1 - d0) * ratio
                break
        else:
            return None

    return estimated.strftime("%d %B %Y")

def estimate_account_creation_date_ar(user_id: int):
    """مثل السابقة لكن بصيغة عربية لاسم الشهر."""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None

    points = sorted((int(pid), datetime.strptime(date, "%Y-%m-%d")) for pid, date in ACCOUNT_DATE_ANCHORS)
    if uid <= points[0][0]:
        estimated = points[0][1]
    elif uid >= points[-1][0]:
        estimated = points[-1][1]
    else:
        estimated = None
        for (x0, d0), (x1, d1) in zip(points, points[1:]):
            if x0 <= uid <= x1:
                ratio = (uid - x0) / (x1 - x0)
                estimated = d0 + (d1 - d0) * ratio
                break
        if estimated is None:
            return None

    return f"{estimated.day:02d} {ARABIC_MONTHS[estimated.month]} {estimated.year}"


def emoji(emoji_char: str) -> str:
    """إرجاع إيموجي Telegram المخصص بصيغة HTML."""
    emoji_id = CUSTOM_EMOJIS.get(emoji_char)
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji>'
    return emoji_char


def convert_custom_emojis(text: str) -> str:
    """تحويل الإيموجيات العادية إلى إيموجيات Telegram مخصصة دون تكرار الوسوم."""
    if not text:
        return text

    result = []
    pos = 0
    closing_tag = "</tg-emoji>"

    while pos < len(text):
        opening = text.find("<tg-emoji", pos)
        if opening == -1:
            segment = text[pos:]
            for char, emoji_id in CUSTOM_EMOJIS.items():
                segment = segment.replace(char, f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>')
            result.append(segment)
            break

        segment = text[pos:opening]
        for char, emoji_id in CUSTOM_EMOJIS.items():
            segment = segment.replace(char, f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>')
        result.append(segment)

        closing = text.find(closing_tag, opening)
        if closing == -1:
            result.append(text[opening:])
            break

        closing += len(closing_tag)
        result.append(text[opening:closing])
        pos = closing

    return "".join(result)


# ============================================================
# نصوص البوت
# ============================================================
TEXTS = {
    "ar": {
        "welcome": (
            f"{emoji('⚡️')} أهلاً بك في بوت المعلومات\n\n"
            f"{emoji('💎')} اختر الخدمة التي تريدها من القائمة السفلية."
        ),
        "id_info": (
            f"{emoji('🆔')} معلومات الحساب:\n\n"
            f"{emoji('💎')} المعرف: <code>{{user_id}}</code>\n"
            f"{emoji('👤')} اسم المستخدم: @{{username}}"
        ),
        "account_info": (
            f"{emoji('📋')} تفاصيل الحساب:\n\n"
            f"{emoji('👤')} الاسم: {{first_name}}\n"
            f"{emoji('🆔')} المعرف: <code>{{user_id}}</code>\n"
            f"{emoji('💬')} اسم المستخدم: @{{username}}\n"
            f"{emoji('📝')} السيرة الذاتية: {{bio}}\n"
            f"{emoji('🌐')} لغة Telegram: {{language}}"
        ),
        "account_date_info": (
            f"{emoji('📋')} تاريخ إنشاء الحساب (تقديري):\n\n"
            f"{emoji('✅')} التاريخ المتوقع: <code>{{estimated_date}}</code>\n\n"
            f"{emoji('⚠️')} تم تقديره اعتمادًا على رقم ID والمقارنة مع نقاط مرجعية معروفة، لذلك قد يختلف عن تاريخ التسجيل الحقيقي."
        ),
        "no_photo": f"{emoji('⚠️')} لا توجد صورة حساب.",
        "dev_info": (
            f"{emoji('👨‍💻')} المطور:\n\n"
            "البوت من تطوير @mouhamed_ma\n"
            "للتواصل: @mouhamed_ma"
        ),
        "channel_info": f"{emoji('🔗')} قناة المطور:\n@forzd9",
        "lang_prompt": f"{emoji('🌐')} اختر لغتك المفضلة:",
        "lang_changed": f"{emoji('✅')} تم تغيير اللغة إلى العربية.",
        "lang_changed_en": f"{emoji('✅')} Language changed to English.",
        "default_reply": f"{emoji('💬')} ما الذي تريده، {{name}}؟",
        "default_reply_en": f"{emoji('💬')} What do you want, {{name}}?",
        "error": f"{emoji('❗️')} حدث خطأ، حاول مرة أخرى.",
        "btn_id": "ايديك",
        "btn_account": "حساب",
        "btn_creation_date": "تاريخ إنشاء الحساب",
        "btn_photo": "صورة حسابك",
        "btn_dev": "المطور",
        "btn_channel": "قناة المطور",
        "btn_lang": "تغيير اللغة",
        "btn_lang_ar": "العربية",
        "btn_lang_en": "English",
    },
    "en": {
        "welcome": (
            f"{emoji('⚡️')} Welcome to Information Bot\n\n"
            f"{emoji('💎')} Choose a service from the bottom menu."
        ),
        "id_info": (
            f"{emoji('🆔')} Account ID:\n\n"
            f"{emoji('💎')} ID: <code>{{user_id}}</code>\n"
            f"{emoji('👤')} Username: @{{username}}"
        ),
        "account_info": (
            f"{emoji('📋')} Account Details:\n\n"
            f"{emoji('👤')} Name: {{first_name}}\n"
            f"{emoji('🆔')} ID: <code>{{user_id}}</code>\n"
            f"{emoji('💬')} Username: @{{username}}\n"
            f"{emoji('📝')} Bio: {{bio}}\n"
            f"{emoji('🌐')} Telegram language: {{language}}"
        ),
        "account_date_info": (
            f"{emoji('📋')} Estimated Telegram account creation date:\n\n"
            f"{emoji('✅')} Estimated date: <code>{{estimated_date}}</code>\n\n"
            f"{emoji('⚠️')} This is estimated from the numeric ID and known reference points, so it may differ from the real registration date."
        ),
        "no_photo": f"{emoji('⚠️')} No profile photo found.",
        "dev_info": (
            f"{emoji('👨‍💻')} Developer:\n\n"
            "Bot developed by @mouhamed_ma\n"
            "Contact: @mouhamed_ma"
        ),
        "channel_info": f"{emoji('🔗')} Developer Channel:\n@forzd9",
        "lang_prompt": f"{emoji('🌐')} Choose your preferred language:",
        "lang_changed": f"{emoji('✅')} Arabic enabled.",
        "lang_changed_en": f"{emoji('✅')} English enabled.",
        "default_reply": f"{emoji('💬')} What do you want, {{name}}?",
        "default_reply_en": f"{emoji('💬')} What do you want, {{name}}?",
        "error": f"{emoji('❗️')} An error occurred, please try again.",
        "btn_id": "ID",
        "btn_account": "Account",
        "btn_creation_date": "Account creation date",
        "btn_photo": "Profile photo",
        "btn_dev": "Developer",
        "btn_channel": "Developer Channel",
        "btn_lang": "Change language",
        "btn_lang_ar": "العربية",
        "btn_lang_en": "English",
    },
}

# ============================================================
# التخزين المحلي: اللغة + أول ظهور في البوت فقط
# ============================================================
_data_lock = threading.Lock()


def load_user_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.error("تعذر تحميل %s: %s", DATA_FILE, exc)
        return {}


user_data = load_user_data()


def save_user_data():
    tmp = f"{DATA_FILE}.tmp"
    with _data_lock:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(user_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception as exc:
            logger.error("تعذر حفظ بيانات المستخدمين: %s", exc)


def ensure_user_record(user_id: int):
    key = str(user_id)
    changed = False
    if key not in user_data:
        user_data[key] = {}
        changed = True

    if "lang" not in user_data[key]:
        user_data[key]["lang"] = "ar"
        changed = True

    if "state" not in user_data[key]:
        user_data[key]["state"] = "main"
        changed = True

    if "first_seen_at" not in user_data[key]:
        user_data[key]["first_seen_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        changed = True

    if changed:
        save_user_data()


def get_user_lang(user_id: int) -> str:
    ensure_user_record(user_id)
    return user_data[str(user_id)].get("lang", "ar")


def set_user_lang(user_id: int, lang: str):
    ensure_user_record(user_id)
    user_data[str(user_id)]["lang"] = lang
    save_user_data()


def get_user_state(user_id: int) -> str:
    ensure_user_record(user_id)
    return user_data[str(user_id)].get("state", "main")


def set_user_state(user_id: int, state: str):
    ensure_user_record(user_id)
    user_data[str(user_id)]["state"] = state
    save_user_data()


def get_first_seen(user_id: int) -> str:
    ensure_user_record(user_id)
    value = user_data[str(user_id)].get("first_seen_at")
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return value or "غير معروف"


# ============================================================
# أزرار القائمة السفلية مع style + custom emoji
# ============================================================
def make_styled_button(text: str, icon_char: str, style: str) -> KeyboardButton:
    """
    Telegram يدعم style للأزرار الحديثة:
    primary / success / danger.

    ونضع icon_custom_emoji_id مباشرة على KeyboardButton حتى تستفيد
    من الإيموجيات الموجودة في ملفك. إذا كانت نسخة pyTelegramBotAPI
    قديمة، حدّثها إلى آخر إصدار.
    """
    button = KeyboardButton(text)

    # متوافق مع Bot API الحديثة. نستخدم setattr حتى لا يفشل الكود
    # مع بعض نسخ المكتبة التي لم تكن تضع الحقول في constructor.
    setattr(button, "style", style)
    emoji_id = CUSTOM_EMOJIS.get(icon_char)
    if emoji_id:
        setattr(button, "icon_custom_emoji_id", emoji_id)

    return button


def get_main_keyboard(lang: str):
    texts = TEXTS[lang]
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    keyboard.add(
        make_styled_button(texts["btn_id"], "🆔", "success"),
        make_styled_button(texts["btn_account"], "👤", "success"),
    )
    keyboard.add(
        make_styled_button(texts["btn_creation_date"], "📋", "primary"),
        make_styled_button(texts["btn_photo"], "🖼", "primary"),
    )
    keyboard.add(
        make_styled_button(texts["btn_dev"], "👨‍💻", "danger"),
        make_styled_button(texts["btn_channel"], "🔗", "danger"),
    )
    keyboard.add(
        make_styled_button(texts["btn_lang"], "🌐", "primary"),
    )
    return keyboard


def get_lang_selection_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        make_styled_button(TEXTS["ar"]["btn_lang_ar"], "🇸🇦", "success"),
        make_styled_button(TEXTS["en"]["btn_lang_en"], "🇬🇧", "primary"),
    )
    return keyboard


# ============================================================
# جلب معلومات المستخدم — لا يتم استدعاؤها إلا بعد اختيار الخدمة
# ============================================================
def get_user_info(user) -> dict:
    first_name = user.first_name or "غير معروف"
    username = user.username or ""
    user_id = user.id
    language = user.language_code or "غير معروف"

    bio = None
    if username:
        try:
            url = f"https://t.me/{username}"
            response = requests.get(
                url,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                meta_b = soup.find("meta", property="og:description")
                if meta_b and meta_b.get("content"):
                    bio = meta_b["content"]
        except Exception as exc:
            logger.warning("تعذر جلب السيرة الذاتية للمستخدم %s: %s", user_id, exc)

    if not bio:
        bio = "لا توجد سيرة ذاتية" if language.startswith("ar") else "No bio"

    return {
        "first_name": first_name,
        "username": username,
        "user_id": user_id,
        "language": language,
        "bio": bio,
    }


# ============================================================
# الإرسال
# ============================================================
def send_quoted(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """إرسال رسالة بصيغة blockquote مع الإيموجيات المخصصة."""
    quoted_text = f"<blockquote>{convert_custom_emojis(text)}</blockquote>"
    try:
        return bot.send_message(
            chat_id,
            quoted_text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
    except Exception as exc:
        logger.error("خطأ في إرسال رسالة مقتبسة: %s", exc)
        return bot.send_message(
            chat_id,
            convert_custom_emojis(text),
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


def send_main_menu(chat_id, lang):
    send_quoted(chat_id, TEXTS[lang]["welcome"], reply_markup=get_main_keyboard(lang))


def send_id_info(chat_id, user, lang):
    info = get_user_info(user)
    username = info["username"] or "لا يوجد"
    text = TEXTS[lang]["id_info"].format(
        user_id=info["user_id"],
        username=html.escape(username),
    )
    send_quoted(chat_id, text, reply_markup=get_main_keyboard(lang))


def send_account_info(chat_id, user, lang):
    info = get_user_info(user)
    username = info["username"] or "لا يوجد"
    text = TEXTS[lang]["account_info"].format(
        username=html.escape(username),
        user_id=info["user_id"],
        first_name=html.escape(info["first_name"]),
        bio=html.escape(info["bio"]),
        language=html.escape(info["language"]),
    )
    send_quoted(chat_id, text, reply_markup=get_main_keyboard(lang))


def send_account_creation_info(chat_id, user, lang):
    # التقدير يعتمد على ID فقط، ولا نرسل معلومات أخرى عند الضغط على هذا الزر.
    estimated = (
        estimate_account_creation_date_ar(user.id)
        if lang == "ar"
        else estimate_account_creation_date(user.id)
    )

    if not estimated:
        estimated = "غير متوفر" if lang == "ar" else "Unavailable"

    text = TEXTS[lang]["account_date_info"].format(
        estimated_date=html.escape(estimated)
    )
    send_quoted(chat_id, text, reply_markup=get_main_keyboard(lang))


def send_profile_photo(chat_id, user, lang):
    try:
        photos = bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            caption = emoji("🖼") + (" صورتك الحالية" if lang == "ar" else " Your current photo")
            bot.send_photo(
                chat_id,
                file_id,
                caption=convert_custom_emojis(f"<blockquote>{caption}</blockquote>"),
                parse_mode="HTML",
                reply_markup=get_main_keyboard(lang),
            )
        else:
            send_quoted(chat_id, TEXTS[lang]["no_photo"], reply_markup=get_main_keyboard(lang))
    except Exception as exc:
        logger.error("خطأ في جلب صورة الحساب: %s", exc)
        send_quoted(chat_id, TEXTS[lang]["error"], reply_markup=get_main_keyboard(lang))


def send_dev_info(chat_id, lang):
    send_quoted(chat_id, TEXTS[lang]["dev_info"], reply_markup=get_main_keyboard(lang))


def send_channel_info(chat_id, lang):
    send_quoted(chat_id, TEXTS[lang]["channel_info"], reply_markup=get_main_keyboard(lang))


def prompt_lang_selection(chat_id, lang):
    send_quoted(chat_id, TEXTS[lang]["lang_prompt"], reply_markup=get_lang_selection_keyboard())
    set_user_state(chat_id, "lang_select")


# ============================================================
# إنشاء البوت
# ============================================================
bot = telebot.TeleBot(TOKEN)


def set_bot_commands():
    commands = [BotCommand("start", "تشغيل البوت")]
    try:
        bot.set_my_commands(commands)
        logger.info("تم تعيين أوامر البوت بنجاح.")
    except Exception as exc:
        logger.error("خطأ في تعيين الأوامر: %s", exc)


# ============================================================
# /start
# مهم: لا نرسل أي معلومة عن المستخدم هنا.
# ============================================================
@bot.message_handler(commands=["start"])
def handle_start(message):
    chat_id = message.chat.id
    ensure_user_record(chat_id)
    set_user_state(chat_id, "main")
    lang = get_user_lang(chat_id)

    # فقط الترحيب + القائمة. معلومات المستخدم لا تُجلب هنا ولا تُرسل.
    send_main_menu(chat_id, lang)


# ============================================================
# الرسائل النصية للقائمة السفلية
# ============================================================
@bot.message_handler(func=lambda message: bool(message.text))
def handle_text(message):
    chat_id = message.chat.id
    user = message.from_user
    text = message.text.strip()

    ensure_user_record(chat_id)
    lang = get_user_lang(chat_id)
    state = get_user_state(chat_id)

    # اختيار اللغة
    if state == "lang_select":
        if text == TEXTS["ar"]["btn_lang_ar"]:
            set_user_lang(chat_id, "ar")
            set_user_state(chat_id, "main")
            send_quoted(chat_id, TEXTS["ar"]["lang_changed"], reply_markup=get_main_keyboard("ar"))
            return

        if text == TEXTS["en"]["btn_lang_en"]:
            set_user_lang(chat_id, "en")
            set_user_state(chat_id, "main")
            send_quoted(chat_id, TEXTS["en"]["lang_changed_en"], reply_markup=get_main_keyboard("en"))
            return

        prompt_lang_selection(chat_id, lang)
        return

    texts = TEXTS[lang]

    # هنا فقط يتم تنفيذ كل خدمة بعد ضغط المستخدم على الزر.
    if text == texts["btn_id"]:
        send_id_info(chat_id, user, lang)
    elif text == texts["btn_account"]:
        send_account_info(chat_id, user, lang)
    elif text == texts["btn_creation_date"]:
        send_account_creation_info(chat_id, user, lang)
    elif text == texts["btn_photo"]:
        send_profile_photo(chat_id, user, lang)
    elif text == texts["btn_dev"]:
        send_dev_info(chat_id, lang)
    elif text == texts["btn_channel"]:
        send_channel_info(chat_id, lang)
    elif text == texts["btn_lang"]:
        prompt_lang_selection(chat_id, lang)
    else:
        name = html.escape(user.first_name or ("صديق" if lang == "ar" else "Friend"))
        reply_key = "default_reply" if lang == "ar" else "default_reply_en"
        send_quoted(
            chat_id,
            texts[reply_key].format(name=name),
            reply_markup=get_main_keyboard(lang),
        )


# ============================================================
# التشغيل
# ============================================================
if __name__ == "__main__":
    try:
        set_bot_commands()
        logger.info("البوت بدأ العمل...")
        bot.infinity_polling(skip_pending=True)
    except Exception as exc:
        logger.exception("خطأ في تشغيل البوت: %s", exc)
