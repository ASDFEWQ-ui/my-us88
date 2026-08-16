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
# فونت‌های تایم (با فونت‌های جدید)
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
    """ساخت عکس یا لوگو - برگرداندن تصویر به صورت bytes"""
    try:
        api = PHOTO_APIS[photo_type]
        if photo_type == 'aiphoto':
            url = f"{api['url']}?apikey={api['api_key']}&text={quote(text)}&style={quote(style or 'default')}"
        elif photo_type == 'gpt_photo':
            url = f"{api['url']}?apikey={api['api_key']}&text={quote(text)}"
        elif photo_type == 'ghibli':
            url = f"{api['url']}?apikey={api['api_key']}&url={quote(url)}"
        elif photo_type == 'logo':
            url = f"{api['url']}?apikey={api['api_key']}&type=logo&id={logo_id}&text={quote(logo_text)}"
        else:
            return None
        response = requests.get(url, timeout=30)
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
# توابع کمکی برای اعمال استایل
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
        self.selected_flag = None
        self.selected_fonts = []
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
                    self.selected_flag = data.get('selected_flag', None)
                    self.selected_fonts = data.get('selected_fonts', [])
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
                'selected_flag': self.selected_flag,
                'selected_fonts': self.selected_fonts
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
            if self.selected_fonts:
                font_index = self.selected_fonts[current_minute % len(self.selected_fonts)]
            elif self.time_font_indices == 'all':
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
                    flag = self.selected_flag or flags[current_minute % len(flags)]
                    new_name = f"『 {flag} 』{current_name} {time_now_classic}"
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
    # متدهای مربوط به هوش مصنوعی جدید
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
    # متدهای مربوط به عکس و لوگو
    # ======================================================
    async def generate_photo_command(self, photo_type, text=None, style=None, url=None, logo_id=None, logo_text=None):
        """ساخت عکس یا لوگو - برگرداندن تصویر"""
        result = await generate_photo(photo_type, text, style, url, logo_id, logo_text)
        if result:
            return result
        return None
    
    # ======================================================
    # متدهای مربوط به ارز و بازار
    # ======================================================
    async def get_price_info(self, query):
        """دریافت قیمت دلار، طلا، نقره و ارزهای دیجیتال"""
        query_lower = query.lower()
        
        try:
            if query_lower in ['دلار', 'dollar', 'usd']:
                data = await get_gold_prices()
                if data and 'dollar' in data:
                    return f"💵 قیمت دلار: {data['dollar']:,} تومان"
            
            elif query_lower in ['طلا', 'gold']:
                data = await get_gold_prices()
                if data and 'gold' in data:
                    return f"💎 قیمت طلا: {data['gold']:,} تومان"
            
            elif query_lower in ['نقره', 'silver']:
                data = await get_gold_prices()
                if data and 'silver' in data:
                    return f"🥈 قیمت نقره: {data['silver']:,} تومان"
            
            elif query_lower in ['بورس', 'bourse']:
                data = await get_bourse_data('index')
                if data and isinstance(data, dict):
                    return f"📊 شاخص بورس: {data}"
            
            else:
                data = await get_crypto_prices()
                if data:
                    for crypto in data:
                        if query_lower in str(crypto.get('symbol', '')).lower() or query_lower in str(crypto.get('name', '')).lower():
                            return f"💰 {crypto.get('name')} ({crypto.get('symbol')}): {crypto.get('price')} تومان"
            
            return "❌ اطلاعاتی برای این درخواست پیدا نشد"
        except Exception as e:
            logger.error(f"خطا در دریافت قیمت: {e}")
            return f"❌ خطا در دریافت اطلاعات: {str(e)[:50]}"

    # ======================================================
    # متدهای اصلی SelfBot
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
            self.selected_flag = self.selected_flag if hasattr(self, 'selected_flag') else None
            
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
    # هندلر پیام‌های دریافتی
    # ======================================================
    async def handle_new_message(self, event):
        """هندلر پیام‌های دریافتی"""
        try:
            # اتوسین
            if self.autosend_mode and isinstance(event.message.peer_id, PeerUser) and not event.message.out:
                try:
                    await event.message.mark_read()
                except:
                    pass
            
            # قفل پیوی همگانی
            settings = db.get_selfbot_settings(self.user_id)
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
                if settings.get('pv_lock_all'):
                    try:
                        await event.message.delete()
                        return
                    except:
                        pass
            
            # قفل پیوی اختصاصی
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
                if db.is_pv_locked(self.user_id, event.sender_id):
                    try:
                        await event.message.delete()
                        return
                    except:
                        pass
            
            # فیلتر کلمات
            if not event.message.out and event.message.text:
                if db.get_filter_enabled(self.user_id):
                    filter_words = db.get_filter_words(self.user_id)
                    for word_info in filter_words:
                        if word_info['enabled'] and word_info['word'].lower() in event.message.text.lower():
                            try:
                                await event.message.delete()
                                return
                            except:
                                pass
            
            # منشی
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
                monshi_data = db.get_monshi_status(self.user_id)
                if monshi_data['status'] and monshi_data['answer']:
                    try:
                        await event.reply(monshi_data['answer'])
                        return
                    except:
                        pass
            
            # پاسخ‌های ذخیره شده
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
                answers = db.get_answers(self.user_id)
                if answers:
                    for question, answer in answers.items():
                        if question in event.message.text:
                            try:
                                await event.reply(answer)
                            except:
                                pass
                            break
            
            # قفل رسانه
            if await self.handle_media_lock_delete(event):
                return
            
            # ذخیره پیام در کش
            chat_id = None
            if isinstance(event.message.peer_id, PeerUser):
                chat_id = event.message.peer_id.user_id
            elif isinstance(event.message.peer_id, PeerChannel):
                chat_id = event.message.peer_id.channel_id
            elif isinstance(event.message.peer_id, PeerChat):
                chat_id = event.message.peer_id.chat_id
            
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
                db.cache_message(self.user_id, chat_id, event.message.id, event.message.text)
            
            # ریکشن خودکار - در گروه و پیوی
            if not event.message.out and event.sender_id:
                sender_id = event.sender_id
                if chat_id:
                    try:
                        reaction = db.get_reaction(self.user_id, chat_id, sender_id)
                        if reaction and reaction in ALLOWED_EMOJIS:
                            try:
                                input_chat = await event.get_input_chat()
                                await self.client(SendReactionRequest(
                                    peer=input_chat,
                                    msg_id=event.message.id,
                                    reaction=[ReactionEmoji(emoticon=reaction)]
                                ))
                            except ChatWriteForbiddenError:
                                logger.warning(f"اجازه ریکت در چت {chat_id} وجود ندارد")
                            except Exception as e:
                                logger.error(f"خطا در ارسال ریکت خودکار: {e}")
                    except Exception as e:
                        logger.error(f"خطا در دریافت ریکت از دیتابیس: {e}")
            
            # هوش مصنوعی در پیوی
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
                sender_id = event.sender_id
                ai_status = settings.get('ai_status', {})
                ai_active = False
                ai_type = None
                if event.message.text:
                    if ai_status.get('ai_deepseek_pm'):
                        ai_active = True
                        ai_type = 'deepseek'
                    elif ai_status.get('ai_chatgpt_pm'):
                        ai_active = True
                        ai_type = 'chatgpt'
                    elif ai_status.get('ai_grok_pm'):
                        ai_active = True
                        ai_type = 'grok'
                    elif ai_status.get('ai_blackbox_pm'):
                        ai_active = True
                        ai_type = 'blackbox'
                    elif ai_status.get('ai_openai_pm'):
                        ai_active = True
                        ai_type = 'openai'
                
                if ai_active and ai_type:
                    try:
                        await self.client(SetTypingRequest(event.chat_id, types.SendMessageTypingAction()))
                        response = await self.get_ai_response(event.message.text, ai_type)
                        if response:
                            # برش به 3 خط
                            lines = response.split('\n')
                            if len(lines) > 3:
                                response = '\n'.join(lines[:3]) + '\n...'
                            text, entities = await apply_text_style(response, settings.get('text_style'))
                            await event.reply(text, formatting_entities=entities)
                        else:
                            await event.reply("❌ خطا در ارتباط با هوش مصنوعی")
                    except Exception as e:
                        logger.error(f"خطا در پاسخ هوش مصنوعی: {e}")
            
            # حفاظت اسپم
            spam_settings = db.get_spam_settings(self.user_id)
            if spam_settings.get('spam_protection') and not event.message.out:
                sender_id = event.sender_id
                chat_key = f"{chat_id}_{sender_id}"
                
                mute_until = self.mute_timestamps.get(chat_key, 0)
                if time.time() < mute_until:
                    try:
                        await event.message.delete()
                        return
                    except:
                        pass
                
                if chat_key not in self.spam_counters:
                    self.spam_counters[chat_key] = []
                now = time.time()
                mute_duration = spam_settings.get('mute_duration', 10)
                spam_limit = spam_settings.get('spam_limit', 10)
                
                self.spam_counters[chat_key] = [t for t in self.spam_counters[chat_key] if now - t <= mute_duration]
                self.spam_counters[chat_key].append(now)
                
                if len(self.spam_counters[chat_key]) > spam_limit:
                    try:
                        await event.message.delete()
                        self.mute_timestamps[chat_key] = now + mute_duration
                        logger.info(f"کاربر {sender_id} در چت {chat_id} به مدت {mute_duration} ثانیه سکوت شد")
                    except:
                        pass
            
            # ذخیره اطلاعات کاربر
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
                sender_id = event.sender_id
                try:
                    sender = await event.get_sender()
                    if sender:
                        username = sender.username if sender.username else None
                        first_name = sender.first_name if sender.first_name else ""
                        last_name = sender.last_name if sender.last_name else ""
                        db.update_user_memory(sender_id, username, first_name, last_name, chat_id)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"خطا در handle_new_message: {e}")
    
    # ======================================================
    # هندلر پیام‌های ویرایش شده
    # ======================================================
    async def handle_edited_message(self, event):
        """هندلر پیام‌های ویرایش شده"""
        try:
            if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
                sender = await event.get_sender()
                if sender.id == self.my_id:
                    return
                settings = db.get_selfbot_settings(self.user_id)
                if settings.get('pv_lock_all') and sender.id != self.my_id:
                    try:
                        await event.message.delete()
                        return
                    except:
                        pass
                if db.is_pv_locked(self.user_id, sender.id):
                    try:
                        await event.message.delete()
                        return
                    except:
                        pass
                if self.report_config.report_edited_messages:
                    message_id = event.message.id
                    chat_id = event.message.peer_id.user_id
                    original_text = message_cache.get((chat_id, message_id), "نامشخص")
                    new_text = event.message.text or "بدون متن"
                    try:
                        sender_info = await self.get_user_info(sender.id)
                        report_text = (
                            f"✍️ پیام ویرایش‌شده\n"
                            f"👤 از: {sender_info}\n"
                            f"🆔 پیام: {message_id}\n"
                            f"📝 متن اصلی:\n{original_text[:1000]}\n"
                            f"📝 متن جدید:\n{new_text[:1000]}\n"
                            f"🕒 زمان: {get_now().strftime('%Y/%m/%d %H:%M:%S')}"
                        )
                        await self.send_report(report_text)
                    except Exception as e:
                        logger.error(f"خطا در گزارش ویرایش پیام: {e}")
                db.cache_message(self.user_id, event.message.peer_id.user_id, event.message.id, event.message.text or "")
        except Exception as e:
            logger.error(f"خطا در handle_edited_message: {e}")
    
    # ======================================================
    # هندلر پیام‌های حذف شده
    # ======================================================
    async def handle_deleted_message(self, event):
        """هندلر پیام‌های حذف شده"""
        try:
            if not self.report_config.report_deleted_media:
                return
            for msg_id in event.deleted_ids:
                if msg_id in media_cache and media_cache[msg_id].get('owner_id') == self.user_id:
                    try:
                        media_info = media_cache[msg_id]
                        sender_info = await self.get_user_info(media_info['user_id'])
                        chat_title = await self.get_chat_title(media_info['chat_id'])
                        file_exists = os.path.exists(media_info['path']) if media_info.get('path') else False
                        report_text = (
                            f"🗑️ رسانه حذف‌شده\n"
                            f"👤 از: {sender_info}\n"
                            f"💬 چت: {chat_title}\n"
                            f"📦 نوع: {media_info['type']}\n"
                            f"🆔 پیام: {msg_id}\n"
                            f"📝 کپشن: {media_info.get('caption', 'بدون کپشن')[:200]}\n"
                            f"💾 فایل ذخیره‌شده: {'✅' if file_exists else '❌'}\n"
                            f"📏 حجم: {media_info.get('file_size', 0) / 1024:.1f} KB\n"
                            f"🕒 زمان ارسال: {media_info.get('timestamp', 'نامشخص')}\n"
                            f"🕒 زمان حذف: {get_now().strftime('%Y/%m/%d %H:%M:%S')}"
                        )
                        if file_exists:
                            await self.send_report(report_text, media_info['path'], f"🗑️ {media_info['type']} حذف‌شده از {sender_info}")
                        else:
                            await self.send_report(report_text)
                        del media_cache[msg_id]
                    except Exception as e:
                        logger.error(f"خطا در گزارش حذف رسانه {msg_id}: {e}")
                        if msg_id in media_cache:
                            del media_cache[msg_id]
                for (chat_id, cached_msg_id), text in list(message_cache.items()):
                    if cached_msg_id == msg_id:
                        try:
                            sender_info = await self.get_user_info(chat_id)
                            chat_title = await self.get_chat_title(chat_id)
                            report_text = (
                                f"🗑️ پیام متنی حذف‌شده\n"
                                f"👤 از: {sender_info}\n"
                                f"💬 چت: {chat_title}\n"
                                f"🆔 پیام: {msg_id}\n"
                                f"📝 متن پیام:\n{text[:1000] or 'بدون متن'}\n"
                                f"🕒 زمان: {get_now().strftime('%Y/%m/%d %H:%M:%S')}"
                            )
                            await self.send_report(report_text)
                            del message_cache[(chat_id, msg_id)]
                        except Exception as e:
                            logger.error(f"خطا در گزارش حذف پیام: {e}")
                            if (chat_id, msg_id) in message_cache:
                                del message_cache[(chat_id, msg_id)]
        except Exception as e:
            logger.error(f"خطا در handle_deleted_message: {e}")
    
    # ======================================================
    # هندلر پیام‌های خروجی
    # ======================================================
    async def handle_outgoing_message(self, event):
        """هندلر پیام‌های خروجی"""
        try:
            message_text = event.text or ""
            
            if self.adding_spam and message_text and not message_text.startswith(COMMAND_KEYWORDS):
                db.add_enemy_spam_message(self.user_id, message_text)
                try:
                    await event.delete()
                except:
                    pass
                return
            
            if event.text:
                settings = db.get_selfbot_settings(self.user_id)
                text_style = settings.get('text_style')
                if text_style and not message_text.startswith(COMMAND_KEYWORDS):
                    try:
                        text, entities = await apply_text_style(message_text, text_style)
                        if entities:
                            await event.message.edit(text, formatting_entities=entities)
                    except:
                        pass
            
            if self.search_mode and message_text and not message_text.startswith(COMMAND_KEYWORDS):
                await self.handle_google_search(event, message_text)
                return
            
            if event.text and not message_text.startswith(COMMAND_KEYWORDS):
                try:
                    translated_text = await self.translate_text(event.text)
                    if translated_text and translated_text.strip() != event.text.strip():
                        try:
                            await event.edit(translated_text)
                        except:
                            pass
                except Exception as e:
                    logger.error(f"خطا در فرآیند ترجمه: {e}")
        except Exception as e:
            logger.error(f"خطا در handle_outgoing_message: {e}")
    
    # ======================================================
    # هندلر کامنت خودکار
    # ======================================================
    async def auto_comment_handler(self, event):
        """هندلر کامنت خودکار در کانال‌ها"""
        try:
            message = event.message
            if not is_channel_post(message):
                return
            chat = await message.get_chat()
            cid = chat.id
            if cid not in self.auto_comment_settings:
                return
            post_key = f"{cid}_{message.id}"
            if post_key in self.auto_comment_sent:
                return
            config = self.auto_comment_settings[cid]
            await asyncio.sleep(0.5)
            await self.client.send_message(
                chat.id,
                config['text'],
                reply_to=message.id
            )
            self.auto_comment_sent.add(post_key)
            self.save_state()
            logger.info(f"✅ نظر ارسال شد به پست {message.id} در کانال {config['title']}")
        except Exception as e:
            logger.error(f"خطا در ارسال نظر اتوماتیک: {e}")
    
    # ======================================================
    # هندلر دستورات
    # ======================================================
    async def handle_commands(self, event):
        if event.sender_id != self.my_id:
            return
        
        command_text = event.text.strip()
        parts = command_text.split()
        if not parts:
            return
        
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        chat_id = None
        if isinstance(event.message.peer_id, PeerUser):
            chat_id = event.message.peer_id.user_id
        elif isinstance(event.message.peer_id, PeerChannel):
            chat_id = event.message.peer_id.channel_id
        elif isinstance(event.message.peer_id, PeerChat):
            chat_id = event.message.peer_id.chat_id
        
        # ========== دستورات عکس و لوگو ==========
        if cmd == 'عکس' and args and args[0] in ['۱', '1', '۲', '2']:
            photo_type = 'aiphoto' if args[0] in ['۱', '1'] else 'gpt_photo'
            text = ' '.join(args[1:])
            if text:
                await event.edit(f"🖼️ در حال ساخت عکس: {text[:30]}...")
                result = await self.generate_photo_command(photo_type, text=text, style='default' if photo_type == 'aiphoto' else None)
                if result:
                    await event.delete()
                    await self.client.send_file(chat_id, BytesIO(result), caption=f"🖼️ عکس ساخته شده: {text[:50]}")
                else:
                    await event.edit("❌ خطا در ساخت عکس")
            else:
                await event.edit("❌ لطفاً متن را وارد کنید")
            return
        
        if cmd == 'جیبلی':
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg.photo:
                    await event.edit("🎨 در حال تبدیل به جیبلی...")
                    photo_data = await reply_msg.download_media(file=BytesIO())
                    # برای جیبلی نیاز به URL داریم
                    await event.edit("❌ متاسفانه تبدیل جیبلی نیاز به آدرس URL عکس دارد")
                else:
                    await event.edit("❌ لطفاً روی یک عکس ریپلای کنید")
            else:
                await event.edit("❌ لطفاً روی یک عکس ریپلای کنید و دستور جیبلی را ارسال کنید")
            return
        
        if cmd == 'لوگو' and len(args) >= 2:
            try:
                logo_id = int(args[0])
                if 1 <= logo_id <= 140:
                    logo_text = ' '.join(args[1:])
                    await event.edit(f"🎨 در حال ساخت لوگو شماره {logo_id}: {logo_text}")
                    result = await self.generate_photo_command('logo', logo_id=logo_id, logo_text=logo_text)
                    if result:
                        await event.delete()
                        await self.client.send_file(chat_id, BytesIO(result), caption=f"🎨 لوگو شماره {logo_id}: {logo_text}")
                    else:
                        await event.edit("❌ خطا در ساخت لوگو")
                else:
                    await event.edit("❌ شماره لوگو باید بین ۱ تا ۱۴۰ باشد")
            except ValueError:
                await event.edit("❌ شماره لوگو باید عدد باشد")
            return
        
        # ========== دستورات ارز و بازار ==========
        if cmd in ['دلار', 'طلا', 'نقره', 'بورس', 'ارز']:
            await event.edit(f"⏳ در حال دریافت اطلاعات {cmd}...")
            query = cmd if cmd != 'ارز' else ' '.join(args)
            result = await self.get_price_info(query)
            if result:
                await event.edit(result)
            else:
                await event.edit("❌ خطا در دریافت اطلاعات")
            return
        
        # ========== دستورات تایم و پرچم ==========
        if cmd == 'تایم' and args:
            if args[0] == 'روشن' and len(args) == 1:
                db.update_selfbot_setting(self.user_id, 'time_enabled', 1)
                db.update_selfbot_setting(self.user_id, 'flag_enabled', 0)
                await self.update_profile_name()
                await event.edit("✅ تایم روشن شد")
                return
            elif args[0] == 'خاموش' and len(args) == 1:
                db.update_selfbot_setting(self.user_id, 'time_enabled', 0)
                db.update_selfbot_setting(self.user_id, 'flag_enabled', 0)
                await self.restore_profile_name()
                await event.edit("✅ تایم خاموش شد")
                return
            elif args[0] == 'پرچم' and len(args) == 2 and args[1] == 'روشن':
                db.update_selfbot_setting(self.user_id, 'time_enabled', 1)
                db.update_selfbot_setting(self.user_id, 'flag_enabled', 1)
                await self.update_profile_name()
                await event.edit("✅ تایم با پرچم روشن شد")
                return

        # ========== دستورات بیو ==========
        bio_commands = {
            'ساعت در بیو': 'ساعت_در_بیو',
            'ساعت در بیو ۲': 'ساعت_در_بیو_۲',
            'بیو تاریخ': 'بیو_تاریخ',
            'بیو کامل': 'بیو_کامل',
            'بیو عاشقانه': 'بیو_عاشقانه',
            'بیو ایموجی': 'بیو_ایموجی',
            'بیو فصل': 'بیو_فصل',
            'بیو روز هفته': 'بیو_روز_هفته',
            'بیو شمارش معکوس': 'بیو_شمارش_معکوس',
            'بیو متن دلخواه': 'بیو_متن_دلخواه',
        }
        
        for bio_cmd, setting_name in bio_commands.items():
            if command_text.startswith(bio_cmd + " "):
                rest = command_text[len(bio_cmd) + 1:].strip()
                if rest in ['روشن', 'خاموش']:
                    status = rest
                    self.set_bio_setting(setting_name, status)
                    if status == 'روشن':
                        await self.update_bio_with_settings()
                        await event.edit(f"✅ {bio_cmd} **{status}** شد و بیو به‌روزرسانی شد")
                    else:
                        await event.edit(f"✅ {bio_cmd} **{status}** شد")
                    return

        # ========== دستورات هوش مصنوعی ==========
        if cmd == 'پیوی' and args and args[0] in ['۱', '1', '۲', '2', '۳', '3', '۴', '4', '۵', '5']:
            ai_map = {
                '۱': 'deepseek', '1': 'deepseek',
                '۲': 'chatgpt', '2': 'chatgpt',
                '۳': 'grok', '3': 'grok',
                '۴': 'blackbox', '4': 'blackbox',
                '۵': 'openai', '5': 'openai'
            }
            ai_name = ai_map.get(args[0])
            if ai_name:
                self.set_active_ai(ai_name, 'pm')
                await event.edit(f"✅ {AI_APIS[ai_name]['name']} در پی‌وی روشن شد")
            return
        
        if cmd == 'گروه' and args and args[0] in ['۱', '1', '۲', '2', '۳', '3', '۴', '4', '۵', '5']:
            ai_map = {
                '۱': 'deepseek', '1': 'deepseek',
                '۲': 'chatgpt', '2': 'chatgpt',
                '۳': 'grok', '3': 'grok',
                '۴': 'blackbox', '4': 'blackbox',
                '۵': 'openai', '5': 'openai'
            }
            ai_name = ai_map.get(args[0])
            if ai_name:
                self.set_active_ai(ai_name, 'group')
                await event.edit(f"✅ {AI_APIS[ai_name]['name']} در گروه روشن شد")
            return
        
        if cmd == 'خاموش' and args and args[0] == 'پیوی' and len(args) == 1:
            self.set_active_ai(None, 'pm')
            await event.edit('✅ همه هوش‌ها در پی‌وی خاموش شدند')
            return
        
        if cmd == 'خاموش' and args and args[0] == 'گروه' and len(args) == 1:
            self.set_active_ai(None, 'group')
            await event.edit('✅ همه هوش‌ها در گروه خاموش شدند')
            return

        # ========== دستورات قفل رسانه ==========
        lock_commands = {
            'لینک': 'lock_link',
            'عکس': 'lock_photo',
            'ویدیو': 'lock_video',
            'استیکر': 'lock_sticker',
            'گیف': 'lock_gif',
            'ویس': 'lock_voice',
            'فایل': 'lock_file',
            'موزیک': 'lock_music',
            'ویدیو نوت': 'lock_video_note',
            'کانتکت': 'lock_contact',
            'لوکیشن': 'lock_location',
            'ایموجی': 'lock_emoji',
            'متن': 'lock_text'
        }
        
        for lock_name, lock_type in lock_commands.items():
            if cmd == f'قفل{lock_name}' and args and args[0] in ['روشن', 'خاموش'] and len(args) == 1:
                target_id = 0
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    target_id = reply_msg.sender_id
                elif isinstance(event.message.peer_id, PeerUser):
                    target_id = event.message.peer_id.user_id
                
                if args[0] == 'روشن':
                    db.set_user_lock(self.user_id, target_id, lock_type, True)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} فعال شد")
                else:
                    db.set_user_lock(self.user_id, target_id, lock_type, False)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} غیرفعال شد")
                return

        # ========== دستورات ترجمه ==========
        translate_map = {
            'انگلیسی': 'english',
            'عربی': 'arabic',
            'عبری': 'hebrew',
            'روسی': 'russian',
            'ترکی': 'turkish'
        }
        if cmd in translate_map and args:
            lang = translate_map[cmd]
            if args[0] == 'روشن' and len(args) == 1:
                self.translate_mode[lang] = True
                db.update_selfbot_setting(self.user_id, f'translate_{lang}', 1)
                await event.edit(f"✅ ترجمه {cmd} فعال شد")
                return
            elif args[0] == 'خاموش' and len(args) == 1:
                self.translate_mode[lang] = False
                db.update_selfbot_setting(self.user_id, f'translate_{lang}', 0)
                await event.edit(f"✅ ترجمه {cmd} غیرفعال شد")
                return

        # ========== دستورات دشمن و دوست ==========
        if cmd == 'دشمن' and not args:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.add_enemy(self.user_id, target_id, 'pv')
                await event.edit(f"✅ دشمن اضافه شد")
                await self.spam_enemy(target_id)
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'دوست' and not args:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.remove_enemy(self.user_id, target_id, 'pv')
                await event.edit(f"✅ دوست حذف شد")
                if target_id in self.spam_tasks:
                    self.spam_tasks[target_id].cancel()
                    del self.spam_tasks[target_id]
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return

        # ========== دستورات قفل پیوی ==========
        if cmd == 'قفل' and args and args[0] == 'پیوی' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.add_locked_pv(self.user_id, target_id)
                await event.edit(f"✅ قفل پیوی برای کاربر {target_id} فعال شد")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'باز' and args and args[0] == 'پی' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.remove_locked_pv(self.user_id, target_id)
                await event.edit(f"✅ قفل پیوی برای کاربر {target_id} غیرفعال شد")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'قفل' and args and args[0] == 'پیوی' and args[1] == 'همه' and len(args) == 2:
            db.update_selfbot_setting(self.user_id, 'pv_lock_all', 1)
            await event.edit("✅ قفل پیوی همگانی فعال شد")
            return
        
        if cmd == 'باز' and args and args[0] == 'پی' and args[1] == 'همه' and len(args) == 2:
            db.update_selfbot_setting(self.user_id, 'pv_lock_all', 0)
            await event.edit("✅ قفل پیوی همگانی غیرفعال شد")
            return

        # ========== دستورات بلاک ==========
        if cmd == 'بلاک' and not args:
            if isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
                await self.client(BlockRequest(id=target_id))
                await event.edit("✅ کاربر بلاک شد")
            else:
                await event.edit("⚠️ فقط در پی‌وی")
            return

        # ========== دستورات ریکت ==========
        if cmd == 'ریکت' and args:
            target_id = await get_target_user(event, self.client)
            if not target_id:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
                return
            
            emoji = args[0]
            if emoji in ALLOWED_EMOJIS:
                chat_id = None
                if isinstance(event.message.peer_id, PeerUser):
                    chat_id = event.message.peer_id.user_id
                elif isinstance(event.message.peer_id, PeerChannel):
                    chat_id = event.message.peer_id.channel_id
                elif isinstance(event.message.peer_id, PeerChat):
                    chat_id = event.message.peer_id.chat_id
                
                if chat_id:
                    db.set_reaction(self.user_id, chat_id, target_id, emoji)
                    await event.edit(f"✅ ریکت {emoji} برای کاربر {target_id} در چت {chat_id} تنظیم شد")
                    
                    try:
                        msg_id = event.message.id
                        input_chat = await event.get_input_chat()
                        await self.client(SendReactionRequest(
                            peer=input_chat,
                            msg_id=msg_id,
                            reaction=[ReactionEmoji(emoticon=emoji)]
                        ))
                        await event.edit(f"✅ ریکت {emoji} روی پیام ارسال شد")
                    except Exception as e:
                        logger.error(f"خطا در ارسال ریکت: {e}")
                        await event.edit(f"✅ ریکت {emoji} تنظیم شد (ارسال خودکار بعداً)")
                else:
                    await event.edit("⚠️ خطا در دریافت شناسه چت")
            else:
                await event.edit(f"⚠️ ایموجی {emoji} مجاز نیست")
            return
        
        if cmd == 'حذف' and args and args[0] == 'ریکت' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if target_id:
                chat_id = None
                if isinstance(event.message.peer_id, PeerUser):
                    chat_id = event.message.peer_id.user_id
                elif isinstance(event.message.peer_id, PeerChannel):
                    chat_id = event.message.peer_id.channel_id
                elif isinstance(event.message.peer_id, PeerChat):
                    chat_id = event.message.peer_id.chat_id
                
                if chat_id:
                    db.remove_reaction(self.user_id, chat_id, target_id)
                    await event.edit(f"✅ ریکت برای کاربر {target_id} در چت {chat_id} حذف شد")
                else:
                    await event.edit("⚠️ خطا در دریافت شناسه چت")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return

        # ========== دستورات تغییر نام و بیو ==========
        if cmd == 'تغییر' and len(args) >= 2:
            if args[0] == 'اسم':
                new_name = ' '.join(args[1:])
                current_name = db.get_current_name(self.user_id)
                if not current_name:
                    db.set_current_name(self.user_id, self.BASE_NAME)
                    current_name = self.BASE_NAME
                
                db.set_current_name(self.user_id, new_name)
                await self.client(UpdateProfileRequest(first_name=new_name))
                
                settings = db.get_selfbot_settings(self.user_id)
                if settings.get('time_enabled'):
                    self.BASE_NAME = new_name
                    await self.update_profile_name()
                else:
                    self.BASE_NAME = new_name
                
                await event.edit(f"✅ نام به {new_name} تغییر کرد")
                return
            
            elif args[0] == 'بیو':
                new_bio = ' '.join(args[1:])
                await self.client(UpdateProfileRequest(about=new_bio))
                self.save_bio(new_bio)
                await event.edit(f"✅ بیو به {new_bio} تغییر کرد")
                return

        # ========== دستورات لیست ==========
        if cmd == 'لیست' and args and args[0] == 'دشمن' and len(args) == 1:
            enemies = db.get_enemies(self.user_id, 'pv')
            if enemies:
                message = "📋 لیست دشمنان:\n\n"
                for i, enemy_id in enumerate(enemies, 1):
                    try:
                        enemy = await self.client.get_entity(enemy_id)
                        enemy_name = enemy.first_name or f"کاربر {enemy_id}"
                        message += f"{i}. {enemy_name} ({enemy_id})\n"
                    except:
                        message += f"{i}. کاربر {enemy_id}\n"
                await event.edit(message)
            else:
                await event.edit("📭 لیست دشمنان خالی است")
            return
        
        if cmd == 'لیست' and args and args[0] == 'اسپم' and len(args) == 1:
            spam_messages = db.get_enemy_spam_messages(self.user_id)
            if spam_messages:
                message = "📜 لیست پیام‌های اسپم:\n\n"
                for i, spam_msg in enumerate(spam_messages, 1):
                    message += f"{i}. {spam_msg['text']}\n"
                message += f"\n📊 تعداد: {len(spam_messages)}"
                await event.edit(message)
            else:
                await event.edit("📭 لیست پیام‌های اسپم خالی است")
            return

        # ========== دستورات اسپم ==========
        if cmd == 'پاک' and args and args[0] == 'کردن' and args[1] == 'اسپم' and len(args) == 2:
            db.clear_enemy_spam_messages(self.user_id)
            await event.edit("✅ لیست اسپم پاک شد")
            return
        
        if cmd == 'اضافه' and args and args[0] == 'اسپم' and len(args) == 1:
            self.adding_spam = True
            await event.edit("📝 حالت اضافه کردن اسپم فعال شد\nبرای پایان: اتمام اسپم")
            return
        
        if cmd == 'اتمام' and args and args[0] == 'اسپم' and len(args) == 1:
            self.adding_spam = False
            await event.edit("✅ حالت اضافه کردن اسپم غیرفعال شد")
            return
        
        if cmd == 'حذف' and len(args) >= 2 and args[0] == 'اسپم' and args[1].isdigit():
            message_id = int(args[1])
            spam_messages = db.get_enemy_spam_messages(self.user_id)
            if 1 <= message_id <= len(spam_messages):
                spam_msg = spam_messages[message_id - 1]
                db.delete_enemy_spam_message(self.user_id, spam_msg['id'])
                await event.edit(f"✅ پیام شماره {message_id} حذف شد")
            else:
                await event.edit(f"⚠️ پیام شماره {message_id} وجود ندارد")
            return

        # ========== دستورات استایل متن ==========
        style_commands = {
            'بولد': 'بولد',
            'زیرخط': 'زیرخط',
            'خط خورده': 'خط خورده',
            'نقل قول': 'نقل قول',
            'اسپویلر': 'اسپویلر',
            'کج': 'کج',
            'کد': 'کد',
            'پیش': 'پیش'
        }
        
        for style_cmd, style_name in style_commands.items():
            if cmd == style_cmd and args and args[0] == 'روشن' and len(args) == 1:
                db.update_selfbot_setting(self.user_id, 'text_style', style_name)
                await event.edit(f"✅ استایل {style_cmd} فعال شد")
                return
            if cmd == style_cmd and args and args[0] == 'خاموش' and len(args) == 1:
                current = db.get_selfbot_settings(self.user_id).get('text_style')
                if current == style_name:
                    db.update_selfbot_setting(self.user_id, 'text_style', None)
                    await event.edit(f"✅ استایل {style_cmd} غیرفعال شد")
                else:
                    await event.edit(f"⚠️ استایل {style_cmd} فعال نیست")
                return

        # ========== دستورات انیمیشن ==========
        if cmd == 'قلب' and not args:
            await event.delete()
            await self.heart_animation(event.chat_id)
            return
        
        if cmd == 'ماه' and not args:
            await event.delete()
            await self.moon_animation(event.chat_id)
            return
        
        if cmd == 'قلب' and args and args[0] == 'پیشرفته' and len(args) == 1:
            await event.delete()
            try:
                msg = await self.client.send_message(event.chat_id, "❤️ شروع...")
                await advanced_heart_animation(msg)
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if cmd == 'عشق' and not args:
            await event.delete()
            try:
                msg = await event.respond("💝 شروع...")
                await advanced_heart_animation(msg)
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if cmd == 'سنتت' and not args:
            await event.delete()
            try:
                msg = await event.respond("🕯️ در حال اجرا...")
                for i in range(101):
                    bar_len = int(i / 100 * 20)
                    bar = "█" * bar_len + "░" * (20 - bar_len)
                    await msg.edit(f"🕯️ {i}% [{bar}]")
                    await asyncio.sleep(0.03)
                await asyncio.sleep(1)
                await msg.edit("✅ انجام شد 🥴")
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if cmd == 'هک' and not args:
            await event.delete()
            try:
                msg = await event.respond("🔍 در حال هک...")
                await asyncio.sleep(2)
                await msg.edit("User online: True\nTelegram access: True\nRead Storage: True")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 0%\n[░░░░░░░░░░░░░░░░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 25%\n[█████░░░░░░░░░░░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 50%\n[██████████░░░░░░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 75%\n[███████████████░░░░░]")
                await asyncio.sleep(2)
                await msg.edit("Hacking... 100%\n[████████████████████]")
                await asyncio.sleep(2)
                await msg.edit("✅ هک کامل شد")
            except Exception as e:
                logger.error(f"خطا: {e}")
            return

        # ========== دستورات اطلاعات ==========
        if cmd == 'اطلاعات' and not args:
            if event.is_reply:
                reply_message = await event.get_reply_message()
                user = await reply_message.get_sender()
            else:
                user = await self.client.get_me()
            
            username = f"@{user.username}" if user.username else "ندارد"
            name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "ندارد"
            
            try:
                full_user = await self.client(GetFullUserRequest(user.id))
                bio = full_user.full_user.about or "ندارد"
            except:
                bio = "ندارد"
            
            user_id_info = user.id
            
            try:
                photos = await self.client(GetUserPhotosRequest(user_id=user.id, offset=0, max_id=0, limit=1))
                photo_count = len(photos.photos) if photos.photos else 0
            except:
                photo_count = 0
            
            info_text = f"📋 اطلاعات کاربر:\n\n"
            info_text += f"👤 یوزرنیم: {username}\n"
            info_text += f"🆔 ID: {user_id_info}\n"
            info_text += f"📛 نام: {name}\n"
            info_text += f"📝 بیو: {bio}\n"
            info_text += f"📸 تعداد عکس: {photo_count}"
            
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user_id_info}.jpg")
                    if photo:
                        await self.client.send_file(event.chat_id, photo, caption=info_text)
                        if os.path.exists(photo):
                            os.remove(photo)
                    else:
                        await event.edit(info_text + "\n\n📸 خطا در دانلود")
                except:
                    await event.edit(info_text + "\n\n📸 خطا در دانلود")
            else:
                await event.edit(info_text + "\n\n📸 عکس پروفایل ندارد")
            await event.delete()
            return
        
        if cmd == 'دانلود' and args and args[0] == 'پروفایل' and len(args) == 1:
            if event.is_reply:
                reply_message = await event.get_reply_message()
                user = await reply_message.get_sender()
            else:
                user = await self.client.get_me()
            
            user_id_info = user.id
            user_name = user.first_name or user.username or "کاربر"
            
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user_id_info}.jpg")
                    if photo and os.path.exists(photo):
                        await self.client.send_file(event.chat_id, photo, caption=f"📸 پروفایل {user_name}")
                        os.remove(photo)
                    else:
                        await event.edit(f"⚠️ خطا در دانلود")
                except:
                    await event.edit(f"⚠️ خطا در دانلود")
            else:
                await event.edit(f"⚠️ عکس پروفایلی وجود ندارد")
            await event.delete()
            return

        # ========== دستورات ست پروفایل ==========
        if cmd == 'ست' and args:
            if args[0] == 'پروف' and len(args) == 1:
                if event.is_reply:
                    reply_message = await event.get_reply_message()
                    user = await reply_message.get_sender()
                    if user.photo:
                        try:
                            photo_path = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user.id}.jpg")
                            if photo_path and os.path.exists(photo_path):
                                me = await self.client.get_me()
                                if me.photo:
                                    photos = await self.client.get_profile_photos(me.id, limit=1)
                                    if photos:
                                        await self.client(DeletePhotosRequest(id=[photos[0]]))
                                file = await self.client.upload_file(photo_path)
                                await self.client(UploadProfilePhotoRequest(file=file))
                                await event.edit("✅ عکس پروفایل ست شد")
                                os.remove(photo_path)
                            else:
                                await event.edit("⚠️ خطا در دانلود")
                        except FloodWaitError as e:
                            await event.edit(f"⚠️ {e.seconds} ثانیه صبر کنید")
                        except Exception as e:
                            await event.edit("⚠️ خطا")
                    else:
                        await event.edit("⚠️ این کاربر عکس پروفایل ندارد")
                else:
                    await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
                await event.delete()
                return
            
            elif args[0] == 'بیو' and len(args) == 1:
                if event.is_reply:
                    reply_message = await event.get_reply_message()
                    user = await reply_message.get_sender()
                    try:
                        full_user = await self.client(GetFullUserRequest(user.id))
                        bio = full_user.full_user.about or ""
                        await self.client(UpdateProfileRequest(about=bio))
                        self.save_bio(bio)
                        await event.edit("✅ بیو ست شد")
                    except Exception as e:
                        await event.edit("⚠️ خطا")
                else:
                    await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
                await event.delete()
                return

        # ========== دستورات حذف ست ==========
        if len(args) >= 2 and cmd == 'حذف':
            if args[0] == 'ست' and args[1] == 'پروف' and len(args) == 2:
                me = await self.client.get_me()
                if me.photo:
                    try:
                        photos = await self.client.get_profile_photos(me.id, limit=1)
                        if photos:
                            await self.client(DeletePhotosRequest(id=[photos[0]]))
                        await event.edit("✅ عکس پروفایل حذف شد")
                    except FloodWaitError as e:
                        await event.edit(f"⚠️ {e.seconds} ثانیه صبر کنید")
                    except Exception as e:
                        await event.edit("⚠️ خطا")
                else:
                    await event.edit("⚠️ عکس پروفایلی وجود ندارد")
                return
            
            elif args[0] == 'ست' and args[1] == 'بیو' and len(args) == 2:
                try:
                    await self.client(UpdateProfileRequest(about=""))
                    self.save_bio("")
                    await event.edit("✅ بیو خالی شد")
                except Exception as e:
                    await event.edit("⚠️ خطا")
                return

        # ========== دستورات اکشن ==========
        if cmd == 'اکشن' and args:
            action_name = ' '.join(args)
            if action_name == 'خاموش' and len(args) == 1:
                if chat_id in self.active_actions:
                    action_name_stop = await self.stop_action(chat_id)
                    await event.edit(f'✅ اکشن {action_name_stop} خاموش شد')
                else:
                    await event.edit('❌ هیچ اکشن فعالی در این چت وجود ندارد')
                return
            elif action_name == 'لیست' and len(args) == 1:
                if self.active_actions:
                    active_list = "🎭 اکشن‌های فعال:\n\n"
                    for cid, action in self.active_actions.items():
                        try:
                            chat_obj = await self.client.get_entity(cid)
                            chat_name = chat_obj.first_name if hasattr(chat_obj, 'first_name') else chat_obj.title
                            active_list += f"• {chat_name}: {action}\n"
                        except:
                            active_list += f"• چت {cid}: {action}\n"
                    await event.edit(active_list)
                else:
                    await event.edit('❌ هیچ اکشن فعالی وجود ندارد')
                return
            elif action_name in action_types:
                if chat_id in self.active_actions:
                    old_action = self.active_actions[chat_id]
                    await self.stop_action(chat_id)
                    await event.edit(f'⏹️ اکشن قبلی {old_action} خاموش شد\n✅ اکشن جدید {action_name} فعال شد')
                else:
                    await event.edit(f'✅ اکشن {action_name} فعال شد')
                await self.start_action(chat_id, action_name)
                await asyncio.sleep(3)
                await event.delete()
                return
            else:
                available = "\n".join([f"• {name}" for name in action_types.keys()])
                await event.edit(f'❌ اکشن "{action_name}" پشتیبانی نمی‌شود\n\n✅ اکشن‌های موجود:\n{available}')
                return

        # ========== دستورات سرچ ==========
        if cmd == 'سرچ' and not args:
            self.search_mode = True
            await event.edit('🔍 حالت سرچ فعال شد.\n\nاکنون هر متنی که ارسال کنید در گوگل جستجو می‌شود.\nبرای خروج از حالت سرچ، دستور خروج سرچ را ارسال کنید.')
            return
        
        if cmd == 'خروج' and args and args[0] == 'سرچ' and len(args) == 1:
            self.search_mode = False
            self.last_search_results = []
            await event.edit('✅ حالت سرچ غیرفعال شد.')
            return

        # ========== دستورات اهنگ ==========
        if cmd == '.اهنگ' and args:
            song_name = ' '.join(args)
            await event.edit(f"🎵 در حال جستجوی آهنگ: {song_name}...")
            try:
                bot_username = MUSIC_BOT.replace('@', '')
                results = await self.client.inline_query(bot_username, song_name)
                if results and len(results) > 0:
                    await results[0].click(chat_id)
                    await event.delete()
                    logger.info(f"✅ آهنگ {song_name} ارسال شد")
                else:
                    await event.edit(f"❌ آهنگی با نام '{song_name}' پیدا نشد")
            except Exception as e:
                await event.edit(f"❌ خطا در ارسال آهنگ: {str(e)[:100]}")
            return

        # ========== دستورات پنل ==========
        if cmd in ['.پنل', 'پنل', '/panel'] and not args:
            try:
                bot_username = BOT_USERNAME.replace('@', '')
                results = await self.client.inline_query(bot_username, '')
                if results and len(results) > 0:
                    await results[0].click(chat_id)
                    await event.delete()
                else:
                    await event.edit("❌ پنل یافت نشد. لطفاً مطمئن شوید ربات فعال است.")
            except Exception as e:
                await event.edit(f"❌ خطا در باز کردن پنل: {str(e)[:100]}")
            return

        # ========== دستورات امار گپ ==========
        if cmd == 'امار' and args and args[0] == 'گپ' and len(args) == 1:
            await event.delete()
            target_user_id = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user_id = reply_msg.sender_id
            
            if not target_user_id and isinstance(event.message.peer_id, PeerUser):
                target_user_id = event.message.peer_id.user_id
            
            if not target_user_id:
                await event.respond("⚠️ لطفاً روی پیام کاربر ریپلای کنید یا در پی‌وی از این دستور استفاده کنید")
                return
            
            stats = await self.get_chat_stats(chat_id, target_user_id)
            if not stats:
                await event.respond("⚠️ خطا در دریافت آمار")
                return
            
            try:
                target_name = await self.get_user_info(target_user_id)
                my_name = await self.get_user_info(self.my_id)
                
                total_my = stats['my_messages']
                total_target = stats['target_messages']
                
                if total_my > total_target:
                    winner = my_name
                elif total_target > total_my:
                    winner = target_name
                else:
                    winner = "مساوی"
                
                if total_target > 0:
                    ratio = f"{total_my} به {total_target}"
                else:
                    ratio = f"{total_my} به 0"
                
                stats_text = f"""
ꕀꔚꨄꕣꕥ✺ღდ
📊 آمار گفتگو
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
نوع                {my_name[:10]}        {target_name[:10]}
────────────────────────────────────
💬 پیام            {total_my:>5}        {total_target:>5}
📸 عکس             {stats['my_photos']:>5}        {stats['target_photos']:>5}
🎙️ ویس             {stats['my_voices']:>5}        {stats['target_voices']:>5}
🎬 ویدیو           {stats['my_videos']:>5}        {stats['target_videos']:>5}
🎨 استیکر          {stats['my_stickers']:>5}        {stats['target_stickers']:>5}
🎞️ گیف             {stats['my_gifs']:>5}        {stats['target_gifs']:>5}
📁 فایل            {stats['my_files']:>5}        {stats['target_files']:>5}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 بیشترین پیام: {winner}
📈 نسبت: {ratio}
ꕀꔚꨄꕣꕥ✺ღდ
                """
                await self.client.send_message(chat_id, stats_text)
            except Exception as e:
                await event.respond(f"⚠️ خطا: {str(e)[:100]}")
            return

        # ========== دستورات کد QR ==========
        if cmd == '.کد' and not args:
            await event.delete()
            try:
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    if reply_msg.text:
                        qr_path, text = await self.generate_qr_code(reply_msg.text)
                    elif reply_msg.photo:
                        qr_path, text = await self.generate_qr_code(reply_msg.media, is_photo=True)
                    else:
                        await event.respond("⚠️ لطفاً روی یک پیام متنی یا عکس ریپلای کنید")
                        return
                else:
                    qr_text = command_text.replace('.کد', '').strip()
                    if qr_text:
                        qr_path, text = await self.generate_qr_code(qr_text)
                    else:
                        await event.respond("⚠️ لطفاً متن یا عکس را مشخص کنید")
                        return
                
                if qr_path and os.path.exists(qr_path):
                    await self.client.send_file(
                        chat_id,
                        qr_path,
                        caption=f"🝰 کد QR\n📝 متن: {text[:100]}{'...' if len(text) > 100 else ''}"
                    )
                    os.remove(qr_path)
                else:
                    await event.respond(f"⚠️ خطا در تولید کد QR: {text}")
            except Exception as e:
                await event.respond(f"⚠️ خطا: {str(e)[:100]}")
            return

        # ========== دستورات تگ ادمین و پین ==========
        if cmd == 'تگ' and args and args[0] == 'ادمین' and len(args) == 1:
            if not isinstance(event.message.peer_id, (PeerChannel, PeerChat)):
                await event.edit("⚠️ این دستور فقط در گروه کار می‌کند")
                return
            
            admins = await self.get_admins(chat_id)
            if admins:
                admin_text = "👑 ادمین‌های گروه:\n\n"
                for admin in admins:
                    mention = f"@{admin.username}" if admin.username else f"[{admin.first_name or 'ادمین'}](tg://user?id={admin.id})"
                    admin_text += f"• {mention}\n"
                
                await event.edit(admin_text, parse_mode='markdown')
            else:
                await event.edit("⚠️ ادمینی یافت نشد")
            return
        
        if cmd == 'پین' and not args:
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if await self.pin_message(chat_id, reply_msg.id):
                    await event.edit("📌 پیام پین شد")
                else:
                    await event.edit("⚠️ خطا در پین کردن پیام")
            else:
                await event.edit("⚠️ روی پیام مورد نظر ریپلای کنید")
            return

        # ========== دستورات حذف پیام ==========
        if cmd == 'حذف' and args and args[0] == 'کامل' and len(args) == 1:
            await event.delete()
            messages = []
            async for msg in self.client.iter_messages(event.chat_id, limit=None):
                if msg.sender_id == self.my_id:
                    messages.append(msg.id)
            if messages:
                try:
                    await self.client.delete_messages(event.chat_id, messages)
                    report_msg = await self.client.send_message(event.chat_id, f"✅ {len(messages)} پیام حذف شدند")
                    await asyncio.sleep(2)
                    await report_msg.delete()
                except Exception as e:
                    await self.client.send_message(event.chat_id, f"⚠️ خطا: {str(e)[:100]}")
            else:
                await self.client.send_message(event.chat_id, "⚠️ هیچ پیامی یافت نشد")
            return
        
        if cmd == 'حذف' and args and args[0].isdigit() and len(args) == 1:
            num = int(args[0])
            await event.delete()
            messages = []
            async for msg in self.client.iter_messages(event.chat_id, limit=num):
                if msg.sender_id == self.my_id:
                    messages.append(msg.id)
            if messages:
                try:
                    await self.client.delete_messages(event.chat_id, messages)
                    report_msg = await self.client.send_message(event.chat_id, f"✅ {len(messages)} پیام حذف شدند")
                    await asyncio.sleep(2)
                    await report_msg.delete()
                except Exception as e:
                    await self.client.send_message(event.chat_id, f"⚠️ خطا: {str(e)[:100]}")
            else:
                await self.client.send_message(event.chat_id, "⚠️ هیچ پیامی یافت نشد")
            return

        # ========== دستورات تنظیم اسپم ==========
        if cmd == 'تنظیم' and args and args[0] == 'اسپم' and len(args) == 3:
            try:
                limit = int(args[1])
                duration = int(args[2])
                if limit > 0 and duration > 0:
                    db.set_spam_settings(self.user_id, spam_limit=limit, mute_duration=duration)
                    await event.edit(f"✅ تنظیمات اسپم بروزرسانی شد\n📊 محدودیت: {limit} پیام\n⏱️ مدت زمان: {duration} ثانیه")
                else:
                    await event.edit("❌ تعداد و زمان باید مثبت باشند")
            except:
                await event.edit("❌ فرمت نامعتبر\nمثال: تنظیم اسپم 5 10")
            return

        # ========== دستورات اسپم ==========
        if cmd == 'اسپم' and args:
            sub_cmd = args[0]
            
            if sub_cmd == 'روشن' and len(args) == 1:
                db.set_spam_settings(self.user_id, spam_protection=1)
                await event.edit("✅ حفاظت اسپم فعال شد")
                return
            
            if sub_cmd == 'خاموش' and len(args) == 1:
                db.set_spam_settings(self.user_id, spam_protection=0)
                await event.edit("✅ حفاظت اسپم غیرفعال شد")
                return
            
            if sub_cmd == 'وضعیت' and len(args) == 1:
                spam_settings = db.get_spam_settings(self.user_id)
                status_text = f"""
🛡️ **حفاظت اسپم:**
🔒 وضعیت: {'✅ فعال' if spam_settings.get('spam_protection') else '❌ غیرفعال'}
📊 محدودیت: {spam_settings.get('spam_limit', 10)} پیام
⏱️ مدت زمان: {spam_settings.get('mute_duration', 10)} ثانیه
                """
                await event.edit(status_text)
                return
            
            if args[0].isdigit() and len(args) >= 2:
                try:
                    num = int(args[0])
                    message_text = ' '.join(args[1:])
                    await event.delete()
                    for _ in range(num):
                        await self.client.send_message(event.chat_id, message_text)
                        await asyncio.sleep(0.05)
                    report_msg = await self.client.send_message(event.chat_id, f"✅ {num} پیام اسپم ارسال شد")
                    await asyncio.sleep(2)
                    await report_msg.delete()
                except:
                    await event.edit("❌ فرمت نامعتبر\nمثال: اسپم 5 سلام")
                return

        # ========== دستورات تایم فونت ==========
        if cmd == 'فونت' and args:
            font_arg = args[0]
            try:
                if font_arg.isdigit():
                    idx = int(font_arg)
                    if 0 <= idx < len(classic_fonts):
                        # اضافه کردن فونت به لیست انتخاب‌ها
                        if idx not in self.selected_fonts:
                            self.selected_fonts.append(idx)
                        else:
                            self.selected_fonts.remove(idx)
                        self.save_state()
                        await event.edit(f"✅ فونت {classic_fonts[idx]} {'افزوده شد' if idx in self.selected_fonts else 'حذف شد'}")
                    else:
                        await event.edit(f"❌ فونت {idx} وجود ندارد (۰ تا {len(classic_fonts)-1})")
                elif font_arg == 'همه':
                    self.selected_fonts = list(range(len(classic_fonts)))
                    self.save_state()
                    await event.edit("✅ همه فونت‌ها انتخاب شدند")
                elif font_arg == 'پاک':
                    self.selected_fonts = []
                    self.save_state()
                    await event.edit("✅ لیست فونت‌ها پاک شد")
                else:
                    await event.edit("❌ فرمت نامعتبر\nمثال: فونت 5 یا فونت همه یا فونت پاک")
            except:
                await event.edit("❌ خطا در تنظیم فونت")
            return

        # ========== دستورات تقویم ==========
        if cmd == 'تقویم' and not args:
            await self.handle_calendar_command(event)
            return

        # ========== دستورات وضعیت و درباره ==========
        if cmd == 'وضعیت' and not args:
            settings = db.get_selfbot_settings(self.user_id)
            await event.edit(self.format_status_info(settings))
            return
        
        if cmd == 'درباره' and not args:
            await event.edit(f"ℹ️ درباره بات\n\n🤖 نسخه: v{BOT_VERSION}\n👨‍💻 سازنده: {BOT_CREATOR}")
            return
        
        if cmd == 'پینگ' and not args:
            start = time.time()
            await event.edit("🏓 پینگ: ...")
            end = time.time()
            ping = round((end - start) * 1000, 2)
            await event.edit(f"🏓 پینگ: {ping} ms")
            return

        # ========== دستورات سلف روشن/خاموش ==========
        if cmd == 'سلف' and args and args[0] in ['روشن', 'خاموش']:
            if args[0] == 'روشن':
                db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 1)
                await event.edit("✅ سلف‌بات فعال شد")
            else:
                db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 0)
                await event.edit("✅ سلف‌بات غیرفعال شد")
            return

        # ========== دستورات استیکر متن ==========
        if cmd == 'استیکر' and args and args[0] == 'متن':
            text = ' '.join(args[1:])
            try:
                img = Image.new('RGBA', (512, 512), (255, 255, 255, 0))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("font.ttf", 50)
                except:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                x = (512 - text_width) // 2
                y = (512 - text_height) // 2
                draw.text((x, y), text, fill=(0, 0, 0, 255), font=font)
                output = BytesIO()
                img.save(output, format='WEBP')
                output.seek(0)
                await self.client.send_file(chat_id, output)
                await event.delete()
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== دستورات اسکرین‌شات ==========
        if cmd == 'اسکرین‌شات':
            try:
                await self.client.send(
                    types.SendScreenshotNotification(
                        peer=await self.client.resolve_peer(chat_id),
                        reply_to_msg_id=0,
                        random_id=self.client.rnd_id(),
                    )
                )
                await event.edit("✅ اسکرین‌شات شبیه‌سازی شد")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== دستورات تشخیص متن (OCR) ==========
        if cmd == 'تشخیص' and args and args[0] == 'متن':
            if not event.is_reply:
                await event.edit("❌ لطفاً به یک عکس ریپلای کن")
                return
            await event.edit("⏳ در حال تشخیص متن...")
            try:
                try:
                    await self.client(UnblockRequest(id="oneGooglebot"))
                except:
                    pass
                reply_msg = await event.get_reply_message()
                if reply_msg.photo:
                    await self.client.send_file("oneGooglebot", reply_msg.photo)
                    await asyncio.sleep(6)
                    async for msg in self.client.get_chat_history("oneGooglebot", limit=2):
                        if msg.text and "OCR detected" in msg.text:
                            text = msg.text.replace("💭 OCR detected:", "").strip()
                            await event.edit(f"📝 **متن تشخیص داده شده:**\n\n{text}")
                            return
                    await event.edit("❌ تشخیص متن انجام نشد")
                else:
                    await event.edit("❌ پیام ریپلای شده عکس نیست")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== دستورات تاریخ ساخت اکانت ==========
        if cmd == 'تاریخ' and args and args[0] == 'ساخت' and len(args) == 2 and args[1] == 'اکانت':
            try:
                try:
                    await self.client(UnblockRequest(id="creationdatebot"))
                except:
                    pass
                await self.client.send_message("creationdatebot", "/start")
                await asyncio.sleep(3)
                async for msg in self.client.get_chat_history("creationdatebot", limit=1):
                    if msg.from_user and msg.from_user.username == "creationdatebot":
                        await event.edit(f"📅 **تاریخ ساخت اکانت:**\n{msg.text}")
                        break
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== دستورات نشست‌های فعال ==========
        if cmd == 'نشست‌های' and args and args[0] == 'فعال':
            try:
                sessions = await self.client(GetAuthorizationsRequest())
                text = "📱 **نشست‌های فعال:**\n\n"
                for i, session in enumerate(sessions.authorizations, 1):
                    text += f"**{i}.** {session.device_model}\n"
                    text += f"   📍 {session.country} ({session.ip})\n"
                    text += f"   📅 {datetime.fromtimestamp(session.date_active).strftime('%Y/%m/%d %H:%M')}\n"
                    text += f"   📱 {session.platform}\n\n"
                await event.edit(text)
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== دستورات اطلاعات سیستم ==========
        if cmd == 'اطلاعات' and args and args[0] == 'سیستم':
            try:
                svmem = psutil.virtual_memory()
                cpufreq = psutil.cpu_freq()
                def sizeof_fmt(num):
                    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                        if abs(num) < 1024.0:
                            return f"{num:.1f} {unit}"
                        num /= 1024.0
                    return f"{num:.1f} PB"
                text = "🖥️ **اطلاعات سیستم:**\n\n"
                text += f"💻 سیستم: {uname().system}\n"
                text += f"🐍 پایتون: {python_version()}\n"
                text += f"🧠 RAM: {sizeof_fmt(svmem.used)}/{sizeof_fmt(svmem.total)} ({svmem.percent}%)\n"
                text += f"⚡ CPU: {psutil.cpu_percent()}%\n"
                text += f"🔄 هسته‌ها: {psutil.cpu_count()}\n"
                text += f"📶 فرکانس: {cpufreq.current:.0f}MHz"
                await event.edit(text)
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return

        # ========== دستورات منشی ==========
        if cmd == 'منشی' and args:
            if args[0] == 'خاموش':
                db.set_monshi_status(self.user_id, False)
                self.monshi_mode = False
                await event.edit("❌ منشی غیرفعال شد")
                return
            else:
                answer = ' '.join(args)
                db.set_monshi_status(self.user_id, True, answer)
                self.monshi_mode = True
                self.monshi_answer = answer
                await event.edit(f"✅ منشی فعال شد:\n{answer}")
                return

        # ========== دستورات پاسخ‌ها ==========
        if cmd == 'افزودن' and args and args[0] == 'پاسخ':
            text = ' '.join(args[1:])
            if ':' in text:
                question, answer = text.split(':', 1)
                db.add_answer(self.user_id, question.strip(), answer.strip())
                await event.edit(f"✅ پاسخ اضافه شد:\nسوال: {question}\nجواب: {answer}")
            else:
                await event.edit("❌ فرمت: افزودن پاسخ سوال:جواب")
            return
        
        if cmd == 'حذف' and args and args[0] == 'پاسخ':
            question = ' '.join(args[1:])
            db.remove_answer(self.user_id, question)
            await event.edit(f"✅ پاسخ '{question}' حذف شد")
            return
        
        if cmd == 'لیست' and args and args[0] == 'پاسخ':
            answers = db.get_answers(self.user_id)
            if answers:
                text = "📋 لیست پاسخ‌ها:\n\n"
                for i, (q, a) in enumerate(answers.items(), 1):
                    text += f"{i}. ❓ {q}\n   💬 {a}\n\n"
                await event.edit(text)
            else:
                await event.edit("❌ هیچ پاسخی ذخیره نشده")
            return
        
        if cmd == 'پاک' and args and args[0] == 'کردن' and len(args) > 1 and args[1] == 'پاسخ‌ها':
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bot_answers WHERE user_id = ?', (self.user_id,))
            conn.commit()
            conn.close()
            await event.edit("✅ همه پاسخ‌ها پاک شدند")
            return

        # ========== دستورات تگ همه ==========
        if cmd == 'تگ' and args and args[0] == 'همه':
            chat_id = event.chat_id
            if chat_id in self.mentioning_groups:
                await event.edit("⏳ در حال تگ کردن هستیم...")
                return
            
            self.mentioning_groups.add(chat_id)
            await event.delete()
            
            text = ' '.join(args[1:]) if len(args) > 1 else ""
            count = 0
            mention_text = ""
            total_users = 0
            
            try:
                async for _ in self.client.iter_participants(chat_id):
                    total_users += 1
                
                async for user in self.client.iter_participants(chat_id):
                    if chat_id not in self.mentioning_groups:
                        break
                    if user.id == self.my_id:
                        continue
                    
                    count += 1
                    name = user.first_name or "کاربر"
                    mention_text += f"[{name}](tg://user?id={user.id}) ✧ "
                    
                    if count % 13 == 0:
                        msg = f"{text}\n\n{mention_text}" if text else mention_text
                        await self.client.send_message(chat_id, msg)
                        await asyncio.sleep(1.5)
                        mention_text = ""
                
                if mention_text:
                    msg = f"{text}\n\n{mention_text}" if text else mention_text
                    await self.client.send_message(chat_id, msg)
                
            except Exception as e:
                logger.error(f"خطا در تگ همه: {e}")
            finally:
                self.mentioning_groups.discard(chat_id)
            return
        
        if cmd == 'لغو' and args and args[0] == 'تگ':
            if chat_id in self.mentioning_groups:
                self.mentioning_groups.discard(chat_id)
                await event.edit("✅ تگ کردن لغو شد")
            else:
                await event.edit("❌ هیچ تگی در این گروه فعال نیست")
            return

        # ========== دستورات بازی‌ها ==========
        if cmd == 'بولینگ':
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("🎳"))
                if msg.media.value == 6:
                    await self.client.send_message(chat_id, "🎉 **بولینگ! ۶ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        if cmd == 'تاس' and args and args[0].isdigit():
            target = int(args[0])
            if 1 <= target <= 6:
                await event.delete()
                while True:
                    msg = await self.client.send_message(chat_id, file=InputMediaDice("🎲"))
                    if msg.media.value == target:
                        await self.client.send_message(chat_id, f"🎉 **{target} آمد! بردی!**")
                        break
                    await asyncio.sleep(1)
            else:
                await event.edit("❌ عدد بین ۱ تا ۶ وارد کن")
            return
        
        if cmd == 'سه' and args and args[0] == 'رنگ':
            colors = ['🔴', '🟢', '🔵']
            seed = self.user_id
            random.seed(seed)
            user_choice = random.choice(colors)
            random.seed(seed + 100)
            system_choice = random.choice(colors)
            text = f"🎨 **بازی سه رنگ**\n\nرنگ شما: {user_choice}\nرنگ سیستم: {system_choice}\n\n"
            text += "🎉 **برنده شدی!**" if user_choice == system_choice else "😢 **باختی!**"
            await event.edit(text)
            return
        
        if cmd == 'شانس' and args and args[0].isdigit():
            chance = int(args[0])
            if chance > 100:
                await event.edit("❌ شانس نباید بیشتر از ۱۰۰ باشه")
                return
            colors = ['🔴', '🟢', '🔵']
            choice = random.choice(colors)
            result = "🎉 **برنده شدی!**" if random.randint(1, 100) <= chance else "😢 **باختی!**"
            await event.edit(f"🎨 **رنگ: {choice}**\n{result} (شانس: {chance}%)")
            return
        
        if cmd == 'دارت' and not args:
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("🎯"))
                if msg.media.value == 6:
                    await self.client.send_message(chat_id, "🎯 **دارت! ۶ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        if cmd == 'بسکتبال' and not args:
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("🏀"))
                if msg.media.value == 5:
                    await self.client.send_message(chat_id, "🏀 **بسکتبال! ۵ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return
        
        if cmd == 'فوتبال' and not args:
            await event.delete()
            while True:
                msg = await self.client.send_message(chat_id, file=InputMediaDice("⚽️"))
                if msg.media.value == 5:
                    await self.client.send_message(chat_id, "⚽️ **فوتبال! ۵ گرفتی!**")
                    break
                await asyncio.sleep(1)
            return

        # ========== دستورات فال ==========
        if cmd == 'فال' and not args:
            await self.fortune_telling(chat_id, event)
            return
        
        if cmd == 'فال' and args and args[0] == 'حافظ' and len(args) == 1:
            await self.hafez_fortune(chat_id, event)
            return
        
        if cmd == 'فال' and args and args[0] == 'قهوه' and len(args) == 1:
            await self.coffee_fortune(chat_id, event)
            return

        # ========== دستورات اتوسین ==========
        if cmd == 'اتوسین' and args and args[0] in ['فعال', 'غیرفعال'] and len(args) == 1:
            if args[0] == 'فعال':
                self.autosend_mode = True
                db.update_selfbot_setting(self.user_id, 'autosend_mode', 1)
                self.save_state()
                await event.edit("✅ اتوسین فعال شد")
            else:
                self.autosend_mode = False
                db.update_selfbot_setting(self.user_id, 'autosend_mode', 0)
                self.save_state()
                await event.edit("✅ اتوسین غیرفعال شد")
            return

        # ========== دستورات فیلتر ==========
        if cmd == 'فیلتر' and args:
            if args[0] == 'روشن' and len(args) == 1:
                db.set_filter_enabled(self.user_id, True)
                await event.edit("✅ فیلتر کلمات فعال شد")
                return
            elif args[0] == 'خاموش' and len(args) == 1:
                db.set_filter_enabled(self.user_id, False)
                await event.edit("✅ فیلتر کلمات غیرفعال شد")
                return
            elif args[0] == 'لیست' and len(args) == 1:
                filters = db.get_filter_words(self.user_id)
                if filters:
                    message_text = "📜 لیست کلمات فیلتر شده:\n\n"
                    for i, word_info in enumerate(filters, 1):
                        status = "فعال" if word_info['enabled'] else "غیرفعال"
                        message_text += f"{i}. {word_info['word']} - {status}\n"
                    await event.edit(message_text)
                else:
                    await event.edit("📭 لیست کلمات فیلتر خالی است")
                return
            elif args[0] == 'حذف' and len(args) >= 2:
                word = ' '.join(args[1:])
                if word:
                    db.remove_filter_word(self.user_id, word)
                    await event.edit(f"✅ کلمه {word} از لیست فیلتر حذف شد")
                else:
                    await event.edit("❌ لطفاً یک کلمه وارد کنید")
                return
        
        if cmd == '.فیلتر' and args:
            word = ' '.join(args)
            if word:
                db.add_filter_word(self.user_id, word)
                await event.edit(f"✅ کلمه {word} به لیست فیلتر اضافه شد")
            else:
                await event.edit("❌ لطفاً یک کلمه وارد کنید")
            return
        
        # ========== دستورات تنظیم گزارش ==========
        if cmd == 'تنظیم' and args and args[0] == 'گزارش' and len(args) == 1:
            if isinstance(event.message.peer_id, (PeerChannel, PeerChat)):
                group_id = event.message.peer_id.channel_id if isinstance(event.message.peer_id, PeerChannel) else event.message.peer_id.chat_id
                self.report_config.set_report_group(group_id)
                await event.edit(f"✅ گروه گزارش تنظیم شد\nآیدی: {group_id}")
            else:
                await event.edit("⚠️ این دستور فقط در گروه کار می‌کند")
            return
        
        if cmd == 'گروه' and args and args[0] == 'گزارش' and len(args) == 1:
            await event.edit(f"📍 گروه گزارش فعلی:\nآیدی: {self.report_config.report_group_id}")
            return

        # ========== دستورات کامنت ==========
        if cmd == 'کامنت' and args:
            comment_text = ' '.join(args)
            chat = await event.get_chat()
            chat_type = "کانال" if hasattr(chat, 'broadcast') and chat.broadcast else "گروه"
            db.set_auto_comment(
                self.user_id,
                chat.id,
                comment_text,
                chat.title,
                chat_type,
                getattr(chat, 'username', None)
            )
            result = self.set_auto_comment(
                chat.id,
                comment_text,
                chat.title,
                chat_type,
                getattr(chat, 'username', None)
            )
            await event.edit(f"✅ {result}")
            return
        
        if cmd == 'کانال‌ها' and not args:
            auto_comments = db.get_auto_comments(self.user_id)
            if auto_comments:
                msg = "📊 کانال‌های تنظیم شده:\n\n"
                for comment in auto_comments:
                    msg += f"• {comment['channel_title']} ({comment['channel_type']})\n"
                    msg += f"  آیدی: {comment['channel_id']}\n"
                    msg += f"  متن: {comment['comment_text'][:30]}...\n\n"
                await event.edit(msg)
            else:
                await event.edit("📭 هیچ کانالی تنظیم نشده")
            return
        
        if cmd == 'حذف' and args and args[0] == 'کانال' and len(args) == 1:
            chat = await event.get_chat()
            channel_id = chat.id
            auto_comment = db.get_auto_comment(self.user_id, channel_id)
            if auto_comment:
                db.remove_auto_comment(self.user_id, channel_id)
                self.remove_auto_comment(channel_id)
                await event.edit(f"✅ تنظیمات {auto_comment['channel_title']} حذف شد")
            else:
                await event.edit("⚠️ این کانال تنظیم نشده است")
            return
        
        if cmd == 'تست' and args and args[0] == 'کانال' and len(args) == 1:
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                chat = await reply_msg.get_chat()
            else:
                chat = await event.get_chat()
            
            info = f"🔍 اطلاعات تست:\n\n"
            info += f"چت: {chat.title}\n"
            info += f"نوع: {'کانال' if hasattr(chat, 'broadcast') and chat.broadcast else 'گروه'}\n"
            info += f"آیدی: {chat.id}\n"
            auto_comment = db.get_auto_comment(self.user_id, chat.id)
            info += f"تنظیم شده: {'✅' if auto_comment else '❌'}\n"
            if auto_comment:
                info += f"متن: {auto_comment['comment_text'][:50]}...\n"
            await event.edit(info)
            return

        # ========== دستورات من کی ام ==========
        if cmd == 'من' and args and args[0] == 'کی' and args[1] == 'ام' and len(args) == 2:
            if isinstance(event.message.peer_id, PeerUser):
                user_id_info = event.sender_id
                user_name = db.get_user_name(user_id_info)
                user_info = db.get_user_info(user_id_info)
                
                info_text = f"👤 اطلاعات شما:\n"
                info_text += f"• نام: {user_name}\n"
                info_text += f"• آی‌دی: {user_id_info}\n"
                
                if user_info:
                    info_text += f"\n📝 اطلاعات ذخیره شده:\n"
                    for key, value in user_info.items():
                        info_text += f"• {key}: {value}\n"
                else:
                    info_text += f"\nℹ️ اطلاعات اضافی ذخیره نشده\n"
                
                await event.edit(info_text)
            return

        # ========== دستورات شروع ==========
        if cmd == 'شروع' and not args:
            await event.delete()
            try:
                await event.respond("🌟 سلف‌بات شروع شد")
            except:
                pass
            return
        
        return

    # ======================================================
    # متدهای دیگر SelfBotManager
    # ======================================================
    async def fortune_telling(self, chat_id, event=None):
        fortune = random.choice(fortunes)
        emoji = random.choice(['🌟', '💫', '🌙', '🌸', '💰', '🎯', '🌈', '💪', '🎉', '💖'])
        
        text = f"""
{emoji} **فال امروز تو** {emoji}
━━━━━━━━━━━━━━━━━━━━

{fortune}

━━━━━━━━━━━━━━━━━━━━
💫 باور داشته باش که بهترین‌ها در راهند!
        """
        
        if event:
            await event.edit(text, parse_mode='markdown')
        else:
            await self.client.send_message(chat_id, text)
    
    async def hafez_fortune(self, chat_id, event=None):
        text, emoji = random.choice(hafez_fortunes)
        
        msg = f"""
🕌 **فال حافظ** 🕌
━━━━━━━━━━━━━━━━━━━━

{emoji} {text}

━━━━━━━━━━━━━━━━━━━━
"زین قفس چون برفتم، آزادم" 🕊️
        """
        
        if event:
            await event.edit(msg, parse_mode='markdown')
        else:
            await self.client.send_message(chat_id, msg)
    
    async def coffee_fortune(self, chat_id, event=None):
        fortune = random.choice(coffee_fortunes)
        
        msg = f"""
☕ **فال قهوه** ☕
━━━━━━━━━━━━━━━━━━━━

{fortune}

━━━━━━━━━━━━━━━━━━━━
☕ قهوه‌ات را بنوش و به فردا امیدوار باش!
        """
        
        if event:
            await event.edit(msg, parse_mode='markdown')
        else:
            await self.client.send_message(chat_id, msg)
    
    async def heart_animation(self, chat_id):
        try:
            message = await self.client.send_message(chat_id, HEARTS[0])
            for i in range(1, len(HEARTS) * 99999):
                await asyncio.sleep(4)
                await self.client.edit_message(chat_id, message, HEARTS[i % len(HEARTS)])
            settings = db.get_selfbot_settings(self.user_id)
            if chat_id != abs(self.report_config.report_group_id):
                await self.client.delete_messages(chat_id, message)
        except:
            pass
    
    async def moon_animation(self, chat_id):
        try:
            message = await self.client.send_message(chat_id, MOONS[0])
            for i in range(1, len(MOONS) * 1):
                await asyncio.sleep(3)
                await self.client.edit_message(chat_id, message, MOONS[i % len(MOONS)])
            settings = db.get_selfbot_settings(self.user_id)
            if chat_id != abs(self.report_config.report_group_id):
                await self.client.delete_messages(chat_id, message)
        except:
            pass
    
    async def spam_enemy(self, enemy_id):
        if enemy_id in self.spam_tasks:
            return
        async def spam_task():
            while db.is_enemy(self.user_id, enemy_id, 'pv'):
                spam_messages = db.get_enemy_spam_messages(self.user_id)
                if spam_messages:
                    for spam_message in spam_messages:
                        try:
                            settings = db.get_selfbot_settings(self.user_id)
                            text, entities = await apply_text_style(spam_message['text'], settings.get('text_style'))
                            await self.client.send_message(enemy_id, text, formatting_entities=entities)
                        except:
                            pass
                        await asyncio.sleep(1)
                else:
                    for spam_message in SPAM_MESSAGES:
                        try:
                            settings = db.get_selfbot_settings(self.user_id)
                            text, entities = await apply_text_style(spam_message, settings.get('text_style'))
                            await self.client.send_message(enemy_id, text, formatting_entities=entities)
                        except:
                            pass
                        await asyncio.sleep(1)
        self.spam_tasks[enemy_id] = asyncio.create_task(spam_task())
    
    async def start_action(self, chat_id, action_name):
        if action_name in action_types:
            action = action_types[action_name]
            if chat_id in self.action_tasks:
                self.action_tasks[chat_id].cancel()
            self.active_actions[chat_id] = action_name
            async def permanent_action():
                try:
                    while True:
                        await self.client(SetTypingRequest(chat_id, action))
                        await asyncio.sleep(5)
                except:
                    pass
                finally:
                    if chat_id in self.active_actions:
                        del self.active_actions[chat_id]
                    if chat_id in self.action_tasks:
                        del self.action_tasks[chat_id]
            task = asyncio.create_task(permanent_action())
            self.action_tasks[chat_id] = task
            return True
        return False
    
    async def stop_action(self, chat_id):
        if chat_id in self.action_tasks:
            self.action_tasks[chat_id].cancel()
            try:
                await self.client(SetTypingRequest(chat_id, types.SendMessageCancelAction()))
            except:
                pass
            if chat_id in self.active_actions:
                action_name = self.active_actions[chat_id]
                del self.active_actions[chat_id]
                del self.action_tasks[chat_id]
                return action_name
        return None
    
    async def get_chat_stats(self, chat_id, target_user_id=None):
        try:
            stats = {
                'my_messages': 0,
                'target_messages': 0,
                'my_photos': 0,
                'target_photos': 0,
                'my_videos': 0,
                'target_videos': 0,
                'my_stickers': 0,
                'target_stickers': 0,
                'my_gifs': 0,
                'target_gifs': 0,
                'my_voices': 0,
                'target_voices': 0,
                'my_files': 0,
                'target_files': 0
            }
            target_user = target_user_id or chat_id
            limit = 5000
            async for message in self.client.iter_messages(chat_id, limit=limit):
                if message.sender_id == self.my_id:
                    stats['my_messages'] += 1
                    if message.photo:
                        stats['my_photos'] += 1
                    elif message.video:
                        stats['my_videos'] += 1
                    elif message.sticker:
                        stats['my_stickers'] += 1
                    elif message.gif:
                        stats['my_gifs'] += 1
                    elif message.voice:
                        stats['my_voices'] += 1
                    elif message.document:
                        stats['my_files'] += 1
                elif message.sender_id == target_user:
                    stats['target_messages'] += 1
                    if message.photo:
                        stats['target_photos'] += 1
                    elif message.video:
                        stats['target_videos'] += 1
                    elif message.sticker:
                        stats['target_stickers'] += 1
                    elif message.gif:
                        stats['target_gifs'] += 1
                    elif message.voice:
                        stats['target_voices'] += 1
                    elif message.document:
                        stats['target_files'] += 1
            return stats
        except Exception as e:
            logger.error(f"خطا در دریافت آمار چت: {e}")
            return None
    
    async def generate_qr_code(self, text_or_photo, is_photo=False):
        try:
            if is_photo:
                photo_path = await self.client.download_media(text_or_photo)
                if photo_path and os.path.exists(photo_path):
                    text = f"Image: {os.path.basename(photo_path)}"
                    os.remove(photo_path)
                else:
                    return None, "خطا در دانلود عکس"
            else:
                text = text_or_photo
            if not text:
                return None, "متن خالی است"
            qr = qrcode.make(text)
            qr_path = f"qr_{self.user_id}_{int(time.time())}.png"
            qr.save(qr_path)
            return qr_path, text
        except Exception as e:
            return None, str(e)
    
    async def get_admins(self, chat_id):
        try:
            admins = []
            async for user in self.client.iter_participants(
                chat_id, 
                filter=ChannelParticipantsAdmins
            ):
                admins.append(user)
            return admins
        except Exception as e:
            logger.error(f"خطا در دریافت ادمین‌ها: {e}")
            return []
    
    async def pin_message(self, chat_id, message_id):
        try:
            await self.client.pin_message(chat_id, message_id)
            return True
        except Exception as e:
            logger.error(f"خطا در پین کردن پیام: {e}")
            return False
    
    async def get_user_info(self, user_id):
        try:
            entity = await self.client.get_entity(user_id)
            if entity.username:
                return f"@{entity.username}"
            elif entity.first_name:
                return f"{entity.first_name} {entity.last_name or ''}".strip()
            else:
                return f"کاربر {user_id}"
        except:
            return f"کاربر {user_id}"
    
    async def handle_calendar_command(self, event):
        try:
            now = get_now()
            
            time_str = now.strftime('%H:%M:%S')
            time_12 = now.strftime('%I:%M:%S %p')
            weekday = now.strftime('%A')
            persian_weekdays = {
                'Monday': 'دوشنبه', 'Tuesday': 'سه‌شنبه', 'Wednesday': 'چهارشنبه',
                'Thursday': 'پنج‌شنبه', 'Friday': 'جمعه', 'Saturday': 'شنبه', 'Sunday': 'یک‌شنبه'
            }
            
            jdate = jdatetime.date.fromgregorian(date=now.date())
            gregorian_date = now.date()
            
            try:
                hijri = Gregorian(now.year, now.month, now.day).to_hijri()
                hijri_str = f"{hijri.day} {hijri.month_name()} {hijri.year}"
                hijri_num = f"{hijri.year:04}/{hijri.month:02}/{hijri.day:02}"
            except:
                hijri_str = "محاسبه نشد"
                hijri_num = "۱۴۴۸/۰۱/۰۸ (تقریبی)"
            
            day_of_year = now.timetuple().tm_yday
            week_number = now.isocalendar()[1]
            
            calendar_text = f"""
ꕀꔚꨄꕣꕥ✺ღდ
🕰 ساعت تهران: {time_str}
⌚️ فرمت ۱۲ ساعته: {time_12}
🌐 منطقه زمانی: Asia/Tehran
📌 روز هفته: {persian_weekdays.get(weekday, weekday)}
📅 هفته: {week_number} (هفته سال)
📆 روز سال: {day_of_year}

╭─────── تقویم‌ها ───────╮
│ 📅 شمسی: {jdate.year:04}/{jdate.month:02}/{jdate.day:02}
│     {jdate.day} {jdate.strftime('%B')} {jdate.year}
│ 🌍 میلادی: {gregorian_date.year}/{gregorian_date.month:02}/{gregorian_date.day:02}
│     {gregorian_date.strftime('%d %B %Y')}
│ 🌙 قمری: {hijri_num}
│     {hijri_str}
╰────────────────────────╯

خلاصه شیک:
الان ساعت {time_str} است؛ تاریخ امروز در تقویم شمسی {jdate.year:04}/{jdate.month:02}/{jdate.day:02}، میلادی {gregorian_date.year}/{gregorian_date.month:02}/{gregorian_date.day:02} و قمری {hijri_num} می‌باشد.

⚠️ قمری: تقریبی، ممکن است با رؤیت هلال ۱ روز اختلاف داشته باشد
ꕀꔚꨄꕣꕥ✺ღდ
            """
            
            settings = db.get_selfbot_settings(self.user_id)
            text, entities = await apply_text_style(calendar_text, settings.get('text_style'))
            await self.client.send_message(event.chat_id, text, formatting_entities=entities)
            await event.delete()
            
        except Exception as e:
            logger.error(f"خطا در تقویم: {e}")
            await event.edit("❌ خطا در دریافت اطلاعات تقویم")
    
    def format_status_info(self, settings):
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM user_memory')
            user_count = cursor.fetchone()[0]
            conn.close()
        except:
            user_count = 0
        pv_enemies = len(db.get_enemies(self.user_id, 'pv'))
        comment_channels = len(self.auto_comment_settings)
        cached_media = len([m for m in media_cache.values() if m.get('owner_id') == self.user_id])
        spam_settings = db.get_spam_settings(self.user_id)
        filter_words = db.get_filter_words(self.user_id)
        active_filters = len([w for w in filter_words if w['enabled']])
        spam_messages = len(db.get_enemy_spam_messages(self.user_id))
        font_info = "همه فونت‌ها" if self.time_font_indices == 'all' else f"فونت‌های {self.time_font_indices}"
        
        ai_status = settings.get('ai_status', {})
        active_ai_pm = "هیچ هوش فعالی در پی‌وی وجود ندارد"
        pm_ais = []
        if ai_status.get('ai_deepseek_pm'):
            pm_ais.append("DeepSeek")
        if ai_status.get('ai_chatgpt_pm'):
            pm_ais.append("ChatGPT")
        if ai_status.get('ai_grok_pm'):
            pm_ais.append("Grok")
        if ai_status.get('ai_blackbox_pm'):
            pm_ais.append("Blackbox")
        if ai_status.get('ai_openai_pm'):
            pm_ais.append("OpenAI")
        if pm_ais:
            active_ai_pm = ", ".join(pm_ais)
        
        active_ai_group = "هیچ هوش فعالی در گروه وجود ندارد"
        group_ais = []
        if ai_status.get('ai_deepseek_group'):
            group_ais.append("DeepSeek")
        if ai_status.get('ai_chatgpt_group'):
            group_ais.append("ChatGPT")
        if ai_status.get('ai_grok_group'):
            group_ais.append("Grok")
        if ai_status.get('ai_blackbox_group'):
            group_ais.append("Blackbox")
        if ai_status.get('ai_openai_group'):
            group_ais.append("OpenAI")
        if group_ais:
            active_ai_group = ", ".join(group_ais)
        
        filter_status = "فعال" if db.get_filter_enabled(self.user_id) else "غیرفعال"
        text_style = settings.get('text_style') or "هیچکدام"
        locked_pvs = db.get_locked_pvs(self.user_id)
        pv_lock_all = settings.get('pv_lock_all', False)
        translate_status = []
        for lang, status in self.translate_mode.items():
            if status:
                translate_status.append(lang)
        translate_text = "، ".join(translate_status) if translate_status else "هیچکدام"
        selfbot_status = "فعال" if settings.get('selfbot_enabled', 1) else "غیرفعال"
        autosend_status = "فعال" if self.autosend_mode else "غیرفعال"
        bio_time1 = self.get_bio_setting('ساعت_در_بیو')
        bio_time2 = self.get_bio_setting('ساعت_در_بیو_۲')
        bio_date = self.get_bio_setting('بیو_تاریخ')
        bio_full = self.get_bio_setting('بیو_کامل')
        bio_love = self.get_bio_setting('بیو_عاشقانه')
        monshi_data = db.get_monshi_status(self.user_id)
        answers_count = len(db.get_answers(self.user_id))
        
        return f"""
ꕀꔚꨄꕣꕥ✺ღდ
وضعیت کامل سلف‌بات
━━━━━━━━━━━━━━━━━━━━
🤖 وضعیت سلف‌بات: {selfbot_status}
🔍 حالت سرچ: {'فعال' if self.search_mode else 'غیرفعال'}
🕐 تایم روی پروفایل: {'فعال' if settings.get('time_enabled') else 'غیرفعال'}
🏳️ پرچم در تایم: {'فعال' if settings.get('flag_enabled') else 'غیرفعال'}
🎨 فونت تایم: {font_info}
🔄 اتوسین: {autosend_status}

📝 تنظیمات بیو:
• ساعت در بیو: {bio_time1}
• ساعت در بیو ۲: {bio_time2}
• بیو تاریخ: {bio_date}
• بیو کامل: {bio_full}
• بیو عاشقانه: {bio_love}

🤖 هوش مصنوعی:
• پی‌وی: {active_ai_pm}
• گروه: {active_ai_group}

✍️ استایل متن: {text_style}

🔒 قفل پیوی همگانی: {'فعال' if pv_lock_all else 'غیرفعال'}
🔒 پی‌وی‌های قفل‌شده: {len(locked_pvs)}
🚫 فیلتر کلمات: {filter_status}

🌐 ترجمه فعال: {translate_text}

📊 آمار:
• دشمنان پیوی: {pv_enemies}
• کانال‌های نظر‌دهی: {comment_channels}
• رسانه‌های ذخیره‌شده: {cached_media}
• کلمات فیلتر فعال: {active_filters}
• پیام‌های اسپم ذخیره شده: {spam_messages}
• کاربران ذخیره شده: {user_count}

🛡️ حفاظت اسپم:
• وضعیت: {'فعال' if spam_settings.get('spam_protection') else 'غیرفعال'}
• محدودیت: {spam_settings.get('spam_limit', 10)} پیام در {spam_settings.get('mute_duration', 10)} ثانیه

🤖 منشی هوشمند:
• وضعیت: {'فعال' if monshi_data['status'] else 'غیرفعال'}
• پاسخ: {monshi_data['answer'][:30] if monshi_data['answer'] else 'تنظیم نشده'}
• تعداد پاسخ‌ها: {answers_count}

📊 گروه گزارش: {self.report_config.report_group_id}
💾 ذخیره خودکار رسانه: {'فعال' if self.report_config.auto_save_media else 'غیرفعال'}
━━━━━━━━━━━━━━━━━━━━
✅ Self-Bot v{BOT_VERSION}
ꕀꔚꨄꕣꕥ✺ღდ
        """
    
    def set_auto_comment(self, channel_id, comment_text, channel_title, channel_type, channel_username):
        self.auto_comment_settings[channel_id] = {
            'text': comment_text,
            'title': channel_title,
            'type': channel_type,
            'username': channel_username
        }
        self.save_state()
        return f"متن کامنت تنظیم شد: {comment_text[:30]}..."
    
    def remove_auto_comment(self, channel_id):
        if channel_id in self.auto_comment_settings:
            title = self.auto_comment_settings[channel_id]['title']
            del self.auto_comment_settings[channel_id]
            self.save_state()
            return f"تنظیمات {title} حذف شد"
        return "این کانال تنظیم نشده است"
    
    async def translate_text(self, text):
        any_lang_active = any(self.translate_mode.values())
        if not any_lang_active:
            return text
        try:
            from deep_translator import GoogleTranslator
        except Exception as e:
            logger.error(f"کتابخانه deep_translator نصب نیست! {e}")
            return text
        for lang, status in self.translate_mode.items():
            if status:
                target_code = TRANSLATE_LANG_CODES.get(lang, lang)
                try:
                    result = await asyncio.to_thread(
                        lambda: GoogleTranslator(source='auto', target=target_code).translate(text)
                    )
                    if result:
                        return result
                    else:
                        logger.warning(f"نتیجه ترجمه خالی بود برای زبان {lang} ({target_code})")
                        return text
                except Exception as e:
                    logger.error(f"خطا در ترجمه به {lang} ({target_code}): {e}")
                    return text
        return text
    
    async def handle_google_search(self, event, query):
        try:
            await event.edit(f'🔍 در حال جستجو: {query}')
            GOOGLE_SEARCH_API_KEY = "AIzaSyCMYOU0NpU5xfu7GrffyywVUugd1yD2uDU"
            GOOGLE_CSE_ID = "3185e48756dfd482f"
            GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': GOOGLE_SEARCH_API_KEY,
                'cx': GOOGLE_CSE_ID,
                'q': query,
                'num': 5,
                'safe': 'active'
            }
            response = requests.get(GOOGLE_SEARCH_URL, params=params, timeout=10)
            if response.status_code == 200:
                results = response.json()
                if 'items' in results and len(results['items']) > 0:
                    self.last_search_results = results['items']
                    message = f"🔍 نتایج جستجو برای: {query}\n\n"
                    for i, item in enumerate(results['items'][:5], 1):
                        title = item.get('title', 'بدون عنوان')
                        link = item.get('link', '')
                        snippet = item.get('snippet', 'بدون توضیح')[:100]
                        message += f"{i}. {title}\n   {snippet}...\n   🔗 {link}\n\n"
                    if len(message) > 4000:
                        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
                        for i, chunk in enumerate(chunks):
                            if i == 0:
                                await event.edit(chunk)
                            else:
                                await event.respond(chunk)
                    else:
                        await event.edit(message)
                else:
                    await event.edit(f'❌ هیچ نتیجه‌ای برای "{query}" پیدا نشد.')
            else:
                await event.edit(f'❌ خطا در جستجو. کد خطا: {response.status_code}')
        except Exception as e:
            logger.error(f"خطا در جستجوی گوگل: {e}")
            await event.edit(f'❌ خطا در جستجو: {str(e)}')
    
    async def send_report(self, report_text, media_path=None, caption=None):
        try:
            if self.report_config.report_group_id:
                if media_path and os.path.exists(media_path):
                    await self.client.send_file(self.report_config.report_group_id, media_path, caption=caption or report_text)
                    logger.info(f"گزارش با فایل ارسال شد: {media_path}")
                else:
                    await self.client.send_message(self.report_config.report_group_id, report_text)
                    logger.info(f"گزارش متنی ارسال شد")
                return True
            return False
        except Exception as e:
            logger.error(f"خطا در ارسال گزارش: {e}")
            return False
    
    async def get_chat_title(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            return entity.title if hasattr(entity, 'title') else (entity.first_name or f"چت {chat_id}")
        except:
            return f"چت {chat_id}"
    
    async def handle_media_lock_delete(self, event):
        if not event.message or event.message.out:
            return False
        target_id = event.sender_id
        if target_id == self.my_id:
            return False
        message = event.message
        message_text = message.text or ""
        lock_types = {
            'lock_link': is_link_message,
            'lock_text': lambda x: bool(x and not is_link_message(x) and not is_emoji_message(x)),
            'lock_emoji': is_emoji_message,
            'lock_photo': lambda x: message.photo,
            'lock_video': lambda x: message.video,
            'lock_sticker': lambda x: message.sticker,
            'lock_gif': lambda x: message.gif,
            'lock_voice': lambda x: message.voice,
            'lock_file': lambda x: message.document and not message.sticker and not message.gif,
            'lock_music': lambda x: message.audio,
            'lock_video_note': lambda x: message.video_note,
            'lock_contact': lambda x: message.contact,
            'lock_location': lambda x: message.geo
        }
        for lock_type, check_func in lock_types.items():
            if db.get_user_lock(self.user_id, 0, lock_type):
                if check_func(message_text):
                    try:
                        await message.delete()
                        return True
                    except:
                        pass
        for lock_type, check_func in lock_types.items():
            if db.get_user_lock(self.user_id, target_id, lock_type):
                if check_func(message_text):
                    try:
                        await message.delete()
                        return True
                    except:
                        pass
        return False

# ======================================================
# توابع API و دیتابیس
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
# ادامه کد با توابع پنل و کیبورد و ...
# ======================================================
# ======================================================
# ادامه کد - توابع پنل و کیبورد
# ======================================================

def get_main_panel_keyboard(user_id):
    buttons_enabled = db.get_buttons_enabled(user_id)
    
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
    selected_fonts = manager.selected_fonts if manager else []
    
    keyboard = []
    row = []
    for i, font in enumerate(classic_fonts):
        is_selected = i in selected_fonts
        row.append(InlineKeyboardButton(f"{font} {'✅' if is_selected else ''}", callback_data=f"exec_font_{i}_{user_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🎨 همه", callback_data=f"exec_font_all_{user_id}")])
    keyboard.append([InlineKeyboardButton("🗑️ پاک کردن", callback_data=f"exec_font_clear_{user_id}")])
    keyboard.append([InlineKeyboardButton("📖 راهنما", callback_data=f"help_font_{user_id}")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}")])
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی انتخاب پرچم
# ======================================================
def get_flagselect_menu_keyboard(user_id):
    manager = selfbot_managers.get(str(user_id))
    selected_flag = manager.selected_flag if manager else None
    
    keyboard = []
    row = []
    for flag in flags:
        row.append(InlineKeyboardButton(f"{flag} {'✅' if flag == selected_flag else ''}", callback_data=f"exec_flag_{flag}_{user_id}"))
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
# منوی بیو
# ======================================================
def get_bio_menu_keyboard(user_id):
    bio_time1 = db.get_bio_setting(user_id, 'ساعت_در_بیو')
    bio_time2 = db.get_bio_setting(user_id, 'ساعت_در_بیو_۲')
    bio_date = db.get_bio_setting(user_id, 'بیو_تاریخ')
    bio_full = db.get_bio_setting(user_id, 'بیو_کامل')
    bio_love = db.get_bio_setting(user_id, 'بیو_عاشقانه')
    bio_emoji = db.get_bio_setting(user_id, 'بیو_ایموجی')
    bio_season = db.get_bio_setting(user_id, 'بیو_فصل')
    bio_weekday = db.get_bio_setting(user_id, 'بیو_روز_هفته')
    bio_countdown = db.get_bio_setting(user_id, 'بیو_شمارش_معکوس')
    
    keyboard = [
        [
            InlineKeyboardButton(f"🕐 ساعت در بیو {'' if bio_time1 != 'روشن' else '✅'}", callback_data=f"exec_bio_time1_{user_id}"),
            InlineKeyboardButton(f"🕐 ساعت در بیو ۲ {'' if bio_time2 != 'روشن' else '✅'}", callback_data=f"exec_bio_time2_{user_id}")
        ],
        [
            InlineKeyboardButton(f"📅 بیو تاریخ {'' if bio_date != 'روشن' else '✅'}", callback_data=f"exec_bio_date_{user_id}"),
            InlineKeyboardButton(f"📅 بیو کامل {'' if bio_full != 'روشن' else '✅'}", callback_data=f"exec_bio_full_{user_id}")
        ],
        [
            InlineKeyboardButton(f"💕 بیو عاشقانه {'' if bio_love != 'روشن' else '✅'}", callback_data=f"exec_bio_love_{user_id}"),
            InlineKeyboardButton(f"🎨 بیو ایموجی {'' if bio_emoji != 'روشن' else '✅'}", callback_data=f"exec_bio_emoji_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🌸 بیو فصل {'' if bio_season != 'روشن' else '✅'}", callback_data=f"exec_bio_season_{user_id}"),
            InlineKeyboardButton(f"📆 بیو روز هفته {'' if bio_weekday != 'روشن' else '✅'}", callback_data=f"exec_bio_weekday_{user_id}")
        ],
        [
            InlineKeyboardButton(f"⏳ بیو شمارش معکوس {'' if bio_countdown != 'روشن' else '✅'}", callback_data=f"exec_bio_countdown_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی انیمیشن
# ======================================================
def get_animation_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("❤️ قلب", callback_data=f"exec_heart_{user_id}"),
            InlineKeyboardButton("🌙 ماه", callback_data=f"exec_moon_{user_id}")
        ],
        [
            InlineKeyboardButton("💖 قلب پیشرفته", callback_data=f"exec_advanced_heart_{user_id}"),
            InlineKeyboardButton("💝 عشق", callback_data=f"exec_love_{user_id}")
        ],
        [
            InlineKeyboardButton("🕯️ سنتت", callback_data=f"exec_santet_{user_id}"),
            InlineKeyboardButton("💻 هک", callback_data=f"exec_hack_{user_id}")
        ],
        [
            InlineKeyboardButton("🎨 استیکر متن", callback_data=f"exec_sticker_text_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_animation_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی مدیریت کاربران
# ======================================================
def get_user_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🥷 دشمن", callback_data=f"exec_enemy_{user_id}"),
            InlineKeyboardButton("🧸 دوست", callback_data=f"exec_friend_{user_id}")
        ],
        [
            InlineKeyboardButton("🔒 قفل پیوی", callback_data=f"exec_lock_pv_{user_id}"),
            InlineKeyboardButton("🔓 باز پی", callback_data=f"exec_unlock_pv_{user_id}")
        ],
        [
            InlineKeyboardButton("🔒 قفل پیوی همه", callback_data=f"exec_lock_all_{user_id}"),
            InlineKeyboardButton("🔓 باز پی همه", callback_data=f"exec_unlock_all_{user_id}"),
            InlineKeyboardButton("⛔ بلاک", callback_data=f"exec_block_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_user_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی قفل رسانه
# ======================================================
def get_lock_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🔗 قفل لینک", callback_data=f"exec_lock_link_{user_id}"),
            InlineKeyboardButton("📸 قفل عکس", callback_data=f"exec_lock_photo_{user_id}"),
            InlineKeyboardButton("🎥 قفل ویدیو", callback_data=f"exec_lock_video_{user_id}")
        ],
        [
            InlineKeyboardButton("🎨 قفل استیکر", callback_data=f"exec_lock_sticker_{user_id}"),
            InlineKeyboardButton("🎞️ قفل گیف", callback_data=f"exec_lock_gif_{user_id}"),
            InlineKeyboardButton("🎤 قفل ویس", callback_data=f"exec_lock_voice_{user_id}")
        ],
        [
            InlineKeyboardButton("📁 قفل فایل", callback_data=f"exec_lock_file_{user_id}"),
            InlineKeyboardButton("🎵 قفل موزیک", callback_data=f"exec_lock_music_{user_id}"),
            InlineKeyboardButton("📹 قفل ویدیو نوت", callback_data=f"exec_lock_video_note_{user_id}")
        ],
        [
            InlineKeyboardButton("📞 قفل کانتکت", callback_data=f"exec_lock_contact_{user_id}"),
            InlineKeyboardButton("📍 قفل لوکیشن", callback_data=f"exec_lock_location_{user_id}"),
            InlineKeyboardButton("😀 قفل ایموجی", callback_data=f"exec_lock_emoji_{user_id}")
        ],
        [
            InlineKeyboardButton("📝 قفل متن", callback_data=f"exec_lock_text_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_lock_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی کامنت
# ======================================================
def get_comment_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("💬 کامنت", callback_data=f"exec_comment_{user_id}"),
            InlineKeyboardButton("📊 کانال‌ها", callback_data=f"exec_channels_{user_id}")
        ],
        [
            InlineKeyboardButton("🗑️ حذف کانال", callback_data=f"exec_delete_channel_{user_id}"),
            InlineKeyboardButton("🔍 تست کانال", callback_data=f"exec_test_channel_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_comment_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی عمومی
# ======================================================
def get_general_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📊 وضعیت", callback_data=f"exec_status_{user_id}"),
            InlineKeyboardButton("ℹ️ درباره", callback_data=f"exec_about_{user_id}")
        ],
        [
            InlineKeyboardButton("⏱️ پینگ", callback_data=f"exec_ping_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_general_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی اکشن
# ======================================================
def get_action_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🎮 اکشن [نام]", callback_data=f"exec_action_{user_id}"),
            InlineKeyboardButton("⏹️ اکشن خاموش", callback_data=f"exec_action_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📋 اکشن لیست", callback_data=f"exec_action_list_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_action_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی بازی‌ها
# ======================================================
def get_games_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🎲 تاس ۱", callback_data=f"exec_dice_1_{user_id}"),
            InlineKeyboardButton("🎲 تاس ۲", callback_data=f"exec_dice_2_{user_id}"),
            InlineKeyboardButton("🎲 تاس ۳", callback_data=f"exec_dice_3_{user_id}")
        ],
        [
            InlineKeyboardButton("🎲 تاس ۴", callback_data=f"exec_dice_4_{user_id}"),
            InlineKeyboardButton("🎲 تاس ۵", callback_data=f"exec_dice_5_{user_id}"),
            InlineKeyboardButton("🎲 تاس ۶", callback_data=f"exec_dice_6_{user_id}")
        ],
        [
            InlineKeyboardButton("🎯 دارت", callback_data=f"exec_dart_{user_id}"),
            InlineKeyboardButton("🏀 بسکتبال", callback_data=f"exec_basketball_{user_id}"),
            InlineKeyboardButton("⚽️ فوتبال", callback_data=f"exec_football_{user_id}")
        ],
        [
            InlineKeyboardButton("🎳 بولینگ", callback_data=f"exec_bowling_{user_id}"),
            InlineKeyboardButton("🎲 تاس کازینو", callback_data=f"exec_casino_dice_{user_id}"),
            InlineKeyboardButton("🎨 سه رنگ", callback_data=f"exec_three_colors_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_games_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی ترجمه
# ======================================================
def get_translate_menu_keyboard(user_id):
    translate_mode = {}
    if str(user_id) in selfbot_managers:
        translate_mode = selfbot_managers[str(user_id)].translate_mode
    
    keyboard = [
        [
            InlineKeyboardButton(f"🇬🇧 انگلیسی {'' if not translate_mode.get('english') else '✅'}", callback_data=f"exec_translate_en_{user_id}"),
            InlineKeyboardButton(f"🇸🇦 عربی {'' if not translate_mode.get('arabic') else '✅'}", callback_data=f"exec_translate_ar_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🇮🇱 عبری {'' if not translate_mode.get('hebrew') else '✅'}", callback_data=f"exec_translate_he_{user_id}"),
            InlineKeyboardButton(f"🇷🇺 روسی {'' if not translate_mode.get('russian') else '✅'}", callback_data=f"exec_translate_ru_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🇹🇷 ترکی {'' if not translate_mode.get('turkish') else '✅'}", callback_data=f"exec_translate_tr_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_translate_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی گوگل
# ======================================================
def get_google_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🔍 سرچ", callback_data=f"exec_search_on_{user_id}"),
            InlineKeyboardButton("❌ خروج جستجو", callback_data=f"exec_search_off_{user_id}"),
            InlineKeyboardButton("🎵 اهنگ", callback_data=f"exec_music_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_google_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی اطلاعاتی
# ======================================================
def get_info_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 اطلاعات", callback_data=f"exec_info_{user_id}"),
            InlineKeyboardButton("⬇️ دانلود پروفایل", callback_data=f"exec_download_profile_{user_id}")
        ],
        [
            InlineKeyboardButton("📅 تاریخ ساخت اکانت", callback_data=f"exec_account_age_{user_id}"),
            InlineKeyboardButton("📱 نشست‌های فعال", callback_data=f"exec_active_sessions_{user_id}")
        ],
        [
            InlineKeyboardButton("🖥️ اطلاعات سیستم", callback_data=f"exec_system_info_{user_id}")
        ],
        [
            InlineKeyboardButton("🔍 تشخیص متن", callback_data=f"exec_ocr_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_info_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی پروفایل
# ======================================================
def get_profile_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📸 ست پروف", callback_data=f"exec_set_profile_{user_id}"),
            InlineKeyboardButton("✏️ ست بیو", callback_data=f"exec_set_bio_{user_id}")
        ],
        [
            InlineKeyboardButton("🗑️ حذف ست پروف", callback_data=f"exec_delete_profile_{user_id}"),
            InlineKeyboardButton("🗑️ حذف ست بیو", callback_data=f"exec_delete_bio_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_profile_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی استایل متن
# ======================================================
def get_style_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    current = settings.get('text_style', 'هیچ')
    
    keyboard = [
        [
            InlineKeyboardButton(f"بولد {'' if current != 'بولد' else '✅'}", callback_data=f"exec_bold_{user_id}"),
            InlineKeyboardButton(f"زیرخط {'' if current != 'زیرخط' else '✅'}", callback_data=f"exec_underline_{user_id}"),
            InlineKeyboardButton(f"خط خورده {'' if current != 'خط خورده' else '✅'}", callback_data=f"exec_strike_{user_id}")
        ],
        [
            InlineKeyboardButton(f"نقل قول {'' if current != 'نقل قول' else '✅'}", callback_data=f"exec_quote_{user_id}"),
            InlineKeyboardButton(f"اسپویلر {'' if current != 'اسپویلر' else '✅'}", callback_data=f"exec_spoiler_{user_id}"),
            InlineKeyboardButton(f"کج {'' if current != 'کج' else '✅'}", callback_data=f"exec_italic_{user_id}")
        ],
        [
            InlineKeyboardButton(f"کد {'' if current != 'کد' else '✅'}", callback_data=f"exec_code_{user_id}"),
            InlineKeyboardButton(f"پیش {'' if current != 'پیش' else '✅'}", callback_data=f"exec_pre_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_style_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی مدیریت پیام
# ======================================================
def get_message_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🧹 حذف کامل", callback_data=f"exec_delete_all_{user_id}"),
            InlineKeyboardButton("🧹 حذف کامل ۵۰", callback_data=f"exec_delete_50_{user_id}")
        ],
        [
            InlineKeyboardButton("🗑️ حذف ۱۰", callback_data=f"exec_delete_10_{user_id}"),
            InlineKeyboardButton("👁️ فعال اتوسین", callback_data=f"exec_autosend_on_{user_id}")
        ],
        [
            InlineKeyboardButton("🙈 غیرفعال اتوسین", callback_data=f"exec_autosend_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📸 اسکرین‌شات", callback_data=f"exec_screenshot_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_message_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی ریکشن
# ======================================================
def get_reaction_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("👍 ریکت", callback_data=f"exec_reaction_{user_id}"),
            InlineKeyboardButton("❌ حذف ریکت", callback_data=f"exec_reaction_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_reaction_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی اسپم
# ======================================================
def get_spam_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📩 اسپم", callback_data=f"exec_spam_{user_id}")],
        [InlineKeyboardButton("📖 راهنما", callback_data=f"help_spam_{user_id}")],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی تغییر پروفایل
# ======================================================
def get_change_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("✏️ تغییر اسم", callback_data=f"exec_change_name_{user_id}"),
            InlineKeyboardButton("✏️ تغییر بیو", callback_data=f"exec_change_bio_{user_id}")
        ],
        [
            InlineKeyboardButton("📸 تغییر پروفایل", callback_data=f"exec_change_profile_{user_id}"),
            InlineKeyboardButton("📸 پروف", callback_data=f"exec_change_profile_alt_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_change_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی مدیریت دشمنان
# ======================================================
def get_enemy_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 لیست دشمن", callback_data=f"exec_enemy_list_{user_id}"),
            InlineKeyboardButton("📝 اضافه اسپم", callback_data=f"exec_add_spam_{user_id}")
        ],
        [
            InlineKeyboardButton("✅ اتمام اسپم", callback_data=f"exec_end_spam_{user_id}"),
            InlineKeyboardButton("📜 لیست اسپم", callback_data=f"exec_spam_list_{user_id}")
        ],
        [
            InlineKeyboardButton("🗑️ پاک کردن اسپم", callback_data=f"exec_clear_spam_{user_id}"),
            InlineKeyboardButton("🗑️ حذف اسپم", callback_data=f"exec_delete_spam_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_enemy_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی فیلتر کلمات
# ======================================================
def get_filter_menu_keyboard(user_id):
    is_enabled = db.get_filter_enabled(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("🚫 .فیلتر [کلمه]", callback_data=f"exec_filter_word_{user_id}"),
            InlineKeyboardButton(f"✅ فیلتر روشن {'✅' if is_enabled else ''}", callback_data=f"exec_filter_on_{user_id}")
        ],
        [
            InlineKeyboardButton(f"❌ فیلتر خاموش {'✅' if not is_enabled else ''}", callback_data=f"exec_filter_off_{user_id}"),
            InlineKeyboardButton("📜 لیست / مدیریت کلمات", callback_data=f"exec_filter_list_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_filter_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی حفاظت اسپم
# ======================================================
def get_protection_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🛡️ اسپم روشن", callback_data=f"exec_spam_protection_on_{user_id}"),
            InlineKeyboardButton("🛡️ اسپم خاموش", callback_data=f"exec_spam_protection_off_{user_id}")
        ],
        [
            InlineKeyboardButton("⚙️ تنظیم اسپم", callback_data=f"exec_spam_settings_{user_id}"),
            InlineKeyboardButton("📊 وضعیت اسپم", callback_data=f"exec_spam_status_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_protection_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی گزارش
# ======================================================
def get_report_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📍 تنظیم گزارش", callback_data=f"exec_set_report_{user_id}"),
            InlineKeyboardButton("ℹ️ گروه گزارش", callback_data=f"exec_show_report_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_report_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی ابزار
# ======================================================
def get_tools_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📊 امار گپ", callback_data=f"exec_stats_{user_id}"),
            InlineKeyboardButton("🝰 کد QR", callback_data=f"exec_qr_{user_id}")
        ],
        [
            InlineKeyboardButton("👑 تگ ادمین", callback_data=f"exec_tag_admin_{user_id}"),
            InlineKeyboardButton("📌 پین", callback_data=f"exec_pin_{user_id}")
        ],
        [
            InlineKeyboardButton("🤖 سلف روشن", callback_data=f"exec_self_on_{user_id}"),
            InlineKeyboardButton("⛔ سلف خاموش", callback_data=f"exec_self_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_tools_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی منشی هوشمند
# ======================================================
def get_monshi_menu_keyboard(user_id):
    monshi_data = db.get_monshi_status(user_id)
    status = monshi_data['status']
    
    keyboard = [
        [
            InlineKeyboardButton(f"🤖 منشی {'✅' if status else ''}", callback_data=f"exec_monshi_on_{user_id}"),
            InlineKeyboardButton(f"⛔ خاموش {'✅' if not status else ''}", callback_data=f"exec_monshi_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📝 افزودن پاسخ", callback_data=f"exec_add_answer_{user_id}"),
            InlineKeyboardButton("🗑️ حذف پاسخ", callback_data=f"exec_remove_answer_{user_id}")
        ],
        [
            InlineKeyboardButton("📋 لیست پاسخ‌ها", callback_data=f"exec_list_answers_{user_id}"),
            InlineKeyboardButton("🧹 پاک کردن پاسخ‌ها", callback_data=f"exec_clear_answers_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_monshi_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی تگ همه
# ======================================================
def get_mention_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🏷️ تگ همه [متن]", callback_data=f"exec_mention_all_{user_id}"),
            InlineKeyboardButton("⛔ لغو تگ", callback_data=f"exec_cancel_mention_{user_id}")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"help_mention_{user_id}")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# منوی فال
# ======================================================
def get_fortune_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("🌟 فال عمومی", callback_data=f"exec_fortune_general_{user_id}")],
        [InlineKeyboardButton("🕌 فال حافظ", callback_data=f"exec_fortune_hafez_{user_id}")],
        [InlineKeyboardButton("☕ فال قهوه", callback_data=f"exec_fortune_coffee_{user_id}")],
        [InlineKeyboardButton("📖 راهنما", callback_data=f"help_fortune_{user_id}")],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ======================================================
# توابع بکاپ
# ======================================================
async def create_backup():
    """ایجاد فایل بکاپ از تمام دیتابیس‌ها"""
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
    """بازیابی دیتابیس از فایل بکاپ"""
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
# توابع مدیریت زمان برای بکاپ خودکار
# ======================================================
async def auto_backup_task():
    """انجام بکاپ خودکار هر ۱۲ ساعت"""
    while True:
        try:
            await asyncio.sleep(12 * 3600)  # 12 ساعت
            
            logger.info("⏳ شروع بکاپ خودکار...")
            zip_path = await create_backup()
            
            if zip_path and os.path.exists(zip_path):
                # ارسال به ادمین
                try:
                    bot = Application.builder().token(BOT_TOKEN).build()
                    await bot.initialize()
                    await bot.send_document(
                        chat_id=ADMIN_ID,
                        document=open(zip_path, 'rb'),
                        caption=f"💾 بکاپ خودکار دیتابیس\n📅 تاریخ: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
                    )
                    os.remove(zip_path)
                    logger.info("✅ بکاپ خودکار با موفقیت ارسال شد")
                except Exception as e:
                    logger.error(f"خطا در ارسال بکاپ خودکار: {e}")
            else:
                logger.error("❌ خطا در ایجاد بکاپ خودکار")
                
        except Exception as e:
            logger.error(f"خطا در task بکاپ خودکار: {e}")

# ======================================================
# توابع inline panel
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
            ("֍ اطلاعاتی", "info", "اطلاعات کاربر/سیستم/نشست‌ها/تاریخ ساخت اکانت/تشخیص متن"),
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
                            InlineKeyboardButton(f"ℹ️ توضیحات", callback_data=f"desc_{cmd}"),
                            InlineKeyboardButton(f"▶️ باز کردن", callback_data=f"menu_{cmd}")
                        ]])
                    )
                )
    await query.answer(results, cache_time=0, is_personal=True)

# ======================================================
# توابع start و panel و ...
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
# توابع مدیریت پیام‌ها
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
        await update.message.reply_text("❌ لطفاً فایل ZIP را ارسال کنید")
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

async def admin_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت بکاپ دیتابیس"""
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
    """آپلود و بازیابی بکاپ دیتابیس"""
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
    """پردازش فایل بکاپ آپلود شده"""
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
# تابع button_callback
# ======================================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    
    # بررسی وجود query.message
    if not query.message:
        await query.answer("⚠️ پیام یافت نشد", show_alert=True)
        return
    
    # بررسی دسترسی
    if '_' in data and not data.startswith(('admin_', 'approve_', 'reject_', 'stop_selfbot_', 'restart_selfbot_', 'desc_', 'menu_')):
        parts = data.split('_')
        for part in parts:
            if part.isdigit() and len(part) >= 5:
                if part != user_id_str:
                    await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
                    return
                break
    
    # ========== دکمه‌های اصلی ==========
    if data == "back_main":
        await query.edit_message_text("🌟 پنل مدیریت سلف‌بات\n\n⚠️ توجه: این پنل فقط مخصوص شماست\n\n✅ سلف‌بات به صورت ۲۴ ساعته فعال می‌ماند", reply_markup=get_main_panel_keyboard(user_id))
        return
    
    if data == "close_panel_" or data.startswith("close_panel_"):
        await query.answer("❌ بستن پنل")
        try:
            await query.message.delete()
        except:
            await query.edit_message_text("✅ پنل بسته شد")
        return
    
    # ========== منوهای ادمین ==========
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
    
    # ========== دکمه‌های منوها ==========
    if data.startswith("time_menu_"):
        await query.edit_message_text("⚈ **زمان و پروفایل**\n\nمدیریت زمان، پرچم، بیو و تقویم", reply_markup=get_time_menu_keyboard(user_id))
        return
    
    if data.startswith("font_menu_"):
        await query.edit_message_text("🎨 **انتخاب فونت تایم**\n\nفونت مورد نظر خود را انتخاب کنید:\n(می‌توانید چند فونت انتخاب کنید)", reply_markup=get_font_menu_keyboard(user_id))
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
    
    if data.startswith("bio_menu_"):
        await query.edit_message_text("📝 **تنظیمات بیو**\n\nانتخاب کنید:", reply_markup=get_bio_menu_keyboard(user_id))
        return
    
    if data.startswith("animation_menu_"):
        await query.edit_message_text("☻ **انیمیشن‌ها**\n\nانیمیشن قلب، ماه، سنتت، هک و استیکر متن", reply_markup=get_animation_menu_keyboard(user_id))
        return
    
    if data.startswith("user_menu_"):
        await query.edit_message_text("☗ **مدیریت کاربران**\n\nمدیریت دشمن، دوست، قفل پیوی و بلاک", reply_markup=get_user_menu_keyboard(user_id))
        return
    
    if data.startswith("lock_menu_"):
        await query.edit_message_text("⊖ **قفل رسانه**\n\nقفل انواع رسانه‌ها و محتوا", reply_markup=get_lock_menu_keyboard(user_id))
        return
    
    if data.startswith("comment_menu_"):
        await query.edit_message_text("✼ **کامنت خودکار**\n\nتنظیم کامنت خودکار در کانال‌ها", reply_markup=get_comment_menu_keyboard(user_id))
        return
    
    if data.startswith("general_menu_"):
        await query.edit_message_text("✿ **عمومی**\n\nوضعیت، درباره و پینگ", reply_markup=get_general_menu_keyboard(user_id))
        return
    
    if data.startswith("action_menu_"):
        await query.edit_message_text("☥ **اکشن‌ها**\n\nاکشن‌های تایپ، ویس، ویدیو و ...", reply_markup=get_action_menu_keyboard(user_id))
        return
    
    if data.startswith("games_menu_"):
        await query.edit_message_text("⚕ **بازی‌ها**\n\nبازی‌های تاس، دارت، بسکتبال، فوتبال، بولینگ و ...", reply_markup=get_games_menu_keyboard(user_id))
        return
    
    if data.startswith("translate_menu_"):
        await query.edit_message_text("❍ **ترجمه**\n\nترجمه خودکار پیام‌ها به زبان‌های مختلف", reply_markup=get_translate_menu_keyboard(user_id))
        return
    
    if data.startswith("google_menu_"):
        await query.edit_message_text("𖢅 **گوگل و اهنگ**\n\nجستجوی گوگل و پخش آهنگ", reply_markup=get_google_menu_keyboard(user_id))
        return
    
    if data.startswith("info_menu_"):
        await query.edit_message_text("֍ **اطلاعاتی**\n\nاطلاعات کاربر، سیستم، نشست‌ها و ...", reply_markup=get_info_menu_keyboard(user_id))
        return
    
    if data.startswith("profile_menu_"):
        await query.edit_message_text("𖢨 **پروفایل**\n\nکپی و مدیریت پروفایل و بیو", reply_markup=get_profile_menu_keyboard(user_id))
        return
    
    if data.startswith("style_menu_"):
        await query.edit_message_text("⩐ **استایل متن**\n\nاستایل‌های مختلف برای متن", reply_markup=get_style_menu_keyboard(user_id))
        return
    
    if data.startswith("message_menu_"):
        await query.edit_message_text("𑪡 **مدیریت پیام**\n\nحذف پیام، اتوسین و اسکرین‌شات", reply_markup=get_message_menu_keyboard(user_id))
        return
    
    if data.startswith("reaction_menu_"):
        await query.edit_message_text("☖ **ریکشن**\n\nریکت خودکار روی پیام‌ها", reply_markup=get_reaction_menu_keyboard(user_id))
        return
    
    if data.startswith("spam_menu_"):
        await query.edit_message_text("𖥞 **اسپم**\n\nارسال اسپم به کاربران", reply_markup=get_spam_menu_keyboard(user_id))
        return
    
    if data.startswith("change_menu_"):
        await query.edit_message_text("☗ **تغییر پروفایل**\n\nتغییر نام، بیو و پروفایل", reply_markup=get_change_menu_keyboard(user_id))
        return
    
    if data.startswith("enemy_menu_"):
        await query.edit_message_text("⚇ **مدیریت دشمنان**\n\nمدیریت لیست دشمنان و پیام‌های اسپم", reply_markup=get_enemy_menu_keyboard(user_id))
        return
    
    if data.startswith("filter_menu_"):
        await query.edit_message_text("✿ **فیلتر کلمات**\n\nفیلتر کردن کلمات خاص", reply_markup=get_filter_menu_keyboard(user_id))
        return
    
    if data.startswith("protection_menu_"):
        await query.edit_message_text("⚉ **حفاظت اسپم**\n\nمحافظت در برابر اسپم", reply_markup=get_protection_menu_keyboard(user_id))
        return
    
    if data.startswith("report_menu_"):
        await query.edit_message_text("֎ **گزارش**\n\nتنظیم گروه گزارش", reply_markup=get_report_menu_keyboard(user_id))
        return
    
    if data.startswith("tools_menu_"):
        await query.edit_message_text("🛠 **ابزار**\n\nامار گپ، کد QR، تگ ادمین، پین و ...", reply_markup=get_tools_menu_keyboard(user_id))
        return
    
    if data.startswith("monshi_menu_"):
        await query.edit_message_text("🤖 **منشی هوشمند**\n\nمدیریت منشی و پاسخ‌های خودکار", reply_markup=get_monshi_menu_keyboard(user_id))
        return
    
    if data.startswith("mention_menu_"):
        await query.edit_message_text("🏷️ **تگ همه**\n\nتگ کردن همه اعضای گروه", reply_markup=get_mention_menu_keyboard(user_id))
        return
    
    if data.startswith("fortune_menu_"):
        await query.edit_message_text("🔮 **فال**\n\nفال عمومی، فال حافظ و فال قهوه", reply_markup=get_fortune_menu_keyboard(user_id))
        return
    
    if data.startswith("timeflag_menu_"):
        await query.edit_message_text("🕐 **تایم و پرچم**\n\nمدیریت تایم، پرچم و فونت‌ها", reply_markup=get_time_menu_keyboard(user_id))
        return
    
    # ========== دکمه‌های exec ==========
    if data.startswith("exec_"):
        await exec_command_handler(update, context)
        return
    
    # ========== دکمه‌های help ==========
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
    
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ در حال اجرا...")
    except Exception:
        msg = None
    
    # ========== دستورات تایم ==========
    if cmd == 'time_on':
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.update_profile_name()
        if msg:
            await msg.edit_text("✅ تایم روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        except:
            pass
        return
    
    if cmd == 'time_flag':
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)
        await manager.update_profile_name()
        if msg:
            await msg.edit_text("✅ تایمر پرچم روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        except:
            pass
        return
    
    if cmd == 'time_off':
        db.update_selfbot_setting(user_id, 'time_enabled', 0)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.restore_profile_name()
        if msg:
            await msg.edit_text("✅ تایم خاموش شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        except:
            pass
        return
    
    # ========== دستورات فونت ==========
    if cmd.startswith('font_') and cmd != 'font_all' and cmd != 'font_clear':
        try:
            font_index = int(cmd.split('_')[1])
            if 0 <= font_index < len(classic_fonts):
                if font_index in manager.selected_fonts:
                    manager.selected_fonts.remove(font_index)
                else:
                    manager.selected_fonts.append(font_index)
                manager.save_state()
                if msg:
                    await msg.edit_text(f"✅ فونت {classic_fonts[font_index]} {'حذف شد' if font_index not in manager.selected_fonts else 'افزوده شد'}")
                try:
                    await query.message.edit_text(query.message.text, reply_markup=get_font_menu_keyboard(user_id))
                except:
                    pass
            else:
                if msg:
                    await msg.edit_text("❌ فونت نامعتبر")
        except:
            if msg:
                await msg.edit_text("❌ خطا در انتخاب فونت")
        return
    
    if cmd == 'font_all':
        manager.selected_fonts = list(range(len(classic_fonts)))
        manager.save_state()
        if msg:
            await msg.edit_text("✅ همه فونت‌ها انتخاب شدند")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_font_menu_keyboard(user_id))
        except:
            pass
        return
    
    if cmd == 'font_clear':
        manager.selected_fonts = []
        manager.save_state()
        if msg:
            await msg.edit_text("✅ لیست فونت‌ها پاک شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_font_menu_keyboard(user_id))
        except:
            pass
        return
    
    # ========== دستورات پرچم ==========
    if cmd.startswith('flag_'):
        flag = cmd.split('_')[1]
        if flag in flags:
            manager.selected_flag = flag
            manager.save_state()
            if msg:
                await msg.edit_text(f"✅ پرچم {flag} انتخاب شد")
            try:
                await query.message.edit_text(query.message.text, reply_markup=get_flagselect_menu_keyboard(user_id))
            except:
                pass
        else:
            if msg:
                await msg.edit_text("❌ پرچم نامعتبر")
        return
    
    # ========== دستورات هوش مصنوعی ==========
    if cmd.startswith('ai_pm_'):
        ai_name = cmd.replace('ai_pm_', '')
        if ai_name == 'off':
            manager.set_active_ai(None, 'pm')
            if msg:
                await msg.edit_text('✅ همه هوش‌ها در پی‌وی خاموش شدند')
        else:
            manager.set_active_ai(ai_name, 'pm')
            if msg:
                await msg.edit_text(f"✅ {AI_APIS[ai_name]['name']} در پی‌وی روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_ai_menu_keyboard(user_id))
        except:
            pass
        return
    
    if cmd.startswith('ai_group_'):
        ai_name = cmd.replace('ai_group_', '')
        if ai_name == 'off':
            manager.set_active_ai(None, 'group')
            if msg:
                await msg.edit_text('✅ همه هوش‌ها در گروه خاموش شدند')
        else:
            manager.set_active_ai(ai_name, 'group')
            if msg:
                await msg.edit_text(f"✅ {AI_APIS[ai_name]['name']} در گروه روشن شد")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_ai_menu_keyboard(user_id))
        except:
            pass
        return
    
    # ========== دستورات دکمه‌ها ==========
    if cmd == 'buttons_on':
        db.set_buttons_enabled(user_id, True)
        if msg:
            await msg.edit_text("✅ دکمه‌ها رنگی شدند")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_buttons_menu_keyboard(user_id))
        except:
            pass
        return
    
    if cmd == 'buttons_off':
        db.set_buttons_enabled(user_id, False)
        if msg:
            await msg.edit_text("✅ دکمه‌ها سفید شدند")
        try:
            await query.message.edit_text(query.message.text, reply_markup=get_buttons_menu_keyboard(user_id))
        except:
            pass
        return
    
    # ========== دستورات بیو ==========
    bio_commands = {
        'bio_time1': 'ساعت_در_بیو',
        'bio_time2': 'ساعت_در_بیو_۲',
        'bio_date': 'بیو_تاریخ',
        'bio_full': 'بیو_کامل',
        'bio_love': 'بیو_عاشقانه',
        'bio_emoji': 'بیو_ایموجی',
        'bio_season': 'بیو_فصل',
        'bio_weekday': 'بیو_روز_هفته',
        'bio_countdown': 'بیو_شمارش_معکوس',
    }
    for cmd_key, setting_name in bio_commands.items():
        if cmd.startswith(cmd_key):
            current = manager.get_bio_setting(setting_name)
            new_status = 'خاموش' if current == 'روشن' else 'روشن'
            manager.set_bio_setting(setting_name, new_status)
            if new_status == 'روشن':
                await manager.update_bio_with_settings()
            if msg:
                await msg.edit_text(f"✅ {setting_name}: **{new_status}**")
            try:
                await query.message.edit_text(query.message.text, reply_markup=get_bio_menu_keyboard(user_id))
            except:
                pass
            return
    
    # ========== دستورات عمومی ==========
    if cmd == 'calendar':
        try:
            if query.message:
                await manager.handle_calendar_command(query.message)
                if msg:
                    await msg.delete()
            else:
                if msg:
                    await msg.edit_text("❌ خطا در نمایش تقویم")
        except Exception as e:
            if msg:
                await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'status':
        settings = db.get_selfbot_settings(user_id)
        if msg:
            await msg.edit_text(manager.format_status_info(settings))
        return
    
    if cmd == 'about':
        if msg:
            await msg.edit_text(f"ℹ️ درباره بات\n\n🤖 نسخه: v{BOT_VERSION}\n👨‍💻 سازنده: {BOT_CREATOR}")
        return
    
    if cmd == 'ping':
        start = time.time()
        if msg:
            await msg.edit_text("🏓 پینگ: ...")
        end = time.time()
        ping = round((end - start) * 1000, 2)
        if msg:
            await msg.edit_text(f"🏓 پینگ: {ping} ms")
        return
    
    # ========== دستورات عکس و لوگو ==========
    if cmd == 'photo1':
        if msg:
            await msg.edit_text("🖼️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nعکس ۱ [متن]")
        return
    
    if cmd == 'photo2':
        if msg:
            await msg.edit_text("🖼️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nعکس ۲ [متن]")
        return
    
    if cmd == 'ghibli':
        if msg:
            await msg.edit_text("🎨 لطفاً روی یک عکس ریپلای کنید و دستور جیبلی را ارسال کنید")
        return
    
    if cmd == 'logo':
        if msg:
            await msg.edit_text("🎨 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nلوگو [عدد] [متن]\nمثال: لوگو 5 mmd")
        return
    
    # ========== دستورات ارز و بازار ==========
    if cmd == 'crypto':
        if msg:
            await msg.edit_text("💰 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nارز [نام ارز]\nمثال: ارز bitcoin")
        return
    
    if cmd == 'gold':
        if msg:
            await msg.edit_text("💎 لطفاً یکی از دستورات زیر را ارسال کنید:\n\nدلار\nطلا\nنقره")
        return
    
    if cmd == 'bourse':
        if msg:
            await msg.edit_text("📊 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nبورس [نماد]\nمثال: بورس شاخص")
        return
    
    if cmd == 'nobitex':
        if msg:
            await msg.edit_text("💵 در حال دریافت نرخ ارز...")
        result = await get_nobitex_rate()
        if result:
            if msg:
                await msg.edit_text(f"💵 **نرخ ارز:**\n{result}")
        else:
            if msg:
                await msg.edit_text("❌ خطا در دریافت نرخ ارز")
        return
    
    # ========== سایر دستورات ==========
    if msg:
        await msg.edit_text(f"✅ دستور {cmd} اجرا شد")

# ======================================================
# تابع help_handler
# ======================================================
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
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
   • می‌توانید چند فونت را همزمان انتخاب کنید
   • فونت‌ها به صورت چرخشی تغییر می‌کنند

🏳️ **فونت پرچم**: با کلیک روی این دکمه، می‌توانید پرچم مورد نظر خود را انتخاب کنید

📝 **تنظیمات بیو**: مدیریت بیو با گزینه‌های:
• ساعت در بیو: نمایش ساعت در بیو
• ساعت در بیو ۲: نمایش ساعت با ثانیه
• بیو تاریخ: نمایش تاریخ شمسی
• بیو کامل: نمایش همه اطلاعات
• بیو عاشقانه: نمایش با قلب
• بیو ایموجی: نمایش با ایموجی تصادفی
• بیو فصل: نمایش فصل فعلی
• بیو روز هفته: نمایش روز هفته
• بیو شمارش معکوس: شمارش معکوس تا سال نو
""",
        'help_font': """
🎨 **راهنمای فونت‌های تایم**

شما می‌توانید از بین ۱۵ فونت مختلف، فونت مورد نظر خود را انتخاب کنید.
با کلیک روی هر فونت، آن فونت به لیست انتخاب‌ها اضافه یا حذف می‌شود.

✅ فونت‌های انتخاب شده با تیک مشخص شده‌اند.

🎨 **همه**: با انتخاب این گزینه، همه فونت‌ها انتخاب می‌شوند
🗑️ **پاک کردن**: با انتخاب این گزینه، همه فونت‌ها از لیست حذف می‌شوند

📌 فونت‌های انتخاب شده به صورت چرخشی روی پروفایل نمایش داده می‌شوند
""",
        'help_flag': """
🏳️ **راهنمای انتخاب پرچم**

شما می‌توانید از بین بیش از ۲۰۰ پرچم مختلف، پرچم مورد نظر خود را انتخاب کنید.
با کلیک روی هر پرچم، آن پرچم کنار ساعت روی پروفایل شما نمایش داده می‌شود.

✅ پرچم فعلی با تیک مشخص شده است.
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

📌 تمام خروجی‌ها به صورت تصویر ارسال می‌شوند
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

📌 در گروه: هوش فقط به پیام‌هایی که ریپلای شده‌اند پاسخ می‌دهد
📌 در پی‌وی: هوش به همه پیام‌ها پاسخ می‌دهد (۳ خط اول)
""",
        'help_lock': """
⊖ **راهنمای قفل رسانه**

با فعال شدن هر قفل، پیام‌های مربوطه به طور خودکار حذف می‌شوند:

🔗 **قفل لینک**: حذف پیام‌های حاوی لینک
📸 **قفل عکس**: حذف پیام‌های حاوی عکس
🎥 **قفل ویدیو**: حذف پیام‌های حاوی ویدیو
🎨 **قفل استیکر**: حذف پیام‌های حاوی استیکر
🎞️ **قفل گیف**: حذف پیام‌های حاوی گیف
🎤 **قفل ویس**: حذف پیام‌های حاوی ویس
📁 **قفل فایل**: حذف پیام‌های حاوی فایل
🎵 **قفل موزیک**: حذف پیام‌های حاوی موزیک
📹 **قفل ویدیو نوت**: حذف پیام‌های حاوی ویدیو نوت
📞 **قفل کانتکت**: حذف پیام‌های حاوی کانتکت
📍 **قفل لوکیشن**: حذف پیام‌های حاوی لوکیشن
😀 **قفل ایموجی**: حذف پیام‌های فقط ایموجی
📝 **قفل متن**: حذف پیام‌های متنی

📌 قفل‌ها را می‌توان برای همه کاربران یا کاربر خاص فعال کرد
""",
        'help_enemy': """
⚇ **راهنمای مدیریت دشمنان**

🥷 **دشمن**: با ریپلای روی پیام کاربر، او را به لیست دشمنان اضافه می‌کند
🧸 **دوست**: با ریپلای روی پیام کاربر، او را از لیست دشمنان حذف می‌کند

📝 **اضافه اسپم**: وارد حالت اضافه کردن پیام اسپم می‌شود
✅ **اتمام اسپم**: خروج از حالت اضافه کردن اسپم

📜 **لیست اسپم**: نمایش لیست پیام‌های اسپم
🗑️ **پاک کردن اسپم**: حذف همه پیام‌های اسپم
🗑️ **حذف اسپم**: حذف یک پیام اسپم خاص

📌 دشمنان به طور خودکار اسپم دریافت می‌کنند
""",
        'help_filter': """
✿ **راهنمای فیلتر کلمات**

🚫 **.فیلتر [کلمه]**: افزودن کلمه به لیست فیلتر
✅ **فیلتر روشن**: فعال کردن فیلتر کلمات
❌ **فیلتر خاموش**: غیرفعال کردن فیلتر کلمات
📜 **لیست / مدیریت کلمات**: نمایش لیست کلمات فیلتر شده

📌 با فعال بودن فیلتر، پیام‌های حاوی کلمات فیلتر شده حذف می‌شوند
""",
        'help_protection': """
⚉ **راهنمای حفاظت اسپم**

🛡️ **اسپم روشن**: فعال کردن حفاظت اسپم
🛡️ **اسپم خاموش**: غیرفعال کردن حفاظت اسپم

⚙️ **تنظیم اسپم**: تنظیم تعداد پیام مجاز و مدت زمان سکوت
📊 **وضعیت اسپم**: نمایش وضعیت فعلی حفاظت اسپم

📌 با فعال بودن، کاربرانی که بیش از حد مجاز پیام ارسال کنند، سکوت می‌شوند
""",
        'help_mention': """
🏷️ **راهنمای تگ همه**

🏷️ **تگ همه [متن]**: تگ کردن همه اعضای گروه با متن دلخواه
⛔ **لغو تگ**: لغو عملیات تگ کردن

📌 تگ‌ها به صورت ۱۳ نفره ارسال می‌شوند
📌 فقط در گروه‌ها قابل استفاده است
""",
        'help_fortune': """
🔮 **راهنمای فال**

🌟 **فال عمومی**: فال روزانه با پیام‌های انگیزشی
🕌 **فال حافظ**: فال با اشعار حافظ
☕ **فال قهوه**: فال با طعم قهوه

📌 هر بار یک فال جدید و تصادفی نمایش داده می‌شود
""",
        'help_monshi': """
🤖 **راهنمای منشی هوشمند**

🤖 **منشی**: فعال کردن منشی با پاسخ دلخواه
⛔ **خاموش**: غیرفعال کردن منشی

📝 **افزودن پاسخ**: افزودن پاسخ خودکار برای سوال خاص
🗑️ **حذف پاسخ**: حذف پاسخ خودکار
📋 **لیست پاسخ‌ها**: نمایش لیست پاسخ‌های ذخیره شده
🧹 **پاک کردن پاسخ‌ها**: حذف همه پاسخ‌ها

📌 منشی به پیام‌های کاربران پاسخ می‌دهد
📌 پاسخ‌های ذخیره شده به سوالات خاص پاسخ می‌دهند
""",
        'help_google': """
𖢅 **راهنمای گوگل و اهنگ**

🔍 **سرچ**: فعال کردن حالت جستجوی گوگل
❌ **خروج جستجو**: خروج از حالت جستجو
🎵 **اهنگ**: جستجو و پخش آهنگ

📌 در حالت سرچ، هر پیامی که ارسال شود در گوگل جستجو می‌شود
📌 برای پخش آهنگ: `.اهنگ [نام آهنگ]`
""",
        'help_info': """
֍ **راهنمای اطلاعاتی**

📋 **اطلاعات**: نمایش اطلاعات کاربر (ریپلای)
⬇️ **دانلود پروفایل**: دانلود عکس پروفایل کاربر (ریپلای)
📅 **تاریخ ساخت اکانت**: نمایش تاریخ ساخت اکانت
📱 **نشست‌های فعال**: نمایش نشست‌های فعال تلگرام
🖥️ **اطلاعات سیستم**: نمایش اطلاعات سیستم سرور
🔍 **تشخیص متن**: تشخیص متن از روی عکس (ریپلای عکس)
""",
        'help_profile': """
𖢨 **راهنمای پروفایل**

📸 **ست پروف**: کپی عکس پروفایل کاربر (ریپلای)
✏️ **ست بیو**: کپی بیو کاربر (ریپلای)
🗑️ **حذف ست پروف**: حذف عکس پروفایل خود
🗑️ **حذف ست بیو**: خالی کردن بیو خود
""",
        'help_style': """
⩐ **راهنمای استایل متن**

استایل‌های مختلف برای متن ارسالی:

• **بولد**: پررنگ
• **زیرخط**: زیرخط دار
• **خط خورده**: خط خورده
• **نقل قول**: به صورت نقل قول
• **اسپویلر**: مخفی (با کلیک نمایش داده می‌شود)
• **کج**: ایتالیک
• **کد**: به صورت کد
• **پیش**: به صورت پیش‌فرض

📌 فقط یک استایل می‌تواند فعال باشد
""",
        'help_message': """
𑪡 **راهنمای مدیریت پیام**

🧹 **حذف کامل**: حذف همه پیام‌های خود در چت
🧹 **حذف کامل ۵۰**: حذف ۵۰ پیام آخر خود
🗑️ **حذف ۱۰**: حذف ۱۰ پیام آخر خود
👁️ **فعال اتوسین**: فعال کردن نشاندن خودکار پیام‌ها
🙈 **غیرفعال اتوسین**: غیرفعال کردن نشاندن خودکار
📸 **اسکرین‌شات**: شبیه‌سازی اسکرین‌شات
""",
        'help_reaction': """
☖ **راهنمای ریکشن**

👍 **ریکت**: تنظیم ریکت خودکار برای کاربر (ریپلای)
❌ **حذف ریکت**: حذف ریکت خودکار

📌 با تنظیم ریکت، هر بار کاربر پیام ارسال کند، ریکت مشخص شده روی پیام او زده می‌شود
""",
        'help_spam': """
𖥞 **راهنمای اسپم**

📩 **اسپم**: ارسال پیام اسپم به کاربر

نحوه استفاده: `اسپم [تعداد] [متن]`
مثال: `اسپم 5 سلام`

📌 پیام‌ها با فاصله ۰.۰۵ ثانیه ارسال می‌شوند
""",
        'help_change': """
☗ **راهنمای تغییر پروفایل**

✏️ **تغییر اسم**: تغییر نام پروفایل
✏️ **تغییر بیو**: تغییر بیو
📸 **تغییر پروفایل**: تغییر عکس پروفایل با ریپلای
📸 **پروف**: تغییر عکس پروفایل با ریپلای

نحوه استفاده:
• تغییر اسم [نام جدید]
• تغییر بیو [متن جدید]
• روی عکس ریپلای کنید و دستور را بزنید
""",
        'help_tools': """
🛠 **راهنمای ابزار**

📊 **امار گپ**: نمایش آمار گفتگو با کاربر (ریپلای)
🝰 **کد QR**: تولید کد QR از متن یا عکس (ریپلای)
👑 **تگ ادمین**: نمایش لیست ادمین‌های گروه
📌 **پین**: پین کردن پیام (ریپلای)
🤖 **سلف روشن**: فعال کردن سلف‌بات
⛔ **سلف خاموش**: غیرفعال کردن سلف‌بات
"""
    }
    
    if data in help_texts:
        # استخراج نام منو برای دکمه بازگشت
        menu_name = data.replace('help_', '') + '_menu'
        await query.edit_message_text(
            help_texts[data],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚈ بازگشت", callback_data=f"{menu_name}_{user_id}")]
            ])
        )
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
    """لغو عملیات جاری"""
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
    
    # شروع تسک بکاپ خودکار
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
