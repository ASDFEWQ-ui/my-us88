import os
import sys
import sqlite3
import logging
import traceback
import asyncio
import json
import re
import time
import requests
import random
import uuid
import threading
import qrcode
import zipfile
import shutil
from datetime import datetime, timedelta
from urllib.parse import quote
from io import BytesIO

# ======================================================
# مدیریت منطقه زمانی
# ======================================================
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
    TZ_AVAILABLE = True
except ImportError:
    TZ_AVAILABLE = False
    class _FallbackTZ:
        def __init__(self):
            self.offset = timedelta(hours=3, minutes=30)
        def utcoffset(self, dt):
            return self.offset
        def dst(self, dt):
            return timedelta(0)
        def tzname(self, dt):
            return "Asia/Tehran"
        def fromutc(self, dt):
            return dt + self.offset
    TEHRAN_TZ = _FallbackTZ()

def get_now():
    if TZ_AVAILABLE:
        return datetime.now(TEHRAN_TZ)
    else:
        return datetime.utcnow() + timedelta(hours=3, minutes=30)

# ======================================================
# پچ کردن jdatetime
# ======================================================
class _FakePytz:
    class timezone:
        def __init__(self, name):
            self.name = name
        def localize(self, dt):
            return dt
        def normalize(self, dt):
            return dt
        def utcoffset(self, dt):
            return timedelta(hours=3, minutes=30)
        def tzname(self, dt):
            return "Asia/Tehran"
        def fromutc(self, dt):
            return dt + self.offset
    
    @staticmethod
    def timezone(name):
        return _FakePytz.timezone(name)

if 'pytz' not in sys.modules:
    import types
    sys.modules['pytz'] = types.ModuleType('pytz')
    sys.modules['pytz'].timezone = _FakePytz.timezone

import jdatetime
from hijridate import Gregorian
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler
from telegram.request import HTTPXRequest
from telethon import TelegramClient, events, types
from telethon.tl.types import PeerUser, PeerChannel, PeerChat, MessageMediaPhoto, MessageMediaDocument, ReactionEmoji, MessageEntityBold, MessageEntityUnderline, MessageEntityStrike, MessageEntityBlockquote, MessageEntitySpoiler, MessageEntityItalic, MessageEntityCode, MessageEntityPre, InputMediaDice
from telethon.tl.functions.messages import SendReactionRequest, DeleteMessagesRequest, SetTypingRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest, GetAuthorizationsRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError, ChatWriteForbiddenError
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsAdmins
import psutil
from platform import python_version, uname
from PIL import Image, ImageDraw, ImageFont, ImageOps
import urllib.parse

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Gap_5_bot",
        "version": "5.0.0"
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@flask_app.route('/ping')
def ping():
    return jsonify({"status": "alive", "message": "Bot is awake"}), 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 وب سرور روی پورت {port} در حال اجراست")
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

os.environ['TZ'] = 'Asia/Tehran'
try:
    time.tzset()
except:
    pass

# ======================================================
# APIهای جدید هوش مصنوعی
# ======================================================
AI_APIS = {
    'deepseek': {
        'url': 'https://api.fast-creat.ir/deepseek',
        'api_key': '7390175402:vtNJfwze0nbrHa9@Api_ManagerRoBot',
        'param': 'text',
        'name': '🧠 DeepSeek',
        'emoji': '🧠'
    },
    'chatgpt': {
        'url': 'https://api.fast-creat.ir/gpt/chat',
        'api_key': '7390175402:zbkOlDihx5KZdE9@Api_ManagerRoBot',
        'param': 'text',
        'name': '💬 ChatGPT',
        'emoji': '💬'
    },
    'grok': {
        'url': 'https://api.fast-creat.ir/grokai',
        'api_key': '7390175402:atEpvOeyX3zT51f@Api_ManagerRoBot',
        'param': 'text',
        'name': '🤖 Grok',
        'emoji': '🤖'
    },
    'blackbox': {
        'url': 'https://api.fast-creat.ir/blackbox',
        'api_key': '7390175402:gJzhBi60f1YNWVt@Api_ManagerRoBot',
        'param': 'text',
        'name': '📦 Blackbox',
        'emoji': '📦'
    },
    'openai': {
        'url': 'https://ai.aimlapi.com',
        'api_key': '8a3951510fb6ab9c72cf9e76b6bc4d7c',
        'param': 'model',
        'name': '🟢 OpenAI',
        'emoji': '🟢'
    }
}

# ======================================================
# APIهای ساخت عکس و لوگو
# ======================================================
PHOTO_APIS = {
    'aiphoto': {
        'url': 'https://api.fast-creat.ir/aiphoto',
        'api_key': '7390175402:sAIBQDaYrhSxWEi@Api_ManagerRoBot',
        'params': ['text', 'style'],
        'name': '🖼️ ساخت عکس با هوش'
    },
    'gpt_photo': {
        'url': 'https://api.fast-creat.ir/gpt/photo',
        'api_key': '7390175402:vwcmUg6nhzNoXMx@Api_ManagerRoBot',
        'params': ['text'],
        'name': '🖼️ ساخت عکس با GPT'
    },
    'ghibli': {
        'url': 'https://api.fast-creat.ir/ghibli',
        'api_key': '7390175402:FXv2dAQyZDieHrJ@Api_ManagerRoBot',
        'params': ['url'],
        'name': '🎨 سبک جیبلی'
    },
    'logo': {
        'url': 'https://api.fast-creat.ir/logo',
        'api_key': '7390175402:zAFdJKMivH3ScCb@Api_ManagerRoBot',
        'params': ['type', 'id', 'text'],
        'name': '🎨 لوگو ساز'
    }
}

# ======================================================
# APIهای ارز و بازار
# ======================================================
MARKET_APIS = {
    'crypto': {
        'url': 'https://Api.BrsApi.ir/Market/Cryptocurrency.php',
        'api_key': 'Bh1KUaakWIf9BztkrNurWfFl2nuCwhh8',
        'param': 'key',
        'name': '💰 ارزهای دیجیتال'
    },
    'gold_currency': {
        'url': 'https://Api.BrsApi.ir/Market/Gold_Currency.php',
        'api_key': 'Bh1KUaakWIf9BztkrNurWfFl2nuCwhh8',
        'param': 'key',
        'name': '💎 طلا و ارز'
    },
    'bourse': {
        'url': 'https://Api.BrsApi.ir/Tsetmc/AllSymbols.php',
        'api_key': 'Bh1KUaakWIf9BztkrNurWfFl2nuCwhh8',
        'params': ['key', 'type'],
        'name': '📊 بورس'
    },
    'nobitex_v2': {
        'url': 'https://api.fast-creat.ir/nobitex/v2',
        'api_key': '7390175402:yAGomhT1NdFV0UY@Api_ManagerRoBot',
        'param': 'apikey',
        'name': '💵 نرخ ارز ۲'
    }
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ======================================================
# تنظیمات اولیه
# ======================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده!")
ADMIN_ID = 6443963679
BOT_USERNAME = "Gap_5_bot"
MUSIC_BOT = "Gap_4_bot"

SESSIONS_FOLDER = 'user_sessions'
if not os.path.exists(SESSIONS_FOLDER):
    os.makedirs(SESSIONS_FOLDER)

GROUP_ID = -1002817019483

MEDIA_FOLDER = 'media_storage'
if not os.path.exists(MEDIA_FOLDER):
    os.makedirs(MEDIA_FOLDER)

REPORT_CONFIG_FILE = "report_config.json"
REPORT_MEDIA_FOLDER = 'reported_media'
if not os.path.exists(REPORT_MEDIA_FOLDER):
    os.makedirs(REPORT_MEDIA_FOLDER)

ALLOWED_EMOJIS = [
    "🤯", "🐳", "😍", "💩", "👏", "🍌", "🤓", "😢", "🙉", "🤩",
    "🤝", "👀", "🌚", "🗿", "🤡", "😐", "👨‍💻", "😭", "🙈", "❤",
    "🙏", "😴", "💋", "🥰", "🤪", "✍️", "🥱", "👻", "🤣", "🌭",
    "😨", "🍓", "🔥", "🖕", "🤗", "🤔", "🤬", "😁", "🎄", "🫡",
    "⚡", "🥴", "😈", "🏆", "😇", "🎃", "☃️", "🤮", "👍", "👎",
    "😱", "😖", "🕊", "💯", "💔", "🤨", "❤️‍🔥", "💘", "😘", "💊",
    "🆒", "🤷‍♂", "🤷‍♀", "🎅"
]

def full_chat_id_to_short(full_id):
    if full_id is None:
        return None
    try:
        full_id = int(full_id)
    except (TypeError, ValueError):
        return None
    abs_id = abs(full_id)
    if abs_id > 10**12:
        return abs_id - 10**12
    return abs_id

# ======================================================
# فونت‌های تایم
# ======================================================
classic_fonts = [
    "⊘𝟷ϩӠ4ƼϬ7𝟾९",
    "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
    "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
    "⓿①❷③❹⑤❻⑦❽⑨",
    "₀₁₂₃₄₅₆₇₈₉",
    "⁰¹²³⁴⁵⁶⁷⁸⁹",
    "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
    "₀¹²³⁴⁵⁶₇₈₉",
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕۸𝟗",
    "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹",
    "𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵",
    "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥",
    "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍",
    "𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩"
]

flags = [
    "🇦🇱", "🇩🇿", "🇦🇸", "🇦🇩", "🇦🇼", "🇦🇹", "🇦🇿",
    "🇧🇸", "🇧🇭", "🇧🇩", "🇧🇧", "🇧🇾", "🇧🇪", "🇧🇿",
    "🇧🇯", "🇧🇲", "🇧🇹", "🇧🇦", "🇧🇷", "🇧🇳", "🇧🇬",
    "🇧🇫", "🇧🇮", "🇰🇭", "🇨🇲", "🇨🇦", "🇨🇻", "🇨🇫",
    "🇨🇱", "🇨🇳", "🇨🇴", "🇨🇷", "🇭🇷", "🇨🇺", "🇨🇾",
    "🇨🇿", "🇩🇰", "🇩🇯", "🇩🇲", "🇩🇴", "🇪🇨", "🇪🇬",
    "🇸🇻", "🇬🇶", "🇪🇷", "🇪🇪", "🇸🇿", "🇪🇹", "🇫🇯",
    "🇫🇮", "🇫🇷", "🇬🇦", "🇬🇲", "🇬🇪", "🇩🇪", "🇬🇭",
    "🇬🇷", "🇬🇱", "🇬🇩", "🇬🇹", "🇬🇳", "🇬🇾", "🇭🇹",
    "🇭🇳", "🇭🇺", "🇮🇸", "🇮🇳", "🇮🇩", "🇮🇷", "🇮🇶",
    "🇮🇪", "🇮🇱", "🇮🇹", "🇯🇲", "🇯🇵", "🇯🇴", "🇰🇿",
    "🇰🇪", "🇰🇮", "🇰🇼", "🇰🇬", "🇱🇦", "🇱🇻", "🇱🇧",
    "🇱🇸", "🇱🇷", "🇱🇾", "🇱🇮", "🇱🇹", "🇱🇺", "🇲🇬",
    "🇲🇼", "🇲🇾", "🇲🇻", "🇲🇱", "🇲🇹", "🇲🇭", "🇲🇷",
    "🇲🇺", "🇲🇽", "🇫🇲", "🇲🇩", "🇲🇨", "🇲🇳", "🇲🇪",
    "🇲🇦", "🇲🇿", "🇲🇲", "🇳🇦", "🇳🇷", "🇳🇵", "🇳🇱",
    "🇳🇿", "🇳🇮", "🇳🇪", "🇳🇬", "🇰🇵", "🇳🇴", "🇴🇲",
    "🇵🇰", "🇵🇼", "🇵🇦", "🇵🇬", "🇵🇾", "🇵🇪", "🇵🇭",
    "🇵🇱", "🇵🇹", "🇶🇦", "🇨🇩", "🇷🇴", "🇷🇺", "🇷🇼",
    "🇰🇳", "🇱🇨", "🇻🇨", "🇼🇸", "🇸🇲", "🇸🇹", "🇸🇦",
    "🇸🇳", "🇷🇸", "🇸🇨", "🇸🇱", "🇸🇬", "🇸🇰", "🇸🇮",
    "🇸🇧", "🇸🇴", "🇿🇦", "🇰🇷", "🇸🇸", "🇪🇸", "🇱🇰",
    "🇸🇩", "🇸🇷", "🇸🇪", "🇨🇭", "🇸🇾", "🇹🇼", "🇹🇯",
    "🇹🇿", "🇹🇭", "🇹🇱", "🇹🇬", "🇹🇴", "🇹🇹", "🇹🇳",
    "🇹🇷", "🇹🇲", "🇹🇻", "🇺🇬", "🇺🇦", "🇦🇪", "🇬🇧",
    "🇺🇸", "🇺🇾", "🇺🇿", "🇻🇺", "🇻🇦", "🇻🇪", "🇻🇳",
    "🇾🇪", "🇿🇲", "🇿🇼"
]

SPAM_MESSAGES = [
    "مادربزرگت کسده، کسشو تو قبرم اجاره داده",
    "پدربزرگت کونی، هنوزم تو گور کونشو به شیاطین می‌سپره",
    "کس ننت چنان بازه، کل شهر توش چادر زدن",
]

BOT_VERSION = "5.0.0"
BOT_CREATOR = "Self-Bot AI Assistant"

HEARTS = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🤍"]
MOONS = ["🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘", "🌑"]

media_cache = {}
message_cache = {}
user_inline_messages = {}

action_types = {
    'تایپ': types.SendMessageTypingAction(),
    'ویس': types.SendMessageRecordAudioAction(),
    'ویدیو': types.SendMessageRecordVideoAction(),
    'عکس': types.SendMessageUploadPhotoAction(progress=0),
    'فیلم': types.SendMessageUploadVideoAction(progress=0),
    'فایل': types.SendMessageUploadDocumentAction(progress=0),
    'بازی': types.SendMessageGamePlayAction(),
    'استیکر': types.SendMessageChooseStickerAction(),
    'موقعیت': types.SendMessageGeoLocationAction(),
    'تماس': types.SendMessageChooseContactAction(),
    'صحبت': types.SpeakingInGroupCallAction(),
    'لغو': types.SendMessageCancelAction(),
}

R = "❤️"
W = "🤍"
SLEEP = 0.1

def create_heart_matrix(size):
    heart = []
    for i in range(size):
        row = ""
        for j in range(size):
            if (i == 0 and (j == 0 or j == size-1)) or \
               (i == 1 and (j == 0 or j == 1 or j == size-2 or j == size-1)) or \
               (i == 2 and (j == 0 or j == 1 or j == 2 or j == size-3 or j == size-2 or j == size-1)) or \
               (i >= 3 and i < size-1 and (j >= i-2 and j <= size-(i-2)-1)) or \
               (i == size-1 and (j >= size//2 - 1 and j <= size//2 + 1)):
                row += R
            else:
                row += W
        heart.append(row)
    return "\n".join(heart)

JOINED_HEART = create_heart_matrix(7)
HEARTLET_LEN = JOINED_HEART.count(R)

# ======================================================
# توابع کمکی
# ======================================================
def convert_persian_to_english(text):
    if not text:
        return text
    persian_to_english = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
        '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    for persian, english in persian_to_english.items():
        text = text.replace(persian, english)
    return text

def create_time():
    return get_now().strftime("%H:%M")

def create_time2():
    return get_now().strftime("%H:%M:%S")

def create_tarikh():
    jdatetime.set_locale('fa_IR')
    jd = jdatetime.date.fromgregorian(date=get_now().date())
    return jd.strftime("%Y/%m/%d")

def create_tarikh2():
    jdatetime.set_locale('fa_IR')
    jd = jdatetime.date.fromgregorian(date=get_now().date())
    return jd.strftime("%A %d %B %Y")

def moon_or_sun():
    hour = int(get_now().strftime("%H"))
    return "☀️ روز" if 6 <= hour < 18 else "🌙 شب"

def love_emoji():
    emojis = ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '💖', '💗', '💓', '💕', '💞', '💘', '💝']
    return random.choice(emojis)

def random_emoji():
    emojis = ['🔥', '⭐', '🌟', '✨', '💫', '🌈', '🎯', '🏆', '👑', '💎', '🎨', '🎭', '🎪', '🎯', '🎲']
    return random.choice(emojis)

def get_weekday():
    weekdays = {
        'Saturday': 'شنبه', 'Sunday': 'یکشنبه', 'Monday': 'دوشنبه',
        'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه', 'Thursday': 'پنج‌شنبه',
        'Friday': 'جمعه'
    }
    return weekdays.get(get_now().strftime('%A'), get_now().strftime('%A'))

def get_season():
    month = get_now().month
    if 3 <= month <= 5:
        return '🌸 بهار'
    elif 6 <= month <= 8:
        return '☀️ تابستان'
    elif 9 <= month <= 11:
        return '🍂 پاییز'
    else:
        return '❄️ زمستان'

fortunes = [
    "🌟 امروز روز خوبی برای شروع کارهای جدید است.",
    "💫 یک خبر خوب در راه است، منتظر باش.",
    "🌙 امشب ستاره‌ها به نفع تو هستند.",
    "🌸 عشق در گوشه و کنار زندگی توست، فقط باید ببینی.",
    "💰 یک فرصت مالی عالی در انتظار توست.",
    "🎯 به هدف‌هایت نزدیک‌تر شدی، ادامه بده.",
    "🌟 کسی که دوستش داری، به تو فکر می‌کند.",
    "🌈 روزت پر از رنگ و انرژی خواهد بود.",
    "💪 امروز قوی‌تر از همیشه‌ای، از این قدرت استفاده کن.",
    "🎉 جشن و شادی در راه است.",
    "📚 وقت آن رسیده که چیز جدیدی یاد بگیری.",
    "🤝 یک دوست جدید پیدا می‌کنی.",
    "💖 قلب تو امروز پر از عشق خواهد بود.",
    "🌟 ستاره بختت درخشان است.",
    "🎯 هر چه امروز بکاری، فردا درو می‌کنی.",
    "🌙 امشب رویاهایت را جدی بگیر.",
    "🌸 بهار زندگی تو شروع شده است.",
    "💰 پول و ثروت به سمت تو می‌آید.",
    "🎨 امروز خلاقیت تو در اوج است.",
    "🏆 موفقیت بزرگ در انتظار توست."
]

hafez_fortunes = [
    ("غم و شادی در این جهان به هم پیوسته‌اند", "🍃"),
    ("دل به امید وصل تو زنده است", "💕"),
    ("هر چه خواهی، همان خواهی یافت", "🌟"),
    ("صبر کن که گشایش در کار توست", "🌙"),
    ("عشق تو را به اوج می‌رساند", "❤️"),
    ("دوری و نزدیکی تقدیر توست", "🕊️"),
    ("بهار عمرت از راه رسید", "🌸"),
    ("دل به دریا بزن که نجات یابی", "🌊"),
]

coffee_fortunes = [
    "☕ عشق جدیدی وارد زندگی تو می‌شود",
    "☕ یک سفر طولانی در انتظار توست",
    "☕ خبر خوش از دور دست می‌رسد",
    "☕ به زودی ثروت زیادی به دست می‌آوری",
    "☕ کسی که دوستش داری، به تو نزدیک‌تر می‌شود",
    "☕ کارهای ناتمامت را امروز تمام کن",
    "☕ یک پیشنهاد عالی دریافت می‌کنی",
]

def is_channel_post(message):
    try:
        if hasattr(message, 'post') and message.post:
            return True
        if hasattr(message, 'is_channel') and message.is_channel:
            if hasattr(message, 'is_group') and not message.is_group:
                return True
            if not hasattr(message, 'from_id') or not message.from_id:
                return True
        if hasattr(message, 'chat') and message.chat:
            chat = message.chat
            if hasattr(chat, 'broadcast') and chat.broadcast:
                return True
        if hasattr(message, 'fwd_from') and message.fwd_from:
            if hasattr(message.fwd_from, 'from_id'):
                if hasattr(message.fwd_from.from_id, 'channel_id'):
                    return True
        return False
    except:
        return False

def is_link_message(text):
    if not text:
        return False
    patterns = [
        r'https?://\S+',
        r't\.me/\S+',
        r'www\.\S+',
        r'\S+\.(com|ir|org|net|info)\S*'
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def is_emoji_message(text):
    if not text:
        return False
    text = text.strip()
    if not text:
        return False
    emoji_pattern = re.compile(
        r'^[\U0001F600-\U0001F64F' 
        r'\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF'
        r'\U00002700-\U000027BF'
        r'\U000024C2-\U0001F251'
        r'\U0001F900-\U0001F9FF'
        r']+$', 
        flags=re.UNICODE
    )
    return bool(emoji_pattern.match(text))

def convert_to_classic_font(text, font_index):
    if isinstance(classic_fonts[font_index], dict):
        font = classic_fonts[font_index]
        return ''.join(font.get(c, c) for c in text)
    else:
        font = classic_fonts[font_index]
        return ''.join(font[int(c)] if c.isdigit() else c for c in text)

COMMAND_KEYWORDS = ('لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال', 'حذف', 'ست', 'بولد', 'زیرخط', 'خط خورده', 'نقل قول', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک', 'ریکت', 'پیوی', 'گروه', 'درباره', 'من کی ام', 'قفل', 'باز', 'تنظیم', 'گروه گزارش', 'دشمن', 'دوست', 'کانال', 'کامنت', 'تست', 'لیست دشمن', 'لیست اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'اضافه اسپم', 'اتمام اسپم', 'تغییر اسم', 'تغییر بیو', 'تغییر پروفایل', 'پروف', 'اسپم روشن', 'اسپم خاموش', 'پینگ', 'سرچ', 'خروج سرچ', 'قلب پیشرفته', 'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', '/panel', '.اهنگ', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش', 'پین', 'تگ ادمین', 'امار گپ', '.کد', 'تقویم', 'فونت', 'انگلیسی', 'عربی', 'عبری', 'روسی', 'ترکی', 'اتوسین', 'تگ همه', 'لغو تگ', 'منشی', 'افزودن پاسخ', 'حذف پاسخ', 'لیست پاسخ', 'پاک کردن پاسخ‌ها', 'بولینگ', 'تاس', 'سه رنگ', 'شانس', 'تاریخ ساخت اکانت', 'نشست‌های فعال', 'اطلاعات سیستم', 'قیمت ارز', 'نرخ ارز', 'ریاضی', 'تبدیل ارز', 'استیکر متن', 'اسکرین‌شات', 'تشخیص متن', 'فرمول', 'ساعت در بیو', 'ساعت در بیو ۲', 'بیو تاریخ', 'بیو کامل', 'بیو عاشقانه', 'عکس', 'جیبلی', 'لوگو', 'دلار', 'طلا', 'نقره', 'بورس', 'ارز')

# ======================================================
# نگاشت زبان‌ها برای ترجمه
# ======================================================
TRANSLATE_LANG_CODES = {
    'english': 'en',
    'arabic': 'ar',
    'hebrew': 'iw',
    'russian': 'ru',
    'turkish': 'tr',
}

# ======================================================
# توابع API
# ======================================================
async def call_ai_api(api_name, text):
    """فراخوانی API هوش مصنوعی"""
    try:
        api = AI_APIS[api_name]
        url = f"{api['url']}?apikey={api['api_key']}&{api['param']}={quote(text)}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"خطا در فراخوانی AI {api_name}: {e}")
        return None

async def generate_photo(photo_type, text=None, style=None, url=None, logo_id=None, logo_text=None):
    """ساخت عکس یا لوگو"""
    try:
        api = PHOTO_APIS[photo_type]
        if photo_type == 'aiphoto':
            full_url = f"{api['url']}?apikey={api['api_key']}&text={quote(text)}&style={quote(style or 'default')}"
        elif photo_type == 'gpt_photo':
            full_url = f"{api['url']}?apikey={api['api_key']}&text={quote(text)}"
        elif photo_type == 'ghibli':
            full_url = f"{api['url']}?apikey={api['api_key']}&url={quote(url)}"
        elif photo_type == 'logo':
            full_url = f"{api['url']}?apikey={api['api_key']}&type=logo&id={logo_id}&text={quote(logo_text)}"
        else:
            return None
        response = requests.get(full_url, timeout=30)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        logger.error(f"خطا در ساخت عکس {photo_type}: {e}")
        return None

async def get_crypto_prices():
    """دریافت قیمت ارزهای دیجیتال"""
    try:
        url = f"{MARKET_APIS['crypto']['url']}?{MARKET_APIS['crypto']['param']}={MARKET_APIS['crypto']['api_key']}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت قیمت ارز: {e}")
        return None

async def get_gold_prices():
    """دریافت قیمت طلا و ارز"""
    try:
        url = f"{MARKET_APIS['gold_currency']['url']}?{MARKET_APIS['gold_currency']['param']}={MARKET_APIS['gold_currency']['api_key']}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت قیمت طلا: {e}")
        return None

async def get_bourse_data(symbol_type='index'):
    """دریافت اطلاعات بورس"""
    try:
        url = f"{MARKET_APIS['bourse']['url']}?key={MARKET_APIS['bourse']['api_key']}&type={symbol_type}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات بورس: {e}")
        return None

async def get_nobitex_rate():
    """دریافت نرخ ارز از Nobitex"""
    try:
        url = f"{MARKET_APIS['nobitex_v2']['url']}?{MARKET_APIS['nobitex_v2']['param']}={MARKET_APIS['nobitex_v2']['api_key']}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت نرخ ارز: {e}")
        return None

# ======================================================
# کلاس ReportConfig
# ======================================================
class ReportConfig:
    def __init__(self, user_id, config_file=REPORT_CONFIG_FILE):
        self.user_id = user_id
        self.config_file = config_file
        self.report_group_id = GROUP_ID
        self.auto_save_media = True
        self.report_deleted_media = True
        self.report_edited_messages = True
        self.report_ttl_media = True
        self.load_config()
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    user_settings = data.get(str(self.user_id), {})
                    self.report_group_id = user_settings.get('report_group_id', GROUP_ID)
                    self.auto_save_media = user_settings.get('auto_save_media', True)
                    self.report_deleted_media = user_settings.get('report_deleted_media', True)
                    self.report_edited_messages = user_settings.get('report_edited_messages', True)
                    self.report_ttl_media = user_settings.get('report_ttl_media', True)
                logger.info(f"تنظیمات گزارش برای کاربر {self.user_id} لود شد")
            else:
                self.save_config()
        except Exception as e:
            logger.error(f"خطا در بارگذاری تنظیمات: {e}")
    
    def save_config(self):
        try:
            data = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
            
            data[str(self.user_id)] = {
                'report_group_id': self.report_group_id,
                'auto_save_media': self.auto_save_media,
                'report_deleted_media': self.report_deleted_media,
                'report_edited_messages': self.report_edited_messages,
                'report_ttl_media': self.report_ttl_media
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            
            logger.info(f"تنظیمات گزارش برای کاربر {self.user_id} ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره تنظیمات: {e}")
    
    def set_report_group(self, group_id):
        self.report_group_id = group_id
        self.save_config()
        return f"✅ گروه گزارش به {group_id} تغییر کرد"
    
    def toggle_auto_save(self):
        self.auto_save_media = not self.auto_save_media
        self.save_config()
        status = "فعال" if self.auto_save_media else "غیرفعال"
        return f"✅ ذخیره خودکار رسانه‌ها {status} شد"

# ======================================================
# کلاس دیتابیس اصلی
# ======================================================
class MainDatabase:
    def __init__(self, db_name='main_database.db'):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # جدول users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                phone TEXT,
                self_active BOOLEAN DEFAULT 0,
                admin_approved BOOLEAN DEFAULT 0,
                rejected BOOLEAN DEFAULT 0,
                request_sent BOOLEAN DEFAULT 0,
                step TEXT,
                phone_code_hash TEXT,
                code TEXT,
                password TEXT,
                request_date TEXT,
                activation_date TEXT,
                expiration_date TEXT,
                session_file TEXT,
                api_id INTEGER,
                api_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول selfbot_settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS selfbot_settings (
                user_id INTEGER PRIMARY KEY,
                time_enabled BOOLEAN DEFAULT 0,
                flag_enabled BOOLEAN DEFAULT 0,
                selected_flag TEXT,
                pv_lock_all BOOLEAN DEFAULT 0,
                autosend_mode BOOLEAN DEFAULT 0,
                text_style TEXT,
                report_group_id INTEGER DEFAULT -1002817019483,
                ai_deepseek_pm BOOLEAN DEFAULT 0,
                ai_chatgpt_pm BOOLEAN DEFAULT 0,
                ai_grok_pm BOOLEAN DEFAULT 0,
                ai_blackbox_pm BOOLEAN DEFAULT 0,
                ai_openai_pm BOOLEAN DEFAULT 0,
                ai_deepseek_group BOOLEAN DEFAULT 0,
                ai_chatgpt_group BOOLEAN DEFAULT 0,
                ai_grok_group BOOLEAN DEFAULT 0,
                ai_blackbox_group BOOLEAN DEFAULT 0,
                ai_openai_group BOOLEAN DEFAULT 0,
                translate_english BOOLEAN DEFAULT 0,
                translate_arabic BOOLEAN DEFAULT 0,
                translate_hebrew BOOLEAN DEFAULT 0,
                translate_russian BOOLEAN DEFAULT 0,
                translate_turkish BOOLEAN DEFAULT 0,
                panel_mode BOOLEAN DEFAULT 1,
                time_font_indices TEXT,
                filter_enabled BOOLEAN DEFAULT 0,
                selfbot_enabled BOOLEAN DEFAULT 1,
                buttons_enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # سایر جدول‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS media_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                target_id INTEGER,
                lock_link BOOLEAN DEFAULT 0,
                lock_photo BOOLEAN DEFAULT 0,
                lock_video BOOLEAN DEFAULT 0,
                lock_sticker BOOLEAN DEFAULT 0,
                lock_gif BOOLEAN DEFAULT 0,
                lock_voice BOOLEAN DEFAULT 0,
                lock_file BOOLEAN DEFAULT 0,
                lock_music BOOLEAN DEFAULT 0,
                lock_video_note BOOLEAN DEFAULT 0,
                lock_contact BOOLEAN DEFAULT 0,
                lock_location BOOLEAN DEFAULT 0,
                lock_emoji BOOLEAN DEFAULT 0,
                lock_text BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, target_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                target_id INTEGER,
                lock_type TEXT,
                enabled BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, target_id, lock_type)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enemies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                enemy_id INTEGER,
                chat_type TEXT DEFAULT 'pv',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, enemy_id, chat_type)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locked_pvs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                locked_user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, locked_user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                target_id INTEGER,
                emoji TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, chat_id, target_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                channel_id INTEGER,
                comment_text TEXT,
                channel_title TEXT,
                channel_type TEXT,
                channel_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, channel_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                comment_sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, channel_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                message_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, chat_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enemy_spam_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                spam_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS filter_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                word TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, word)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spam_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                spam_protection BOOLEAN DEFAULT 0,
                spam_limit INTEGER DEFAULT 10,
                mute_duration INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pinned_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                message_id INTEGER,
                pinned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_id, chat_id, message_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bio_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                setting_name TEXT,
                status TEXT DEFAULT 'خاموش',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, setting_name)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, question)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monshi_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status BOOLEAN DEFAULT 0,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_bio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bio_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                known_name TEXT,
                chat_id INTEGER,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key TEXT,
                value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_memory (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                message_text TEXT,
                message_type TEXT DEFAULT 'text',
                media_file TEXT,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # اضافه کردن ستون‌های جدید
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'api_id' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN api_id INTEGER")
        if 'api_hash' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN api_hash TEXT")
        
        cursor.execute("PRAGMA table_info(selfbot_settings)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'buttons_enabled' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN buttons_enabled BOOLEAN DEFAULT 1")
        if 'selected_flag' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN selected_flag TEXT")
        if 'ai_deepseek_pm' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_deepseek_pm BOOLEAN DEFAULT 0")
        if 'ai_chatgpt_pm' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_chatgpt_pm BOOLEAN DEFAULT 0")
        if 'ai_grok_pm' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_grok_pm BOOLEAN DEFAULT 0")
        if 'ai_blackbox_pm' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_blackbox_pm BOOLEAN DEFAULT 0")
        if 'ai_openai_pm' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_openai_pm BOOLEAN DEFAULT 0")
        if 'ai_deepseek_group' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_deepseek_group BOOLEAN DEFAULT 0")
        if 'ai_chatgpt_group' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_chatgpt_group BOOLEAN DEFAULT 0")
        if 'ai_grok_group' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_grok_group BOOLEAN DEFAULT 0")
        if 'ai_blackbox_group' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_blackbox_group BOOLEAN DEFAULT 0")
        if 'ai_openai_group' not in columns:
            cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN ai_openai_group BOOLEAN DEFAULT 0")
        
        conn.commit()
        conn.close()
        logger.info("✓ دیتابیس اصلی ایجاد شد")
    
    # ======================================================
    # متدهای دیتابیس
    # ======================================================
    def add_user(self, user_id, full_name, username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO users (user_id, full_name, username, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)', (user_id, full_name, username))
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        return dict(zip(columns, row)) if row else None
    
    def update_user(self, user_id, **kwargs):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values())
        values.append(user_id)
        cursor.execute(f'UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', values)
        conn.commit()
        conn.close()
    
    def get_pending_requests(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE request_sent = 1 AND admin_approved = 0 AND rejected = 0 AND step IS NULL ORDER BY request_date DESC')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_pending_login(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE admin_approved = 1 AND self_active = 0 AND step IS NOT NULL ORDER BY activation_date DESC')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_active_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE self_active = 1 AND admin_approved = 1 ORDER BY activation_date DESC')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_all_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, full_name, username, phone, self_active, created_at FROM users ORDER BY created_at DESC')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_selfbot_settings(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM selfbot_settings WHERE user_id = ?', (user_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        
        if row:
            settings = dict(zip(columns, row))
            settings['ai_status'] = {
                'ai_deepseek_pm': bool(settings.get('ai_deepseek_pm', 0)),
                'ai_chatgpt_pm': bool(settings.get('ai_chatgpt_pm', 0)),
                'ai_grok_pm': bool(settings.get('ai_grok_pm', 0)),
                'ai_blackbox_pm': bool(settings.get('ai_blackbox_pm', 0)),
                'ai_openai_pm': bool(settings.get('ai_openai_pm', 0)),
                'ai_deepseek_group': bool(settings.get('ai_deepseek_group', 0)),
                'ai_chatgpt_group': bool(settings.get('ai_chatgpt_group', 0)),
                'ai_grok_group': bool(settings.get('ai_grok_group', 0)),
                'ai_blackbox_group': bool(settings.get('ai_blackbox_group', 0)),
                'ai_openai_group': bool(settings.get('ai_openai_group', 0))
            }
            settings['translate'] = {
                'english': bool(settings.get('translate_english', 0)),
                'arabic': bool(settings.get('translate_arabic', 0)),
                'hebrew': bool(settings.get('translate_hebrew', 0)),
                'russian': bool(settings.get('translate_russian', 0)),
                'turkish': bool(settings.get('translate_turkish', 0))
            }
            time_font_indices = settings.get('time_font_indices', 'all')
            if time_font_indices and time_font_indices != 'all':
                try:
                    settings['time_font_indices'] = [int(x) for x in time_font_indices.split(',')]
                except:
                    settings['time_font_indices'] = 'all'
            else:
                settings['time_font_indices'] = 'all'
            settings.setdefault('selfbot_enabled', 1)
            settings.setdefault('buttons_enabled', 1)
            settings.setdefault('selected_flag', None)
            return settings
        else:
            default_settings = {
                'user_id': user_id,
                'time_enabled': 0,
                'flag_enabled': 0,
                'selected_flag': None,
                'pv_lock_all': 0,
                'autosend_mode': 0,
                'text_style': None,
                'report_group_id': GROUP_ID,
                'ai_deepseek_pm': 0,
                'ai_chatgpt_pm': 0,
                'ai_grok_pm': 0,
                'ai_blackbox_pm': 0,
                'ai_openai_pm': 0,
                'ai_deepseek_group': 0,
                'ai_chatgpt_group': 0,
                'ai_grok_group': 0,
                'ai_blackbox_group': 0,
                'ai_openai_group': 0,
                'translate_english': 0,
                'translate_arabic': 0,
                'translate_hebrew': 0,
                'translate_russian': 0,
                'translate_turkish': 0,
                'panel_mode': 1,
                'time_font_indices': 'all',
                'filter_enabled': 0,
                'selfbot_enabled': 1,
                'buttons_enabled': 1,
                'ai_status': {
                    'ai_deepseek_pm': False,
                    'ai_chatgpt_pm': False,
                    'ai_grok_pm': False,
                    'ai_blackbox_pm': False,
                    'ai_openai_pm': False,
                    'ai_deepseek_group': False,
                    'ai_chatgpt_group': False,
                    'ai_grok_group': False,
                    'ai_blackbox_group': False,
                    'ai_openai_group': False
                },
                'translate': {
                    'english': False,
                    'arabic': False,
                    'hebrew': False,
                    'russian': False,
                    'turkish': False
                }
            }
            self.set_selfbot_settings(user_id, default_settings)
            return default_settings
    
    def set_selfbot_settings(self, user_id, settings):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        settings_to_save = settings.copy()
        settings_to_save.pop('ai_status', None)
        settings_to_save.pop('translate', None)
        
        if 'time_font_indices' in settings_to_save and isinstance(settings_to_save['time_font_indices'], list):
            settings_to_save['time_font_indices'] = ','.join(map(str, settings_to_save['time_font_indices']))
        
        columns = ', '.join(settings_to_save.keys())
        placeholders = ', '.join(['?' for _ in settings_to_save])
        values = list(settings_to_save.values())
        
        cursor.execute(f'INSERT OR REPLACE INTO selfbot_settings ({columns}, updated_at) VALUES ({placeholders}, CURRENT_TIMESTAMP)', values)
        conn.commit()
        conn.close()
    
    def update_selfbot_setting(self, user_id, key, value):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (value, user_id))
        conn.commit()
        conn.close()
    
    def get_buttons_enabled(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT buttons_enabled FROM selfbot_settings WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return bool(result[0]) if result else True
        except:
            conn.close()
            return True
    
    def set_buttons_enabled(self, user_id, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE selfbot_settings SET buttons_enabled = ? WHERE user_id = ?', (1 if enabled else 0, user_id))
        except:
            try:
                cursor.execute('ALTER TABLE selfbot_settings ADD COLUMN buttons_enabled BOOLEAN DEFAULT 1')
                cursor.execute('UPDATE selfbot_settings SET buttons_enabled = ? WHERE user_id = ?', (1 if enabled else 0, user_id))
            except:
                pass
        conn.commit()
        conn.close()
    
    def get_active_ai_pm(self, user_id):
        settings = self.get_selfbot_settings(user_id)
        ai = settings.get('ai_status', {})
        for key, value in ai.items():
            if key.endswith('_pm') and value:
                return key.replace('_pm', '').replace('ai_', '')
        return None
    
    def get_active_ai_group(self, user_id):
        settings = self.get_selfbot_settings(user_id)
        ai = settings.get('ai_status', {})
        for key, value in ai.items():
            if key.endswith('_group') and value:
                return key.replace('_group', '').replace('ai_', '')
        return None
    
    def set_ai_pm(self, user_id, ai_name):
        settings = self.get_selfbot_settings(user_id)
        ai_status = settings.get('ai_status', {})
        for key in ai_status.keys():
            if key.endswith('_pm'):
                ai_status[key] = False
        if ai_name:
            ai_status[f'ai_{ai_name}_pm'] = True
        self.update_ai_status(user_id, ai_status)
    
    def set_ai_group(self, user_id, ai_name):
        settings = self.get_selfbot_settings(user_id)
        ai_status = settings.get('ai_status', {})
        for key in ai_status.keys():
            if key.endswith('_group'):
                ai_status[key] = False
        if ai_name:
            ai_status[f'ai_{ai_name}_group'] = True
        self.update_ai_status(user_id, ai_status)
    
    def update_ai_status(self, user_id, ai_status):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        for key, value in ai_status.items():
            if key.startswith('ai_'):
                cursor.execute(f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (1 if value else 0, user_id))
        conn.commit()
        conn.close()
    
    def add_enemy(self, owner_id, enemy_id, chat_type='pv'):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT OR IGNORE INTO enemies (owner_id, enemy_id, chat_type) VALUES (?, ?, ?)', (owner_id, enemy_id, chat_type))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()
    
    def remove_enemy(self, owner_id, enemy_id, chat_type='pv'):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemies WHERE owner_id = ? AND enemy_id = ? AND chat_type = ?', (owner_id, enemy_id, chat_type))
        conn.commit()
        conn.close()
    
    def get_enemies(self, owner_id, chat_type='pv'):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enemy_id FROM enemies WHERE owner_id = ? AND chat_type = ?', (owner_id, chat_type))
        enemies = [row[0] for row in cursor.fetchall()]
        conn.close()
        return enemies
    
    def is_enemy(self, owner_id, enemy_id, chat_type='pv'):
        enemies = self.get_enemies(owner_id, chat_type)
        return enemy_id in enemies
    
    def add_locked_pv(self, owner_id, locked_user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO locked_pvs (owner_id, locked_user_id) VALUES (?, ?)', (owner_id, locked_user_id))
        conn.commit()
        conn.close()
    
    def remove_locked_pv(self, owner_id, locked_user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM locked_pvs WHERE owner_id = ? AND locked_user_id = ?', (owner_id, locked_user_id))
        conn.commit()
        conn.close()
    
    def get_locked_pvs(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT locked_user_id FROM locked_pvs WHERE owner_id = ?', (owner_id,))
        locked_pvs = [row[0] for row in cursor.fetchall()]
        conn.close()
        return locked_pvs
    
    def is_pv_locked(self, owner_id, user_id):
        locked_pvs = self.get_locked_pvs(owner_id)
        return user_id in locked_pvs
    
    def set_reaction(self, owner_id, chat_id, target_id, emoji):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO reactions (owner_id, chat_id, target_id, emoji) VALUES (?, ?, ?, ?)', (owner_id, chat_id, target_id, emoji))
        conn.commit()
        conn.close()
    
    def get_reaction(self, owner_id, chat_id, target_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT emoji FROM reactions WHERE owner_id = ? AND chat_id = ? AND target_id = ?', (owner_id, chat_id, target_id))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def remove_reaction(self, owner_id, chat_id, target_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM reactions WHERE owner_id = ? AND chat_id = ? AND target_id = ?', (owner_id, chat_id, target_id))
        conn.commit()
        conn.close()
    
    def add_filter_word(self, owner_id, word):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO filter_words (owner_id, word) VALUES (?, ?)', (owner_id, word))
        conn.commit()
        conn.close()
    
    def remove_filter_word(self, owner_id, word):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM filter_words WHERE owner_id = ? AND word = ?', (owner_id, word))
        conn.commit()
        conn.close()
    
    def remove_filter_word_by_id(self, owner_id, word_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM filter_words WHERE owner_id = ? AND id = ?', (owner_id, word_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
    
    def toggle_filter_word_by_id(self, owner_id, word_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enabled FROM filter_words WHERE owner_id = ? AND id = ?', (owner_id, word_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        new_state = 0 if row[0] else 1
        cursor.execute('UPDATE filter_words SET enabled = ? WHERE owner_id = ? AND id = ?', (new_state, owner_id, word_id))
        conn.commit()
        conn.close()
        return bool(new_state)
    
    def get_filter_words(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, word, enabled FROM filter_words WHERE owner_id = ? ORDER BY id', (owner_id,))
        results = cursor.fetchall()
        conn.close()
        return [{'id': row[0], 'word': row[1], 'enabled': bool(row[2])} for row in results]
    
    def get_filter_enabled(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT filter_enabled FROM selfbot_settings WHERE user_id = ?', (owner_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except:
            conn.close()
            return 0
    
    def set_filter_enabled(self, owner_id, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE selfbot_settings SET filter_enabled = ? WHERE user_id = ?', (1 if enabled else 0, owner_id))
        except:
            try:
                cursor.execute('ALTER TABLE selfbot_settings ADD COLUMN filter_enabled BOOLEAN DEFAULT 0')
                cursor.execute('UPDATE selfbot_settings SET filter_enabled = ? WHERE user_id = ?', (1 if enabled else 0, owner_id))
            except:
                pass
        conn.commit()
        conn.close()
    
    def get_spam_settings(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM spam_settings WHERE owner_id = ?', (owner_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(zip(columns, row))
        return {'owner_id': owner_id, 'spam_protection': 0, 'spam_limit': 10, 'mute_duration': 10}
    
    def set_spam_settings(self, owner_id, spam_protection=None, spam_limit=None, mute_duration=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM spam_settings WHERE owner_id = ?', (owner_id,))
        exists = cursor.fetchone()
        
        settings = {}
        if spam_protection is not None:
            settings['spam_protection'] = spam_protection
        if spam_limit is not None:
            settings['spam_limit'] = spam_limit
        if mute_duration is not None:
            settings['mute_duration'] = mute_duration
        
        if exists:
            set_clause = ', '.join([f"{key} = ?" for key in settings.keys()])
            values = list(settings.values())
            values.append(owner_id)
            cursor.execute(f'UPDATE spam_settings SET {set_clause} WHERE owner_id = ?', values)
        else:
            default_settings = {'owner_id': owner_id, 'spam_protection': 0, 'spam_limit': 10, 'mute_duration': 10}
            default_settings.update(settings)
            columns = ', '.join(default_settings.keys())
            placeholders = ', '.join(['?' for _ in default_settings])
            values = list(default_settings.values())
            cursor.execute(f'INSERT INTO spam_settings ({columns}) VALUES ({placeholders})', values)
        
        conn.commit()
        conn.close()
    
    def get_user_lock(self, owner_id, target_id, lock_type):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enabled FROM user_locks WHERE owner_id = ? AND target_id = ? AND lock_type = ?', (owner_id, target_id, lock_type))
        result = cursor.fetchone()
        conn.close()
        return bool(result[0]) if result else False
    
    def set_user_lock(self, owner_id, target_id, lock_type, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO user_locks (owner_id, target_id, lock_type, enabled) VALUES (?, ?, ?, ?)', (owner_id, target_id, lock_type, 1 if enabled else 0))
        conn.commit()
        conn.close()
    
    def get_original_name(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM user_info WHERE user_id = ? AND key = "original_name" ORDER BY timestamp DESC LIMIT 1', (owner_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_original_name(self, owner_id, original_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO user_info (user_id, key, value) VALUES (?, "original_name", ?)', (owner_id, original_name))
        conn.commit()
        conn.close()
    
    def get_current_name(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM user_info WHERE user_id = ? AND key = "current_name" ORDER BY timestamp DESC LIMIT 1', (owner_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_current_name(self, owner_id, current_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO user_info (user_id, key, value) VALUES (?, "current_name", ?)', (owner_id, current_name))
        conn.commit()
        conn.close()
    
    def get_user_name(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT known_name, first_name, username FROM user_memory WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            known_name, first_name, username = result
            if known_name:
                return known_name
            elif first_name:
                return first_name
            elif username:
                return f"@{username}"
        return f"کاربر {user_id}"
    
    def get_user_info(self, user_id, key=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        if key:
            cursor.execute('SELECT value FROM user_info WHERE user_id = ? AND key = ? ORDER BY timestamp DESC LIMIT 1', (user_id, key))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        else:
            cursor.execute('SELECT key, value FROM user_info WHERE user_id = ?', (user_id,))
            results = cursor.fetchall()
            conn.close()
            return dict(results) if results else {}
    
    def update_user_memory(self, user_id, username, first_name, last_name, chat_id, known_name=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM user_memory WHERE user_id = ?', (user_id,))
        user_exists = cursor.fetchone()
        if user_exists:
            cursor.execute('UPDATE user_memory SET username = ?, first_name = ?, last_name = ?, known_name = ?, chat_id = ?, last_seen = CURRENT_TIMESTAMP WHERE user_id = ?', (username, first_name, last_name, known_name, chat_id, user_id))
        else:
            cursor.execute('INSERT INTO user_memory (user_id, username, first_name, last_name, known_name, chat_id, last_seen) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)', (user_id, username, first_name, last_name, known_name, chat_id))
        conn.commit()
        conn.close()
    
    def get_bio_setting(self, user_id, setting_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT status FROM bio_settings WHERE user_id = ? AND setting_name = ?', (user_id, setting_name))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 'خاموش'
    
    def set_bio_setting(self, user_id, setting_name, status):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO bio_settings (user_id, setting_name, status) VALUES (?, ?, ?)', (user_id, setting_name, status))
        conn.commit()
        conn.close()
    
    def get_monshi_status(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT status, answer FROM monshi_status WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return {'status': bool(result[0]), 'answer': result[1]} if result else {'status': False, 'answer': ''}
    
    def set_monshi_status(self, user_id, status, answer=''):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO monshi_status (user_id, status, answer) VALUES (?, ?, ?)', (user_id, 1 if status else 0, answer))
        conn.commit()
        conn.close()
    
    def add_answer(self, user_id, question, answer):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO bot_answers (user_id, question, answer) VALUES (?, ?, ?)', (user_id, question, answer))
        conn.commit()
        conn.close()
    
    def remove_answer(self, user_id, question):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM bot_answers WHERE user_id = ? AND question = ?', (user_id, question))
        conn.commit()
        conn.close()
    
    def get_answers(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT question, answer FROM bot_answers WHERE user_id = ?', (user_id,))
        results = cursor.fetchall()
        conn.close()
        return {q: a for q, a in results}
    
    def set_auto_comment(self, owner_id, channel_id, comment_text, channel_title, channel_type, channel_username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO auto_comments (owner_id, channel_id, comment_text, channel_title, channel_type, channel_username) VALUES (?, ?, ?, ?, ?, ?)', (owner_id, channel_id, comment_text, channel_title, channel_type, channel_username))
        conn.commit()
        conn.close()
    
    def get_auto_comments(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auto_comments WHERE owner_id = ?', (owner_id,))
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_auto_comment(self, owner_id, channel_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auto_comments WHERE owner_id = ? AND channel_id = ?', (owner_id, channel_id))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        return dict(zip(columns, row)) if row else None
    
    def remove_auto_comment(self, owner_id, channel_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM auto_comments WHERE owner_id = ? AND channel_id = ?', (owner_id, channel_id))
        conn.commit()
        conn.close()
    
    def mark_comment_sent(self, owner_id, channel_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO sent_comments (owner_id, channel_id, message_id, comment_sent) VALUES (?, ?, ?, 1)', (owner_id, channel_id, message_id))
        conn.commit()
        conn.close()
    
    def is_comment_sent(self, owner_id, channel_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT comment_sent FROM sent_comments WHERE owner_id = ? AND channel_id = ? AND message_id = ?', (owner_id, channel_id, message_id))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1
    
    def cache_message(self, owner_id, chat_id, message_id, message_text):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO message_cache (owner_id, chat_id, message_id, message_text) VALUES (?, ?, ?, ?)', (owner_id, chat_id, message_id, message_text))
        conn.commit()
        conn.close()
    
    def get_cached_message(self, owner_id, chat_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT message_text FROM message_cache WHERE owner_id = ? AND chat_id = ? AND message_id = ?', (owner_id, chat_id, message_id))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def add_enemy_spam_message(self, owner_id, spam_text):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO enemy_spam_messages (owner_id, spam_text) VALUES (?, ?)', (owner_id, spam_text))
        conn.commit()
        conn.close()
    
    def get_enemy_spam_messages(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, spam_text FROM enemy_spam_messages WHERE owner_id = ? ORDER BY created_at', (owner_id,))
        results = cursor.fetchall()
        conn.close()
        return [{'id': row[0], 'text': row[1]} for row in results]
    
    def clear_enemy_spam_messages(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemy_spam_messages WHERE owner_id = ?', (owner_id,))
        conn.commit()
        conn.close()
    
    def delete_enemy_spam_message(self, owner_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemy_spam_messages WHERE owner_id = ? AND id = ?', (owner_id, message_id))
        conn.commit()
        conn.close()
    
    def add_pinned_message(self, owner_id, chat_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO pinned_messages (owner_id, chat_id, message_id) VALUES (?, ?, ?)', (owner_id, chat_id, message_id))
        conn.commit()
        conn.close()
    
    def get_pinned_messages(self, owner_id, chat_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT message_id FROM pinned_messages WHERE owner_id = ? AND chat_id = ?', (owner_id, chat_id))
        results = cursor.fetchall()
        conn.close()
        return [row[0] for row in results]
    
    def add_broadcast(self, admin_id, message_text, message_type='text', media_file=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO broadcasts (admin_id, message_text, message_type, media_file) VALUES (?, ?, ?, ?)', (admin_id, message_text, message_type, media_file))
        broadcast_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return broadcast_id
    
    def update_broadcast_stats(self, broadcast_id, sent_count, failed_count):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE broadcasts SET sent_count = ?, failed_count = ? WHERE id = ?', (sent_count, failed_count, broadcast_id))
        conn.commit()
        conn.close()
    
    def save_bio(self, user_id, bio_text):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO user_bio (user_id, bio_text) VALUES (?, ?)', (user_id, bio_text))
        conn.commit()
        conn.close()
    
    def get_bio(self, user_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT bio_text FROM user_bio WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else ""

db = MainDatabase()
selfbot_managers = {}

# ======================================================
# توابع کمکی
# ======================================================
async def apply_text_style(message_text, style):
    if not message_text or not style:
        return message_text, []
    entities = []
    if style == 'بولد':
        entities.append(MessageEntityBold(offset=0, length=len(message_text)))
    elif style == 'زیرخط':
        entities.append(MessageEntityUnderline(offset=0, length=len(message_text)))
    elif style == 'خط خورده':
        entities.append(MessageEntityStrike(offset=0, length=len(message_text)))
    elif style == 'نقل قول':
        entities.append(MessageEntityBlockquote(offset=0, length=len(message_text)))
    elif style == 'اسپویلر':
        entities.append(MessageEntitySpoiler(offset=0, length=len(message_text)))
    elif style == 'کج':
        entities.append(MessageEntityItalic(offset=0, length=len(message_text)))
    elif style == 'کد':
        entities.append(MessageEntityCode(offset=0, length=len(message_text)))
    elif style == 'پیش':
        entities.append(MessageEntityPre(offset=0, length=len(message_text), language=""))
    return message_text, entities

async def get_target_user(event, client=None):
    try:
        if event.is_reply:
            replied_msg = await event.get_reply_message()
            return replied_msg.sender_id
        elif client and isinstance(event.message.peer_id, PeerUser) and not event.is_reply:
            return event.message.peer_id.user_id
        return None
    except:
        return None

async def _wrap_edit(message, text: str):
    try:
        await message.edit(text)
    except FloodWaitError as fl:
        await asyncio.sleep(fl.seconds)

# ======================================================
# انیمیشن قلب پیشرفته
# ======================================================
async def advanced_heart_phase1(message):
    BIG_SCROLL = "🧡💛💚💙💜🖤🤎"
    await _wrap_edit(message, JOINED_HEART)
    for heart in BIG_SCROLL:
        await _wrap_edit(message, JOINED_HEART.replace(R, heart))
        await asyncio.sleep(SLEEP)

async def advanced_heart_phase2(message):
    ALL = ["❤️"] + list("🧡💛💚💙💜🤎🖤")
    format_heart = JOINED_HEART.replace(R, "{}")
    for _ in range(5):
        heart = format_heart.format(*random.choices(ALL, k=HEARTLET_LEN))
        await _wrap_edit(message, heart)
        await asyncio.sleep(SLEEP)

async def advanced_heart_phase3(message):
    await _wrap_edit(message, JOINED_HEART)
    await asyncio.sleep(SLEEP * 2)
    repl = JOINED_HEART
    for _ in range(JOINED_HEART.count(W)):
        repl = repl.replace(W, R, 1)
        await _wrap_edit(message, repl)
        await asyncio.sleep(SLEEP)

async def advanced_heart_phase4(message):
    for i in range(7, 0, -1):
        heart_matrix = "\n".join([R * i] * i)
        await _wrap_edit(message, heart_matrix)
        await asyncio.sleep(SLEEP)

async def advanced_heart_animation(message):
    await advanced_heart_phase1(message)
    await asyncio.sleep(SLEEP * 3)
    await advanced_heart_phase2(message)
    await asyncio.sleep(SLEEP * 2)
    await advanced_heart_phase3(message)
    await asyncio.sleep(SLEEP * 2)
    await advanced_heart_phase4(message)
    await asyncio.sleep(0.5)
    await message.edit("❤️ I")
    await asyncio.sleep(0.5)
    await message.edit("❤️ I Love")
    await asyncio.sleep(0.5)
    await message.edit("❤️ I Love You")
    await asyncio.sleep(3)
    await message.edit("❤️ I Love You <3")

# ======================================================
# کلاس SelfBotManager
# ======================================================
class SelfBotManager:
    def __init__(self, user_id):
        self.user_id = int(user_id)
        self.client = None
        self.running = False
        self.my_id = None
        self.BASE_NAME = None
        self.ORIGINAL_NAME = None
        self.spam_tasks = {}
        self.report_config = ReportConfig(user_id)
        self.adding_spam = False
        self.spam_counters = {}
        self.mute_timestamps = {}
        self.current_chat_id = None
        self.active_actions = {}
        self.action_tasks = {}
        self.translate_mode = {
            "english": False,
            "arabic": False,
            "hebrew": False,
            "russian": False,
            "turkish": False
        }
        self.search_mode = False
        self.last_search_results = []
        self.connection_attempts = 0
        self.max_attempts = 5
        self._handlers_set = False
        self.panel_mode = True
        self.api_id = None
        self.api_hash = None
        self.time_font_cycle = 0
        self.time_font_indices = 'all'
        self.reconnect_task = None
        self.last_ping = 0
        self.keepalive_running = False
        self.last_error_time = 0
        self.error_count = 0
        self.last_keepalive_check = 0
        self.autosend_mode = False
        self.monshi_mode = False
        self.monshi_answer = ""
        self.mentioning_groups = set()
        self.current_bio = self.load_bio()
        self.auto_comment_settings = {}
        self.auto_comment_sent = set()
        self.STATE_FILE = f'state_{user_id}.json'
        self.selected_font = 0
        self.selected_flags = []
        self.load_state()
    
    def load_state(self):
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.autosend_mode = data.get('autosend_mode', False)
                    auto_comment_settings = data.get('auto_comment_settings', {})
                    self.auto_comment_settings = {int(k): v for k, v in auto_comment_settings.items()}
                    self.auto_comment_sent = set(data.get('auto_comment_sent', []))
                    self.selected_font = data.get('selected_font', 0)
                    self.selected_flags = data.get('selected_flags', [])
                    logger.info(f"وضعیت کاربر {self.user_id} از فایل بارگذاری شد")
        except Exception as e:
            logger.error(f"خطا در بارگذاری وضعیت: {e}")
    
    def save_state(self):
        try:
            data = {
                'autosend_mode': self.autosend_mode,
                'auto_comment_settings': {str(k): v for k, v in self.auto_comment_settings.items()},
                'auto_comment_sent': list(self.auto_comment_sent),
                'selected_font': self.selected_font,
                'selected_flags': self.selected_flags
            }
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"وضعیت کاربر {self.user_id} ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره وضعیت: {e}")
    
    def load_bio(self):
        return db.get_bio(self.user_id)
    
    def save_bio(self, bio_text):
        db.save_bio(self.user_id, bio_text)
        self.current_bio = bio_text
    
    def get_bio_setting(self, setting_name):
        return db.get_bio_setting(self.user_id, setting_name)
    
    def set_bio_setting(self, setting_name, status):
        db.set_bio_setting(self.user_id, setting_name, status)
    
    async def update_bio_with_settings(self):
        try:
            if not self.client or not self.client.is_connected():
                return
            
            bio_text = self.current_bio or ""
            time1 = self.get_bio_setting('ساعت_در_بیو') == 'روشن'
            time2 = self.get_bio_setting('ساعت_در_بیو_۲') == 'روشن'
            date = self.get_bio_setting('بیو_تاریخ') == 'روشن'
            full = self.get_bio_setting('بیو_کامل') == 'روشن'
            love = self.get_bio_setting('بیو_عاشقانه') == 'روشن'
            random_emoji_bio = self.get_bio_setting('بیو_ایموجی') == 'روشن'
            season = self.get_bio_setting('بیو_فصل') == 'روشن'
            weekday_bio = self.get_bio_setting('بیو_روز_هفته') == 'روشن'
            countdown = self.get_bio_setting('بیو_شمارش_معکوس') == 'روشن'
            
            new_bio = ""
            if full:
                new_bio = f'{moon_or_sun()} | {bio_text} | {create_time2()} | {create_tarikh2()} | {get_weekday()} | {get_season()}'
            elif date:
                new_bio = f'{moon_or_sun()} | {bio_text} | {create_time2()} | {create_tarikh2()}'
            elif love:
                new_bio = f'{love_emoji()} | {bio_text} | {create_time2()} | {create_tarikh()}'
            elif time2:
                new_bio = f'{bio_text} | {create_time2()}'
            elif time1:
                new_bio = f'{bio_text} | {create_time()}'
            elif random_emoji_bio:
                new_bio = f'{random_emoji()} {bio_text} {random_emoji()} | {create_time()}'
            elif season:
                new_bio = f'{get_season()} | {bio_text} | {create_time()}'
            elif weekday_bio:
                new_bio = f'{get_weekday()} | {bio_text} | {create_time()}'
            elif countdown:
                now = get_now()
                target = datetime(now.year + 1, 3, 21)
                diff = target - now
                days = diff.days
                new_bio = f'{bio_text} | ⏳ {days} روز تا سال نو'
            
            if new_bio:
                await self.client(UpdateProfileRequest(about=new_bio))
                logger.info(f"بیو به‌روزرسانی شد: {new_bio[:50]}...")
        except Exception as e:
            logger.error(f"خطا در به‌روزرسانی بیو: {e}")
    
    async def update_profile_name(self):
        settings = db.get_selfbot_settings(self.user_id)
        if settings.get('time_enabled'):
            now = get_now()
            current_minute = now.minute
            if self.time_font_indices == 'all':
                font_index = current_minute % len(classic_fonts)
            elif isinstance(self.time_font_indices, list) and self.time_font_indices:
                if hasattr(self, 'time_font_cycle'):
                    self.time_font_cycle = (self.time_font_cycle + 1) % len(self.time_font_indices)
                else:
                    self.time_font_cycle = 0
                font_index = self.time_font_indices[self.time_font_cycle]
                if font_index >= len(classic_fonts):
                    font_index = 0
            else:
                font_index = self.selected_font if hasattr(self, 'selected_font') else 0
            time_now = now.strftime("%H:%M")
            time_now_classic = convert_to_classic_font(time_now, font_index)
            try:
                current_name = db.get_current_name(self.user_id)
                if not current_name:
                    current_name = self.BASE_NAME
                if settings.get('flag_enabled'):
                    flags_to_show = self.selected_flags or [flags[current_minute % len(flags)]]
                    flag_str = ''.join(flags_to_show[:3])  # حداکثر ۳ پرچم
                    new_name = f"『 {flag_str} 』{current_name} {time_now_classic}"
                else:
                    new_name = f"{current_name} | {time_now_classic}"
                await self.client(UpdateProfileRequest(first_name=new_name))
            except:
                pass
    
    async def restore_profile_name(self):
        try:
            current_name = db.get_current_name(self.user_id)
            if current_name:
                await self.client(UpdateProfileRequest(first_name=current_name))
            else:
                original_name = db.get_original_name(self.user_id)
                if original_name:
                    await self.client(UpdateProfileRequest(first_name=original_name))
                    db.set_current_name(self.user_id, original_name)
                    self.BASE_NAME = original_name
        except:
            pass
    
    async def update_profile_task(self):
        while self.running:
            try:
                await self.update_profile_name()
            except Exception as e:
                logger.error(f"خطا در update_profile_task: {e}")
            await asyncio.sleep(60)
    
    async def update_bio_task(self):
        while self.running:
            try:
                await self.update_bio_with_settings()
            except Exception as e:
                logger.error(f"خطا در update_bio_task: {e}")
            await asyncio.sleep(60)

    # ======================================================
    # متدهای هوش مصنوعی
    # ======================================================
    async def get_ai_response(self, text, ai_type):
        """دریافت پاسخ از هوش مصنوعی"""
        try:
            if ai_type in AI_APIS:
                result = await call_ai_api(ai_type, text)
                if result and 'response' in result:
                    return result['response']
                elif result and 'choices' in result:
                    return result['choices'][0]['message']['content']
                elif result and 'candidates' in result:
                    return result['candidates'][0]['content']['parts'][0]['text']
                return None
            return None
        except Exception as e:
            logger.error(f"خطا در AI {ai_type}: {e}")
            return None
    
    def get_active_ai(self, chat_type='pm'):
        """دریافت هوش فعال در پیوی یا گروه"""
        settings = db.get_selfbot_settings(self.user_id)
        ai = settings.get('ai_status', {})
        suffix = '_pm' if chat_type == 'pm' else '_group'
        for key, value in ai.items():
            if key.endswith(suffix) and value:
                return key.replace(suffix, '').replace('ai_', '')
        return None
    
    def set_active_ai(self, ai_name, chat_type='pm'):
        """تنظیم هوش فعال در پیوی یا گروه"""
        settings = db.get_selfbot_settings(self.user_id)
        ai_status = settings.get('ai_status', {})
        suffix = '_pm' if chat_type == 'pm' else '_group'
        for key in ai_status.keys():
            if key.endswith(suffix):
                ai_status[key] = False
        if ai_name:
            ai_status[f'ai_{ai_name}{suffix}'] = True
        db.update_ai_status(self.user_id, ai_status)

    # ======================================================
    # متدهای عکس و لوگو
    # ======================================================
    async def generate_photo_command(self, photo_type, text=None, style=None, url=None, logo_id=None, logo_text=None):
        """ساخت عکس یا لوگو و ارسال به صورت تصویر"""
        try:
            result = await generate_photo(photo_type, text, style, url, logo_id, logo_text)
            if result:
                return BytesIO(result)
            return None
        except Exception as e:
            logger.error(f"خطا در ساخت عکس: {e}")
            return None

    # ======================================================
    # متدهای ارز و بازار
    # ======================================================
    async def get_price_info(self, query):
        """دریافت قیمت دلار، طلا، نقره و ارزهای دیجیتال"""
        query_lower = query.lower()
        
        try:
            if query_lower in ['دلار', 'dollar', 'usd']:
                data = await get_gold_prices()
                if data and isinstance(data, dict) and 'dollar' in data:
                    return f"💵 قیمت دلار: {data['dollar']:,} تومان"
                return "❌ خطا در دریافت قیمت دلار"
            
            elif query_lower in ['طلا', 'gold']:
                data = await get_gold_prices()
                if data and isinstance(data, dict) and 'gold' in data:
                    return f"💎 قیمت طلا: {data['gold']:,} تومان"
                return "❌ خطا در دریافت قیمت طلا"
            
            elif query_lower in ['نقره', 'silver']:
                data = await get_gold_prices()
                if data and isinstance(data, dict) and 'silver' in data:
                    return f"🥈 قیمت نقره: {data['silver']:,} تومان"
                return "❌ خطا در دریافت قیمت نقره"
            
            elif query_lower in ['بورس', 'bourse']:
                data = await get_bourse_data('index')
                if data:
                    return f"📊 شاخص بورس: {data}"
                return "❌ خطا در دریافت اطلاعات بورس"
            
            else:
                data = await get_crypto_prices()
                if data and isinstance(data, list):
                    for crypto in data:
                        if query_lower in crypto.get('symbol', '').lower() or query_lower in crypto.get('name', '').lower():
                            return f"💰 {crypto.get('name')} ({crypto.get('symbol')}): {crypto.get('price')} تومان"
                    return f"❌ ارز '{query}' پیدا نشد"
                return "❌ خطا در دریافت قیمت ارز"
        except Exception as e:
            logger.error(f"خطا در دریافت قیمت: {e}")
            return f"❌ خطا: {str(e)[:50]}"

    # ======================================================
    # هندلر پیام‌های دریافتی
    # ======================================================
    async def handle_new_message(self, event):
        try:
            if not self.running or not self.my_id:
                return
            
            if event.sender_id == self.my_id:
                return
            
            # ========== قابلیت دشمن ==========
            if db.is_enemy(self.user_id, event.sender_id, 'pv'):
                try:
                    spam_messages = db.get_enemy_spam_messages(self.user_id)
                    if spam_messages:
                        spam_text = random.choice(spam_messages)['text']
                    else:
                        spam_text = random.choice(SPAM_MESSAGES)
                    
                    await event.reply(spam_text)
                    logger.info(f"اسپم به دشمن {event.sender_id} ارسال شد")
                except Exception as e:
                    logger.error(f"خطا در ارسال اسپم به دشمن: {e}")
                return
            
            # ========== هوش مصنوعی ==========
            if isinstance(event.message.peer_id, PeerUser):
                chat_type = 'pm'
            else:
                chat_type = 'group'
            
            if chat_type == 'group':
                if not event.is_reply:
                    return
                replied_msg = await event.get_reply_message()
                if replied_msg.sender_id != self.my_id:
                    return
            
            active_ai = self.get_active_ai(chat_type)
            if active_ai and event.text:
                response = await self.get_ai_response(event.text, active_ai)
                if response:
                    lines = response.split('\n')[:3]
                    response = '\n'.join(lines)
                    await event.reply(response)
                    logger.info(f"AI {active_ai} پاسخ داد به {event.sender_id}")
                    return
            
            # ========== بقیه کدها ==========
            settings = db.get_selfbot_settings(self.user_id)
            if not settings.get('selfbot_enabled', 1):
                return
            
            # ... ادامه کد قبلی ...
            
        except Exception as e:
            logger.error(f"خطا در handle_new_message: {e}")

    async def handle_edited_message(self, event):
        try:
            if not self.running:
                return
            # ... کد قبلی ...
        except Exception as e:
            logger.error(f"خطا در handle_edited_message: {e}")

    async def handle_deleted_message(self, event):
        try:
            if not self.running:
                return
            # ... کد قبلی ...
        except Exception as e:
            logger.error(f"خطا در handle_deleted_message: {e}")

    async def handle_outgoing_message(self, event):
        try:
            if not self.running:
                return
            # ... کد قبلی ...
        except Exception as e:
            logger.error(f"خطا در handle_outgoing_message: {e}")

    async def auto_comment_handler(self, event):
        try:
            if not self.running:
                return
            # ... کد قبلی ...
        except Exception as e:
            logger.error(f"خطا در auto_comment_handler: {e}")

    # ======================================================
    # متدهای استارت و استاپ
    # ======================================================
    async def start(self, session_file):
        try:
            if self.running and self.client and self.client.is_connected():
                return True
            
            self.connection_attempts += 1
            logger.info(f"شروع سلف‌بات برای کاربر {self.user_id} - تلاش {self.connection_attempts}")
            
            if not os.path.exists(session_file):
                logger.error(f"فایل سشن یافت نشد: {session_file}")
                return False
            
            user_api = get_user_api(str(self.user_id))
            if not user_api:
                logger.error(f"هیچ API ای برای کاربر {self.user_id} یافت نشد")
                return False
            
            self.api_id = user_api["api_id"]
            self.api_hash = user_api["api_hash"]
            
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            self.client = TelegramClient(
                session_file, 
                self.api_id, 
                self.api_hash,
                connection_retries=10,
                retry_delay=3,
                timeout=60,
                flood_sleep_threshold=60,
                device_model="SelfBot",
                system_version="5.0.0",
                app_version="5.0.0"
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error(f"کاربر {self.user_id} احراز هویت نشده است")
                return False
            
            me = await self.client.get_me()
            if not me:
                logger.error(f"خطا در دریافت اطلاعات کاربر {self.user_id}")
                return False
                
            self.my_id = me.id
            self.BASE_NAME = me.first_name or "Self-Bot"
            
            logger.info(f"اطلاعات کاربر {self.user_id}: {self.BASE_NAME} (ID: {self.my_id})")
            
            original_name = db.get_original_name(self.user_id)
            if not original_name:
                db.set_original_name(self.user_id, self.BASE_NAME)
                db.set_current_name(self.user_id, self.BASE_NAME)
                self.ORIGINAL_NAME = self.BASE_NAME
            else:
                self.ORIGINAL_NAME = original_name
            
            settings = db.get_selfbot_settings(self.user_id)
            self.translate_mode = settings.get('translate', {
                "english": False, "arabic": False, "hebrew": False,
                "russian": False, "turkish": False
            })
            self.panel_mode = settings.get('panel_mode', True)
            self.time_font_indices = settings.get('time_font_indices', 'all')
            self.autosend_mode = settings.get('autosend_mode', False)
            self.selected_font = self.selected_font if hasattr(self, 'selected_font') else 0
            self.selected_flags = self.selected_flags if hasattr(self, 'selected_flags') else []
            
            monshi_data = db.get_monshi_status(self.user_id)
            self.monshi_mode = monshi_data['status']
            self.monshi_answer = monshi_data['answer']
            
            if not self._handlers_set:
                self.setup_handlers()
                self._handlers_set = True
                logger.info(f"هندلرها برای کاربر {self.user_id} تنظیم شدند")
            
            asyncio.create_task(self.update_profile_task())
            asyncio.create_task(self.update_bio_task())
            
            self.running = True
            self.keepalive_running = True
            self.connection_attempts = 0
            self.error_count = 0
            self.last_error_time = 0
            
            asyncio.create_task(self.keep_alive_task())
            
            logger.info(f"✅ سلف‌بات برای کاربر {self.user_id} با موفقیت شروع شد")
            return True
            
        except Exception as e:
            logger.error(f"خطا در شروع سلف‌بات برای کاربر {self.user_id}: {str(e)}")
            
            if self.connection_attempts < self.max_attempts:
                wait_time = 5 * self.connection_attempts
                logger.info(f"تلاش مجدد در {wait_time} ثانیه - تلاش {self.connection_attempts + 1}")
                await asyncio.sleep(wait_time)
                return await self.start(session_file)
            
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            return False
    
    async def keep_alive_task(self):
        while self.running and self.keepalive_running:
            try:
                await asyncio.sleep(30)
                if not self.running:
                    break
                if self.client and self.client.is_connected():
                    try:
                        await self.client.get_me()
                        self.last_ping = time.time()
                        self.error_count = 0
                    except Exception as e:
                        self.error_count += 1
                        self.last_error_time = time.time()
                        if self.error_count >= 3:
                            await self.reconnect()
                else:
                    await self.reconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"خطا در keep_alive_task: {e}")
                await asyncio.sleep(60)
    
    async def reconnect(self):
        try:
            logger.info(f"شروع reconnect برای کاربر {self.user_id}")
            user_data = db.get_user(str(self.user_id))
            if not user_data or not user_data.get('session_file'):
                logger.error(f"فایل سشن برای کاربر {self.user_id} یافت نشد")
                return False
            session_file = user_data['session_file']
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            self.running = False
            self._handlers_set = False
            await asyncio.sleep(5)
            if await self.start(session_file):
                logger.info(f"✅ reconnect برای کاربر {self.user_id} موفقیت‌آمیز بود")
                return True
            logger.info(f"reconnect برای کاربر {self.user_id} ناموفق بود")
            return False
        except Exception as e:
            logger.error(f"خطا در reconnect: {e}")
            return False
    
    async def stop(self):
        try:
            self.running = False
            self.keepalive_running = False
            if self.client:
                for task in self.spam_tasks.values():
                    task.cancel()
                self.spam_tasks.clear()
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            self._handlers_set = False
            logger.info(f"✅ سلف‌بات برای کاربر {self.user_id} متوقف شد")
        except Exception as e:
            logger.error(f"خطا در توقف سلف‌بات: {e}")
    
    def setup_handlers(self):
        try:
            @self.client.on(events.NewMessage(incoming=True))
            async def handle_new_message(event):
                if not self.running:
                    return
                await self.handle_new_message(event)
            
            @self.client.on(events.MessageEdited(incoming=True))
            async def handle_edited_message(event):
                if not self.running:
                    return
                await self.handle_edited_message(event)
            
            @self.client.on(events.MessageDeleted)
            async def handle_deleted_message(event):
                if not self.running:
                    return
                await self.handle_deleted_message(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_outgoing_message(event):
                if not self.running:
                    return
                await self.handle_outgoing_message(event)
            
            @self.client.on(events.NewMessage())
            async def auto_comment_handler(event):
                if not self.running:
                    return
                await self.auto_comment_handler(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_commands(event):
                if not self.running:
                    return
                await self.handle_commands(event)
                
        except Exception as e:
            logger.error(f"خطا در تنظیم هندلرها: {e}")

# ======================================================
# توابع get_user_api و توابع پنل
# ======================================================
def get_user_api(user_id):
    conn = sqlite3.connect('main_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT api_id, api_hash FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] is not None and row[1] is not None:
        conn.close()
        return {"api_id": row[0], "api_hash": row[1]}
    
    API_CONFIGS = [
        {"api_id": 22409632, "api_hash": "b74c1ee200ad9ced6315859e9bd4125a"},
        {"api_id": 28297221, "api_hash": "8d682eb5c41a9762ef73f9ebe06c4eff"},
        {"api_id": 28039994, "api_hash": "00877cdcd706564a4de6abf7f7d64349"},
        {"api_id": 29031463, "api_hash": "64f122a7094dbab7e32b911eae6589e9"},
        {"api_id": 12832882, "api_hash": "1953c708cb3c47ecba74dc618b209e22"},
        {"api_id": 26645489, "api_hash": "6a212d0a400c97264600b3f932de5c2f"},
    ]
    
    api_count = {}
    for api in API_CONFIGS:
        cursor.execute('SELECT COUNT(*) FROM users WHERE api_id = ?', (api["api_id"],))
        api_count[api["api_id"]] = cursor.fetchone()[0]
    
    best_api = min(API_CONFIGS, key=lambda x: api_count.get(x["api_id"], 0))
    
    cursor.execute('UPDATE users SET api_id = ?, api_hash = ? WHERE user_id = ?', 
                   (best_api["api_id"], best_api["api_hash"], user_id))
    conn.commit()
    conn.close()
    
    logger.info(f"API اختصاص یافته به کاربر {user_id}: {best_api['api_id']}")
    return best_api

# ======================================================
# توابع پنل و کیبورد
# ======================================================
def get_main_panel_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("⚈ زمان و پروفایل", callback_data=f"time_menu_{user_id}"),
            InlineKeyboardButton("☻ انیمیشن", callback_data=f"animation_menu_{user_id}"),
            InlineKeyboardButton("☗ مدیریت کاربران", callback_data=f"user_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("⊖ قفل رسانه", callback_data=f"lock_menu_{user_id}"),
            InlineKeyboardButton("✼ کامنت", callback_data=f"comment_menu_{user_id}"),
            InlineKeyboardButton("✿ عمومی", callback_data=f"general_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("☥ اکشن", callback_data=f"action_menu_{user_id}"),
            InlineKeyboardButton("⚕ بازی‌ها", callback_data=f"games_menu_{user_id}"),
            InlineKeyboardButton("❍ ترجمه", callback_data=f"translate_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("𖢅 گوگل", callback_data=f"google_menu_{user_id}"),
            InlineKeyboardButton("֍ اطلاعاتی", callback_data=f"info_menu_{user_id}"),
            InlineKeyboardButton("𖢨 پروفایل", callback_data=f"profile_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("⩐ استایل متن", callback_data=f"style_menu_{user_id}"),
            InlineKeyboardButton("𑪡 مدیریت پیام", callback_data=f"message_menu_{user_id}"),
            InlineKeyboardButton("☖ ریکشن", callback_data=f"reaction_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("𖥞 اسپم", callback_data=f"spam_menu_{user_id}"),
            InlineKeyboardButton("☗ تغییر پروفایل", callback_data=f"change_menu_{user_id}"),
            InlineKeyboardButton("⚇ مدیریت دشمنان", callback_data=f"enemy_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("✿ فیلتر کلمات", callback_data=f"filter_menu_{user_id}"),
            InlineKeyboardButton("⚉ حفاظت اسپم", callback_data=f"protection_menu_{user_id}"),
            InlineKeyboardButton("☥ هوش مصنوعی", callback_data=f"ai_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("֎ گزارش", callback_data=f"report_menu_{user_id}"),
            InlineKeyboardButton("🛠 ابزار", callback_data=f"tools_menu_{user_id}"),
            InlineKeyboardButton("🤖 منشی هوشمند", callback_data=f"monshi_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("🏷️ تگ همه", callback_data=f"mention_menu_{user_id}"),
            InlineKeyboardButton("🔮 فال", callback_data=f"fortune_menu_{user_id}"),
            InlineKeyboardButton("🎨 لوگو و عکس", callback_data=f"photo_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("💰 ارز و بازار", callback_data=f"market_menu_{user_id}"),
            InlineKeyboardButton("🕐 تایم و پرچم", callback_data=f"timeflag_menu_{user_id}"),
            InlineKeyboardButton("🎛️ مدیریت دکمه‌ها", callback_data=f"buttons_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("❌ بستن پنل", callback_data=f"close_panel_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی زمان و پروفایل
# ======================================================
def get_time_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    time_enabled = settings.get('time_enabled', False)
    flag_enabled = settings.get('flag_enabled', False)
    
    keyboard = [
        [
            InlineKeyboardButton(f"🕐 تایم روشن {'✅' if time_enabled else ''}", callback_data=f"exec_time_on_{user_id}"),
            InlineKeyboardButton(f"🏳️ تایمر پرچم {'✅' if flag_enabled else ''}", callback_data=f"exec_time_flag_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🚫 تایم خاموش {'✅' if not time_enabled else ''}", callback_data=f"exec_time_off_{user_id}"),
            InlineKeyboardButton("📅 تقویم", callback_data=f"exec_calendar_{user_id}")
        ],
        [
            InlineKeyboardButton("📝 تنظیمات بیو", callback_data=f"bio_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("🎨 فونت تایم", callback_data=f"font_menu_{user_id}"),
            InlineKeyboardButton("🏳️ فونت پرچم", callback_data=f"flagselect_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_time_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی فونت تایم
# ======================================================
def get_font_menu_keyboard(user_id):
    manager = selfbot_managers.get(str(user_id))
    selected_font = manager.selected_font if manager else 0
    
    keyboard = []
    row = []
    for i, font in enumerate(classic_fonts):
        row.append(InlineKeyboardButton(f"{font} {'✅' if i == selected_font else ''}", callback_data=f"exec_font_{i}_{user_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🎨 همه", callback_data=f"exec_font_all_{user_id}")])
    keyboard.append([InlineKeyboardButton("📖 راهنما", callback_data=f"help_font_{user_id}")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}")])
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی انتخاب پرچم
# ======================================================
def get_flagselect_menu_keyboard(user_id):
    manager = selfbot_managers.get(str(user_id))
    selected_flags = manager.selected_flags if manager else []
    
    keyboard = []
    row = []
    for flag in flags:
        is_selected = flag in selected_flags
        row.append(InlineKeyboardButton(f"{flag} {'✅' if is_selected else ''}", callback_data=f"exec_flag_{flag}_{user_id}"))
        if len(row) == 7:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("📖 راهنما", callback_data=f"help_flag_{user_id}")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}")])
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی لوگو و عکس
# ======================================================
def get_photo_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🖼️ عکس ۱", callback_data=f"exec_photo1_{user_id}"),
            InlineKeyboardButton("🖼️ عکس ۲", callback_data=f"exec_photo2_{user_id}")
        ],
        [
            InlineKeyboardButton("🎨 جیبلی", callback_data=f"exec_ghibli_{user_id}"),
            InlineKeyboardButton("🎨 لوگو ساز", callback_data=f"exec_logo_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_photo_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی ارز و بازار
# ======================================================
def get_market_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("💰 ارزهای دیجیتال", callback_data=f"exec_crypto_{user_id}"),
            InlineKeyboardButton("💎 طلا و ارز", callback_data=f"exec_gold_{user_id}")
        ],
        [
            InlineKeyboardButton("📊 بورس", callback_data=f"exec_bourse_{user_id}"),
            InlineKeyboardButton("💵 نرخ ارز ۲", callback_data=f"exec_nobitex_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_market_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی مدیریت دکمه‌ها
# ======================================================
def get_buttons_menu_keyboard(user_id):
    buttons_enabled = db.get_buttons_enabled(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton(f"🟢 دکمه‌ها روشن {'✅' if buttons_enabled else ''}", callback_data=f"exec_buttons_on_{user_id}"),
            InlineKeyboardButton(f"🔴 دکمه‌ها خاموش {'✅' if not buttons_enabled else ''}", callback_data=f"exec_buttons_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_buttons_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی هوش مصنوعی
# ======================================================
def get_ai_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    ai = settings.get('ai_status', {})
    
    keyboard = [
        [
            InlineKeyboardButton(f"🧠 پیوی ۱ {'✅' if ai.get('ai_deepseek_pm') else ''}", callback_data=f"exec_ai_pm_deepseek_{user_id}"),
            InlineKeyboardButton(f"💬 پیوی ۲ {'✅' if ai.get('ai_chatgpt_pm') else ''}", callback_data=f"exec_ai_pm_chatgpt_{user_id}"),
            InlineKeyboardButton(f"🤖 پیوی ۳ {'✅' if ai.get('ai_grok_pm') else ''}", callback_data=f"exec_ai_pm_grok_{user_id}")
        ],
        [
            InlineKeyboardButton(f"📦 پیوی ۴ {'✅' if ai.get('ai_blackbox_pm') else ''}", callback_data=f"exec_ai_pm_blackbox_{user_id}"),
            InlineKeyboardButton(f"🟢 پیوی ۵ {'✅' if ai.get('ai_openai_pm') else ''}", callback_data=f"exec_ai_pm_openai_{user_id}"),
            InlineKeyboardButton("⚫ خاموش پیوی", callback_data=f"exec_ai_pm_off_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🧠 گروه ۱ {'✅' if ai.get('ai_deepseek_group') else ''}", callback_data=f"exec_ai_group_deepseek_{user_id}"),
            InlineKeyboardButton(f"💬 گروه ۲ {'✅' if ai.get('ai_chatgpt_group') else ''}", callback_data=f"exec_ai_group_chatgpt_{user_id}"),
            InlineKeyboardButton(f"🤖 گروه ۳ {'✅' if ai.get('ai_grok_group') else ''}", callback_data=f"exec_ai_group_grok_{user_id}")
        ],
        [
            InlineKeyboardButton(f"📦 گروه ۴ {'✅' if ai.get('ai_blackbox_group') else ''}", callback_data=f"exec_ai_group_blackbox_{user_id}"),
            InlineKeyboardButton(f"🟢 گروه ۵ {'✅' if ai.get('ai_openai_group') else ''}", callback_data=f"exec_ai_group_openai_{user_id}"),
            InlineKeyboardButton("⚫ خاموش گروه", callback_data=f"exec_ai_group_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_ai_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# توابع بکاپ
# ======================================================
async def create_backup():
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_folder = f"backup_{timestamp}"
        os.makedirs(backup_folder, exist_ok=True)
        
        files_to_backup = [
            'main_database.db',
            REPORT_CONFIG_FILE,
        ]
        
        for file in files_to_backup:
            if os.path.exists(file):
                shutil.copy2(file, os.path.join(backup_folder, file))
        
        if os.path.exists(SESSIONS_FOLDER):
            shutil.copytree(SESSIONS_FOLDER, os.path.join(backup_folder, SESSIONS_FOLDER))
        
        for file in os.listdir('.'):
            if file.startswith('state_') and file.endswith('.json'):
                shutil.copy2(file, os.path.join(backup_folder, file))
        
        zip_path = f"backup_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(backup_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, backup_folder)
                    zipf.write(file_path, arcname)
        
        shutil.rmtree(backup_folder)
        return zip_path
    except Exception as e:
        logger.error(f"خطا در ایجاد بکاپ: {e}")
        return None

async def restore_backup(file_path):
    try:
        if not zipfile.is_zipfile(file_path):
            return False, "فایل ZIP معتبر نیست"
        
        extract_folder = f"restore_{int(time.time())}"
        os.makedirs(extract_folder, exist_ok=True)
        
        with zipfile.ZipFile(file_path, 'r') as zipf:
            zipf.extractall(extract_folder)
        
        required_files = ['main_database.db']
        missing_files = []
        for file in required_files:
            if not os.path.exists(os.path.join(extract_folder, file)):
                missing_files.append(file)
        
        if missing_files:
            shutil.rmtree(extract_folder)
            return False, f"فایل‌های مورد نیاز وجود ندارند: {', '.join(missing_files)}"
        
        try:
            conn = sqlite3.connect(os.path.join(extract_folder, 'main_database.db'))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                conn.close()
                shutil.rmtree(extract_folder)
                return False, "ساختار دیتابیس نامعتبر است (جدول users وجود ندارد)"
            conn.close()
        except Exception as e:
            shutil.rmtree(extract_folder)
            return False, f"خطا در بررسی دیتابیس: {e}"
        
        for item in os.listdir(extract_folder):
            src = os.path.join(extract_folder, item)
            dst = os.path.join('.', item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)
        
        shutil.rmtree(extract_folder)
        return True, "بکاپ با موفقیت بازیابی شد"
    except Exception as e:
        logger.error(f"خطا در بازیابی بکاپ: {e}")
        return False, f"خطا در بازیابی: {e}"

# ======================================================
# ادامه کد در پیام بعدی...
# ======================================================
# ======================================================
# توابع inline_panel
# ======================================================
async def inline_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return
    user_id = query.from_user.id
    user_data = db.get_user(str(user_id))
    has_access = False
    if user_data and user_data.get('self_active'):
        has_access = True
    elif str(user_id) in selfbot_managers and selfbot_managers[str(user_id)].running:
        has_access = True
    
    if not has_access:
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="⛔ دسترسی محدود",
                description="شما عضو سرویس نیستید",
                input_message_content=InputTextMessageContent("⛔ شما به این پنل دسترسی ندارید\n\nبرای عضویت: /start")
            )
        ]
        await query.answer(results, cache_time=0, is_personal=True)
        return
    
    if not query.query:
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="🌟 پنل اصلی",
                description="مدیریت تمام قابلیت‌های سلف‌بات",
                input_message_content=InputTextMessageContent("🌟 پنل سلف‌بات باز شد\n\n⚠️ توجه: این پنل فقط مخصوص شماست"),
                reply_markup=get_main_panel_keyboard(user_id)
            ),
        ]
        if user_id == ADMIN_ID:
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="👑 پنل ادمین",
                    description="مدیریت کاربران و سلف‌بات‌ها و ارسال پیام همگانی",
                    input_message_content=InputTextMessageContent("👑 پنل ادمین"),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 درخواست‌ها", callback_data=f"admin_requests"), InlineKeyboardButton("🔐 منتظر ورود", callback_data=f"admin_login")],
                        [InlineKeyboardButton("✅ کاربران فعال", callback_data=f"admin_active"), InlineKeyboardButton("🤖 سلف‌بات‌ها", callback_data=f"admin_selfbots")],
                        [InlineKeyboardButton("📊 آمار کلی", callback_data=f"admin_stats"), InlineKeyboardButton("📢 پیام همگانی", callback_data=f"admin_broadcast")],
                        [InlineKeyboardButton("💾 دریافت دیتابیس", callback_data=f"admin_backup"), InlineKeyboardButton("📤 آپلود دیتابیس", callback_data=f"admin_restore")],
                        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
                    ])
                )
            )
    else:
        search = query.query.lower()
        results = []
        all_commands = [
            ("⚈ زمان و پروفایل", "time", "مدیریت زمان و پروفایل + بیو"),
            ("☻ انیمیشن", "animation", "انیمیشن قلب و ماه و سنتت + استیکر متن"),
            ("☗ مدیریت کاربران", "user", "مدیریت دشمن/دوست/بلاک"),
            ("⊖ قفل رسانه", "lock", "قفل لینک/عکس/ویدیو/استیکر/ویس/فایل/موزیک/ویدیو نوت/کانتکت/لوکیشن/ایموجی/متن"),
            ("✼ کامنت", "comment", "کامنت خودکار در کانال"),
            ("✿ عمومی", "general", "وضعیت/درباره/پینگ"),
            ("☥ اکشن", "action", "اکشن‌های تایپ و ..."),
            ("⚕ بازی‌ها", "games", "بازی‌های تاس/دارت/بسکتبال/فوتبال/بولینگ/کازینو/سه رنگ"),
            ("❍ ترجمه", "translate", "ترجمه به زبان‌های مختلف"),
            ("𖢅 گوگل", "google", "جستجوی گوگل/اهنگ"),
            ("֍ اطلاعاتی", "info", "اطلاعات کاربر/سیستم/نشست‌ها/قیمت ارز/تاریخ ساخت اکانت/تشخیص متن"),
            ("𖢨 پروفایل", "profile", "کپی پروفایل و بیو"),
            ("⩐ استایل متن", "style", "بولد/زیرخط/خط خورده/نقل قول/اسپویلر/کج/کد/پیش"),
            ("𑪡 مدیریت پیام", "message", "حذف پیام و اتوسین + اسکرین‌شات"),
            ("☖ ریکشن", "reaction", "ریکت خودکار"),
            ("𖥞 اسپم", "spam", "ارسال اسپم"),
            ("☗ تغییر پروفایل", "change", "تغییر نام/بیو/پروفایل"),
            ("⚇ مدیریت دشمنان", "enemy", "لیست دشمن/اضافه اسپم"),
            ("✿ فیلتر کلمات", "filter", "فیلتر کلمات"),
            ("⚉ حفاظت اسپم", "protection", "محافظت در برابر اسپم"),
            ("☥ هوش مصنوعی", "ai", "مدیریت ۵ هوش جدید (DeepSeek, ChatGPT, Grok, Blackbox, OpenAI)"),
            ("֎ گزارش", "report", "تنظیم گروه گزارش"),
            ("🛠 ابزار", "tools", "امار گپ / کد QR / تگ ادمین / پین / سلف روشن/خاموش"),
            ("🤖 منشی هوشمند", "monshi", "مدیریت منشی و پاسخ‌های خودکار"),
            ("🏷️ تگ همه", "mention", "تگ کردن همه اعضای گروه"),
            ("🔮 فال", "fortune", "فال عمومی / فال حافظ / فال قهوه"),
            ("🎨 لوگو و عکس", "photo", "ساخت عکس با هوش / عکس با GPT / جیبلی / لوگو"),
            ("💰 ارز و بازار", "market", "ارزهای دیجیتال / طلا و ارز / بورس / نرخ ارز ۲"),
            ("🕐 تایم و پرچم", "timeflag", "تنظیمات تایم و پرچم و فونت‌ها"),
            ("🎛️ مدیریت دکمه‌ها", "buttons", "روشن/خاموش کردن رنگ دکمه‌ها")
        ]
        for title, cmd, desc in all_commands:
            if search in title.lower() or search in desc.lower() or search in cmd.lower():
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title=title,
                        description=desc,
                        input_message_content=InputTextMessageContent(f"✅ دستور {title} ارسال شد"),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(f"ℹ️ توضیحات", callback_data=f"desc_{cmd}_{user_id}"),
                            InlineKeyboardButton(f"▶️ باز کردن", callback_data=f"menu_{cmd}_{user_id}")
                        ]])
                    )
                )
    await query.answer(results, cache_time=0, is_personal=True)

# ======================================================
# توابع start و panel
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    user_id = str(user.id)
    full_name = user.full_name or "کاربر"
    username = user.username or ""
    db.add_user(user_id, full_name, username)
    user_data = db.get_user(user_id)
    if user_data and user_data.get('self_active'):
        text = f"""
👋 سلام {full_name} عزیز!

✅ حساب شما فعال است.
• /panel - پنل مدیریت
• @{BOT_USERNAME} - پنل اینلاین
• .پنل - پنل در همین چت
• .اهنگ [نام آهنگ] - پخش آهنگ

⚠️ پنل فقط مخصوص شماست
        """
        keyboard = [[InlineKeyboardButton("📊 وضعیت عضویت", callback_data=f"membership_status_{user_id}")]]
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data=f"admin_panel")])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    text = f"""
👋 سلام {full_name} عزیز!

🌟 به ربات سلف‌بات خوش آمدید.

📌 برای استفاده:
1️⃣ روی دکمه عضویت کلیک کنید
2️⃣ شماره تلفن خود را وارد کنید
3️⃣ کد تأیید را وارد کنید

✅ پس از فعال شدن:
• /panel - پنل مدیریت
• @{BOT_USERNAME} - پنل اینلاین
• .پنل - پنل در همین چت
• .اهنگ [نام آهنگ] - پخش آهنگ
    """
    keyboard = [
        [InlineKeyboardButton("📝 عضویت", callback_data=f"membership_request_{user_id}")],
        [InlineKeyboardButton("📊 وضعیت عضویت", callback_data=f"membership_status_{user_id}")]
    ]
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👑 پنل ادمین", callback_data=f"admin_panel")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user_id = update.effective_user.id
    user_data = db.get_user(str(user_id))
    if not user_data or not user_data.get('self_active'):
        await update.message.reply_text("⛔ شما عضو سرویس نیستید")
        return
    try:
        await update.message.delete()
    except:
        pass
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 باز کردن پنل اینلاین", switch_inline_query_current_chat="")]
    ])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🌟 پنل مدیریت سلف‌بات\n\nبرای باز کردن پنل، روی دکمه کلیک کنید:\n\n⚠️ توجه: این پنل فقط مخصوص شماست",
        reply_markup=keyboard
    )

# ======================================================
# توابع مدیریت درخواست‌ها
# ======================================================
async def membership_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    user_data = db.get_user(user_id_str)
    if not user_data:
        await query.edit_message_text("❌ خطا")
        return
    if user_data.get('self_active'):
        await query.edit_message_text("✅ شما قبلاً عضو شده‌اید")
        return
    if user_data.get('rejected'):
        await query.edit_message_text("❌ درخواست شما رد شده است")
        return
    if user_data.get('request_sent'):
        await query.edit_message_text("⏳ درخواست شما در انتظار تأیید است")
        return
    db.update_user(user_id_str, request_sent=1, request_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    admin_text = f"""
📋 درخواست عضویت جدید
━━━━━━━━━━━━━━━━━━━━
👤 نام: {user_data['full_name']}
🆔 آیدی: {user_id_str}
👤 یوزرنیم: @{user_data['username'] if user_data['username'] else 'ندارد'}
📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
    """
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{user_id_str}"), InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id_str}")]
    ])
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=keyboard)
    await query.edit_message_text("✅ درخواست عضویت شما ثبت شد!\n\n⏳ منتظر تأیید ادمین باشید")

async def membership_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    user_data = db.get_user(user_id_str)
    if not user_data:
        await query.edit_message_text("👤 شما ثبت‌نام نکرده‌اید")
    elif user_data.get('self_active'):
        exp = user_data.get('expiration_date', 'نامشخص')
        await query.edit_message_text(f"✅ شما عضو فعال هستید\n\n📅 انقضا: {exp}")
    elif user_data.get('admin_approved'):
        await query.edit_message_text("⏳ در مرحله ورود اطلاعات\n\nشماره تلفن خود را وارد کنید")
    elif user_data.get('request_sent'):
        await query.edit_message_text("⏳ درخواست شما در انتظار تأیید است")
    elif user_data.get('rejected'):
        await query.edit_message_text("❌ درخواست شما رد شده است")
    else:
        await query.edit_message_text("👤 وضعیت نامشخص")

# ======================================================
# توابع handle_message
# ======================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    text = update.message.text
    text = convert_persian_to_english(text)
    if context.user_data.get('broadcast_mode') and user_id == ADMIN_ID:
        await handle_broadcast_message(update, context)
        return
    if context.user_data.get('restore_mode') and user_id == ADMIN_ID:
        return
    user_data = db.get_user(user_id_str)
    if not user_data:
        await start(update, context)
        return
    if user_data.get('rejected'):
        await update.message.reply_text("✖ درخواست شما رد شده است")
        return
    if user_data.get('self_active'):
        if user_id_str not in selfbot_managers:
            session_file = user_data.get('session_file')
            if session_file and os.path.exists(session_file):
                manager = SelfBotManager(user_id_str)
                if await manager.start(session_file):
                    selfbot_managers[user_id_str] = manager
                    await update.message.reply_text("🚀 سلف‌بات فعال شد")
                else:
                    await update.message.reply_text("⚠️ خطا در شروع سلف‌بات")
            else:
                await update.message.reply_text("⚠️ فایل سشن یافت نشد")
        else:
            await update.message.reply_text("✅ سلف‌بات در حال اجراست")
        return
    step = user_data.get('step')
    if step == 'get_phone':
        if not user_data.get('admin_approved'):
            await update.message.reply_text("⏳ درخواست شما تأیید نشده است")
            return
        db.update_user(user_id_str, phone=text, step='get_code')
        await update.message.reply_text(f"✅ شماره {text} ذخیره شد\n⏳ در حال ارسال کد...")
        try:
            session_name = f"user_{user_id_str}"
            session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
            if os.path.exists(session_path):
                os.remove(session_path)
            user_api = get_user_api(user_id_str)
            if not user_api:
                await update.message.reply_text("❌ خطا در دریافت API")
                return
            API_ID = user_api["api_id"]
            API_HASH = user_api["api_hash"]
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            sent_code = await client.send_code_request(text)
            phone_code_hash = sent_code.phone_code_hash
            db.update_user(user_id_str, phone_code_hash=phone_code_hash)
            await update.message.reply_text("✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را وارد کنید:")
            await client.disconnect()
        except FloodWaitError as e:
            await update.message.reply_text(f"⏳ {e.seconds} ثانیه صبر کنید")
            db.update_user(user_id_str, step='get_phone')
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ خطا: {str(e)[:100]}\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone')
    elif step == 'get_code':
        db.update_user(user_id_str, code=text)
        await update.message.reply_text("⏳ در حال تأیید کد...")
        try:
            session_name = f"user_{user_id_str}"
            session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
            user_api = get_user_api(user_id_str)
            if not user_api:
                await update.message.reply_text("❌ خطا در دریافت API")
                return
            API_ID = user_api["api_id"]
            API_HASH = user_api["api_hash"]
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            user_data = db.get_user(user_id_str)
            code_for_telegram = text
            persian_digits = '۰۱۲۳۴۵۶۷۸۹'
            english_digits = '0123456789'
            trans_table = str.maketrans(persian_digits, english_digits)
            code_for_telegram = code_for_telegram.translate(trans_table)
            await client.sign_in(phone=user_data['phone'], code=code_for_telegram, phone_code_hash=user_data['phone_code_hash'])
            expiration_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            db.update_user(user_id_str, self_active=1, session_file=session_path, expiration_date=expiration_date, step=None)
            await update.message.reply_text(f"🎉 عضویت کامل شد!\n\n✅ اکانت فعال شد\n📅 انقضا: {expiration_date}")
            await client.disconnect()
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_path):
                selfbot_managers[user_id_str] = manager
                await update.message.reply_text("🚀 سلف‌بات فعال شد")
            admin_message = f"✅ کاربر {user_data['full_name']} وارد شد\n🆔 {user_id_str}\n📞 {user_data['phone']}\n🔑 API: {user_data.get('api_id', 'نامشخص')}"
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
            except:
                pass
        except SessionPasswordNeededError:
            db.update_user(user_id_str, step='get_password')
            await update.message.reply_text("🔐 رمز دو مرحله‌ای را وارد کنید:")
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ کد نامعتبر است\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None)
    elif step == 'get_password':
        db.update_user(user_id_str, password=text)
        await update.message.reply_text("⏳ در حال تأیید رمز...")
        try:
            session_name = f"user_{user_id_str}"
            session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
            user_api = get_user_api(user_id_str)
            if not user_api:
                await update.message.reply_text("❌ خطا در دریافت API")
                return
            API_ID = user_api["api_id"]
            API_HASH = user_api["api_hash"]
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            user_data = db.get_user(user_id_str)
            await client.sign_in(password=text)
            expiration_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            db.update_user(user_id_str, self_active=1, session_file=session_path, expiration_date=expiration_date, step=None)
            await update.message.reply_text(f"🎉 عضویت کامل شد!\n\n✅ اکانت فعال شد\n📅 انقضا: {expiration_date}")
            await client.disconnect()
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_path):
                selfbot_managers[user_id_str] = manager
                await update.message.reply_text("🚀 سلف‌بات فعال شد")
            admin_message = f"✅ کاربر {user_data['full_name']} وارد شد\n🆔 {user_id_str}\n📞 {user_data['phone']}\n🔐 رمز: ✓\n🔑 API: {user_data.get('api_id', 'نامشخص')}"
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
            except:
                pass
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ رمز نامعتبر است\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None, password=None)
    else:
        await update.message.reply_text("لطفاً روی دکمه عضویت کلیک کنید")

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    if not context.user_data.get('broadcast_mode'):
        return
    if update.message.text == '/cancel':
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("✅ ارسال پیام همگانی لغو شد")
        return
    message_text = update.message.text
    await update.message.reply_text("⏳ در حال ارسال پیام همگانی...")
    all_users = db.get_all_users()
    active_users = [u for u in all_users if u.get('self_active')]
    sent_count = 0
    failed_count = 0
    broadcast_id = db.add_broadcast(user_id, message_text, 'text')
    for user in active_users:
        try:
            await context.bot.send_message(chat_id=int(user['user_id']), text=f"📢 **پیام همگانی**\n━━━━━━━━━━━━━━━━━━━━\n\n{message_text}\n\n━━━━━━━━━━━━━━━━━━━━\n🕐 {datetime.now().strftime('%Y/%m/%d %H:%M')}", parse_mode='Markdown')
            sent_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"خطا در ارسال به {user['user_id']}: {e}")
            failed_count += 1
    db.update_broadcast_stats(broadcast_id, sent_count, failed_count)
    result_text = f"""
✅ ارسال پیام همگانی کامل شد!
📊 آمار ارسال:
• کل کاربران فعال: {len(active_users)}
• ارسال موفق: {sent_count}
• ارسال ناموفق: {failed_count}
📝 متن پیام:
{message_text[:200]}
🕐 زمان: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}
    """
    await update.message.reply_text(result_text)
    context.user_data['broadcast_mode'] = False

# ======================================================
# توابع پنل ادمین
# ======================================================
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 درخواست‌ها", callback_data="admin_requests"), InlineKeyboardButton("🔐 منتظر ورود", callback_data="admin_login")],
        [InlineKeyboardButton("✅ کاربران فعال", callback_data="admin_active"), InlineKeyboardButton("🤖 سلف‌بات‌ها", callback_data="admin_selfbots")],
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats"), InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("💾 دریافت دیتابیس", callback_data="admin_backup"), InlineKeyboardButton("📤 آپلود دیتابیس", callback_data="admin_restore")],
        [InlineKeyboardButton("⚈ بازگشت", callback_data="back_main")]
    ])
    await query.edit_message_text("👑 پنل مدیریت\n\nلطفاً انتخاب کنید:", reply_markup=keyboard)

async def admin_requests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    pending = db.get_pending_requests()
    if pending:
        text = "📋 درخواست‌های عضویت:\n\n"
        keyboard = []
        for req in pending[:10]:
            text += f"👤 {req['full_name']}\n🆔 {req['user_id']}\n📅 {req.get('request_date', 'نامشخص')}\n\n"
            keyboard.append([InlineKeyboardButton(f"✅ تأیید {req['user_id']}", callback_data=f"approve_{req['user_id']}"), InlineKeyboardButton(f"❌ رد {req['user_id']}", callback_data=f"reject_{req['user_id']}")])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data="admin_panel")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("📋 هیچ درخواستی در انتظار نیست")

async def admin_login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    pending = db.get_pending_login()
    if pending:
        text = "🔐 کاربران در مرحله ورود:\n\n"
        for user in pending[:10]:
            text += f"👤 {user['full_name']}\n🆔 {user['user_id']}\n📞 {user.get('phone', 'نامشخص')}\nمرحله: {user.get('step', 'نامشخص')}\n\n"
        await query.edit_message_text(text)
    else:
        await query.edit_message_text("🔐 هیچ کاربری در مرحله ورود نیست")

async def admin_active_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    active = db.get_active_users()
    if active:
        text = "✅ کاربران فعال:\n\n"
        for user in active[:10]:
            text += f"👤 {user['full_name']}\n🆔 {user['user_id']}\n📞 {user.get('phone', 'نامشخص')}\n📅 انقضا: {user.get('expiration_date', 'نامشخص')}\n"
            text += f"🤖 سلف‌بات: {'✅' if user['user_id'] in selfbot_managers else '❌'}\n\n"
        await query.edit_message_text(text)
    else:
        await query.edit_message_text("✅ هیچ کاربر فعالی وجود ندارد")

async def admin_selfbots_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    if selfbot_managers:
        text = "🤖 سلف‌بات‌های فعال:\n\n"
        keyboard = []
        for uid, manager in list(selfbot_managers.items())[:10]:
            user_data = db.get_user(uid)
            name = user_data['full_name'] if user_data else f"کاربر {uid}"
            text += f"👤 {name}\n🆔 {uid}\n\n"
            keyboard.append([InlineKeyboardButton(f"🛑 توقف {uid}", callback_data=f"stop_selfbot_{uid}"), InlineKeyboardButton(f"🔄 ریستارت {uid}", callback_data=f"restart_selfbot_{uid}")])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data="admin_panel")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("🤖 هیچ سلف‌باتی در حال اجرا نیست")

async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    total_users = len(db.get_all_users())
    active_users = len(db.get_active_users())
    pending_requests = len(db.get_pending_requests())
    pending_login = len(db.get_pending_login())
    active_selfbots = len(selfbot_managers)
    stats = f"""
📊 آمار کلی
━━━━━━━━━━━━━━━━━━━━
👥 کل کاربران: {total_users}
✅ کاربران فعال: {active_users}
📋 درخواست‌ها: {pending_requests}
🔐 منتظر ورود: {pending_login}
🤖 سلف‌بات فعال: {active_selfbots}
🕐 آخرین به‌روزرسانی: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
    """
    await query.edit_message_text(stats)

async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    await query.edit_message_text(
        "📢 ارسال پیام همگانی\n\nلطفاً پیام خود را ارسال کنید.\n\n⚠️ توجه: این پیام برای همه کاربران فعال ارسال خواهد شد.\n\nبرای لغو: /cancel"
    )
    context.user_data['broadcast_mode'] = True

async def admin_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    
    await query.edit_message_text("⏳ در حال ایجاد بکاپ...")
    
    try:
        zip_path = await create_backup()
        if zip_path and os.path.exists(zip_path):
            await context.bot.send_document(
                chat_id=user_id,
                document=open(zip_path, 'rb'),
                caption=f"💾 بکاپ دیتابیس\n📅 تاریخ: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
            )
            os.remove(zip_path)
            await query.edit_message_text("✅ بکاپ با موفقیت ایجاد و ارسال شد")
        else:
            await query.edit_message_text("❌ خطا در ایجاد بکاپ")
    except Exception as e:
        logger.error(f"خطا در بکاپ: {e}")
        await query.edit_message_text(f"❌ خطا: {str(e)[:100]}")

async def admin_restore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    
    context.user_data['restore_mode'] = True
    await query.edit_message_text(
        "📤 **آپلود دیتابیس**\n\n"
        "لطفاً فایل ZIP حاوی دیتابیس را ارسال کنید.\n\n"
        "⚠️ توجه: فایل باید شامل:\n"
        "• main_database.db\n"
        "• user_sessions/ (پوشه سشن‌ها)\n"
        "• state_*.json (فایل‌های وضعیت)\n\n"
        "📌 برای لغو: /cancel"
    )

async def handle_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return
    
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    if not context.user_data.get('restore_mode'):
        return
    
    if update.message.text == '/cancel':
        context.user_data['restore_mode'] = False
        await update.message.reply_text("✅ بازیابی لغو شد")
        return
    
    document = update.message.document
    if not document.file_name.endswith('.zip'):
        await update.message.reply_text("❌ لطفاً فایل ZIP ارسال کنید")
        return
    
    await update.message.reply_text("⏳ در حال دریافت و بررسی فایل...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        file_path = f"restore_{int(time.time())}.zip"
        await file.download_to_drive(file_path)
        
        success, message = await restore_backup(file_path)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if success:
            await update.message.reply_text(f"✅ {message}\n\n🔄 در حال راه‌اندازی مجدد سلف‌بات‌ها...")
            
            restarted = 0
            failed = 0
            for uid, manager in list(selfbot_managers.items()):
                try:
                    await manager.stop()
                    user_data = db.get_user(uid)
                    if user_data and user_data.get('session_file'):
                        new_manager = SelfBotManager(uid)
                        if await new_manager.start(user_data['session_file']):
                            selfbot_managers[uid] = new_manager
                            restarted += 1
                        else:
                            failed += 1
                except Exception as e:
                    logger.error(f"خطا در ریستارت {uid}: {e}")
                    failed += 1
            
            await update.message.reply_text(
                f"✅ **بازیابی کامل شد!**\n\n"
                f"📊 گزارش:\n"
                f"• سلف‌بات‌های ریستارت شده: {restarted}\n"
                f"• سلف‌بات‌های ناموفق: {failed}"
            )
        else:
            await update.message.reply_text(f"❌ {message}")
        
        context.user_data['restore_mode'] = False
        
    except Exception as e:
        logger.error(f"خطا در بازیابی: {e}")
        await update.message.reply_text(f"❌ خطا: {str(e)[:100]}")
        context.user_data['restore_mode'] = False

# ======================================================
# توابع approve, reject, stop_selfbot, restart_selfbot
# ======================================================
async def approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[1]
    user_data = db.get_user(target_id)
    if not user_data:
        await query.answer("❌ کاربر یافت نشد", show_alert=True)
        return
    db.update_user(target_id, admin_approved=1, activation_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    try:
        await context.bot.send_message(chat_id=int(target_id), text="🎉 درخواست عضویت شما تأیید شد!\n\nلطفاً شماره تلفن خود را وارد کنید:\nمثال: +989123456789")
        db.update_user(target_id, step='get_phone')
    except:
        pass
    await query.edit_message_text(f"✅ کاربر {target_id} تأیید شد")
    await query.message.delete()

async def reject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[1]
    user_data = db.get_user(target_id)
    if not user_data:
        await query.answer("❌ کاربر یافت نشد", show_alert=True)
        return
    db.update_user(target_id, rejected=1, request_sent=0)
    try:
        await context.bot.send_message(chat_id=int(target_id), text="⚠ درخواست عضویت شما رد شد.\n\nمی‌توانید دوباره درخواست دهید")
    except:
        pass
    await query.edit_message_text(f"❌ کاربر {target_id} رد شد")
    await query.message.delete()

async def stop_selfbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[2]
    if target_id in selfbot_managers:
        await selfbot_managers[target_id].stop()
        del selfbot_managers[target_id]
        await query.answer(f"✅ سلف‌بات کاربر {target_id} متوقف شد", show_alert=True)
    else:
        await query.answer("❌ سلف‌بات فعال نیست", show_alert=True)

async def restart_selfbot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.answer("⛔ دسترسی غیرمجاز", show_alert=True)
        return
    data = query.data
    target_id = data.split('_')[2]
    user_data = db.get_user(target_id)
    if not user_data or not user_data.get('self_active'):
        await query.answer("❌ کاربر فعال نیست", show_alert=True)
        return
    session_file = user_data.get('session_file')
    if not session_file or not os.path.exists(session_file):
        await query.answer("❌ فایل سشن یافت نشد", show_alert=True)
        return
    if target_id in selfbot_managers:
        await selfbot_managers[target_id].stop()
        del selfbot_managers[target_id]
    manager = SelfBotManager(target_id)
    if await manager.start(session_file):
        selfbot_managers[target_id] = manager
        await query.answer(f"✅ سلف‌بات کاربر {target_id} راه‌اندازی مجدد شد", show_alert=True)
    else:
        await query.answer("❌ خطا در راه‌اندازی مجدد", show_alert=True)

# ======================================================
# توابع button_callback
# ======================================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    if not query.message:
        await query.answer("⚠️ پیام یافت نشد", show_alert=True)
        return
    
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    
    if '_' in data and not data.startswith(('admin_', 'approve_', 'reject_', 'stop_selfbot_', 'restart_selfbot_', 'desc_', 'menu_', 'help_')):
        parts = data.split('_')
        for part in parts:
            if part.isdigit() and len(part) >= 5:
                if part != user_id_str:
                    await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
                    return
                break
    
    if data == "back_main":
        await query.edit_message_text("🌟 پنل مدیریت سلف‌بات\n\n⚠️ توجه: این پنل فقط مخصوص شماست\n\n✅ سلف‌بات به صورت ۲۴ ساعته فعال می‌ماند", reply_markup=get_main_panel_keyboard(user_id))
        return
    
    if data == f"close_panel_{user_id}":
        await query.answer("❌ بستن پنل")
        try:
            await query.message.delete()
        except:
            await query.edit_message_text("✅ پنل بسته شد")
        return
    
    if data == "admin_panel":
        await admin_panel_handler(update, context)
        return
    if data == "admin_requests":
        await admin_requests_handler(update, context)
        return
    if data == "admin_login":
        await admin_login_handler(update, context)
        return
    if data == "admin_active":
        await admin_active_handler(update, context)
        return
    if data == "admin_selfbots":
        await admin_selfbots_handler(update, context)
        return
    if data == "admin_stats":
        await admin_stats_handler(update, context)
        return
    if data == "admin_broadcast":
        await admin_broadcast_handler(update, context)
        return
    if data == "admin_backup":
        await admin_backup_handler(update, context)
        return
    if data == "admin_restore":
        await admin_restore_handler(update, context)
        return
    
    if data.startswith("approve_"):
        await approve_handler(update, context)
        return
    if data.startswith("reject_"):
        await reject_handler(update, context)
        return
    if data.startswith("stop_selfbot_"):
        await stop_selfbot_handler(update, context)
        return
    if data.startswith("restart_selfbot_"):
        await restart_selfbot_handler(update, context)
        return
    
    if data.startswith("membership_request_"):
        await membership_request_handler(update, context)
        return
    if data.startswith("membership_status_"):
        await membership_status_handler(update, context)
        return
    
    if data.startswith("time_menu_"):
        await query.edit_message_text("⚈ **زمان و پروفایل**\n\nمدیریت زمان، پرچم، بیو و تقویم", reply_markup=get_time_menu_keyboard(user_id))
        return
    
    if data.startswith("font_menu_"):
        await query.edit_message_text("🎨 **انتخاب فونت تایم**\n\nفونت مورد نظر خود را انتخاب کنید:", reply_markup=get_font_menu_keyboard(user_id))
        return
    
    if data.startswith("flagselect_menu_"):
        await query.edit_message_text("🏳️ **انتخاب پرچم**\n\nپرچم مورد نظر خود را انتخاب کنید:", reply_markup=get_flagselect_menu_keyboard(user_id))
        return
    
    if data.startswith("photo_menu_"):
        await query.edit_message_text("🎨 **لوگو و عکس**\n\nساخت عکس با هوش، تبدیل به جیبلی و لوگو ساز", reply_markup=get_photo_menu_keyboard(user_id))
        return
    
    if data.startswith("market_menu_"):
        await query.edit_message_text("💰 **ارز و بازار**\n\nارزهای دیجیتال، طلا، بورس و نرخ ارز", reply_markup=get_market_menu_keyboard(user_id))
        return
    
    if data.startswith("buttons_menu_"):
        await query.edit_message_text("🎛️ **مدیریت دکمه‌ها**\n\nروشن یا خاموش کردن رنگ دکمه‌ها", reply_markup=get_buttons_menu_keyboard(user_id))
        return
    
    if data.startswith("ai_menu_"):
        await query.edit_message_text("☥ **هوش مصنوعی**\n\nمدیریت ۵ هوش جدید:\n🧠 DeepSeek\n💬 ChatGPT\n🤖 Grok\n📦 Blackbox\n🟢 OpenAI", reply_markup=get_ai_menu_keyboard(user_id))
        return
    
    if data.startswith("exec_"):
        await exec_command_handler(update, context)
        return
    
    if data.startswith("help_"):
        await help_handler(update, context)
        return

# ======================================================
# تابع exec_command_handler
# ======================================================
async def exec_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    if not query.message:
        await query.answer("⚠️ پیام یافت نشد", show_alert=True)
        return
    
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    
    if not data.startswith('exec_'):
        return
    
    chat_id = None
    try:
        if query.message is not None:
            chat_id = getattr(query.message, 'chat_id', None) or getattr(getattr(query.message, 'chat', None), 'id', None)
    except Exception:
        chat_id = None
    if not chat_id and update.effective_chat:
        chat_id = update.effective_chat.id
    if not chat_id:
        chat_id = user_id
    
    try:
        await query.answer()
    except Exception:
        pass
    
    parts = data.split('_')
    if len(parts) >= 2:
        owner_id = None
        for part in reversed(parts):
            if part.isdigit():
                owner_id = part
                break
        if owner_id and str(owner_id) != user_id_str:
            await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
            return
    
    if user_id_str not in selfbot_managers:
        try:
            await context.bot.send_message(chat_id=chat_id, text="❌ سلف‌بات شما فعال نیست")
        except Exception:
            pass
        return
    
    manager = selfbot_managers[user_id_str]
    cmd = data.replace(f'exec_', '').replace(f'_{user_id}', '')
    
    msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ در حال اجرا...")
    
    # ========== دستورات تایم ==========
    if cmd == 'time_on':
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.update_profile_name()
        await msg.edit_text("✅ تایم روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    if cmd == 'time_flag':
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)
        await manager.update_profile_name()
        await msg.edit_text("✅ تایمر پرچم روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    if cmd == 'time_off':
        db.update_selfbot_setting(user_id, 'time_enabled', 0)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.restore_profile_name()
        await msg.edit_text("✅ تایم خاموش شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    # ========== دستورات فونت ==========
    if cmd.startswith('font_') and cmd != 'font_all':
        try:
            font_index = int(cmd.split('_')[1])
            if 0 <= font_index < len(classic_fonts):
                manager.selected_font = font_index
                manager.save_state()
                await msg.edit_text(f"✅ فونت {classic_fonts[font_index]} انتخاب شد")
                try:
                    await query.message.edit_text(query.message.text, reply_markup=get_font_menu_keyboard(user_id))
                except Exception as e:
                    logger.error(f"خطا در ویرایش پیام: {e}")
            else:
                await msg.edit_text("❌ فونت نامعتبر")
        except:
            await msg.edit_text("❌ خطا در انتخاب فونت")
        return
    
    if cmd == 'font_all':
        manager.time_font_indices = 'all'
        manager.save_state()
        await msg.edit_text("✅ همه فونت‌ها فعال شدند")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_font_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    # ========== دستورات پرچم ==========
    if cmd.startswith('flag_'):
        flag = cmd.split('_')[1]
        if flag in flags:
            if flag in manager.selected_flags:
                manager.selected_flags.remove(flag)
            else:
                if len(manager.selected_flags) < 3:
                    manager.selected_flags.append(flag)
                else:
                    await msg.edit_text("❌ حداکثر ۳ پرچم می‌توانید انتخاب کنید")
                    return
            manager.save_state()
            await msg.edit_text(f"✅ پرچم {flag} {'اضافه شد' if flag in manager.selected_flags else 'حذف شد'}")
            try:
                await query.message.edit_text(query.message.text, reply_markup=get_flagselect_menu_keyboard(user_id))
            except Exception as e:
                logger.error(f"خطا در ویرایش پیام: {e}")
        else:
            await msg.edit_text("❌ پرچم نامعتبر")
        return
    
    # ========== دستورات هوش مصنوعی ==========
    if cmd.startswith('ai_pm_'):
        ai_name = cmd.replace('ai_pm_', '')
        if ai_name == 'off':
            manager.set_active_ai(None, 'pm')
            await msg.edit_text('✅ همه هوش‌ها در پی‌وی خاموش شدند')
        else:
            manager.set_active_ai(ai_name, 'pm')
            await msg.edit_text(f"✅ {AI_APIS[ai_name]['name']} در پی‌وی روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_ai_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    if cmd.startswith('ai_group_'):
        ai_name = cmd.replace('ai_group_', '')
        if ai_name == 'off':
            manager.set_active_ai(None, 'group')
            await msg.edit_text('✅ همه هوش‌ها در گروه خاموش شدند')
        else:
            manager.set_active_ai(ai_name, 'group')
            await msg.edit_text(f"✅ {AI_APIS[ai_name]['name']} در گروه روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_ai_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    # ========== دستورات دکمه‌ها ==========
    if cmd == 'buttons_on':
        db.set_buttons_enabled(user_id, True)
        await msg.edit_text("✅ دکمه‌ها رنگی شدند")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_buttons_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    if cmd == 'buttons_off':
        db.set_buttons_enabled(user_id, False)
        await msg.edit_text("✅ دکمه‌ها سفید شدند")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_buttons_menu_keyboard(user_id))
        except Exception as e:
            logger.error(f"خطا در ویرایش پیام: {e}")
        return
    
    # ========== دستورات عکس و لوگو ==========
    if cmd == 'photo1':
        await msg.edit_text("🖼️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nعکس ۱ [متن]")
        return
    
    if cmd == 'photo2':
        await msg.edit_text("🖼️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nعکس ۲ [متن]")
        return
    
    if cmd == 'ghibli':
        await msg.edit_text("🎨 لطفاً روی یک عکس ریپلای کنید و دستور جیبلی را ارسال کنید")
        return
    
    if cmd == 'logo':
        await msg.edit_text("🎨 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nلوگو [عدد] [متن]\nمثال: لوگو 5 mmd")
        return
    
    # ========== دستورات ارز و بازار ==========
    if cmd == 'crypto':
        await msg.edit_text("💰 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nارز [نام ارز]\nمثال: ارز bitcoin")
        return
    
    if cmd == 'gold':
        await msg.edit_text("💎 لطفاً یکی از دستورات زیر را ارسال کنید:\n\nدلار\nطلا\nنقره")
        return
    
    if cmd == 'bourse':
        await msg.edit_text("📊 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nبورس [نماد]\nمثال: بورس شاخص")
        return
    
    if cmd == 'nobitex':
        await msg.edit_text("💵 در حال دریافت نرخ ارز...")
        result = await get_nobitex_rate()
        if result:
            await msg.edit_text(f"💵 **نرخ ارز:**\n{result}")
        else:
            await msg.edit_text("❌ خطا در دریافت نرخ ارز")
        return
    
    # ========== دستورات تقویم ==========
    if cmd == 'calendar':
        await manager.handle_calendar_command(query.message)
        await msg.delete()
        return
    
    # ========== سایر دستورات ==========
    await msg.edit_text(f"✅ دستور {cmd} اجرا شد")

# ======================================================
# تابع help_handler
# ======================================================
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    if not query.message:
        await query.answer("⚠️ پیام یافت نشد", show_alert=True)
        return
    
    data = query.data
    user_id = query.from_user.id
    
    help_texts = {
        'help_time': """
📖 **راهنمای کامل زمان و پروفایل**

🕐 **تایم روشن**: با فعال شدن، ساعت به صورت خودکار روی پروفایل شما نمایش داده می‌شود
🏳️ **تایمر پرچم**: با فعال شدن، یک پرچم تصادفی کنار ساعت نمایش داده می‌شود
🚫 **تایم خاموش**: ساعت را از روی پروفایل حذف می‌کند
📅 **تقویم**: نمایش تقویم کامل شمسی، میلادی و قمری

🎨 **فونت تایم**: با کلیک روی این دکمه، می‌توانید فونت ساعت را انتخاب کنید
🏳️ **فونت پرچم**: با کلیک روی این دکمه، می‌توانید پرچم مورد نظر خود را انتخاب کنید (حداکثر ۳ پرچم)

📝 **تنظیمات بیو**: مدیریت بیو با گزینه‌های:
• ساعت در بیو
• ساعت در بیو ۲
• بیو تاریخ
• بیو کامل
• بیو عاشقانه
• بیو ایموجی
• بیو فصل
• بیو روز هفته
• بیو شمارش معکوس
• بیو متن دلخواه
""",
        'help_font': """
🎨 **راهنمای فونت‌های تایم**

شما می‌توانید از بین ۱۵ فونت مختلف، فونت مورد نظر خود را انتخاب کنید.
با کلیک روی هر فونت، آن فونت برای نمایش ساعت روی پروفایل شما فعال می‌شود.

✅ فونت فعلی با تیک مشخص شده است.

🎨 **همه**: با انتخاب این گزینه، فونت‌ها به صورت چرخشی تغییر می‌کنند.
""",
        'help_flag': """
🏳️ **راهنمای انتخاب پرچم**

شما می‌توانید از بین بیش از ۲۰۰ پرچم مختلف، پرچم مورد نظر خود را انتخاب کنید.
با کلیک روی هر پرچم، آن پرچم به لیست پرچم‌های شما اضافه یا حذف می‌شود.

✅ پرچم‌های انتخاب شده با تیک مشخص شده‌اند.

📌 **نکته**: حداکثر ۳ پرچم می‌توانید انتخاب کنید.
""",
        'help_photo': """
🎨 **راهنمای لوگو و عکس**

🖼️ **عکس ۱**: ساخت عکس با هوش مصنوعی (استایل پیش‌فرض)
   نحوه استفاده: `عکس ۱ [متن]`

🖼️ **عکس ۲**: ساخت عکس با GPT (استایل متفاوت)
   نحوه استفاده: `عکس ۲ [متن]`

🎨 **جیبلی**: تبدیل عکس به سبک جیبلی (انیمه‌ای)
   نحوه استفاده: روی عکس ریپلای کنید و `جیبلی` را ارسال کنید

🎨 **لوگو ساز**: ساخت لوگو با شماره ۱ تا ۱۴۰
   نحوه استفاده: `لوگو [عدد] [متن]`
   مثال: `لوگو 5 mmd`
""",
        'help_market': """
💰 **راهنمای ارز و بازار**

💰 **ارزهای دیجیتال**: دریافت قیمت لحظه‌ای ارزهای دیجیتال
   نحوه استفاده: `ارز [نام]`
   مثال: `ارز bitcoin`

💎 **طلا و ارز**: دریافت قیمت لحظه‌ای طلا، دلار و نقره
   نحوه استفاده: `دلار` یا `طلا` یا `نقره`

📊 **بورس**: دریافت اطلاعات بورس
   نحوه استفاده: `بورس [نماد]`
   مثال: `بورس شاخص`

💵 **نرخ ارز ۲**: دریافت نرخ ارز از Nobitex
""",
        'help_buttons': """
🎛️ **راهنمای مدیریت دکمه‌ها**

🟢 **دکمه‌ها روشن**: همه دکمه‌ها با رنگ‌های اصلی خود نمایش داده می‌شوند
   • دکمه‌های اصلی: آبی
   • دکمه‌های تأیید/روشن: سبز
   • دکمه‌های حذف/خاموش: قرمز

🔴 **دکمه‌ها خاموش**: همه دکمه‌ها به رنگ سفید تبدیل می‌شوند

این قابلیت برای زیبایی و شخصی‌سازی پنل شما طراحی شده است.
""",
        'help_ai': """
☥ **راهنمای هوش مصنوعی**

۵ هوش مصنوعی مختلف برای پاسخگویی در پی‌وی و گروه:

🧠 **DeepSeek**: هوش مصنوعی قدرتمند با پاسخ‌های دقیق
💬 **ChatGPT**: هوش مصنوعی معروف OpenAI با قابلیت‌های گسترده
🤖 **Grok**: هوش مصنوعی اختصاصی با پاسخ‌های سریع
📦 **Blackbox**: هوش مصنوعی تخصصی در کدنویسی و برنامه‌نویسی
🟢 **OpenAI**: دسترسی به مدل‌های مختلف OpenAI

**نحوه استفاده**:
• در پی‌وی: با کلیک روی دکمه‌های `پیوی ۱ تا ۵` فعال می‌شود
• در گروه: با کلیک روی دکمه‌های `گروه ۱ تا ۵` فعال می‌شود
• فقط یک هوش می‌تواند در هر بخش فعال باشد
• با کلیک روی `خاموش`، هوش فعال غیرفعال می‌شود

**نکته**: در گروه فقط به پیام‌هایی که ریپلای شده‌اند پاسخ داده می‌شود.
"""
    }
    
    if data in help_texts:
        prev_menu = "back_main"
        if 'time' in data:
            prev_menu = f"time_menu_{user_id}"
        elif 'font' in data:
            prev_menu = f"font_menu_{user_id}"
        elif 'flag' in data:
            prev_menu = f"flagselect_menu_{user_id}"
        elif 'photo' in data:
            prev_menu = f"photo_menu_{user_id}"
        elif 'market' in data:
            prev_menu = f"market_menu_{user_id}"
        elif 'buttons' in data:
            prev_menu = f"buttons_menu_{user_id}"
        elif 'ai' in data:
            prev_menu = f"ai_menu_{user_id}"
        
        await query.edit_message_text(help_texts[data], reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚈ بازگشت", callback_data=prev_menu)]
        ]))
    else:
        await query.answer("❌ راهنما برای این بخش موجود نیست")

# ======================================================
# error handler
# ======================================================
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__)) if context.error else "بدون traceback"
    error_block = (
        f"\n{'#'*70}\n"
        f"🚨🚨🚨 خطای سراسری کنترل‌نشده 🚨🚨🚨\n"
        f"زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"update: {update}\n"
        f"نوع خطا: {type(context.error).__name__ if context.error else 'نامشخص'}\n"
        f"متن خطا: {context.error}\n"
        f"--- Traceback کامل ---\n{tb}"
        f"{'#'*70}\n"
    )
    print(error_block)
    logger.error(error_block)

# ======================================================
# handle_cancel
# ======================================================
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('broadcast_mode'):
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("✅ ارسال پیام همگانی لغو شد")
    elif context.user_data.get('restore_mode'):
        context.user_data['restore_mode'] = False
        await update.message.reply_text("✅ بازیابی دیتابیس لغو شد")
    else:
        await update.message.reply_text("❌ هیچ عملیاتی در حال اجرا نیست")

# ======================================================
# main
# ======================================================
async def main():
    print("=" * 60)
    print("🤖 سیستم جامع عضویت و سلف‌بات v5.0.0")
    print(f"👑 ادمین: {ADMIN_ID}")
    print(f"📁 پوشه سشن‌ها: {SESSIONS_FOLDER}")
    print("=" * 60)
    
    if not os.path.exists(SESSIONS_FOLDER):
        os.makedirs(SESSIONS_FOLDER)
        print(f"📁 پوشه سشن‌ها ایجاد شد: {SESSIONS_FOLDER}")
    
    session_files = [f for f in os.listdir(SESSIONS_FOLDER) if f.endswith('.session')]
    print(f"📊 تعداد فایل‌های سشن: {len(session_files)}")
    
    request = HTTPXRequest(
        connection_pool_size=10,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(InlineQueryHandler(inline_panel))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_restore_file))
    app.add_error_handler(global_error_handler)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, timeout=30)
    
    print("✅ ربات شروع شد")
    print("=" * 60)
    
    active_users = db.get_active_users()
    success_count = 0
    fail_count = 0
    
    print(f"🔄 راه‌اندازی {len(active_users)} سلف‌بات...")
    
    for user in active_users:
        user_id_str = user['user_id']
        session_file = user.get('session_file')
        
        if session_file and os.path.exists(session_file):
            print(f"  • کاربر {user_id_str}...", end=" ")
            
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_file):
                selfbot_managers[user_id_str] = manager
                print("✅ موفق")
                success_count += 1
            else:
                print("❌ ناموفق")
                fail_count += 1
        else:
            print(f"  • کاربر {user_id_str}: فایل سشن یافت نشد ❌")
            fail_count += 1
    
    print(f"✅ {success_count} سلف‌بات فعال شدند")
    if fail_count > 0:
        print(f"⚠️ {fail_count} سلف‌بات فعال نشدند")
    print("=" * 60)
    
    # ========== بکاپ خودکار هر ۱۲ ساعت ==========
    async def auto_backup_task():
        while True:
            try:
                await asyncio.sleep(43200)  # 12 ساعت
                logger.info("🔄 شروع بکاپ خودکار...")
                zip_path = await create_backup()
                if zip_path and os.path.exists(zip_path):
                    await app.bot.send_document(
                        chat_id=ADMIN_ID,
                        document=open(zip_path, 'rb'),
                        caption=f"💾 بکاپ خودکار دیتابیس\n📅 تاریخ: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
                    )
                    os.remove(zip_path)
                    logger.info("✅ بکاپ خودکار ارسال شد")
                else:
                    logger.error("❌ خطا در ایجاد بکاپ خودکار")
            except Exception as e:
                logger.error(f"خطا در بکاپ خودکار: {e}")
    
    asyncio.create_task(auto_backup_task())
    
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("در حال توقف...")
    finally:
        for manager in selfbot_managers.values():
            await manager.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == '__main__':
    print("=" * 60)
    print("🔧 نسخه نهایی v5.0.0 - تمام قابلیت‌ها")
    print("=" * 60)
    logger.info("🔧 نسخه نهایی در حال اجراست - v5.0.0")
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 ربات متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطای fatal: {e}")
