import os
import base64
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
from datetime import datetime, timedelta
from urllib.parse import quote

# ======================================================
# مدیریت منطقه زمانی (بدون pytz) - کاملاً سازگار با Python 3.13
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
# پچ کردن jdatetime و hijridate برای کار با zoneinfo
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InlineQueryResultCachedPhoto, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler
from telegram.request import HTTPXRequest
from telethon import TelegramClient, events, types
from telethon.tl.types import PeerUser, PeerChannel, PeerChat, MessageMediaPhoto, MessageMediaDocument, ReactionEmoji, MessageEntityBold, MessageEntityUnderline, MessageEntityStrike, MessageEntityBlockquote, MessageEntitySpoiler, MessageEntityItalic, MessageEntityCode, MessageEntityPre, InputMediaDice
from telethon.tl.functions.messages import SendReactionRequest, DeleteMessagesRequest, SetTypingRequest, ToggleDialogPinRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest, GetAuthorizationsRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError, ChatWriteForbiddenError
from telethon.tl.functions.channels import GetParticipantsRequest, CreateChannelRequest, EditPhotoRequest
from telethon.tl.types import ChannelParticipantsAdmins, InputPeerEmpty
import psutil
from platform import python_version, uname
from currency_converter import CurrencyConverter
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import urllib.parse

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "VROOM",
        "version": "4.9.6"
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

GOOGLE_SEARCH_API_KEY = "AIzaSyCMYOU0NpU5xfu7GrffyywVUugd1yD2uDU"
GOOGLE_CSE_ID = "3185e48756dfd482f"
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

GEMINI_KEY = "AIzaSyBhlSytH4Zfe-ww1D8HsrgJfCf5TRY1SLc"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PAXSENIX_API_KEY = "sk-paxsenix-Xo_BAFNGgWVZ_ymWd02Rk1JHbyoDSEzfPhiolJ3F12cY6XZG"
PAXSENIX_API_URL = "https://api.paxsenix.org/v1/chat/completions"
DEEPSEEK_FREE_URL = "https://deepseek.api-sina-free.workers.dev/?text="

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_CONFIGS = [
    {"api_id": 22409632, "api_hash": "b74c1ee200ad9ced6315859e9bd4125a"},
    {"api_id": 28297221, "api_hash": "8d682eb5c41a9762ef73f9ebe06c4eff"},
    {"api_id": 28039994, "api_hash": "00877cdcd706564a4de6abf7f7d64349"},
    {"api_id": 29031463, "api_hash": "64f122a7094dbab7e32b911eae6589e9"},
    {"api_id": 12832882, "api_hash": "1953c708cb3c47ecba74dc618b209e22"},
    {"api_id": 26645489, "api_hash": "6a212d0a400c97264600b3f932de5c2f"},
]

def get_user_api(user_id):
    conn = sqlite3.connect('main_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT api_id, api_hash FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] is not None and row[1] is not None:
        conn.close()
        return {"api_id": row[0], "api_hash": row[1]}
    
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

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده! توی Railway برو Variables و مقدار BOT_TOKEN رو با توکن جدیدت ست کن.")
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
    "①②③④⑤⑥⑦⑧⑨⓪",
    "➀➁➂➃➄➅➆➇➈➉",
    "❶❷❸❹❺❻❼❽❾❿",
    "１２３４５６７８９０",
    "⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽",
    "⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑",
    "一二三四五六七八九〇",
    "๑๒๓๔๕๖๗๘๙๐",
]

flags = [
    "🇮🇷", "🇺🇸", "🇬🇧", "🇩🇪", "🇫🇷", "🇮🇹", "🇪🇸", "🇹🇷", "🇷🇺",
    "🇨🇳", "🇯🇵", "🇰🇷", "🇸🇦", "🇦🇪", "🇶🇦", "🇰🇼", "🇮🇶", "🇸🇾",
    "🇱🇧", "🇯🇴", "🇪🇬", "🇲🇦", "🇩🇿", "🇹🇳", "🇱🇾", "🇸🇩", "🇾🇪",
    "🇴🇲", "🇧🇭", "🇵🇰", "🇦🇫", "🇮🇳", "🇧🇩", "🇧🇷", "🇦🇷", "🇲🇽",
    "🇨🇦", "🇦🇺", "🇳🇿", "🇿🇦", "🇳🇬", "🇰🇪", "🇪🇹", "🇬🇭", "🇺🇬",
    "🇺🇦", "🇵🇱", "🇳🇱", "🇧🇪", "🇸🇪", "🇳🇴", "🇩🇰", "🇫🇮", "🇨🇭",
    "🇦🇹", "🇬🇷", "🇵🇹", "🇮🇪", "🇨🇿", "🇭🇺", "🇷🇴", "🇧🇬", "🇷🇸",
    "🇭🇷", "🇸🇰", "🇸🇮", "🇱🇹", "🇱🇻", "🇪🇪", "🇦🇿", "🇦🇲", "🇬🇪",
    "🇰🇿", "🇺🇿", "🇹🇯", "🇹🇲", "🇰🇬", "🇲🇳", "🇻🇳", "🇹🇭", "🇲🇾",
    "🇸🇬", "🇮🇩", "🇵🇭", "🇲🇲", "🇰🇭", "🇱🇦", "🇳🇵", "🇱🇰", "🇲🇻",
]

SPAM_MESSAGES = [
    "مادربزرگت کسده، کسشو تو قبرم اجاره داده",
    "پدربزرگت کونی، هنوزم تو گور کونشو به شیاطین می‌سپره",
    "کس ننت چنان بازه، کل شهر توش چادر زدن",
]

BOT_VERSION = "4.9.6"
BOT_CREATOR = "VROOM"
PANEL_HEADER_IMAGE = "panel_header.png"  # تصویر بالای پنل (تصویر جدید VROOM)

# تصویر پنل embed شده — اگر فایل کنار اسکریپت نباشد از این ساخته می‌شود
_PANEL_HEADER_B64 = """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"""

def ensure_panel_header_files():
    """ساخت فایل‌های تصویر پنل از base64 اگر روی دیسک نباشند"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        targets = [
            os.path.join(base_dir, "panel_header.png"),
            os.path.join(base_dir, "panel_header_base.png"),
            os.path.join(base_dir, "user_panel_header.png"),
            "panel_header.png",
            "panel_header_base.png",
            "user_panel_header.png",
            os.path.join("media_storage", "panel_header.png"),
        ]
        raw = None
        for t in targets:
            try:
                if t and os.path.exists(t) and os.path.getsize(t) > 1000:
                    return t
            except Exception:
                pass
        try:
            raw = base64.b64decode(_PANEL_HEADER_B64)
        except Exception as e:
            logger.error(f"decode panel b64: {e}")
            return None
        for t in targets[:3]:
            try:
                os.makedirs(os.path.dirname(t) or ".", exist_ok=True)
                with open(t, "wb") as f:
                    f.write(raw)
            except Exception as e:
                logger.debug(f"write panel {t}: {e}")
        return targets[0] if os.path.exists(targets[0]) else ("panel_header.png" if os.path.exists("panel_header.png") else None)
    except Exception as e:
        logger.error(f"ensure_panel_header_files: {e}")
        return None


HEARTS = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🤍"]
MOONS = ["🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘", "🌑"]

media_cache = {}
panel_photo_cache = {}  # user_id -> photo file_id برای اینلاین یک‌پیامه
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

class MainDatabase:
    def __init__(self, db_name='main_database.db'):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
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
            CREATE TABLE IF NOT EXISTS selfbot_settings (
                user_id INTEGER PRIMARY KEY,
                time_enabled BOOLEAN DEFAULT 0,
                flag_enabled BOOLEAN DEFAULT 0,
                pv_lock_all BOOLEAN DEFAULT 0,
                autosend_mode BOOLEAN DEFAULT 0,
                text_style TEXT,
                report_group_id INTEGER DEFAULT -1002817019483,
                ai_1_pm BOOLEAN DEFAULT 0,
                ai_2_pm BOOLEAN DEFAULT 0,
                ai_3_pm BOOLEAN DEFAULT 0,
                ai_1_group BOOLEAN DEFAULT 0,
                ai_2_group BOOLEAN DEFAULT 0,
                ai_3_group BOOLEAN DEFAULT 0,
                translate_english BOOLEAN DEFAULT 0,
                translate_arabic BOOLEAN DEFAULT 0,
                translate_hebrew BOOLEAN DEFAULT 0,
                translate_russian BOOLEAN DEFAULT 0,
                translate_turkish BOOLEAN DEFAULT 0,
                panel_mode BOOLEAN DEFAULT 1,
                time_font_indices TEXT,
                selected_flags TEXT,
                filter_enabled BOOLEAN DEFAULT 0,
                selfbot_enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'api_id' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN api_id INTEGER")
        if 'api_hash' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN api_hash TEXT")
        
        # migration for selected_flags in selfbot_settings
        cursor.execute("PRAGMA table_info(selfbot_settings)")
        sb_columns = [col[1] for col in cursor.fetchall()]
        if 'selected_flags' not in sb_columns:
            try:
                cursor.execute("ALTER TABLE selfbot_settings ADD COLUMN selected_flags TEXT")
            except Exception:
                pass
        
        conn.commit()
        conn.close()
        logger.info("✓ دیتابیس اصلی ایجاد شد (و ستون‌های api_id و api_hash و selected_flags اضافه شدند)")
    
    def add_user(self, user_id, full_name, username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, full_name, username, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, full_name, username))
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
        cursor.execute('''
            SELECT * FROM users 
            WHERE request_sent = 1 AND admin_approved = 0 AND rejected = 0 AND step IS NULL
            ORDER BY request_date DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_pending_login(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users 
            WHERE admin_approved = 1 AND self_active = 0 AND step IS NOT NULL
            ORDER BY activation_date DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_active_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users 
            WHERE self_active = 1 AND admin_approved = 1
            ORDER BY activation_date DESC
        ''')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]
    
    def get_all_users(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, full_name, username, phone, self_active, created_at 
            FROM users ORDER BY created_at DESC
        ''')
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
                'ai_1_pm': bool(settings.get('ai_1_pm', 0)),
                'ai_2_pm': bool(settings.get('ai_2_pm', 0)),
                'ai_3_pm': bool(settings.get('ai_3_pm', 0)),
                'ai_1_group': bool(settings.get('ai_1_group', 0)),
                'ai_2_group': bool(settings.get('ai_2_group', 0)),
                'ai_3_group': bool(settings.get('ai_3_group', 0))
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
            selected_flags = settings.get('selected_flags')
            if selected_flags and selected_flags != 'all' and selected_flags.strip():
                try:
                    settings['selected_flags'] = [f for f in selected_flags.split(',') if f]
                except:
                    settings['selected_flags'] = 'all'
            else:
                settings['selected_flags'] = 'all'
            settings.setdefault('selfbot_enabled', 1)
            return settings
        else:
            default_settings = {
                'user_id': user_id,
                'time_enabled': 0,
                'flag_enabled': 0,
                'pv_lock_all': 0,
                'autosend_mode': 0,
                'text_style': None,
                'report_group_id': GROUP_ID,
                'ai_1_pm': 0,
                'ai_2_pm': 0,
                'ai_3_pm': 0,
                'ai_1_group': 0,
                'ai_2_group': 0,
                'ai_3_group': 0,
                'translate_english': 0,
                'translate_arabic': 0,
                'translate_hebrew': 0,
                'translate_russian': 0,
                'translate_turkish': 0,
                'panel_mode': 1,
                'time_font_indices': 'all',
                'selected_flags': 'all',
                'filter_enabled': 0,
                'selfbot_enabled': 1,
                'ai_status': {
                    'ai_1_pm': False,
                    'ai_2_pm': False,
                    'ai_3_pm': False,
                    'ai_1_group': False,
                    'ai_2_group': False,
                    'ai_3_group': False
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
        if 'selected_flags' in settings_to_save and isinstance(settings_to_save['selected_flags'], list):
            settings_to_save['selected_flags'] = ','.join(settings_to_save['selected_flags'])
        
        columns = ', '.join(settings_to_save.keys())
        placeholders = ', '.join(['?' for _ in settings_to_save])
        values = list(settings_to_save.values())
        
        cursor.execute(f'''
            INSERT OR REPLACE INTO selfbot_settings ({columns}, updated_at) 
            VALUES ({placeholders}, CURRENT_TIMESTAMP)
        ''', values)
        conn.commit()
        conn.close()
    
    def update_selfbot_setting(self, user_id, key, value):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM selfbot_settings WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            # اگر ردیف وجود ندارد، اول بساز
            self.get_selfbot_settings(user_id)
        cursor.execute(f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (value, user_id))
        conn.commit()
        conn.close()
    
    def update_ai_status(self, user_id, ai_status):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        for key, value in ai_status.items():
            if key in ['ai_1_pm', 'ai_2_pm', 'ai_3_pm', 'ai_1_group', 'ai_2_group', 'ai_3_group']:
                cursor.execute(f'UPDATE selfbot_settings SET {key} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (1 if value else 0, user_id))
        conn.commit()
        conn.close()
    
    def add_enemy(self, owner_id, enemy_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        try:
            enemy_id = int(enemy_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO enemies (owner_id, enemy_id, chat_type)
                VALUES (?, ?, ?)
            ''', (owner_id, enemy_id, chat_type))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()
    
    def remove_enemy(self, owner_id, enemy_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
            enemy_id = int(enemy_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM enemies WHERE owner_id = ? AND enemy_id = ? AND chat_type = ?', (owner_id, enemy_id, chat_type))
        conn.commit()
        conn.close()
    
    def get_enemies(self, owner_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT enemy_id FROM enemies WHERE owner_id = ? AND chat_type = ?', (owner_id, chat_type))
        enemies = [row[0] for row in cursor.fetchall()]
        conn.close()
        return enemies
    
    def is_enemy(self, owner_id, enemy_id, chat_type='pv'):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        try:
            enemy_id = int(enemy_id)
        except Exception:
            pass
        enemies = self.get_enemies(owner_id, chat_type)
        for e in enemies:
            try:
                if int(e) == int(enemy_id):
                    return True
            except Exception:
                if e == enemy_id:
                    return True
        return False
    
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
    
    def get_media_locks(self, owner_id, target_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM media_locks WHERE owner_id = ? AND target_id = ?', (owner_id, target_id))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(zip(columns, row))
        return {
            'owner_id': owner_id,
            'target_id': target_id,
            'lock_link': 0,
            'lock_photo': 0,
            'lock_video': 0,
            'lock_sticker': 0,
            'lock_gif': 0,
            'lock_voice': 0,
            'lock_file': 0,
            'lock_music': 0,
            'lock_video_note': 0,
            'lock_contact': 0,
            'lock_location': 0,
            'lock_emoji': 0,
            'lock_text': 0
        }
    
    def set_media_lock(self, owner_id, target_id, lock_type, value):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM media_locks WHERE owner_id = ? AND target_id = ?', (owner_id, target_id))
        exists = cursor.fetchone()
        
        if exists:
            cursor.execute(f'UPDATE media_locks SET {lock_type} = ?, created_at = CURRENT_TIMESTAMP WHERE owner_id = ? AND target_id = ?', (1 if value else 0, owner_id, target_id))
        else:
            lock_settings = {
                'owner_id': owner_id,
                'target_id': target_id,
                'lock_link': 0,
                'lock_photo': 0,
                'lock_video': 0,
                'lock_sticker': 0,
                'lock_gif': 0,
                'lock_voice': 0,
                'lock_file': 0,
                'lock_music': 0,
                'lock_video_note': 0,
                'lock_contact': 0,
                'lock_location': 0,
                'lock_emoji': 0,
                'lock_text': 0
            }
            lock_settings[lock_type] = 1 if value else 0
            columns = ', '.join(lock_settings.keys())
            placeholders = ', '.join(['?' for _ in lock_settings])
            values = list(lock_settings.values())
            cursor.execute(f'INSERT INTO media_locks ({columns}) VALUES ({placeholders})', values)
        
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
        cursor.execute('''
            INSERT OR REPLACE INTO user_locks (owner_id, target_id, lock_type, enabled)
            VALUES (?, ?, ?, ?)
        ''', (owner_id, target_id, lock_type, 1 if enabled else 0))
        conn.commit()
        conn.close()
    
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
    
    def set_auto_comment(self, owner_id, channel_id, comment_text, channel_title, channel_type, channel_username):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO auto_comments (owner_id, channel_id, comment_text, channel_title, channel_type, channel_username)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (owner_id, channel_id, comment_text, channel_title, channel_type, channel_username))
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
        cursor.execute('''
            INSERT OR REPLACE INTO sent_comments (owner_id, channel_id, message_id, comment_sent) 
            VALUES (?, ?, ?, 1)
        ''', (owner_id, channel_id, message_id))
        conn.commit()
        conn.close()
    
    def is_comment_sent(self, owner_id, channel_id, message_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT comment_sent FROM sent_comments 
            WHERE owner_id = ? AND channel_id = ? AND message_id = ?
        ''', (owner_id, channel_id, message_id))
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
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO enemy_spam_messages (owner_id, spam_text) VALUES (?, ?)', (owner_id, spam_text))
        conn.commit()
        conn.close()
    
    def get_enemy_spam_messages(self, owner_id):
        try:
            owner_id = int(owner_id)
        except Exception:
            pass
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
    
    def toggle_filter_word(self, owner_id, word, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE filter_words SET enabled = ? WHERE owner_id = ? AND word = ?', (1 if enabled else 0, owner_id, word))
        conn.commit()
        conn.close()
    
    def toggle_all_filters(self, owner_id, enabled):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE filter_words SET enabled = ? WHERE owner_id = ?', (1 if enabled else 0, owner_id))
        conn.commit()
        conn.close()
    
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
        return {
            'owner_id': owner_id,
            'spam_protection': 0,
            'spam_limit': 10,
            'mute_duration': 10
        }
    
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
            default_settings = {
                'owner_id': owner_id,
                'spam_protection': 0,
                'spam_limit': 10,
                'mute_duration': 10
            }
            default_settings.update(settings)
            columns = ', '.join(default_settings.keys())
            placeholders = ', '.join(['?' for _ in default_settings])
            values = list(default_settings.values())
            cursor.execute(f'INSERT INTO spam_settings ({columns}) VALUES ({placeholders})', values)
        
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
            cursor.execute('''
                UPDATE user_memory 
                SET username = ?, first_name = ?, last_name = ?, known_name = ?, chat_id = ?, last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (username, first_name, last_name, known_name, chat_id, user_id))
        else:
            cursor.execute('''
                INSERT INTO user_memory (user_id, username, first_name, last_name, known_name, chat_id, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, username, first_name, last_name, known_name, chat_id))
        conn.commit()
        conn.close()
    
    def add_broadcast(self, admin_id, message_text, message_type='text', media_file=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO broadcasts (admin_id, message_text, message_type, media_file)
            VALUES (?, ?, ?, ?)
        ''', (admin_id, message_text, message_type, media_file))
        broadcast_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return broadcast_id
    
    def update_broadcast_stats(self, broadcast_id, sent_count, failed_count):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE broadcasts SET sent_count = ?, failed_count = ?
            WHERE id = ?
        ''', (sent_count, failed_count, broadcast_id))
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
        cursor.execute('''
            INSERT OR REPLACE INTO bio_settings (user_id, setting_name, status) 
            VALUES (?, ?, ?)
        ''', (user_id, setting_name, status))
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
        cursor.execute('''
            INSERT OR REPLACE INTO monshi_status (user_id, status, answer) 
            VALUES (?, ?, ?)
        ''', (user_id, 1 if status else 0, answer))
        conn.commit()
        conn.close()
    
    def add_answer(self, user_id, question, answer):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO bot_answers (user_id, question, answer) 
            VALUES (?, ?, ?)
        ''', (user_id, question, answer))
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

db = MainDatabase()
selfbot_managers = {}

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
    if font_index < 0 or font_index >= len(classic_fonts):
        font_index = 0
    if isinstance(classic_fonts[font_index], dict):
        font = classic_fonts[font_index]
        return ''.join(font.get(c, c) for c in text)
    else:
        font = classic_fonts[font_index]
        result = []
        for c in text:
            if c.isdigit():
                d = int(c)
                if len(font) >= 10:
                    result.append(font[d])
                elif len(font) > 0:
                    result.append(font[d % len(font)])
                else:
                    result.append(c)
            else:
                result.append(c)
        return ''.join(result)

async def get_ai_response(text, ai_type, user_id=None):
    try:
        if ai_type == 1:
            url = f"{GEMINI_URL}?key={GEMINI_KEY}"
            payload = {"contents": [{"parts": [{"text": text}]}]}
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result:
                    return result['candidates'][0]['content']['parts'][0]['text'].strip()
        elif ai_type == 2:
            headers = {'Authorization': f'Bearer {PAXSENIX_API_KEY}', 'Content-Type': 'application/json'}
            data = {'model': 'gpt-3.5-turbo', 'messages': [{'role': 'user', 'content': text}]}
            response = requests.post(PAXSENIX_API_URL, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result:
                    return result['choices'][0]['message']['content'].strip()
        elif ai_type == 3:
            response = requests.get(DEEPSEEK_FREE_URL + quote(text), timeout=30)
            if response.status_code == 200:
                return response.text.strip()
    except:
        pass
    return None

COMMAND_KEYWORDS = ('لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال', 'حذف', 'ست', 'بولد', 'زیرخط', 'خط خورده', 'نقل قول', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک', 'ریکت', 'پیوی', 'گروه', 'درباره', 'من کی ام', 'قفل', 'باز', 'تنظیم', 'گروه گزارش', 'دشمن', 'دوست', 'دشمن گروه', 'دوست گروه', 'کانال', 'کامنت', 'تست', 'لیست دشمن', 'لیست اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'اضافه اسپم', 'اتمام اسپم', 'تغییر اسم', 'تغییر بیو', 'تغییر پروفایل', 'پروف', 'اسپم روشن', 'اسپم خاموش', 'پینگ', 'سرچ', 'خروج سرچ', 'قلب پیشرفته', 'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', 'پنل کاربر', '/panel', '.اهنگ', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش', 'پین', 'تگ ادمین', 'امار گپ', '.کد', 'تقویم', 'فونت', 'انگلیسی', 'عربی', 'عبری', 'روسی', 'ترکی', 'اتوسین', 'تگ همه', 'لغو تگ', 'منشی', 'افزودن پاسخ', 'حذف پاسخ', 'لیست پاسخ', 'پاک کردن پاسخ‌ها', 'بولینگ', 'تاس', 'سه رنگ', 'شانس', 'تاریخ ساخت اکانت', 'نشست‌های فعال', 'اطلاعات سیستم', 'قیمت ارز', 'نرخ ارز', 'استیکر متن', 'ساخت استیکر', 'اسکرین‌شات', 'تشخیص متن', 'ساعت در بیو', 'ساعت در بیو ۲', 'بیو تاریخ', 'بیو کامل', 'بیو عاشقانه')

TRANSLATE_LANG_CODES = {
    'english': 'en',
    'arabic': 'ar',
    'hebrew': 'iw',
    'russian': 'ru',
    'turkish': 'tr',
}

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
                    logger.info(f"وضعیت کاربر {self.user_id} از فایل بارگذاری شد")
        except Exception as e:
            logger.error(f"خطا در بارگذاری وضعیت: {e}")
    
    def save_state(self):
        try:
            data = {
                'autosend_mode': self.autosend_mode,
                'auto_comment_settings': {str(k): v for k, v in self.auto_comment_settings.items()},
                'auto_comment_sent': list(self.auto_comment_sent)
            }
            with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"وضعیت کاربر {self.user_id} ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره وضعیت: {e}")
    
    def load_bio(self):
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT bio_text FROM user_bio WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (self.user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else ""
        except:
            return ""
    
    def save_bio(self, bio_text):
        try:
            conn = sqlite3.connect('main_database.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO user_bio (user_id, bio_text) VALUES (?, ?)', (self.user_id, bio_text))
            conn.commit()
            conn.close()
            self.current_bio = bio_text
        except Exception as e:
            logger.error(f"خطا در ذخیره بیو: {e}")
    
    def get_bio_setting(self, setting_name):
        return db.get_bio_setting(self.user_id, setting_name)
    
    def set_bio_setting(self, setting_name, status):
        db.set_bio_setting(self.user_id, setting_name, status)
    
    async def ensure_original_bio_saved(self):
        try:
            if self.current_bio is not None and str(self.current_bio).strip() != "":
                return
            if not self.client or not self.client.is_connected():
                return
            me = await self.client.get_me()
            full = await self.client(GetFullUserRequest(me.id))
            about = ""
            try:
                about = full.full_user.about or ""
            except Exception:
                about = getattr(full, 'about', None) or ""
            any_on = any(
                self.get_bio_setting(n) == 'روشن'
                for n in (
                    'ساعت_در_بیو', 'ساعت_در_بیو_۲', 'بیو_تاریخ', 'بیو_کامل',
                    'بیو_عاشقانه', 'بیو_ایموجی', 'بیو_فصل', 'بیو_روز_هفته',
                    'بیو_شمارش_معکوس', 'بیو_متن_دلخواه'
                )
            )
            if not any_on:
                self.save_bio(about or "")
        except Exception as e:
            logger.debug(f"ensure_original_bio: {e}")

    async def update_bio_with_settings(self):
        try:
            if not self.client or not self.client.is_connected():
                logger.warning(f"کلاینت برای کاربر {self.user_id} متصل نیست")
                return

            await self.ensure_original_bio_saved()
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
            custom_text = self.get_bio_setting('بیو_متن_دلخواه') == 'روشن'

            any_on = any([time1, time2, date, full, love, random_emoji_bio, season, weekday_bio, countdown, custom_text])

            if not any_on:
                new_bio = bio_text or ""
                await self.client(UpdateProfileRequest(about=new_bio[:70] if new_bio else " "))
                if not new_bio:
                    await asyncio.sleep(0.3)
                    await self.client(UpdateProfileRequest(about=""))
                logger.info(f"بیو پاک/بازیابی شد برای {self.user_id}")
                return

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
                try:
                    target = datetime(now.year + 1, 3, 21)
                    if getattr(now, 'tzinfo', None):
                        target = target.replace(tzinfo=now.tzinfo)
                    diff = target - now
                    days = getattr(diff, 'days', 0)
                except Exception:
                    days = 0
                new_bio = f'{bio_text} | ⏳ {days} روز تا سال نو'
            elif custom_text:
                custom = self.get_bio_setting('بیو_متن_دلخواه_متن') or ""
                new_bio = f'{custom} | {bio_text} | {create_time()}'
            else:
                new_bio = bio_text or ""

            await self.client(UpdateProfileRequest(about=(new_bio or "")[:70]))
            logger.info(f"بیو به‌روزرسانی شد: {(new_bio or '(خالی)')[:50]}...")
        except Exception as e:
            logger.error(f"خطا در به‌روزرسانی بیو: {e}\n{traceback.format_exc()}")
    
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
    
    async def auto_sync_message(self, event):
        if self.autosend_mode and isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            try:
                await event.message.mark_read()
                logger.debug(f"اتوسین: پیام {event.message.id} سین شد")
            except Exception as e:
                logger.error(f"خطا در اتوسین: {e}")
    
    def set_auto_comment(self, channel_id, comment_text, channel_title, channel_type, channel_username):
        self.auto_comment_settings[channel_id] = {
            'text': comment_text,
            'title': channel_title,
            'type': channel_type,
            'username': channel_username
        }
        self.save_state()
        return f"متن کامنت تنظیم شد: {comment_text[:30]}..."
    
    def get_auto_comments(self):
        return self.auto_comment_settings
    
    def remove_auto_comment(self, channel_id):
        if channel_id in self.auto_comment_settings:
            title = self.auto_comment_settings[channel_id]['title']
            del self.auto_comment_settings[channel_id]
            self.save_state()
            return f"تنظیمات {title} حذف شد"
        return "این کانال تنظیم نشده است"
    
    async def auto_comment_handler(self, event):
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
    
    async def start(self, session_file):
        try:
            if self.running and self.client and self.client.is_connected():
                logger.info(f"سلف‌بات برای کاربر {self.user_id} از قبل در حال اجراست")
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
                system_version="4.8.0",
                app_version="4.8.0"
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
            
            logger.info(f"اطلاعات کاربر {self.user_id}: {self.BASE_NAME} (ID: {self.my_id}) | API: {self.api_id}")
            
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
            
            try:
                asyncio.create_task(self.ensure_report_group())
            except Exception as e:
                logger.error(f"ensure_report_group schedule: {e}")
            
            logger.info(f"✅ سلف‌بات برای کاربر {self.user_id} با موفقیت شروع شد")
            return True
            
        except Exception as e:
            logger.error(f"خطا در شروع سلف‌بات برای کاربر {self.user_id}: {str(e)}")
            
            if self.connection_attempts < self.max_attempts:
                wait_time = 5 * self.connection_attempts
                logger.info(f"تلاش مجدد در {wait_time} ثانیه برای کاربر {self.user_id} - تلاش {self.connection_attempts + 1}")
                await asyncio.sleep(wait_time)
                return await self.start(session_file)
            
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            return False
    
    async def ensure_report_group(self):
        try:
            current = self.report_config.report_group_id
            if current and current != GROUP_ID and current != 0:
                try:
                    await self.client.get_entity(current)
                    return
                except Exception:
                    pass
            
            logger.info(f"در حال ساخت گروه گزارش برای کاربر {self.user_id}...")
            result = await self.client(CreateChannelRequest(
                title="گزارش دهی",
                about="گروه اختصاصی گزارش‌های سلف‌بات VROOM\nپیام‌های حذف‌شده، ویرایش‌شده و رسانه‌ها اینجا ذخیره می‌شوند.",
                megagroup=True
            ))
            if not result or not result.chats:
                logger.error("CreateChannelRequest نتیجه خالی برگرداند")
                return
            new_chat = result.chats[0]
            full_id = int(f"-100{new_chat.id}")
            self.report_config.set_report_group(full_id)
            try:
                db.update_selfbot_setting(self.user_id, 'report_group_id', full_id)
            except Exception:
                pass
            
            guide = (
                "📌 **گروه گزارش‌دهی اختصاصی شما**\n\n"
                "از این لحظه تمام گزارش‌های سلف‌بات (پیام‌های حذف‌شده، ویرایش‌شده، رسانه‌ها و ...) "
                "در همین گروه ارسال می‌شوند.\n\n"
                "🔧 راهنمای سریع:\n"
                "• برای تغییر گروه گزارش: داخل گروه موردنظر دستور `تنظیم گزارش` را بزنید.\n"
                "• می‌توانید یک کانال سیو مسیج یا گروه دیگری هم تنظیم کنید.\n"
                "• برای دیدن گروه فعلی: `گروه گزارش`\n\n"
                "✅ این گروه برای شما سنجاق شده است."
            )
            try:
                await self.client.send_message(full_id, guide)
            except Exception as e:
                logger.debug(f"ارسال راهنما: {e}")
            
            try:
                peer = await self.client.get_input_entity(full_id)
                try:
                    await self.client(ToggleDialogPinRequest(peer=peer, pinned=True))
                except Exception as pin_err:
                    logger.debug(f"پین اول ناموفق: {pin_err}")
                    try:
                        dialogs = await self.client.get_dialogs(limit=30)
                        pinned = [d for d in dialogs if getattr(d, 'pinned', False)]
                        if pinned:
                            old = pinned[-1]
                            old_peer = await self.client.get_input_entity(old.entity)
                            await self.client(ToggleDialogPinRequest(peer=old_peer, pinned=False))
                            await asyncio.sleep(0.5)
                            await self.client(ToggleDialogPinRequest(peer=peer, pinned=True))
                    except Exception as e2:
                        logger.debug(f"آزادسازی پین: {e2}")
            except Exception as e:
                logger.debug(f"سنجاق گروه گزارش: {e}")
            
            logger.info(f"✅ گروه گزارش {full_id} برای کاربر {self.user_id} ساخته و تنظیم شد")
        except Exception as e:
            logger.error(f"ensure_report_group error for {self.user_id}: {e}\n{traceback.format_exc()}")
    
    async def keep_alive_task(self):
        reconnect_attempts = 0
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
                        reconnect_attempts = 0
                        logger.debug(f"Keepalive برای کاربر {self.user_id} موفق")
                    except Exception as e:
                        self.error_count += 1
                        self.last_error_time = time.time()
                        logger.warning(f"خطا در keepalive برای کاربر {self.user_id} ({self.error_count}): {e}")
                        
                        if self.error_count >= 3:
                            logger.warning(f"تلاش مجدد برای کاربر {self.user_id} بعد از {self.error_count} خطا")
                            reconnect_attempts += 1
                            await self.reconnect()
                else:
                    logger.warning(f"اتصال کاربر {self.user_id} قطع شده، تلاش برای reconnect...")
                    reconnect_attempts += 1
                    await self.reconnect()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"خطا در keep_alive_task برای کاربر {self.user_id}: {e}")
                reconnect_attempts += 1
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
            
            attempt = 0
            while True:
                attempt += 1
                logger.info(f"تلاش reconnect {attempt} برای کاربر {self.user_id}")
                
                if await self.start(session_file):
                    logger.info(f"✅ reconnect برای کاربر {self.user_id} موفقیت‌آمیز بود")
                    return True
                
                wait_time = min(attempt * 10, 300)
                logger.info(f"تلاش reconnect {attempt} ناموفق بود، صبر {wait_time} ثانیه...")
                await asyncio.sleep(wait_time)
                
        except Exception as e:
            logger.error(f"خطا در reconnect برای کاربر {self.user_id}: {e}")
            return False
    
    async def stop(self):
        try:
            self.running = False
            self.keepalive_running = False
            
            settings = db.get_selfbot_settings(self.user_id)
            settings['panel_mode'] = self.panel_mode
            db.set_selfbot_settings(self.user_id, settings)
            
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
            logger.error(f"خطا در توقف سلف‌بات برای کاربر {self.user_id}: {e}")
    
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
            
            @self.client.on(events.NewMessage())
            async def report_handler(event):
                if not self.running:
                    return
                await self.handle_report_message(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_commands(event):
                if not self.running:
                    return
                await self.handle_commands(event)
                
        except Exception as e:
            logger.error(f"خطا در تنظیم هندلرها برای کاربر {self.user_id}: {e}")
    
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
        
        # ========== تنظیمات بیو (اصلاح شده) ==========
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
                    await self.update_bio_with_settings()
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    return
        
        # ========== فال ==========
        if cmd == 'فال' and not args:
            await self.fortune_telling(chat_id, event)
            return
        
        if cmd == 'فال' and args and args[0] == 'حافظ' and len(args) == 1:
            await self.hafez_fortune(chat_id, event)
            return
        
        if cmd == 'فال' and args and args[0] == 'قهوه' and len(args) == 1:
            await self.coffee_fortune(chat_id, event)
            return
        
        # ========== منشی ==========
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
        
        # ========== پاسخ‌ها ==========
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
        
        # ========== تگ همه ==========
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
        
        # ========== بازی‌ها ==========
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
        
        # ========== نشست‌های فعال ==========
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
        
        # ========== تاریخ ساخت اکانت ==========
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
        
        # ========== اطلاعات سیستم ==========
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
        
        # ========== قیمت ارز ==========
        if cmd == 'قیمت' and args and args[0] == 'ارز' and len(args) > 1:
            currency = args[1].upper()
            try:
                url = "https://api.nobitex.ir/market/stats"
                params = {"srcCurrency": currency, "dstCurrency": "irt"}
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                if "stats" in data and f"{currency}-irt" in data["stats"]:
                    stats = data["stats"][f"{currency}-irt"]
                    text = f"💰 **قیمت {currency}:**\n\n"
                    text += f"خرید: {stats['bestBuy']} تومان\n"
                    text += f"فروش: {stats['bestSell']} تومان\n"
                    text += f"تغییرات: {stats['dayChange']}%\n"
                    text += f"بالاترین: {stats['dayHigh']} تومان\n"
                    text += f"پایین‌ترین: {stats['dayLow']} تومان"
                    await event.edit(text)
                else:
                    await event.edit(f"❌ ارز '{currency}' یافت نشد")
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # ========== نرخ ارز ==========
        if cmd == 'نرخ' and args and args[0] == 'ارز':
            try:
                url = "https://api.exchangerate-api.com/v4/latest/USD"
                response = requests.get(url, timeout=10)
                data = response.json()
                currencies = {
                    'USD': 'دلار', 'EUR': 'یورو', 'GBP': 'پوند',
                    'AED': 'درهم', 'TRY': 'لیر', 'CHF': 'فرانک', 'CNY': 'یوان'
                }
                text = "💵 **نرخ ارزهای جهانی (هر ۱۰۰۰ واحد):**\n\n"
                for code, name in currencies.items():
                    if code in data['rates']:
                        rate = (1 / data['rates'][code]) * 1000
                        text += f"{name}: {rate:,.0f} تومان\n"
                await event.edit(text)
            except Exception as e:
                await event.edit(f"❌ خطا: {e}")
            return
        
        # ========== تشخیص متن (OCR) ==========
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
        
        # ========== استیکر متن ==========
        if cmd == 'استیکر' and args and args[0] == 'متن':
            text = ' '.join(args[1:])
            if not text:
                await event.edit("⚠️ فرمت: استیکر متن [متن]")
                return
            try:
                img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
                except Exception:
                    try:
                        font = ImageFont.truetype("font.ttf", 48)
                    except Exception:
                        font = ImageFont.load_default()
                words = text.split()
                lines, cur = [], ""
                for w in words:
                    test = (cur + " " + w).strip()
                    bbox = draw.textbbox((0, 0), test, font=font)
                    if bbox[2] - bbox[0] > 480 and cur:
                        lines.append(cur)
                        cur = w
                    else:
                        cur = test
                if cur:
                    lines.append(cur)
                total_h = 0
                line_sizes = []
                for ln in lines:
                    bbox = draw.textbbox((0, 0), ln, font=font)
                    line_sizes.append((bbox[2]-bbox[0], bbox[3]-bbox[1]))
                    total_h += bbox[3]-bbox[1] + 8
                y = max(0, (512 - total_h) // 2)
                for ln, (lw, lh) in zip(lines, line_sizes):
                    x = (512 - lw) // 2
                    draw.text((x, y), ln, fill=(255, 255, 255, 255), font=font)
                    y += lh + 8
                output = BytesIO()
                img.save(output, format='WEBP')
                output.name = "sticker.webp"
                output.seek(0)
                await self.client.send_file(
                    chat_id, output,
                    force_document=False,
                    attributes=[types.DocumentAttributeSticker(
                        alt=text[:16],
                        stickerset=types.InputStickerSetEmpty(),
                        mask=False
                    )]
                )
                await event.delete()
            except Exception as e:
                logger.error(f"استیکر متن: {e}")
                try:
                    await event.edit(f"❌ خطا: {e}")
                except Exception:
                    pass
            return
        
        # ========== عکس → استیکر / فیلم → گیف ==========
        if cmd == 'استیکر' and (not args or (args and args[0] not in ('متن',))):
            if not event.message.is_reply:
                await event.edit("⚠️ روی عکس ریپلای کنید و بنویسید: استیکر")
                return
            try:
                reply_msg = await event.get_reply_message()
                if not reply_msg or not reply_msg.media:
                    await event.edit("❌ رسانه یافت نشد")
                    return
                await event.edit("⏳ در حال تبدیل...")
                buf = BytesIO()
                path = await self.client.download_media(reply_msg, file=buf)
                buf.seek(0)
                is_video = bool(reply_msg.video or reply_msg.gif or (reply_msg.document and getattr(reply_msg.document, 'mime_type', '').startswith('video')))
                if is_video:
                    buf.name = "anim.mp4"
                    await self.client.send_file(chat_id, buf, force_document=False, supports_streaming=True, video_note=False)
                    try:
                        buf.seek(0)
                        await self.client.send_file(chat_id, buf, attributes=[types.DocumentAttributeAnimated()], force_document=False)
                    except Exception:
                        pass
                else:
                    try:
                        img = Image.open(buf).convert('RGBA')
                        img = ImageOps.fit(img, (512, 512), centering=(0.5, 0.5))
                        out = BytesIO()
                        img.save(out, format='WEBP')
                        out.name = "sticker.webp"
                        out.seek(0)
                        await self.client.send_file(
                            chat_id, out,
                            force_document=False,
                            attributes=[types.DocumentAttributeSticker(
                                alt="🙂",
                                stickerset=types.InputStickerSetEmpty(),
                                mask=False
                            )]
                        )
                    except Exception as e:
                        buf.seek(0)
                        await self.client.send_file(chat_id, buf)
                await event.delete()
            except Exception as e:
                logger.error(f"استیکر convert: {e}")
                try:
                    await event.edit(f"❌ خطا: {str(e)[:80]}")
                except Exception:
                    pass
            return
        
        # ========== ساخت استیکر با @QuotLyBot ==========
        if cmd == 'ساخت' and args and args[0] == 'استیکر':
            if not event.message.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید و بنویسید: ساخت استیکر")
                return
            try:
                reply_msg = await event.get_reply_message()
                if not reply_msg:
                    await event.edit("❌ پیام ریپلای یافت نشد")
                    return
                await event.edit("⏳ در حال ساخت استیکر...")
                quotly = await self.client.get_entity("QuotLyBot")
                sent_to_bot = await self.client.forward_messages(quotly, reply_msg)
                sent_id = sent_to_bot[0].id if isinstance(sent_to_bot, (list, tuple)) else sent_to_bot.id
                sticker_msg = None
                for _ in range(18):
                    await asyncio.sleep(1.0)
                    async for m in self.client.iter_messages(quotly, limit=8):
                        if m.id <= sent_id:
                            continue
                        is_sticker = False
                        if m.sticker:
                            is_sticker = True
                        elif m.document:
                            mt = getattr(m.document, 'mime_type', '') or ''
                            if mt in ('application/x-tgsticker', 'image/webp', 'video/webm'):
                                is_sticker = True
                            attrs = getattr(m.document, 'attributes', None) or []
                            for a in attrs:
                                if type(a).__name__ in ('DocumentAttributeSticker', 'DocumentAttributeAnimated'):
                                    is_sticker = True
                                    break
                        if is_sticker:
                            sticker_msg = m
                            break
                    if sticker_msg:
                        break
                if sticker_msg and sticker_msg.media:
                    await self.client.send_file(
                        event.chat_id,
                        sticker_msg.media,
                        reply_to=reply_msg.id,
                        caption=None,
                        force_document=False
                    )
                    try:
                        await event.delete()
                    except Exception:
                        pass
                else:
                    await event.edit("❌ استیکر از QuotLyBot دریافت نشد. دوباره امتحان کنید.")
                try:
                    msgs_to_del = []
                    async for m in self.client.iter_messages(quotly, limit=25):
                        msgs_to_del.append(m.id)
                    if msgs_to_del:
                        await self.client.delete_messages(quotly, msgs_to_del)
                except Exception as del_e:
                    logger.debug(f"پاک کردن چت QuotLy: {del_e}")
            except Exception as e:
                logger.error(f"ساخت استیکر: {e}\n{traceback.format_exc()}")
                try:
                    await event.edit(f"❌ خطا در ساخت استیکر: {str(e)[:100]}")
                except Exception:
                    pass
            return
        
        # ========== اسکرین‌شات ==========
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
        
        # ========== ادامه دستورات قبلی ==========
        
        if cmd == 'سلف' and args and args[0] in ['روشن', 'خاموش']:
            if args[0] == 'روشن':
                db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 1)
                await event.edit("✅ سلف‌بات فعال شد")
            else:
                db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 0)
                await event.edit("✅ سلف‌بات غیرفعال شد")
            return
        
        if cmd == 'تقویم' and not args:
            await self.handle_calendar_command(event)
            return
        
        if cmd == 'فونت' and args:
            font_arg = args[0]
            try:
                if font_arg.isdigit():
                    idx = int(font_arg)
                    if 0 <= idx < len(classic_fonts):
                        self.time_font_indices = [idx]
                        db.update_selfbot_setting(self.user_id, 'time_font_indices', str(idx))
                        await event.edit(f"✅ فونت ساعت به فونت شماره {idx} تغییر کرد")
                    else:
                        await event.edit(f"❌ فونت {idx} وجود ندارد (۰ تا {len(classic_fonts)-1})")
                elif font_arg == 'همه':
                    self.time_font_indices = 'all'
                    db.update_selfbot_setting(self.user_id, 'time_font_indices', 'all')
                    await event.edit("✅ همه فونت‌ها فعال شدند")
                else:
                    await event.edit("❌ فرمت نامعتبر\nمثال: فونت 5 یا فونت همه")
            except:
                await event.edit("❌ خطا در تنظیم فونت")
            return
        
        settings = db.get_selfbot_settings(self.user_id)
        if not settings.get('selfbot_enabled', 1):
            return
        
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
            else:
                try:
                    indices = []
                    for part in args[0].split('.'):
                        if part.isdigit():
                            idx = int(part)
                            if 0 <= idx < len(classic_fonts):
                                indices.append(idx)
                    if indices:
                        self.time_font_indices = indices
                        db.update_selfbot_setting(self.user_id, 'time_font_indices', ','.join(map(str, indices)))
                        await event.edit(f"✅ فونت‌های تایم تنظیم شد: {indices}")
                    else:
                        await event.edit(f"❌ ایندکس نامعتبر. محدوده: ۰ تا {len(classic_fonts)-1}")
                except:
                    await event.edit("❌ فرمت نامعتبر\nمثال: تایم 5.10")
            return
        
        if cmd == 'تاریخ' and args and args[0] == 'کامل' and len(args) == 1:
            date_info = self.get_full_date_info()
            await event.edit(date_info)
            return
        
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
            elif cmd == 'قفل' and args and len(args) >= 2 and args[0] == lock_name and args[1] in ['روشن', 'خاموش'] and len(args) == 2:
                target_id = 0
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    target_id = reply_msg.sender_id
                elif isinstance(event.message.peer_id, PeerUser):
                    target_id = event.message.peer_id.user_id
                
                if args[1] == 'روشن':
                    db.set_user_lock(self.user_id, target_id, lock_type, True)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} فعال شد")
                else:
                    db.set_user_lock(self.user_id, target_id, lock_type, False)
                    target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                    await event.edit(f"✅ قفل {lock_name} برای {target_name} غیرفعال شد")
                return
        
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
        
        if cmd == 'دشمن' and args and args[0] == 'گروه' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if target_id:
                db.add_enemy(self.user_id, target_id, 'group')
                await event.edit(f"✅ دشمن گروه اضافه شد — هر پیامش با یک اسپم ریپلای می‌شود (پیوی جداست)")
            else:
                await event.edit("⚠️ روی پیام کاربر در گروه ریپلای کنید")
            return
        
        if cmd == 'دوست' and args and args[0] == 'گروه' and len(args) == 1:
            target_id = await get_target_user(event, self.client)
            if target_id:
                db.remove_enemy(self.user_id, target_id, 'group')
                await event.edit(f"✅ دشمن گروه حذف شد")
            else:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
            return
        
        if cmd == 'دشمن' and not args:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.add_enemy(self.user_id, target_id, 'pv')
                if target_id in self.spam_tasks:
                    try:
                        self.spam_tasks[target_id].cancel()
                    except Exception:
                        pass
                    self.spam_tasks.pop(target_id, None)
                await event.edit(f"✅ دشمن پیوی اضافه شد — هر پیام یک اسپم (پیام پاک نمی‌شود)")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
        if cmd == 'دوست' and not args:
            target_id = await get_target_user(event, self.client)
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            if target_id:
                db.remove_enemy(self.user_id, target_id, 'pv')
                await event.edit(f"✅ دوست — دشمن پیوی حذف شد")
                if target_id in self.spam_tasks:
                    try:
                        self.spam_tasks[target_id].cancel()
                    except Exception:
                        pass
                    self.spam_tasks.pop(target_id, None)
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
            return
        
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
        
        if cmd == 'بلاک' and not args:
            if isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
                await self.client(BlockRequest(id=target_id))
                await event.edit("✅ کاربر بلاک شد")
            else:
                await event.edit("⚠️ فقط در پی‌وی")
            return
        
        # ========== ریکت - اصلاح شده برای گروه و پیوی ==========
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
                    try:
                        full_cid = event.chat_id
                        if full_cid and full_cid != chat_id:
                            db.set_reaction(self.user_id, full_cid, target_id, emoji)
                    except Exception:
                        pass
                    await event.edit(f"✅ ریکت {emoji} برای کاربر {target_id} در چت {chat_id} تنظیم شد")
                    
                    try:
                        msg_id = event.message.reply_to_msg_id or event.message.id
                        if event.is_reply:
                            replied = await event.get_reply_message()
                            if replied:
                                msg_id = replied.id
                        input_chat = await event.get_input_chat()
                        await self.client(SendReactionRequest(
                            peer=input_chat,
                            msg_id=msg_id,
                            reaction=[ReactionEmoji(emoticon=emoji)]
                        ))
                        await event.edit(f"✅ ریکت {emoji} روی پیام ارسال شد و برای بعد ذخیره شد")
                    except Exception as e:
                        logger.error(f"خطا در ارسال ریکت: {e}")
                        await event.edit(f"✅ ریکت {emoji} تنظیم شد (ارسال خودکار بعداً فعال است)")
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
        
        if cmd == 'پیوی' and args and args[0] in ['۱', '۲', '۳'] and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_num = int(args[0])
            if ai_num == 1:
                ai_status['ai_1_pm'] = True
                ai_status['ai_2_pm'] = False
                ai_status['ai_3_pm'] = False
                message = '✅ هوش ۱ (Gemini) در پی‌وی روشن شد'
            elif ai_num == 2:
                ai_status['ai_1_pm'] = False
                ai_status['ai_2_pm'] = True
                ai_status['ai_3_pm'] = False
                message = '✅ هوش ۲ (Paxsenix) در پی‌وی روشن شد'
            else:
                ai_status['ai_1_pm'] = False
                ai_status['ai_2_pm'] = False
                ai_status['ai_3_pm'] = True
                message = '✅ هوش ۳ (DeepSeek) در پی‌وی روشن شد'
            db.update_ai_status(self.user_id, ai_status)
            await event.edit(message)
            return
        
        if cmd == 'خاموش' and args and args[0] == 'پیوی' and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_status['ai_1_pm'] = False
            ai_status['ai_2_pm'] = False
            ai_status['ai_3_pm'] = False
            db.update_ai_status(self.user_id, ai_status)
            await event.edit('✅ همه هوش‌ها در پی‌وی خاموش شدند')
            return
        
        if cmd == 'گروه' and args and args[0] in ['۱', '۲', '۳'] and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_num = int(args[0])
            if ai_num == 1:
                ai_status['ai_1_group'] = True
                ai_status['ai_2_group'] = False
                ai_status['ai_3_group'] = False
                message = '✅ هوش ۱ (Gemini) در گروه روشن شد'
            elif ai_num == 2:
                ai_status['ai_1_group'] = False
                ai_status['ai_2_group'] = True
                ai_status['ai_3_group'] = False
                message = '✅ هوش ۲ (Paxsenix) در گروه روشن شد'
            else:
                ai_status['ai_1_group'] = False
                ai_status['ai_2_group'] = False
                ai_status['ai_3_group'] = True
                message = '✅ هوش ۳ (DeepSeek) در گروه روشن شد'
            db.update_ai_status(self.user_id, ai_status)
            await event.edit(message)
            return
        
        if cmd == 'خاموش' and args and args[0] == 'گروه' and len(args) == 1:
            ai_status = settings.get('ai_status', {})
            ai_status['ai_1_group'] = False
            ai_status['ai_2_group'] = False
            ai_status['ai_3_group'] = False
            db.update_ai_status(self.user_id, ai_status)
            await event.edit('✅ همه هوش‌ها در گروه خاموش شدند')
            return
        
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
        
        if cmd == 'وضعیت' and not args:
            settings = db.get_selfbot_settings(self.user_id)
            await event.edit(self.format_status_info(settings))
            return
        
        if cmd == 'پینگ' and not args:
            start = time.time()
            await event.edit("🏓 پینگ: ...")
            end = time.time()
            ping = round((end - start) * 1000, 2)
            await event.edit(f"› 🏓 پینگ: {ping} ms")
            return
        
        if cmd == 'درباره' and not args:
            await event.edit(f"ℹ️ درباره بات\n\n🤖 نسخه: v{BOT_VERSION}\n👨‍💻 سازنده: {BOT_CREATOR}")
            return
        
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
            
            photo_count = 0
            try:
                photos = await self.client(GetUserPhotosRequest(user_id=user.id, offset=0, max_id=0, limit=100))
                if hasattr(photos, 'count') and photos.count is not None:
                    photo_count = int(photos.count)
                elif photos.photos:
                    photo_count = len(photos.photos)
                    offset = len(photos.photos)
                    while len(photos.photos) >= 100:
                        more = await self.client(GetUserPhotosRequest(user_id=user.id, offset=offset, max_id=0, limit=100))
                        if not more.photos:
                            break
                        photo_count += len(more.photos)
                        offset += len(more.photos)
                        if hasattr(more, 'count') and more.count is not None:
                            photo_count = int(more.count)
                            break
                if user.photo and photo_count == 0:
                    photo_count = 1
            except Exception as e:
                logger.debug(f"photo count: {e}")
                photo_count = 1 if getattr(user, 'photo', None) else 0
            
            info_text = f"📋 اطلاعات کاربر:\n\n"
            info_text += f"👤 یوزرنیم: {username}\n"
            info_text += f"🆔 ID: {user_id_info}\n"
            info_text += f"📛 نام: {name}\n"
            info_text += f"📝 بیو: {bio}\n"
            info_text += f"📸 تعداد عکس: {photo_count}"
            
            sent = False
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user_id_info}.jpg")
                    if photo and os.path.exists(photo):
                        await self.client.send_file(event.chat_id, photo, caption=info_text)
                        try:
                            os.remove(photo)
                        except Exception:
                            pass
                        sent = True
                except Exception as e:
                    logger.debug(f"download profile: {e}")
            if not sent:
                try:
                    await self.client.send_message(event.chat_id, info_text + "\n\n📸 عکس پروفایل ندارد")
                except Exception:
                    await event.edit(info_text + "\n\n📸 عکس پروفایل ندارد")
            try:
                await event.delete()
            except Exception:
                pass
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
        
        if cmd == 'سرچ' and not args:
            self.search_mode = True
            await event.edit('🔍 حالت سرچ فعال شد.\n\nاکنون هر متنی که ارسال کنید در گوگل جستجو می‌شود.\nبرای خروج از حالت سرچ، دستور خروج سرچ را ارسال کنید.')
            return
        
        if cmd == 'خروج' and args and args[0] == 'سرچ' and len(args) == 1:
            self.search_mode = False
            self.last_search_results = []
            await event.edit('✅ حالت سرچ غیرفعال شد.')
            return
        
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
        
        if cmd in ['.پنل', 'پنل', '/panel'] and not args:
            try:
                await event.delete()
            except Exception:
                pass
            try:
                bot_username = BOT_USERNAME.replace('@', '')
                results = await self.client.inline_query(bot_username, '')
                if results:
                    await results[0].click(chat_id)
                else:
                    await self.client.send_message(chat_id, "⚠️ پنل یافت نشد. ربات را استارت کنید.")
            except Exception as e:
                try:
                    await self.client.send_message(chat_id, f"❌ خطا در پنل: {str(e)[:120]}")
                except Exception:
                    pass
            return
        
        # ========== پنل کاربر (ریپلای) ==========
        if cmd == 'پنل' and args and args[0] == 'کاربر':
            if not event.message.is_reply:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید و بنویسید: پنل کاربر")
                return
            try:
                reply_msg = await event.get_reply_message()
                target = await reply_msg.get_sender()
                if not target:
                    await event.edit("❌ کاربر یافت نشد")
                    return
                tid = int(target.id)
                panel_lock_targets[self.user_id] = tid
                name = (getattr(target, 'first_name', '') or '')
                if getattr(target, 'last_name', None):
                    name = (name + ' ' + target.last_name).strip()
                if not name:
                    name = f"User {tid}"
                uname = f"@{target.username}" if getattr(target, 'username', None) else "ندارد"
                is_bot = "بله" if getattr(target, 'bot', False) else "خیر"
                is_premium = "بله" if getattr(target, 'premium', False) else "خیر"
                is_enemy_pv = db.is_enemy(self.user_id, tid, 'pv')
                is_enemy_g = db.is_enemy(self.user_id, tid, 'group')
                is_pv_locked = db.is_pv_locked(self.user_id, tid)
                caption = (
                    f"👤 {name}\n"
                    f"🆔 {tid}\n"
                    f"📎 {uname}\n"
                    f"🤖 ربات: {is_bot} | ⭐ پرمیوم: {is_premium}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"دشمن پیوی: {'✅' if is_enemy_pv else '❌'} | دشمن گروه: {'✅' if is_enemy_g else '❌'}\n"
                    f"قفل پیوی: {'✅' if is_pv_locked else '❌'}\n"
                    f"از دکمه‌ها برای مدیریت استفاده کنید"
                )
                avatar_path = None
                try:
                    photos = await self.client.get_profile_photos(target, limit=1)
                    if photos:
                        avatar_path = os.path.join(MEDIA_FOLDER, f"uav_{tid}.jpg")
                        os.makedirs(MEDIA_FOLDER, exist_ok=True)
                        await self.client.download_media(photos[0], file=avatar_path)
                except Exception as e:
                    logger.warning(f"پنل کاربر avatar: {e}")
                photo_path = render_user_panel_image(name, avatar_path)
                kb = get_user_manage_keyboard(self.user_id, tid)
                kb_dict = {
                    'inline_keyboard': [
                        [{'text': b.text, 'callback_data': b.callback_data} for b in row]
                        for row in kb.inline_keyboard
                    ]
                }
                api = f"https://api.telegram.org/bot{BOT_TOKEN}"
                sent = False

                # اولویت ۱: همین چت با Bot API (عکس + دکمه‌ها)
                try:
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, 'rb') as f:
                            r = requests.post(
                                f"{api}/sendPhoto",
                                data={
                                    'chat_id': chat_id,
                                    'caption': caption,
                                    'reply_markup': json.dumps(kb_dict),
                                },
                                files={'photo': ('panel.jpg', f, 'image/jpeg')},
                                timeout=30
                            )
                    else:
                        r = requests.post(
                            f"{api}/sendMessage",
                            json={'chat_id': chat_id, 'text': caption, 'reply_markup': kb_dict},
                            timeout=15
                        )
                    body = r.json() if r.content else {}
                    if r.status_code == 200 and body.get('ok'):
                        sent = True
                        logger.info(f"پنل کاربر → same chat bot OK chat={chat_id}")
                    else:
                        logger.warning(f"پنل کاربر same chat fail: {r.text[:200]}")
                except Exception as e:
                    logger.warning(f"پنل کاربر same chat: {e}")

                # اولویت ۲: پیوی کاربر با ربات (اگر در گروه ربات عضو نباشد)
                if not sent:
                    try:
                        dest = int(self.user_id)
                        if photo_path and os.path.exists(photo_path):
                            with open(photo_path, 'rb') as f:
                                r = requests.post(
                                    f"{api}/sendPhoto",
                                    data={
                                        'chat_id': dest,
                                        'caption': caption,
                                        'reply_markup': json.dumps(kb_dict),
                                    },
                                    files={'photo': ('panel.jpg', f, 'image/jpeg')},
                                    timeout=30
                                )
                        else:
                            r = requests.post(
                                f"{api}/sendMessage",
                                json={'chat_id': dest, 'text': caption, 'reply_markup': kb_dict},
                                timeout=15
                            )
                        body = r.json() if r.content else {}
                        if r.status_code == 200 and body.get('ok'):
                            sent = True
                            try:
                                if photo_path and os.path.exists(photo_path):
                                    await self.client.send_file(chat_id, photo_path, caption=caption)
                            except Exception:
                                pass
                            logger.info(f"پنل کاربر → PV bot OK + photo in chat")
                    except Exception as e:
                        logger.warning(f"پنل کاربر PV fallback: {e}")

                # اولویت ۳: فقط سلف عکس در همین چت
                if not sent:
                    try:
                        if photo_path and os.path.exists(photo_path):
                            await self.client.send_file(chat_id, photo_path, caption=caption)
                        else:
                            await self.client.send_message(chat_id, caption)
                        sent = True
                        try:
                            requests.post(
                                f"{api}/sendMessage",
                                json={
                                    'chat_id': int(self.user_id),
                                    'text': f"👤 مدیریت {name}\nID: {tid}\nاز دکمه‌ها استفاده کن:",
                                    'reply_markup': kb_dict
                                },
                                timeout=12
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"پنل کاربر telethon: {e}")

                for path in (avatar_path, photo_path):
                    try:
                        if path and os.path.exists(path):
                            bn = os.path.basename(path)
                            if bn.startswith('uav_') or bn.startswith('panel_') or bn.startswith('up_'):
                                os.remove(path)
                    except Exception:
                        pass
                try:
                    await event.delete()
                except Exception:
                    pass
                if not sent:
                    await self.client.send_message(chat_id, "❌ ارسال پنل کاربر ناموفق بود. ربات را استارت کنید.")
            except Exception as e:
                logger.error(f"پنل کاربر: {e}\n{traceback.format_exc()}")
                try:
                    await event.edit(f"❌ خطا: {str(e)[:120]}")
                except Exception:
                    pass
            return
        
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
        
        if cmd == 'شروع' and not args:
            await event.delete()
            try:
                await event.respond("🌟 سلف‌بات شروع شد")
            except:
                pass
            return
        
        return
    
    async def update_bio_task(self):
        while self.running:
            try:
                await self.update_bio_with_settings()
            except Exception as e:
                logger.error(f"خطا در update_bio_task برای کاربر {self.user_id}: {e}")
            await asyncio.sleep(60)
    
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
    
    def get_full_date_info(self):
        now = get_now()
        try:
            jdate = jdatetime.date.fromgregorian(date=now.date())
            hijri = Gregorian(now.year, now.month, now.day).to_hijri()
            persian_weekdays = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یک‌شنبه"]
            gregorian_weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            return f"""
ꕀꔚꨄꕣꕥ✺ღდ
📅 تاریخ کامل
━━━━━━━━━━━━━━━━━━━━
🕐 ساعت: {now.strftime('%H:%M:%S')}
📆 شمسی:
{persian_weekdays[jdate.weekday()]} - {jdate.day} {jdate.strftime('%B')} {jdate.year}
📆 میلادی:
{gregorian_weekdays[now.weekday()]} - {now.strftime('%B %d, %Y')}
📆 قمری:
{hijri.day} {hijri.month_name()} {hijri.year}
━━━━━━━━━━━━━━━━━━━━
ꕀꔚꨄꕣꕥ✺ღდ
            """
        except:
            return f"📅 تاریخ: {now.strftime('%Y/%m/%d %H:%M:%S')}"
    
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
    
    async def spam_enemy(self, enemy_id):
        return
        if enemy_id in self.spam_tasks:
            return
        async def spam_task():
            while False and db.is_enemy(self.user_id, enemy_id, 'pv'):
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
                font_index = 0
            time_now = now.strftime("%H:%M")
            time_now_classic = convert_to_classic_font(time_now, font_index)
            try:
                current_name = db.get_current_name(self.user_id)
                if not current_name:
                    current_name = self.BASE_NAME
                if settings.get('flag_enabled'):
                    sel_flags = settings.get('selected_flags', 'all')
                    if sel_flags == 'all' or not sel_flags:
                        use_flags = flags
                    else:
                        use_flags = sel_flags if isinstance(sel_flags, list) else flags
                    if not use_flags:
                        use_flags = flags
                    flag_index = current_minute % len(use_flags)
                    flag = use_flags[flag_index]
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
                logger.error(f"خطا در update_profile_task برای کاربر {self.user_id}: {e}")
            await asyncio.sleep(60)
    
    async def heart_animation(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            message = await self.client.send_message(entity, HEARTS[0])
            for i in range(1, len(HEARTS) * 3):
                await asyncio.sleep(0.8)
                try:
                    await message.edit(HEARTS[i % len(HEARTS)])
                except Exception:
                    break
        except Exception as e:
            logger.error(f"heart_animation: {e}")
    
    async def moon_animation(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            message = await self.client.send_message(entity, MOONS[0])
            for i in range(1, len(MOONS) * 3):
                await asyncio.sleep(0.8)
                try:
                    await message.edit(MOONS[i % len(MOONS)])
                except Exception:
                    break
        except Exception as e:
            logger.error(f"moon_animation: {e}")
    
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
        if ai_status.get('ai_1_pm'):
            active_ai_pm = "هوش ۱ (Gemini)"
        elif ai_status.get('ai_2_pm'):
            active_ai_pm = "هوش ۲ (Paxsenix API)"
        elif ai_status.get('ai_3_pm'):
            active_ai_pm = "هوش ۳ (DeepSeek)"
        active_ai_group = "هیچ هوش فعالی در گروه وجود ندارد"
        if ai_status.get('ai_1_group'):
            active_ai_group = "هوش ۱ (Gemini)"
        elif ai_status.get('ai_2_group'):
            active_ai_group = "هوش ۲ (Paxsenix API)"
        elif ai_status.get('ai_3_group'):
            active_ai_group = "هوش ۳ (DeepSeek)"
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
    
    async def handle_new_message(self, event):
        if not self.my_id:
            return
        
        await self.auto_sync_message(event)
        
        settings = db.get_selfbot_settings(self.user_id)
        if not settings.get('selfbot_enabled', 1):
            return
        chat_id = None
        peer_id = event.message.peer_id
        if isinstance(peer_id, PeerChannel):
            chat_id = peer_id.channel_id
        elif isinstance(peer_id, PeerUser):
            chat_id = peer_id.user_id
        elif isinstance(peer_id, PeerChat):
            chat_id = peer_id.chat_id
        else:
            return
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
            monshi_data = db.get_monshi_status(self.user_id)
            if monshi_data['status'] and monshi_data['answer']:
                try:
                    await event.reply(monshi_data['answer'])
                    return
                except:
                    pass
            
            answers = db.get_answers(self.user_id)
            if answers:
                for question, answer in answers.items():
                    if question in event.message.text:
                        try:
                            await event.reply(answer)
                        except:
                            pass
                        break
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            if settings.get('pv_lock_all'):
                try:
                    await event.message.delete()
                    return
                except:
                    pass
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            if db.is_pv_locked(self.user_id, event.sender_id):
                try:
                    await event.message.delete()
                    return
                except:
                    pass
        
        if await self.handle_media_lock_delete(event):
            return
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out and event.message.text:
            db.cache_message(self.user_id, chat_id, event.message.id, event.message.text)
        
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
        
        # ========== اسپم دشمن (پیوی / گروه) — یک اسپم تصادفی به ازای هر پیام، بدون تکرار پشت‌سرهم ==========
        if not event.message.out and event.sender_id:
            try:
                sender_id = int(event.sender_id)
                is_pv = isinstance(event.message.peer_id, PeerUser)
                chat_type = 'pv' if is_pv else 'group'
                if db.is_enemy(self.user_id, sender_id, chat_type):
                    spam_list = db.get_enemy_spam_messages(self.user_id)
                    candidates = []
                    if spam_list:
                        candidates = [s['text'] for s in spam_list]
                    elif SPAM_MESSAGES:
                        candidates = list(SPAM_MESSAGES)
                    if not candidates:
                        candidates = ["..."]
                    last_key = f"_last_spam_{sender_id}_{chat_type}"
                    last_text = getattr(self, last_key, None)
                    if len(candidates) > 1 and last_text in candidates:
                        choices = [c for c in candidates if c != last_text]
                        spam_text = random.choice(choices)
                    else:
                        spam_text = random.choice(candidates)
                    setattr(self, last_key, spam_text)
                    sent = False
                    try:
                        settings_e = db.get_selfbot_settings(self.user_id)
                        style = settings_e.get('text_style') if settings_e else None
                        text_s, entities = await apply_text_style(spam_text, style)
                        await event.reply(text_s, formatting_entities=entities if entities else None)
                        sent = True
                    except Exception as e:
                        logger.debug(f"اسپم دشمن reply: {e}")
                    if not sent:
                        try:
                            await self.client.send_message(event.chat_id, spam_text, reply_to=event.message.id)
                            sent = True
                        except Exception as e2:
                            logger.error(f"اسپم دشمن send: {e2}")
                    if sent:
                        logger.info(f"اسپم دشمن → user={sender_id} type={chat_type}")
            except Exception as e:
                logger.error(f"خطا در اسپم دشمن: {e}")
        
        # ========== ریکشن خودکار (پیوی + گروه + سوپرگروه + کانال) ==========
        report_short_id = full_chat_id_to_short(self.report_config.report_group_id)
        if not event.message.out and event.sender_id and chat_id != report_short_id:
            sender_id = event.sender_id
            try:
                reaction = db.get_reaction(self.user_id, chat_id, sender_id)
                if not reaction:
                    try:
                        full_cid = event.chat_id
                        if full_cid and full_cid != chat_id:
                            reaction = db.get_reaction(self.user_id, full_cid, sender_id)
                            if reaction:
                                chat_id = full_cid
                    except Exception:
                        pass
                if reaction and reaction in ALLOWED_EMOJIS:
                    reacted = False
                    for peer_getter in (
                        lambda: event.get_input_chat(),
                        lambda: self.client.get_input_entity(event.chat_id),
                        lambda: self.client.get_input_entity(chat_id),
                    ):
                        if reacted:
                            break
                        try:
                            peer = await peer_getter()
                            await self.client(SendReactionRequest(
                                peer=peer,
                                msg_id=event.message.id,
                                reaction=[ReactionEmoji(emoticon=reaction)]
                            ))
                            reacted = True
                        except ChatWriteForbiddenError:
                            logger.warning(f"⚠️ اجازه ریکت در چت {chat_id} نیست")
                            break
                        except FloodWaitError as fl:
                            await asyncio.sleep(min(getattr(fl, 'seconds', 5), 20))
                        except Exception as e:
                            logger.debug(f"ریکت تلاش ناموفق: {e}")
                    if not reacted:
                        logger.error(f"خطا در ارسال ریکت خودکار برای {sender_id} در {chat_id}")
            except Exception as e:
                logger.error(f"خطا در دریافت ریکت از دیتابیس: {e}")
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            sender_id = event.sender_id
            ai_status = settings.get('ai_status', {})
            ai_active = False
            ai_type = None
            if event.message.text:
                if ai_status.get('ai_1_pm'):
                    ai_active = True
                    ai_type = 1
                elif ai_status.get('ai_2_pm'):
                    ai_active = True
                    ai_type = 2
                elif ai_status.get('ai_3_pm'):
                    ai_active = True
                    ai_type = 3
            if ai_active and ai_type:
                try:
                    await self.client(SetTypingRequest(event.chat_id, types.SendMessageTypingAction()))
                    response = await get_ai_response(event.message.text, ai_type, self.user_id)
                    if response:
                        text, entities = await apply_text_style(response, settings.get('text_style'))
                        await event.reply(text, formatting_entities=entities)
                    else:
                        await event.reply("❌ خطا در ارتباط با هوش مصنوعی. لطفاً بعداً تلاش کنید.")
                except Exception as e:
                    logger.error(f"خطا در پاسخ هوش مصنوعی: {e}")
        
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
    
    async def handle_edited_message(self, event):
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
    
    async def handle_deleted_message(self, event):
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
    
    async def handle_report_message(self, event):
        try:
            message = event.message
            if not message:
                return
            if isinstance(message.peer_id, PeerUser) and not message.out:
                if message.text:
                    chat_id = message.peer_id.user_id
                    message_cache[(chat_id, message.id)] = message.text
                if message.media:
                    media_type = self.get_media_type(message)
                    if media_type:
                        saved_path = await self.save_media(message, media_type)
                        if self.report_config.report_ttl_media and hasattr(message.media, 'ttl_seconds') and message.media.ttl_seconds:
                            sender_info = await self.get_user_info(message.sender_id)
                            if saved_path:
                                await self.send_report(
                                    f"⏰ رسانه نابودشونده دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"⏱️ زمان باقی‌مانده: {message.media.ttl_seconds} ثانیه\n"
                                    f"💾 ذخیره شده: ✅",
                                    saved_path,
                                    f"⏰ {media_type} نابودشونده از {sender_info}"
                                )
                            else:
                                await self.send_report(
                                    f"⏰ رسانه نابودشونده دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"⏱️ زمان باقی‌مانده: {message.media.ttl_seconds} ثانیه\n"
                                    f"💾 ذخیره شده: ❌"
                                )
                        elif hasattr(message.media, 'noforwards') and message.media.noforwards:
                            sender_info = await self.get_user_info(message.sender_id)
                            if saved_path:
                                await self.send_report(
                                    f"🚫 رسانه یک‌بارمصرف دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"💾 ذخیره شده: ✅",
                                    saved_path,
                                    f"🚫 {media_type} یک‌بارمصرف از {sender_info}"
                                )
                            else:
                                await self.send_report(
                                    f"🚫 رسانه یک‌بارمصرف دریافت شد\n"
                                    f"👤 از: {sender_info}\n"
                                    f"📦 نوع: {media_type}\n"
                                    f"💾 ذخیره شده: ❌"
                                )
        except Exception as e:
            logger.error(f"خطا در پردازش گزارش پیام: {e}")
    
    async def handle_outgoing_message(self, event):
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
                    except Exception as e:
                        logger.error(f"خطا در ادیت پیام ترجمه شده: {e}")
            except Exception as e:
                logger.error(f"خطا در فرآیند ترجمه: {e}")
    
    async def translate_text(self, text):
        any_lang_active = any(self.translate_mode.values())
        if not any_lang_active:
            return text
        try:
            from deep_translator import GoogleTranslator
        except Exception as e:
            logger.error(
                "❌ کتابخانه deep_translator نصب نیست! "
                "به requirements.txt خط 'deep-translator' رو اضافه کن و ری‌دیپلوی کن. "
                f"جزئیات خطا: {e}"
            )
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
    
    def get_media_type(self, message):
        if not hasattr(message, 'media') or not message.media:
            return None
        if isinstance(message.media, MessageMediaPhoto):
            return 'photo'
        elif isinstance(message.media, MessageMediaDocument):
            document = message.media.document
            if hasattr(document, 'attributes'):
                for attr in document.attributes:
                    if hasattr(attr, 'voice'):
                        return 'voice'
            if hasattr(document, 'mime_type'):
                if 'video' in document.mime_type:
                    for attr in document.attributes:
                        if hasattr(attr, 'voice'):
                            return 'video_note'
                    return 'video'
                elif 'image' in document.mime_type:
                    for attr in document.attributes:
                        if hasattr(attr, 'stickerset'):
                            return 'sticker'
                        elif hasattr(attr, 'animated'):
                            return 'gif'
                    return 'image'
                elif 'audio' in document.mime_type:
                    return 'music'
            if hasattr(document, 'attributes'):
                for attr in document.attributes:
                    if hasattr(attr, 'alt') and attr.alt:
                        return 'sticker'
            return 'file'
        elif isinstance(message.media, MessageMediaWebPage):
            return 'webpage'
        elif hasattr(message.media, 'contact'):
            return 'contact'
        elif hasattr(message.media, 'geo'):
            return 'location'
        return 'unknown'
    
    def get_file_extension(self, media_type):
        extensions = {
            'photo': '.jpg',
            'voice': '.ogg',
            'video': '.mp4',
            'video_note': '.mp4',
            'sticker': '.webp',
            'gif': '.mp4',
            'image': '.jpg',
            'file': '.bin',
            'music': '.mp3'
        }
        return extensions.get(media_type, '.bin')
    
    async def save_media(self, message, media_type):
        try:
            if not self.report_config.auto_save_media:
                return None
            chat_id = message.peer_id.user_id if isinstance(message.peer_id, PeerUser) else (
                message.peer_id.channel_id if isinstance(message.peer_id, PeerChannel) else message.peer_id.chat_id
            )
            timestamp = get_now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{media_type}_{message.sender_id}_{message.id}_{timestamp}"
            file_extension = self.get_file_extension(media_type)
            file_path = os.path.join(REPORT_MEDIA_FOLDER, file_name + file_extension)
            downloaded_path = await self.client.download_media(message.media, file=file_path)
            if downloaded_path and os.path.exists(downloaded_path):
                media_cache[message.id] = {
                    'path': downloaded_path,
                    'type': media_type,
                    'user_id': message.sender_id,
                    'chat_id': chat_id,
                    'caption': message.text or '',
                    'timestamp': timestamp,
                    'file_size': os.path.getsize(downloaded_path),
                    'owner_id': self.user_id
                }
                logger.info(f"رسانه ذخیره شد: {media_type} - {downloaded_path}")
                return downloaded_path
            return None
        except Exception as e:
            logger.error(f"خطا در ذخیره رسانه: {e}")
            return None
    
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

async def inline_panel(update:Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return
    user_id = query.from_user.id
    user_data = db.get_user(str(user_id))
    has_access = False
    if user_id == ADMIN_ID:
        has_access = True
    elif user_data:
        sa = user_data.get('self_active')
        if sa in (1, "1", True, "true", "True"):
            has_access = True
        elif user_data.get('admin_approved') in (1, "1", True) and user_data.get('session_file'):
            sf = user_data.get('session_file')
            if sf and os.path.exists(sf):
                has_access = True
                try:
                    db.update_user(str(user_id), self_active=1)
                except Exception:
                    pass
    if not has_access and str(user_id) in selfbot_managers and getattr(selfbot_managers[str(user_id)], 'running', False):
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
        name = get_main_panel_text(query.from_user)
        keyboard = get_main_panel_keyboard(user_id)
        results = []
        file_id = await get_panel_photo_file_id(context.bot, query.from_user)
        if file_id:
            results.append(
                InlineQueryResultCachedPhoto(
                    id=str(uuid.uuid4()),
                    photo_file_id=file_id,
                    title="⬛ پنل",
                    description="عکس + دکمه‌ها",
                    caption=name,
                    reply_markup=keyboard
                )
            )
        else:
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="⬛ پنل کنترل",
                    description="پنل مدیریت",
                    input_message_content=InputTextMessageContent(name),
                    reply_markup=keyboard
                )
            )
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
            ("☥ هوش مصنوعی", "ai", "مدیریت هوش مصنوعی"),
            ("֎ گزارش", "report", "تنظیم گروه گزارش"),
            ("🛠 ابزار", "tools", "امار گپ / کد QR / تگ ادمین / پین / سلف روشن/خاموش / ساخت استیکر"),
            ("🤖 منشی هوشمند", "monshi", "مدیریت منشی و پاسخ‌های خودکار"),
            ("🏷️ تگ همه", "mention", "تگ کردن همه اعضای گروه"),
            ("🔮 فال", "fortune", "فال عمومی / فال حافظ / فال قهوه")
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
                            InlineKeyboardButton(f"ℹ️ توضیحات", callback_data=f"desc_{cmd}", style="primary"),
                            InlineKeyboardButton(f"▶️ باز کردن", callback_data=f"menu_{cmd}", style="success")
                        ]])
                    )
                )
    await query.answer(results, cache_time=0, is_personal=True)




def _load_panel_base_image():
    from PIL import Image
    ensured = ensure_panel_header_files()
    candidates = [
        ensured,
        PANEL_HEADER_IMAGE,
        "panel_header.png",
        "panel_header_base.png",
        "user_panel_header.png",
        "/app/panel_header.png",
        "/app/panel_header_base.png",
        "/app/user_panel_header.png",
        os.path.join("media_storage", "panel_header.png"),
        os.path.join("media_storage", "panel_header_base.png"),
        os.path.join("media_storage", "user_panel_header.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header_base.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_panel_header.png"),
    ]
    for pth in candidates:
        try:
            if pth and os.path.exists(pth) and os.path.getsize(pth) > 1000:
                return Image.open(pth).convert('RGBA'), pth
        except Exception:
            continue
    logger.error("هیچ تصویر پنل یافت نشد!")
    return None, None


def _composite_panel(username: str, avatar_path: str = None) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
        img, base_path = _load_panel_base_image()
        if img is None:
            return None
        W, H = img.size

        cx = int(round(W * 0.6146))
        cy = int(round(H * 0.4770))
        radius = int(round(min(W, H) * 0.255))
        size = radius * 2

        if avatar_path and os.path.exists(avatar_path):
            try:
                avatar = Image.open(avatar_path).convert('RGBA')
                try:
                    avatar = ImageOps.fit(
                        avatar, (size, size),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5)
                    )
                except Exception:
                    avatar = ImageOps.fit(avatar, (size, size), centering=(0.5, 0.5))
                mask = Image.new('L', (size, size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
                try:
                    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.7))
                except Exception:
                    pass
                avatar.putalpha(mask)
                img.paste(avatar, (cx - radius, cy - radius), avatar)
            except Exception as e:
                logger.debug(f"avatar composite: {e}")

        safe_name = (username or "User")[:22]
        for ch in ('_', '*', '`', '[', ']', '\n', '\r', '|'):
            safe_name = safe_name.replace(ch, ' ')
        safe_name = ' '.join(safe_name.split()) or "User"

        plate_cx = int(W * 0.613)
        plate_cy = int(H * 0.872)
        plate_w = int(W * 0.36)
        plate_h = int(H * 0.065)

        max_text_w = int(plate_w * 0.95)
        max_text_h = int(plate_h * 0.92)

        draw = ImageDraw.Draw(img, 'RGBA')
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        font = ImageFont.load_default()
        tw = th = 0
        for fs in range(max(int(plate_h * 1.6), 30), 14, -1):
            f = None
            for path in font_candidates:
                try:
                    f = ImageFont.truetype(path, fs)
                    break
                except Exception:
                    continue
            if f is None:
                f = ImageFont.load_default()
            try:
                bbox = draw.textbbox((0, 0), safe_name, font=f)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = len(safe_name) * fs // 2, fs
            if tw <= max_text_w and th <= max_text_h:
                font = f
                break

        text_x = plate_cx - tw // 2
        try:
            ascent, descent = font.getmetrics()
            text_y = plate_cy - (ascent - descent) // 2 - 5
        except Exception:
            text_y = plate_cy - th // 2 - 2

        for ox, oy, col in (
            (3, 3, (0, 4, 10, 160)),
            (2, 2, (20, 60, 120, 120)),
            (1, 1, (60, 140, 220, 90)),
            (0, -1, (100, 200, 255, 50)),
        ):
            draw.text((text_x + ox, text_y + oy), safe_name, font=font, fill=col)
        draw.text((text_x, text_y), safe_name, font=font, fill=(175, 245, 255, 255))

        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        out = os.path.join(
            MEDIA_FOLDER,
            f"panel_{abs(hash(safe_name + str(avatar_path or '') + str(W) + 'v12')) % 10**9}.jpg"
        )
        img.convert('RGB').save(out, 'JPEG', quality=94)
        return out
    except Exception as e:
        logger.error(f"_composite_panel: {e}\n{traceback.format_exc()}")
        return None


def render_panel_image(username: str, avatar_path: str = None) -> str:
    return _composite_panel(username, avatar_path)


def render_user_panel_image(username: str, avatar_path: str = None) -> str:
    return _composite_panel(username, avatar_path)


async def get_panel_photo_file_id(bot, user, force_refresh=False):
    user_id = user.id
    if not force_refresh and user_id in panel_photo_cache:
        return panel_photo_cache[user_id]
    name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None) or "User"
    for ch in ('_', '*', '`', '['):
        name = name.replace(ch, ' ')
    avatar_path = None
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            pf = await bot.get_file(photos.photos[0][-1].file_id)
            avatar_path = os.path.join(MEDIA_FOLDER, f"pf_{user_id}.jpg")
            os.makedirs(MEDIA_FOLDER, exist_ok=True)
            await pf.download_to_drive(avatar_path)
    except Exception as e:
        logger.debug(f"avatar for panel: {e}")
    photo_path = render_panel_image(name, avatar_path)
    if avatar_path:
        try:
            os.remove(avatar_path)
        except Exception:
            pass
    if not photo_path or not os.path.exists(photo_path):
        return None
    try:
        with open(photo_path, 'rb') as f:
            msg = await bot.send_photo(chat_id=ADMIN_ID, photo=f)
        file_id = msg.photo[-1].file_id
        panel_photo_cache[user_id] = file_id
        try:
            await bot.delete_message(chat_id=ADMIN_ID, message_id=msg.message_id)
        except Exception:
            pass
        return file_id
    except Exception as e:
        logger.error(f"upload panel photo: {e}")
        return None

def get_main_panel_text(user):
    try:
        name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None) or "User"
    except Exception:
        name = "User"
    for ch in ('_', '*', '`', '['):
        name = name.replace(ch, ' ')
    return name

def get_help_back_keyboard(user_id, back_callback):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback, style="danger")]
    ])

async def safe_edit_panel(query, text, reply_markup=None, parse_mode=None):
    kwargs = {}
    if reply_markup is not None:
        kwargs['reply_markup'] = reply_markup
    if parse_mode:
        kwargs['parse_mode'] = parse_mode
    has_photo = False
    try:
        has_photo = bool(query.message and query.message.photo)
    except Exception:
        pass
    if has_photo:
        try:
            await query.edit_message_caption(caption=text or query.message.caption or " ", **kwargs)
            return True
        except Exception as e:
            logger.debug(f"edit_caption: {e}")
            if reply_markup is not None:
                try:
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
                    return True
                except Exception as e2:
                    logger.debug(f"edit_markup after caption fail: {e2}")
    try:
        await query.edit_message_text(text, **kwargs)
        return True
    except Exception as e1:
        try:
            if reply_markup is not None:
                await query.edit_message_reply_markup(reply_markup=reply_markup)
                return True
        except Exception as e2:
            logger.debug(f"safe_edit_panel: {e1} | {e2}")
    return False

async def refresh_panel_keyboard(query, user_id, menu_text, keyboard_func):
    kb = keyboard_func(user_id)
    ok = await safe_edit_panel(query, menu_text, reply_markup=kb)
    if not ok and kb is not None:
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass

def get_main_panel_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("⏰ زمان و پروفایل", callback_data=f"time_menu_{user_id}", style="primary"),
            InlineKeyboardButton("✨ انیمیشن", callback_data=f"animation_menu_{user_id}", style="primary"),
            InlineKeyboardButton("👤 کاربران", callback_data=f"user_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🔒 قفل رسانه", callback_data=f"lock_menu_{user_id}", style="danger"),
            InlineKeyboardButton("💬 کامنت", callback_data=f"comment_menu_{user_id}", style="success"),
            InlineKeyboardButton("📌 عمومی", callback_data=f"general_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎭 اکشن", callback_data=f"action_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🎮 بازی‌ها", callback_data=f"games_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🌐 ترجمه", callback_data=f"translate_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🔎 گوگل", callback_data=f"google_menu_{user_id}", style="primary"),
            InlineKeyboardButton("ℹ️ اطلاعاتی", callback_data=f"info_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🖼 پروفایل", callback_data=f"profile_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("✍️ استایل متن", callback_data=f"style_menu_{user_id}", style="primary"),
            InlineKeyboardButton("📨 مدیریت پیام", callback_data=f"message_menu_{user_id}", style="primary"),
            InlineKeyboardButton("👍 ریکشن", callback_data=f"reaction_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("💣 اسپم", callback_data=f"spam_menu_{user_id}", style="danger"),
            InlineKeyboardButton("✏️ تغییر پروفایل", callback_data=f"change_menu_{user_id}", style="primary"),
            InlineKeyboardButton("👹 دشمنان", callback_data=f"enemy_menu_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🚫 فیلتر کلمات", callback_data=f"filter_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🛡 حفاظت اسپم", callback_data=f"protection_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🤖 هوش مصنوعی", callback_data=f"ai_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📣 گزارش", callback_data=f"report_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🛠 ابزار", callback_data=f"tools_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🗣 منشی هوشمند", callback_data=f"monshi_menu_{user_id}", style="success"),
            InlineKeyboardButton("📢 تگ همه", callback_data=f"mention_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🔮 فال", callback_data=f"fortune_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("✖️ بستن پنل", callback_data=f"close_panel_{user_id}", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_fortune_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("🌟 فال عمومی", callback_data=f"exec_fortune_general_{user_id}", style="primary")],
        [InlineKeyboardButton("🕌 فال حافظ", callback_data=f"exec_fortune_hafez_{user_id}", style="primary")],
        [InlineKeyboardButton("☕ فال قهوه", callback_data=f"exec_fortune_coffee_{user_id}", style="primary")],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_fortune_help_{user_id}", style="primary")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_time_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    time_enabled = settings.get('time_enabled', False)
    flag_enabled = settings.get('flag_enabled', False)
    keyboard = [
        [
            InlineKeyboardButton(f"🕐 تایم روشن {'' if not time_enabled else '✓'}", callback_data=f"exec_time_on_{user_id}", style="success" if not time_enabled else "primary"),
            InlineKeyboardButton(f"🏳️ تایمر پرچم {'' if not flag_enabled else '✓'}", callback_data=f"exec_time_flag_{user_id}", style="success" if not flag_enabled else "primary")
        ],
        [
            InlineKeyboardButton(f"🚫 تایم خاموش {'' if time_enabled else '✓'}", callback_data=f"exec_time_off_{user_id}", style="danger" if time_enabled else "primary"),
            InlineKeyboardButton("📅 تقویم", callback_data=f"exec_calendar_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🔤 انتخاب فونت تایم", callback_data=f"font_menu_{user_id}", style="primary"),
            InlineKeyboardButton("🏳️ انتخاب پرچم", callback_data=f"flag_menu_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📝 تنظیمات بیو", callback_data=f"bio_menu_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_time_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_font_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    selected = settings.get('time_font_indices', 'all')
    if selected == 'all' or selected is None:
        selected_set = set()
        all_selected = True
    else:
        try:
            selected_set = set(int(x) for x in (selected if isinstance(selected, list) else []))
        except Exception:
            selected_set = set()
        all_selected = False
    keyboard = []
    keyboard.append([
        InlineKeyboardButton(
            f"{'✓ ' if all_selected else ''}همه فونت‌ها (چرخش خودکار)",
            callback_data=f"exec_font_all_{user_id}",
            style="success" if all_selected else "primary"
        )
    ])
    row = []
    for i, font in enumerate(classic_fonts):
        sample = ''.join(font[int(c)] if c.isdigit() else c for c in "123")
        label = f"{'✓ ' if (not all_selected and i in selected_set) else ''}{i}: {sample}"
        row.append(InlineKeyboardButton(label, callback_data=f"exec_font_sel_{i}_{user_id}", style="success" if (not all_selected and i in selected_set) else "primary"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🧹 پاک کردن انتخاب", callback_data=f"exec_font_clear_{user_id}", style="danger")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_flag_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    selected = settings.get('selected_flags', 'all')
    if selected == 'all':
        selected_set = set()
        all_selected = True
    else:
        selected_set = set(selected) if isinstance(selected, list) else set()
        all_selected = False
    keyboard = []
    keyboard.append([
        InlineKeyboardButton(
            f"{'✓ ' if all_selected else ''}همه پرچم‌ها (چرخش خودکار)",
            callback_data=f"exec_flag_all_{user_id}",
            style="success" if all_selected else "primary"
        )
    ])
    row = []
    for i, fl in enumerate(flags):
        label = f"{'✓ ' if (not all_selected and fl in selected_set) else ''}{fl}"
        row.append(InlineKeyboardButton(label, callback_data=f"exec_flag_sel_{i}_{user_id}", style="success" if (not all_selected and fl in selected_set) else "primary"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🧹 پاک کردن انتخاب", callback_data=f"exec_flag_clear_{user_id}", style="danger")])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")])
    return InlineKeyboardMarkup(keyboard)

def get_bio_menu_keyboard(user_id):
    def _on(name):
        return db.get_bio_setting(user_id, name) == 'روشن'
    def _btn(label, key, on):
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{label}",
            callback_data=f"exec_{key}_{user_id}",
            style="success" if on else "primary"
        )
    keyboard = [
        [
            _btn("🕐 ساعت در بیو", "bio_time1", _on('ساعت_در_بیو')),
            _btn("🕐 ساعت در بیو ۲", "bio_time2", _on('ساعت_در_بیو_۲')),
        ],
        [
            _btn("📅 بیو تاریخ", "bio_date", _on('بیو_تاریخ')),
            _btn("📅 بیو کامل", "bio_full", _on('بیو_کامل')),
        ],
        [
            _btn("💕 بیو عاشقانه", "bio_love", _on('بیو_عاشقانه')),
            _btn("🎨 بیو ایموجی", "bio_emoji", _on('بیو_ایموجی')),
        ],
        [
            _btn("🌸 بیو فصل", "bio_season", _on('بیو_فصل')),
            _btn("📆 بیو روز هفته", "bio_weekday", _on('بیو_روز_هفته')),
        ],
        [
            _btn("⏳ شمارش معکوس", "bio_countdown", _on('بیو_شمارش_معکوس')),
            _btn("✏️ متن دلخواه", "bio_custom", _on('بیو_متن_دلخواه')),
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_animation_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("❤️ قلب", callback_data=f"exec_heart_{user_id}", style="primary"),
            InlineKeyboardButton("🌙 ماه", callback_data=f"exec_moon_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("💖 قلب پیشرفته", callback_data=f"exec_advanced_heart_{user_id}", style="primary"),
            InlineKeyboardButton("💝 عشق", callback_data=f"exec_love_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🕯️ سنتت", callback_data=f"exec_santet_{user_id}", style="primary"),
            InlineKeyboardButton("💻 هک", callback_data=f"exec_hack_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🎨 استیکر متن", callback_data=f"exec_sticker_text_{user_id}", style="success")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_animation_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🎲 تاس ۱", callback_data=f"exec_dice_1_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۲", callback_data=f"exec_dice_2_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۳", callback_data=f"exec_dice_3_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎲 تاس ۴", callback_data=f"exec_dice_4_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۵", callback_data=f"exec_dice_5_{user_id}", style="primary"),
            InlineKeyboardButton("🎲 تاس ۶", callback_data=f"exec_dice_6_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎯 دارت", callback_data=f"exec_dart_{user_id}", style="primary"),
            InlineKeyboardButton("🏀 بسکتبال", callback_data=f"exec_basketball_{user_id}", style="primary"),
            InlineKeyboardButton("⚽️ فوتبال", callback_data=f"exec_football_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🎳 بولینگ", callback_data=f"exec_bowling_{user_id}", style="success"),
            InlineKeyboardButton("🎲 تاس کازینو", callback_data=f"exec_casino_dice_{user_id}", style="danger"),
            InlineKeyboardButton("🎨 سه رنگ", callback_data=f"exec_three_colors_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_games_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_info_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 اطلاعات", callback_data=f"exec_info_{user_id}", style="primary"),
            InlineKeyboardButton("⬇️ دانلود پروفایل", callback_data=f"exec_download_profile_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📅 تاریخ ساخت اکانت", callback_data=f"exec_account_age_{user_id}", style="primary"),
            InlineKeyboardButton("📱 نشست‌های فعال", callback_data=f"exec_active_sessions_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🖥️ اطلاعات سیستم", callback_data=f"exec_system_info_{user_id}", style="primary"),
            InlineKeyboardButton("💰 قیمت ارز", callback_data=f"exec_crypto_price_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("💵 نرخ ارز", callback_data=f"exec_global_currency_{user_id}", style="primary"),
            InlineKeyboardButton("🔍 تشخیص متن", callback_data=f"exec_ocr_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_info_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_message_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🧹 حذف کامل", callback_data=f"exec_delete_all_{user_id}", style="danger"),
            InlineKeyboardButton("🧹 حذف کامل ۵۰", callback_data=f"exec_delete_50_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🗑️ حذف ۱۰", callback_data=f"exec_delete_10_{user_id}", style="danger"),
            InlineKeyboardButton("👁️ فعال اتوسین", callback_data=f"exec_autosend_on_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🙈 غیرفعال اتوسین", callback_data=f"exec_autosend_off_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📸 اسکرین‌شات", callback_data=f"exec_screenshot_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_message_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_tools_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📊 امار گپ", callback_data=f"exec_stats_{user_id}", style="primary"),
            InlineKeyboardButton("🝰 کد QR", callback_data=f"exec_qr_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("👑 تگ ادمین", callback_data=f"exec_tag_admin_{user_id}", style="primary"),
            InlineKeyboardButton("📌 پین", callback_data=f"exec_pin_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🤖 سلف روشن", callback_data=f"exec_self_on_{user_id}", style="success"),
            InlineKeyboardButton("⛔ سلف خاموش", callback_data=f"exec_self_off_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🎨 ساخت استیکر", callback_data=f"exec_make_sticker_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_tools_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_monshi_menu_keyboard(user_id):
    monshi_data = db.get_monshi_status(user_id)
    status = monshi_data['status']
    keyboard = [
        [
            InlineKeyboardButton(f"🤖 منشی {'' if not status else '✓'}", callback_data=f"exec_monshi_on_{user_id}", style="success" if not status else "primary"),
            InlineKeyboardButton(f"⛔ خاموش {'' if status else '✓'}", callback_data=f"exec_monshi_off_{user_id}", style="danger" if status else "primary")
        ],
        [
            InlineKeyboardButton("📝 افزودن پاسخ", callback_data=f"exec_add_answer_{user_id}", style="success"),
            InlineKeyboardButton("🗑️ حذف پاسخ", callback_data=f"exec_remove_answer_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📋 لیست پاسخ‌ها", callback_data=f"exec_list_answers_{user_id}", style="primary"),
            InlineKeyboardButton("🧹 پاک کردن پاسخ‌ها", callback_data=f"exec_clear_answers_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_monshi_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_mention_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🏷️ تگ همه [متن]", callback_data=f"exec_mention_all_{user_id}", style="primary"),
            InlineKeyboardButton("⛔ لغو تگ", callback_data=f"exec_cancel_mention_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_mention_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🥷 دشمن", callback_data=f"exec_enemy_{user_id}", style="danger"),
            InlineKeyboardButton("🧸 دوست", callback_data=f"exec_friend_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("👥 دشمن گروه", callback_data=f"exec_enemy_group_{user_id}", style="danger"),
            InlineKeyboardButton("🤝 دوست گروه", callback_data=f"exec_friend_group_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🔒 قفل پیوی", callback_data=f"exec_lock_pv_{user_id}", style="danger"),
            InlineKeyboardButton("🔓 باز پی", callback_data=f"exec_unlock_pv_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🔒 قفل پیوی همه", callback_data=f"exec_lock_all_{user_id}", style="danger"),
            InlineKeyboardButton("🔓 باز پی همه", callback_data=f"exec_unlock_all_{user_id}", style="success"),
            InlineKeyboardButton("⛔ بلاک", callback_data=f"exec_block_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_user_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

panel_lock_targets = {}

def get_lock_menu_keyboard(user_id, target_id=None):
    if target_id is None:
        target_id = panel_lock_targets.get(user_id, 0)
    def _lk(lock_type, label):
        on = db.get_user_lock(user_id, target_id, lock_type)
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{label}",
            callback_data=f"exec_{lock_type}_{user_id}",
            style="success" if on else "danger"
        )
    keyboard = [
        [
            _lk("lock_link", "🔗 لینک"),
            _lk("lock_photo", "📸 عکس"),
            _lk("lock_video", "🎥 ویدیو"),
        ],
        [
            _lk("lock_sticker", "🎨 استیکر"),
            _lk("lock_gif", "🎞️ گیف"),
            _lk("lock_voice", "🎤 ویس"),
        ],
        [
            _lk("lock_file", "📁 فایل"),
            _lk("lock_music", "🎵 موزیک"),
            _lk("lock_video_note", "📹 ویدیو نوت"),
        ],
        [
            _lk("lock_contact", "📞 کانتکت"),
            _lk("lock_location", "📍 لوکیشن"),
            _lk("lock_emoji", "😀 ایموجی"),
        ],
        [
            _lk("lock_text", "📝 متن")
        ],
        [
            InlineKeyboardButton("📖 راهنمای کامل قفل رسانه", callback_data=f"exec_lock_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_manage_keyboard(owner_id, target_id):
    is_enemy_pv = db.is_enemy(owner_id, target_id, 'pv')
    is_enemy_g = db.is_enemy(owner_id, target_id, 'group')
    is_locked_pv = db.is_pv_locked(owner_id, target_id)
    def _lk(lt, label):
        on = db.get_user_lock(owner_id, target_id, lt)
        return InlineKeyboardButton(
            f"{'✓ ' if on else ''}{label}",
            callback_data=f"um_{lt}_{target_id}_{owner_id}",
            style="success" if on else "danger"
        )
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✓ ' if is_enemy_pv else ''}🥷 دشمن پیوی",
                callback_data=f"um_enemy_pv_{target_id}_{owner_id}",
                style="success" if is_enemy_pv else "danger"
            ),
            InlineKeyboardButton(
                f"{'✓ ' if is_enemy_g else ''}👥 دشمن گروه",
                callback_data=f"um_enemy_g_{target_id}_{owner_id}",
                style="success" if is_enemy_g else "danger"
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'✓ ' if is_locked_pv else ''}🔒 قفل پیوی",
                callback_data=f"um_lockpv_{target_id}_{owner_id}",
                style="success" if is_locked_pv else "danger"
            ),
            InlineKeyboardButton(
                "💚 دوست پیوی" if is_enemy_pv else "💚 دوست",
                callback_data=f"um_friend_pv_{target_id}_{owner_id}",
                style="primary"
            ),
        ],
        [
            _lk("lock_sticker", "🎨 استیکر"),
            _lk("lock_photo", "📸 عکس"),
            _lk("lock_video", "🎥 ویدیو"),
        ],
        [
            _lk("lock_gif", "🎞️ گیف"),
            _lk("lock_voice", "🎤 ویس"),
            _lk("lock_music", "🎵 موزیک"),
        ],
        [
            _lk("lock_file", "📁 فایل"),
            _lk("lock_link", "🔗 لینک"),
            _lk("lock_text", "📝 متن"),
        ],
        [
            _lk("lock_contact", "👤 کانتکت"),
            _lk("lock_location", "📍 لوکیشن"),
            _lk("lock_video_note", "🔵 ویدیونوت"),
        ],
        [
            InlineKeyboardButton("✖️ بستن", callback_data=f"um_close_{target_id}_{owner_id}", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_comment_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("💬 کامنت", callback_data=f"exec_comment_{user_id}", style="success"),
            InlineKeyboardButton("📊 کانال‌ها", callback_data=f"exec_channels_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🗑️ حذف کانال", callback_data=f"exec_delete_channel_{user_id}", style="danger"),
            InlineKeyboardButton("🔍 تست کانال", callback_data=f"exec_test_channel_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_comment_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_general_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📊 وضعیت", callback_data=f"exec_status_{user_id}", style="primary"),
            InlineKeyboardButton("ℹ️ درباره", callback_data=f"exec_about_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⏱️ پینگ", callback_data=f"exec_ping_{user_id}", style="primary"),
            InlineKeyboardButton("👤 پنل کاربر", callback_data=f"exec_user_panel_help_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_general_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🎮 اکشن [نام]", callback_data=f"exec_action_{user_id}", style="primary"),
            InlineKeyboardButton("⏹️ اکشن خاموش", callback_data=f"exec_action_off_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📋 اکشن لیست", callback_data=f"exec_action_list_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_action_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_translate_menu_keyboard(user_id):
    translate_mode = {}
    if str(user_id) in selfbot_managers:
        translate_mode = selfbot_managers[str(user_id)].translate_mode
    keyboard = [
        [
            InlineKeyboardButton(f"🇬🇧 انگلیسی {'' if not translate_mode.get('english') else '✓'}", callback_data=f"exec_translate_en_{user_id}", style="success" if not translate_mode.get('english') else "primary"),
            InlineKeyboardButton(f"🇸🇦 عربی {'' if not translate_mode.get('arabic') else '✓'}", callback_data=f"exec_translate_ar_{user_id}", style="success" if not translate_mode.get('arabic') else "primary")
        ],
        [
            InlineKeyboardButton(f"🇮🇱 عبری {'' if not translate_mode.get('hebrew') else '✓'}", callback_data=f"exec_translate_he_{user_id}", style="success" if not translate_mode.get('hebrew') else "primary"),
            InlineKeyboardButton(f"🇷🇺 روسی {'' if not translate_mode.get('russian') else '✓'}", callback_data=f"exec_translate_ru_{user_id}", style="success" if not translate_mode.get('russian') else "primary")
        ],
        [
            InlineKeyboardButton(f"🇹🇷 ترکی {'' if not translate_mode.get('turkish') else '✓'}", callback_data=f"exec_translate_tr_{user_id}", style="success" if not translate_mode.get('turkish') else "primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_translate_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_google_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🔍 سرچ", callback_data=f"exec_search_on_{user_id}", style="success"),
            InlineKeyboardButton("❌ خروج جستجو", callback_data=f"exec_search_off_{user_id}", style="danger"),
            InlineKeyboardButton("🎵 اهنگ", callback_data=f"exec_music_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_google_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_profile_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📸 ست پروف", callback_data=f"exec_set_profile_{user_id}", style="success"),
            InlineKeyboardButton("✏️ ست بیو", callback_data=f"exec_set_bio_{user_id}", style="success")
        ],
        [
            InlineKeyboardButton("🗑️ حذف ست پروف", callback_data=f"exec_delete_profile_{user_id}", style="danger"),
            InlineKeyboardButton("🗑️ حذف ست بیو", callback_data=f"exec_delete_bio_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_profile_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_style_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    current = settings.get('text_style', 'هیچ')
    keyboard = [
        [
            InlineKeyboardButton(f"بولد {'' if current != 'بولد' else '✓'}", callback_data=f"exec_bold_{user_id}", style="primary"),
            InlineKeyboardButton(f"زیرخط {'' if current != 'زیرخط' else '✓'}", callback_data=f"exec_underline_{user_id}", style="primary"),
            InlineKeyboardButton(f"خط خورده {'' if current != 'خط خورده' else '✓'}", callback_data=f"exec_strike_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton(f"نقل قول {'' if current != 'نقل قول' else '✓'}", callback_data=f"exec_quote_{user_id}", style="primary"),
            InlineKeyboardButton(f"اسپویلر {'' if current != 'اسپویلر' else '✓'}", callback_data=f"exec_spoiler_{user_id}", style="primary"),
            InlineKeyboardButton(f"کج {'' if current != 'کج' else '✓'}", callback_data=f"exec_italic_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton(f"کد {'' if current != 'کد' else '✓'}", callback_data=f"exec_code_{user_id}", style="primary"),
            InlineKeyboardButton(f"پیش {'' if current != 'پیش' else '✓'}", callback_data=f"exec_pre_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_style_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reaction_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("👍 ریکت", callback_data=f"exec_reaction_{user_id}", style="success"),
            InlineKeyboardButton("❌ حذف ریکت", callback_data=f"exec_reaction_off_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_reaction_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_spam_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📩 اسپم", callback_data=f"exec_spam_{user_id}", style="danger")],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_spam_help_{user_id}", style="primary")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_change_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("✏️ تغییر اسم", callback_data=f"exec_change_name_{user_id}", style="primary"),
            InlineKeyboardButton("✏️ تغییر بیو", callback_data=f"exec_change_bio_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("📸 تغییر پروفایل", callback_data=f"exec_change_profile_{user_id}", style="success"),
            InlineKeyboardButton("📸 پروف", callback_data=f"exec_change_profile_alt_{user_id}", style="success")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_change_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_enemy_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 لیست دشمن", callback_data=f"exec_enemy_list_{user_id}", style="danger"),
            InlineKeyboardButton("📝 اضافه اسپم", callback_data=f"exec_add_spam_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("✅ اتمام اسپم", callback_data=f"exec_end_spam_{user_id}", style="success"),
            InlineKeyboardButton("📜 لیست اسپم", callback_data=f"exec_spam_list_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("🗑️ پاک کردن اسپم", callback_data=f"exec_clear_spam_{user_id}", style="danger"),
            InlineKeyboardButton("🗑️ حذف اسپم", callback_data=f"exec_delete_spam_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_enemy_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_filter_menu_keyboard(user_id):
    is_enabled = db.get_filter_enabled(user_id)
    keyboard = [
        [
            InlineKeyboardButton("🚫 .فیلتر [کلمه]", callback_data=f"exec_filter_word_{user_id}", style="danger"),
            InlineKeyboardButton(f"✅ فیلتر روشن {'✓' if is_enabled else ''}", callback_data=f"exec_filter_on_{user_id}", style="success" if is_enabled else "secondary")
        ],
        [
            InlineKeyboardButton(f"❌ فیلتر خاموش {'✓' if not is_enabled else ''}", callback_data=f"exec_filter_off_{user_id}", style="danger" if not is_enabled else "secondary"),
            InlineKeyboardButton("📜 لیست / مدیریت کلمات", callback_data=f"exec_filter_list_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_filter_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_filter_words_keyboard(user_id, filters):
    keyboard = []
    if filters:
        for word_info in filters:
            status_icon = "✅" if word_info['enabled'] else "❌"
            word_label = word_info['word']
            if len(word_label) > 20:
                word_label = word_label[:20] + "…"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} {word_label}",
                    callback_data=f"exec_filtertgl_{word_info['id']}_{user_id}",
                    style="success" if word_info['enabled'] else "secondary"
                ),
                InlineKeyboardButton(
                    "🗑️ حذف",
                    callback_data=f"exec_filterdel_{word_info['id']}_{user_id}",
                    style="danger"
                )
            ])
    keyboard.append([
        InlineKeyboardButton("🔄 بروزرسانی لیست", callback_data=f"exec_filter_list_{user_id}", style="primary")
    ])
    keyboard.append([
        InlineKeyboardButton("⚈ بازگشت", callback_data=f"filter_menu_{user_id}", style="danger")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_protection_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🛡️ اسپم روشن", callback_data=f"exec_spam_protection_on_{user_id}", style="success"),
            InlineKeyboardButton("🛡️ اسپم خاموش", callback_data=f"exec_spam_protection_off_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("⚙️ تنظیم اسپم", callback_data=f"exec_spam_settings_{user_id}", style="primary"),
            InlineKeyboardButton("📊 وضعیت اسپم", callback_data=f"exec_spam_status_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_protection_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_ai_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    ai = settings['ai_status']
    keyboard = [
        [
            InlineKeyboardButton(f"🟢 پیوی ۱ {'' if not ai['ai_1_pm'] else '✓'}", callback_data=f"exec_ai_pm_1_{user_id}", style="success" if not ai['ai_1_pm'] else "primary"),
            InlineKeyboardButton(f"🔵 پیوی ۲ {'' if not ai['ai_2_pm'] else '✓'}", callback_data=f"exec_ai_pm_2_{user_id}", style="success" if not ai['ai_2_pm'] else "primary"),
            InlineKeyboardButton(f"🟣 پیوی ۳ {'' if not ai['ai_3_pm'] else '✓'}", callback_data=f"exec_ai_pm_3_{user_id}", style="success" if not ai['ai_3_pm'] else "primary")
        ],
        [
            InlineKeyboardButton("⚫ خاموش پیوی", callback_data=f"exec_ai_pm_off_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton(f"🟢 گروه ۱ {'' if not ai['ai_1_group'] else '✓'}", callback_data=f"exec_ai_group_1_{user_id}", style="success" if not ai['ai_1_group'] else "primary"),
            InlineKeyboardButton(f"🔵 گروه ۲ {'' if not ai['ai_2_group'] else '✓'}", callback_data=f"exec_ai_group_2_{user_id}", style="success" if not ai['ai_2_group'] else "primary"),
            InlineKeyboardButton(f"🟣 گروه ۳ {'' if not ai['ai_3_group'] else '✓'}", callback_data=f"exec_ai_group_3_{user_id}", style="success" if not ai['ai_3_group'] else "primary")
        ],
        [
            InlineKeyboardButton("⚫ خاموش گروه", callback_data=f"exec_ai_group_off_{user_id}", style="danger")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_ai_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_report_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📍 تنظیم گزارش", callback_data=f"exec_set_report_{user_id}", style="success"),
            InlineKeyboardButton("ℹ️ گروه گزارش", callback_data=f"exec_show_report_{user_id}", style="primary")
        ],
        
        [
            InlineKeyboardButton("📖 راهنما", callback_data=f"exec_report_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    q_data = getattr(query, 'data', None)
    q_user = getattr(getattr(query, 'from_user', None), 'id', None)
    print(f"🔘 [DEBUG] کلیک دکمه | user_id={q_user} | callback_data={q_data}")
    try:
        await _button_callback_impl(update, context)
    except Exception as e:
        tb = traceback.format_exc()
        error_block = (
            f"\n{'='*70}\n"
            f"❌❌❌ خطای دکمه پنل ❌❌❌\n"
            f"زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"user_id: {q_user}\n"
            f"callback_data: {q_data}\n"
            f"نوع خطا: {type(e).__name__}\n"
            f"متن خطا: {e}\n"
            f"--- Traceback کامل ---\n{tb}"
            f"{'='*70}\n"
        )
        print(error_block)
        logger.error(error_block)
        try:
            if query:
                await query.answer(f"⚠️ خطا: {type(e).__name__}: {str(e)[:150]}", show_alert=True)
        except Exception:
            pass

async def _button_callback_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    if '_' in data and not data.startswith(('admin_', 'approve_', 'reject_', 'stop_selfbot_', 'restart_selfbot_', 'desc_', 'menu_', 'code_')):
        parts = data.split('_')
        for part in parts:
            if part.isdigit() and len(part) >= 5:
                if part != user_id_str:
                    await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
                    return
                break
    if data.startswith("close_panel_"):
        await query.answer("❌ بستن پنل")
        try:
            await query.message.delete()
        except:
            await query.edit_message_text("✅ پنل بسته شد")
        return
    
    # ========== ورود کد تأیید با دکمه‌های فارسی ==========
    if data.startswith("code_digit_") or data.startswith("code_del_") or data.startswith("code_ok_") or data.startswith("code_back_"):
        await query.answer()
        parts = data.split('_')
        action = parts[1]  # digit / del / ok / back
        user_data = db.get_user(user_id_str)
        if not user_data or user_data.get('step') != 'get_code':
            await query.answer("⚠️ مرحله ورود کد فعال نیست", show_alert=True)
            return
        current_code = user_data.get('code') or ''
        if action == 'digit':
            digit = parts[2]
            if len(current_code) >= 5:
                await query.answer("کد کامل است — تأیید را بزنید", show_alert=False)
                return
            current_code = current_code + digit
            db.update_user(user_id_str, code=current_code)
            display = current_code if len(current_code) >= 5 else (current_code + '•' * (5 - len(current_code)))
            try:
                await query.edit_message_text(
                    f"✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را با دکمه‌های زیر وارد کنید:\n\nکد: `{display}`",
                    reply_markup=query.message.reply_markup,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return
        if action == 'del':
            current_code = current_code[:-1] if current_code else ''
            db.update_user(user_id_str, code=current_code)
            display = '(خالی)' if not current_code else (current_code + '•' * (5 - len(current_code)))
            try:
                await query.edit_message_text(
                    f"✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را با دکمه‌های زیر وارد کنید:\n\nکد: `{display}`",
                    reply_markup=query.message.reply_markup,
                    parse_mode='Markdown'
                )
            except Exception:
                pass
            return
        if action == 'back':
            db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None)
            await query.edit_message_text("🔙 بازگشت\n\nشماره تلفن خود را دوباره وارد کنید:\nمثال: +989123456789")
            return
        if action == 'ok':
            if len(current_code) < 5:
                await query.answer("کد باید ۵ رقم باشد", show_alert=True)
                return
            await query.edit_message_text("⏳ در حال تأیید کد...")
            try:
                session_name = f"user_{user_id_str}"
                session_path = os.path.join(SESSIONS_FOLDER, f"{session_name}.session")
                user_api = get_user_api(user_id_str)
                if not user_api:
                    await query.edit_message_text("❌ خطا در دریافت API")
                    return
                API_ID = user_api["api_id"]
                API_HASH = user_api["api_hash"]
                client = TelegramClient(session_path, API_ID, API_HASH)
                await client.connect()
                user_data = db.get_user(user_id_str)
                await client.sign_in(phone=user_data['phone'], code=current_code, phone_code_hash=user_data['phone_code_hash'])
                expiration_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                db.update_user(user_id_str, self_active=1, session_file=session_path, expiration_date=expiration_date, step=None)
                await client.disconnect()
                manager = SelfBotManager(user_id_str)
                if await manager.start(session_path):
                    selfbot_managers[user_id_str] = manager
                await query.edit_message_text("✅ سلف شما فعال شد")
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"✅ کاربر {user_data.get('full_name')} وارد شد\n🆔 {user_id_str}\n📞 {user_data.get('phone')}"
                    )
                except Exception:
                    pass
            except SessionPasswordNeededError:
                db.update_user(user_id_str, step='get_password')
                await query.edit_message_text("🔐 رمز دو مرحله‌ای را وارد کنید:")
            except Exception as e:
                logger.error(f"کد تأیید: {e}")
                await query.edit_message_text("✖ کد نامعتبر است\nدوباره شماره را وارد کنید")
                db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None)
            return
    
    if data == "back_main":
        name = get_main_panel_text(query.from_user)
        try:
            if query.message and query.message.photo:
                await query.edit_message_caption(
                    caption=name,
                    reply_markup=get_main_panel_keyboard(user_id)
                )
            else:
                await safe_edit_panel(
                    query,
                    name,
                    reply_markup=get_main_panel_keyboard(user_id)
                )
        except Exception:
            try:
                await query.edit_message_reply_markup(
                    reply_markup=get_main_panel_keyboard(user_id)
                )
            except Exception as e:
                logger.debug(f"back_main: {e}")
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
    if data == "admin_backup_db":
        await admin_backup_db_handler(update, context)
        return
    if data == "admin_restore_db":
        await admin_restore_db_handler(update, context)
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
    # ========== پنل مدیریت کاربر (um_) ==========
    if data.startswith("um_"):
        await query.answer()
        try:
            parts = data.split('_')
            owner_id = int(parts[-1])
            if user_id != owner_id and user_id != ADMIN_ID:
                await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
                return
            target_id = int(parts[-2])
            action = '_'.join(parts[1:-2])  # lock_sticker / enemy_pv / lockpv / close
            panel_lock_targets[owner_id] = target_id
            if action == 'close':
                try:
                    await query.message.delete()
                except Exception:
                    pass
                return
            if action == 'enemy_pv':
                if db.is_enemy(owner_id, target_id, 'pv'):
                    db.remove_enemy(owner_id, target_id, 'pv')
                else:
                    db.add_enemy(owner_id, target_id, 'pv')
            elif action == 'friend_pv':
                if db.is_enemy(owner_id, target_id, 'pv'):
                    db.remove_enemy(owner_id, target_id, 'pv')
            elif action == 'enemy_g':
                if db.is_enemy(owner_id, target_id, 'group'):
                    db.remove_enemy(owner_id, target_id, 'group')
                else:
                    db.add_enemy(owner_id, target_id, 'group')
            elif action == 'lockpv':
                if db.is_pv_locked(owner_id, target_id):
                    db.remove_locked_pv(owner_id, target_id)
                else:
                    db.add_locked_pv(owner_id, target_id)
            elif action.startswith('lock_'):
                cur = db.get_user_lock(owner_id, target_id, action)
                db.set_user_lock(owner_id, target_id, action, not cur)
            kb = get_user_manage_keyboard(owner_id, target_id)
            try:
                if query.message and query.message.photo:
                    await query.edit_message_reply_markup(reply_markup=kb)
                else:
                    await query.edit_message_reply_markup(reply_markup=kb)
            except Exception:
                try:
                    await safe_edit_panel(query, query.message.caption or query.message.text or "👤 مدیریت کاربر", reply_markup=kb)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"um_ handler: {e}")
        return

    if data.startswith("exec_"):
        await exec_command_handler(update, context)
        return
    if data.startswith("bio_menu_"):
        await safe_edit_panel(query, "› تنظیمات بیو", reply_markup=get_bio_menu_keyboard(user_id))
        return
    if data.startswith("font_menu_"):
        await safe_edit_panel(query, "› انتخاب فونت تایم", reply_markup=get_font_menu_keyboard(user_id))
        return
    if data.startswith("flag_menu_"):
        await safe_edit_panel(query, "› انتخاب پرچم", reply_markup=get_flag_menu_keyboard(user_id))
        return
    
    parts = data.split('_')
    if len(parts) > 1:
        action = parts[0]
        menu_keyboards = {
            "time": ("⚈ دستورات زمان و پروفایل\n\n• تایم روشن\n• تایمر پرچم روشن\n• تایم خاموش\n• تایم [اعداد]\n• تقویم\n• انتخاب فونت تایم\n• انتخاب پرچم", get_time_menu_keyboard),
            "bio": ("› تنظیمات بیو\n\nانتخاب کنید:", get_bio_menu_keyboard),
            "font": ("› انتخاب فونت تایم\n\nفونت‌های انتخاب‌شده به ترتیب در پروفایل چرخش می‌کنند.", get_font_menu_keyboard),
            "flag": ("› انتخاب پرچم\n\nپرچم‌های انتخاب‌شده در تایمر پرچم استفاده می‌شوند.", get_flag_menu_keyboard),
            "animation": ("☻ انیمیشن‌ها\n\n• قلب\n• ماه\n• قلب پیشرفته\n• عشق\n• سنتت\n• هک\n• استیکر متن", get_animation_menu_keyboard),
            "user": ("☗ مدیریت کاربران\n\n• دشمن / دوست (پیوی)\n• دشمن گروه / دوست گروه\n• قفل پیوی (ریپلای)\n• باز پی (ریپلای)\n• قفل پیوی همه\n• باز پی همه\n• بلاک", get_user_menu_keyboard),
            "lock": ("⊖ قفل رسانه (با ریپلای برای کاربر خاص)\n\n• قفل لینک\n• قفل عکس\n• قفل ویدیو\n• قفل استیکر\n• قفل گیف\n• قفل ویس\n• قفل فایل\n• قفل موزیک\n• قفل ویدیو نوت\n• قفل کانتکت\n• قفل لوکیشن\n• قفل ایموجی\n• قفل متن", get_lock_menu_keyboard),
            "comment": ("✼ کامنت خودکار\n\n• کامنت [متن]\n• کانال‌ها\n• حذف کانال\n• تست کانال", get_comment_menu_keyboard),
            "general": ("✿ دستورات عمومی\n\n• وضعیت\n• درباره\n• پینگ", get_general_menu_keyboard),
            "action": ("☥ اکشن‌ها\n\n• اکشن [نام]\n• اکشن خاموش\n• اکشن لیست\n\nلیست اکشن‌ها:\n• تایپ\n• ویس\n• ویدیو\n• عکس\n• فیلم\n• فایل\n• بازی\n• استیکر\n• موقعیت\n• تماس\n• صحبت\n• لغو", get_action_menu_keyboard),
            "games": ("⚕ بازی‌ها\n\n• تاس [1-6]\n• دارت\n• بسکتبال\n• فوتبال\n• بولینگ\n• تاس کازینو\n• سه رنگ\n• شانس [عدد]", get_games_menu_keyboard),
            "translate": ("❍ ترجمه خودکار\n\n• انگلیسی روشن/خاموش\n• عربی روشن/خاموش\n• عبری روشن/خاموش\n• روسی روشن/خاموش\n• ترکی روشن/خاموش", get_translate_menu_keyboard),
            "google": ("𖢅 گوگل و اهنگ\n\n• سرچ [موضوع]\n• خروج جستجو\n• .اهنگ [نام آهنگ]", get_google_menu_keyboard),
            "info": ("֍ دستورات اطلاعاتی\n\n• اطلاعات (ریپلای)\n• دانلود پروفایل (ریپلای)\n• تاریخ ساخت اکانت\n• نشست‌های فعال\n• اطلاعات سیستم\n• قیمت ارز [نماد]\n• نرخ ارز\n• تشخیص متن (ریپلای عکس)", get_info_menu_keyboard),
            "profile": ("𖢨 مدیریت پروفایل\n\n• ست پروف (ریپلای)\n• ست بیو (ریپلای)\n• حذف ست پروف\n• حذف ست بیو", get_profile_menu_keyboard),
            "style": ("⩐ استایل متن\n\n• بولد\n• زیرخط\n• خط خورده\n• نقل قول\n• اسپویلر\n• کج\n• کد\n• پیش", get_style_menu_keyboard),
            "message": ("𑪡 مدیریت پیام\n\n• حذف کامل\n• حذف کامل ۵۰\n• حذف ۱۰\n• فعال اتوسین\n• غیرفعال اتوسین\n• اسکرین‌شات", get_message_menu_keyboard),
            "reaction": ("☖ ریکشن خودکار\n\n• ریکت [ایموجی] (ریپلای)\n• حذف ریکت (ریپلای)", get_reaction_menu_keyboard),
            "spam": ("𖥞 ارسال اسپم\n\n• اسپم [تعداد] [متن]", get_spam_menu_keyboard),
            "change": ("☗ تغییر پروفایل\n\n• تغییر اسم [نام]\n• تغییر بیو [متن]\n• تغییر پروفایل (ریپلای)\n• پروف (ریپلای)", get_change_menu_keyboard),
            "enemy": ("⚇ مدیریت دشمنان\n\n• لیست دشمن\n• اضافه اسپم\n• اتمام اسپم\n• لیست اسپم\n• پاک کردن اسپم\n• حذف اسپم [شماره]", get_enemy_menu_keyboard),
            "filter": ("✿ فیلتر کلمات\n\n• .فیلتر [کلمه]\n• فیلتر روشن\n• فیلتر خاموش\n• لیست فیلتر\n• حذف فیلتر [کلمه]", get_filter_menu_keyboard),
            "protection": ("⚉ حفاظت اسپم\n\n• اسپم روشن\n• اسپم خاموش\n• تنظیم اسپم [تعداد] [زمان]\n• وضعیت اسپم", get_protection_menu_keyboard),
            "ai": ("☥ هوش مصنوعی\n\n• پیوی ۱/۲/۳\n• خاموش پیوی\n• گروه ۱/۲/۳\n• خاموش گروه", get_ai_menu_keyboard),
            "report": ("֎ گزارش\n\n• تنظیم گزارش\n• گروه گزارش", get_report_menu_keyboard),
            "tools": ("🛠 ابزارها\n\n• امار گپ\n• کد QR\n• تگ ادمین\n• پین\n• سلف روشن/خاموش\n• ساخت استیکر", get_tools_menu_keyboard),
            "monshi": ("🤖 **منشی هوشمند**\n\nمدیریت پاسخ‌های خودکار", get_monshi_menu_keyboard),
            "mention": ("🏷️ **تگ همه**\n\nتگ کردن همه اعضای گروه به صورت ۱۳ نفره", get_mention_menu_keyboard),
            "fortune": ("🔮 **فال و طالع‌بینی**\n\nانتخاب کنید:", get_fortune_menu_keyboard)
        }
        if action in menu_keyboards and parts[1] == "menu":
            text, keyboard_func = menu_keyboards[action]
            await safe_edit_panel(query, text, reply_markup=keyboard_func(user_id))
            return

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
    _raw = data[5:] if data.startswith('exec_') else data
    if _raw.endswith(f'_{user_id}'):
        cmd = _raw[: -(len(str(user_id)) + 1)]
    else:
        cmd = _raw.replace(f'_{user_id}', '')
    
    msg = None
    _silent_prefixes = (
        'bio_', 'time_on', 'time_off', 'time_flag', 'font_', 'flag_',
        'lock_', 'filter_', 'ai_', 'autosend_', 'self_on', 'self_off',
        'monshi_on', 'monshi_off', 'spam_protection_', 'bold', 'underline',
        'strike', 'quote', 'spoiler', 'italic', 'code', 'pre',
        'translate_', 'style_'
    )
    _needs_temp_msg = not any(cmd.startswith(p) or cmd == p.rstrip('_') for p in _silent_prefixes)
    if _needs_temp_msg:
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text="⏳")
        except Exception:
            msg = None
    
    async def _silent_done():
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass
    
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
        'bio_custom': 'بیو_متن_دلخواه',
    }
    for cmd_key, setting_name in bio_commands.items():
        if cmd == cmd_key or cmd.startswith(cmd_key + '_'):
            current = manager.get_bio_setting(setting_name)
            new_status = 'خاموش' if current == 'روشن' else 'روشن'
            if new_status == 'روشن':
                for other_key, other_name in bio_commands.items():
                    if other_name != setting_name:
                        manager.set_bio_setting(other_name, 'خاموش')
            manager.set_bio_setting(setting_name, new_status)
            try:
                await manager.update_bio_with_settings()
            except Exception as e:
                logger.error(f"bio update: {e}")
            await _silent_done()
            try:
                await refresh_panel_keyboard(query, user_id, "📝 تنظیمات بیو", get_bio_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش: {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            return
    
    if cmd == 'fortune_general':
        await manager.fortune_telling(chat_id, msg)
        return
    if cmd == 'fortune_hafez':
        await manager.hafez_fortune(chat_id, msg)
        return
    if cmd == 'fortune_coffee':
        await manager.coffee_fortune(chat_id, msg)
        return
    
    if cmd == 'monshi_on':
        db.set_monshi_status(user_id, True, manager.monshi_answer or "سلام! چطور می‌توانم کمک کنم؟")
        manager.monshi_mode = True
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🗣 منشی", get_monshi_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'monshi_off':
        db.set_monshi_status(user_id, False)
        manager.monshi_mode = False
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🗣 منشی", get_monshi_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'add_answer':
        await msg.edit_text("📝 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nافزودن پاسخ سوال:جواب")
        return
    if cmd == 'remove_answer':
        await msg.edit_text("🗑️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nحذف پاسخ سوال")
        return
    if cmd == 'list_answers':
        answers = db.get_answers(user_id)
        if answers:
            text = "📋 لیست پاسخ‌ها:\n\n"
            for i, (q, a) in enumerate(answers.items(), 1):
                text += f"{i}. ❓ {q}\n   💬 {a}\n\n"
            await msg.edit_text(text)
        else:
            await msg.edit_text("❌ هیچ پاسخی ذخیره نشده")
        return
    if cmd == 'clear_answers':
        conn = sqlite3.connect('main_database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM bot_answers WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        await msg.edit_text("✅ همه پاسخ‌ها پاک شدند")
        return
    
    if cmd == 'mention_all':
        await msg.edit_text("🏷️ لطفاً پیام را به فرمت زیر ارسال کنید:\n\nتگ همه [متن اختیاری]")
        return
    if cmd == 'cancel_mention':
        if query.message.chat_id in manager.mentioning_groups:
            manager.mentioning_groups.discard(query.message.chat_id)
            await msg.edit_text("✅ تگ کردن لغو شد")
        else:
            await msg.edit_text("❌ هیچ تگی در این گروه فعال نیست")
        return
    
    if cmd == 'bowling':
        await msg.edit_text("🎳 در حال بازی بولینگ...")
        asyncio.create_task(manager.force_dice_in_background(query.message.chat_id, "🎳", 6, msg))
        await msg.delete()
        return
    
    if cmd == 'casino_dice':
        await msg.edit_text("🎲 لطفاً عدد ۱ تا ۶ را ارسال کنید (مثال: تاس 5)")
        return
    
    if cmd == 'three_colors':
        colors = ['🔴', '🟢', '🔵']
        seed = user_id
        random.seed(seed)
        user_choice = random.choice(colors)
        random.seed(seed + 100)
        system_choice = random.choice(colors)
        text = f"🎨 **بازی سه رنگ**\n\nرنگ شما: {user_choice}\nرنگ سیستم: {system_choice}\n\n"
        text += "🎉 **برنده شدی!**" if user_choice == system_choice else "😢 **باختی!**"
        await msg.edit_text(text)
        return
    
    if cmd == 'account_age':
        try:
            try:
                await manager.client(UnblockRequest(id="creationdatebot"))
            except:
                pass
            await manager.client.send_message("creationdatebot", "/start")
            await asyncio.sleep(3)
            async for m in manager.client.get_chat_history("creationdatebot", limit=1):
                if m.from_user and m.from_user.username == "creationdatebot":
                    await msg.edit_text(f"📅 **تاریخ ساخت اکانت:**\n{m.text}")
                    break
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'active_sessions':
        try:
            sessions = await manager.client(GetAuthorizationsRequest())
            text = "📱 **نشست‌های فعال:**\n\n"
            for i, session in enumerate(sessions.authorizations, 1):
                text += f"**{i}.** {session.device_model}\n"
                text += f"   📍 {session.country} ({session.ip})\n"
                text += f"   📅 {datetime.fromtimestamp(session.date_active).strftime('%Y/%m/%d %H:%M')}\n"
                text += f"   📱 {session.platform}\n\n"
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'system_info':
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
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'crypto_price':
        await msg.edit_text("💰 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nقیمت ارز [نماد]\nمثال: قیمت ارز BTC")
        return
    
    if cmd == 'global_currency':
        try:
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            response = requests.get(url, timeout=10)
            data = response.json()
            currencies = {
                'USD': 'دلار', 'EUR': 'یورو', 'GBP': 'پوند',
                'AED': 'درهم', 'TRY': 'لیر', 'CHF': 'فرانک', 'CNY': 'یوان'
            }
            text = "💵 **نرخ ارزهای جهانی (هر ۱۰۰۰ واحد):**\n\n"
            for code, name in currencies.items():
                if code in data['rates']:
                    rate = (1 / data['rates'][code]) * 1000
                    text += f"{name}: {rate:,.0f} تومان\n"
            await msg.edit_text(text)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'ocr':
        await msg.edit_text("🔍 لطفاً روی یک عکس ریپلای کنید و دستور تشخیص متن را ارسال کنید")
        return
    
    if cmd == 'sticker_text':
        await msg.edit_text("🎨 لطفاً پیام را به فرمت زیر ارسال کنید:\n\nاستیکر متن [متن]")
        return
    
    if cmd == 'make_sticker':
        await msg.edit_text("🎨 ساخت استیکر:\n\nروی پیام کاربر ریپلای کنید و بنویسید:\n`ساخت استیکر`\n\nاستیکر نقل‌قول از @QuotLyBot بدون فوروارد و بدون متن ارسال می‌شود و چت با ربات پاک می‌شود.")
        return
    
    if cmd == 'screenshot':
        try:
            await manager.client.send(
                types.SendScreenshotNotification(
                    peer=await manager.client.resolve_peer(query.message.chat_id),
                    reply_to_msg_id=0,
                    random_id=manager.client.rnd_id(),
                )
            )
            await msg.edit_text("✅ اسکرین‌شات شبیه‌سازی شد")
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'calendar':
        await manager.handle_calendar_command(query.message)
        await msg.delete()
        return
    
    if cmd == 'stats':
        await msg.edit_text("📊 در حال دریافت آمار گفتگو...")
        target_user_id = None
        if query.message.reply_to_message:
            target_user_id = query.message.reply_to_message.from_user.id
        if not target_user_id and query.message.chat.type == 'private':
            target_user_id = query.message.chat.id
        if not target_user_id:
            await msg.edit_text("⚠️ لطفاً روی پیام کاربر ریپلای کنید یا در پی‌وی از این دستور استفاده کنید")
            return
        stats = await manager.get_chat_stats(query.message.chat_id, target_user_id)
        if not stats:
            await msg.edit_text("⚠️ خطا در دریافت آمار")
            return
        try:
            target_name = await manager.get_user_info(target_user_id)
            my_name = await manager.get_user_info(manager.my_id)
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
            await manager.client.send_message(query.message.chat_id, stats_text)
            await msg.delete()
        except Exception as e:
            await msg.edit_text(f"⚠️ خطا: {str(e)[:100]}")
        return
    
    if cmd == 'qr':
        await msg.edit_text("🝰 در حال تولید کد QR...")
        try:
            if query.message.reply_to_message:
                reply_msg = await manager.client.get_messages(query.message.chat_id, ids=query.message.reply_to_message.message_id)
                if reply_msg.text:
                    qr_path, text = await manager.generate_qr_code(reply_msg.text)
                elif reply_msg.photo:
                    qr_path, text = await manager.generate_qr_code(reply_msg.media, is_photo=True)
                else:
                    await msg.edit_text("⚠️ لطفاً روی یک پیام متنی یا عکس ریپلای کنید")
                    return
            else:
                await msg.edit_text("🝰 لطفاً متنی که می‌خواهید به کد QR تبدیل شود را وارد کنید")
                return
            if qr_path and os.path.exists(qr_path):
                await manager.client.send_file(query.message.chat_id, qr_path, caption=f"🝰 کد QR\n📝 متن: {text[:100]}{'...' if len(text) > 100 else ''}")
                os.remove(qr_path)
                await msg.delete()
            else:
                await msg.edit_text(f"⚠️ خطا در تولید کد QR: {text}")
        except Exception as e:
            await msg.edit_text(f"⚠️ خطا: {str(e)[:100]}")
        return
    
    if cmd == 'tag_admin':
        if not isinstance(query.message.chat, (types.Channel, types.Chat)):
            await msg.edit_text("⚠️ این دستور فقط در گروه کار می‌کند")
            return
        admins = await manager.get_admins(query.message.chat_id)
        if admins:
            admin_text = "👑 ادمین‌های گروه:\n\n"
            for admin in admins:
                mention = f"@{admin.username}" if admin.username else f"[{admin.first_name or 'ادمین'}](tg://user?id={admin.id})"
                admin_text += f"• {mention}\n"
            await msg.edit_text(admin_text, parse_mode='markdown')
        else:
            await msg.edit_text("⚠️ ادمینی یافت نشد")
        return
    
    if cmd == 'pin':
        if query.message.reply_to_message:
            reply_msg = await manager.client.get_messages(query.message.chat_id, ids=query.message.reply_to_message.message_id)
            if await manager.pin_message(query.message.chat_id, reply_msg.id):
                await msg.edit_text("📌 پیام پین شد")
            else:
                await msg.edit_text("⚠️ خطا در پین کردن پیام")
        else:
            await msg.edit_text("⚠️ روی پیام مورد نظر ریپلای کنید")
        return
    
    if cmd == 'self_on':
        db.update_selfbot_setting(user_id, 'selfbot_enabled', 1)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
        except Exception:
            pass
        return
    
    if cmd == 'self_off':
        db.update_selfbot_setting(user_id, 'selfbot_enabled', 0)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🛠 ابزارها", get_tools_menu_keyboard)
        except Exception:
            pass
        return
    
    if cmd.startswith('time_on'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.update_profile_name()
        try:
            await msg.delete()
        except Exception:
            pass
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل", get_time_menu_keyboard)
        return
    if cmd.startswith('time_flag'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)
        await manager.update_profile_name()
        try:
            await msg.delete()
        except Exception:
            pass
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل", get_time_menu_keyboard)
        return
    if cmd.startswith('time_off'):
        db.update_selfbot_setting(user_id, 'time_enabled', 0)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.restore_profile_name()
        try:
            await msg.delete()
        except Exception:
            pass
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل", get_time_menu_keyboard)
        return
    
    # ========== فونت تایم ==========
    async def _refresh_font_kb():
        kb = get_font_menu_keyboard(user_id)
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
            return
        except Exception:
            pass
        try:
            await safe_edit_panel(query, "› انتخاب فونت تایم", reply_markup=kb)
        except Exception as e:
            print(f"refresh font: {e}")

    if cmd == 'font_all':
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = 'all'
        await _refresh_font_kb()
        return
    if cmd == 'font_clear':
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = 'all'
        await _refresh_font_kb()
        return
    if cmd.startswith('font_sel_'):
        try:
            idx = int(cmd.split('_')[2])
        except Exception:
            return
        settings = db.get_selfbot_settings(user_id)
        current = settings.get('time_font_indices', 'all')
        if current == 'all':
            new_list = [idx]
        else:
            new_list = [int(x) for x in current] if isinstance(current, list) else []
            if idx in new_list:
                new_list.remove(idx)
            else:
                new_list.append(idx)
            new_list = sorted(set(new_list))
        if not new_list:
            val = 'all'
            new_list = 'all'
        else:
            val = ','.join(map(str, new_list))
        db.update_selfbot_setting(user_id, 'time_font_indices', val)
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = new_list
        await _refresh_font_kb()
        return
    
    # ========== پرچم ==========
    async def _refresh_flag_kb():
        kb = get_flag_menu_keyboard(user_id)
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
            return
        except Exception:
            pass
        try:
            await safe_edit_panel(query, "› انتخاب پرچم", reply_markup=kb)
        except Exception as e:
            print(f"refresh flag: {e}")

    if cmd == 'flag_all':
        db.update_selfbot_setting(user_id, 'selected_flags', 'all')
        await _refresh_flag_kb()
        return
    if cmd == 'flag_clear':
        db.update_selfbot_setting(user_id, 'selected_flags', 'all')
        await _refresh_flag_kb()
        return
    if cmd.startswith('flag_sel_'):
        try:
            idx = int(cmd.split('_')[2])
            fl = flags[idx]
        except Exception:
            return
        settings = db.get_selfbot_settings(user_id)
        current = settings.get('selected_flags', 'all')
        if current == 'all':
            new_list = [fl]
        else:
            new_list = list(current) if isinstance(current, list) else []
            if fl in new_list:
                new_list.remove(fl)
            else:
                new_list.append(fl)
        if not new_list:
            val = 'all'
            new_list = 'all'
        else:
            val = ','.join(new_list)
        db.update_selfbot_setting(user_id, 'selected_flags', val)
        await _refresh_flag_kb()
        return
    
    # ========== راهنمای قفل رسانه ==========
    if cmd == 'lock_help':
        help_text = """📖 **راهنمای کامل قفل رسانه**

این بخش برای محدود کردن ارسال انواع رسانه در پی‌وی یا گروه است.

🔹 **نحوه استفاده:**
• روی پیام کاربر ریپلای کنید و سپس دکمه قفل مورد نظر را بزنید → فقط برای همان کاربر قفل می‌شود.
• اگر در پی‌وی بدون ریپلای بزنید → برای همان چت اعمال می‌شود.
• قفل‌ها قابل روشن/خاموش هستند (دوباره زدن = غیرفعال).

📋 **لیست قفل‌ها و کاربرد:**

🔗 **قفل لینک** — پیام‌های حاوی لینک (http/t.me/www و دامنه) حذف یا مسدود می‌شوند.
📸 **قفل عکس** — ارسال عکس مسدود می‌شود.
🎥 **قفل ویدیو** — ارسال ویدیو مسدود می‌شود.
🎨 **قفل استیکر** — ارسال استیکر مسدود می‌شود.
🎞️ **قفل گیف** — ارسال گیف/انیمیشن مسدود می‌شود.
🎤 **قفل ویس** — ارسال ویس/صدا مسدود می‌شود.
📁 **قفل فایل** — ارسال فایل/سند مسدود می‌شود.
🎵 **قفل موزیک** — ارسال موزیک/آهنگ مسدود می‌شود.
📹 **قفل ویدیو نوت** — ارسال ویدیو نوت (دایره‌ای) مسدود می‌شود.
📞 **قفل کانتکت** — ارسال مخاطب/شماره مسدود می‌شود.
📍 **قفل لوکیشن** — ارسال موقعیت مکانی مسدود می‌شود.
😀 **قفل ایموجی** — پیام‌هایی که فقط از ایموجی تشکیل شده‌اند مسدود می‌شوند.
📝 **قفل متن** — ارسال پیام متنی ساده مسدود می‌شود.

⚠️ **نکته:** قفل‌ها فقط روی پیام‌های ورودی دیگران اعمال می‌شوند و روی پیام‌های خود شما تأثیری ندارند. برای قفل کلی پی‌وی از بخش «مدیریت کاربران» استفاده کنید."""
        try:
            await query.edit_message_text(
                help_text,
                reply_markup=get_help_back_keyboard(user_id, f"lock_menu_{user_id}")
            )
        except Exception:
            await msg.edit_text(help_text, reply_markup=get_help_back_keyboard(user_id, f"lock_menu_{user_id}"))
        try:
            await msg.delete()
        except Exception:
            pass
        return
    

    # ========== راهنماهای بخش‌ها ==========
    HELP_TEXTS = {
        'google_help': """📖 راهنمای گوگل و آهنگ

› 🔍 سرچ — حالت جستجوی گوگل را روشن می‌کند. بعد از روشن شدن، هر متنی بفرستید جستجو می‌شود.
› ❌ خروج جستجو — حالت سرچ را خاموش می‌کند.
› 🎵 آهنگ — برای پخش آهنگ از دستور `.اهنگ [نام]` استفاده کنید.

مثال: `.اهنگ شادمهر`""",
        'time_help': """📖 راهنمای زمان و پروفایل

› 🕐 تایم روشن — ساعت را در اسم پروفایل نمایش می‌دهد.
› 🏳️ تایمر پرچم — علاوه بر ساعت، پرچم هم در اسم می‌چرخد.
› 🚫 تایم خاموش — نمایش ساعت/پرچم را قطع می‌کند.
› 📅 تقویم — تاریخ شمسی و میلادی را نشان می‌دهد.
› 🔤 انتخاب فونت تایم — فونت‌های ساعت را انتخاب کنید (چندتایی با تیک).
› 🏳️ انتخاب پرچم — پرچم‌های مورد نظر را برای چرخش انتخاب کنید.
› 📝 تنظیمات بیو — ساعت/تاریخ/فصل و ... را در بیو قرار دهید.""",
        'animation_help': """📖 راهنمای انیمیشن

› ❤️ قلب — انیمیشن ساده قلب
› 🌙 ماه — انیمیشن ماه
› 💖 قلب پیشرفته — انیمیشن چندمرحله‌ای قلب
› 💝 عشق — انیمیشن I Love You
› 🕯️ سنتت — نوار پیشرفت تقلبی
› 💻 هک — انیمیشن هک تقلبی
› 🎨 استیکر متن — ساخت استیکر از متن با دستور `استیکر متن [متن]`""",
        'user_help': """📖 راهنمای مدیریت کاربران

› 🥷 دشمن — ریپلای در پیوی: هر پیام دشمن با یک اسپم جواب داده می‌شود (پیام پاک نمی‌شود).
› 🧸 دوست — پایان دشمن پیوی.
› 👥 دشمن گروه — ریپلای در گروه: فقط در گروه روی همان کاربر اسپم ریپلای می‌شود.
› 🧸 دوست گروه — پایان دشمن گروه.
› 🔒 قفل پیوی — پیام‌های آن کاربر در پی‌وی حذف می‌شود.
› 🔓 باز پی — قفل پی‌وی را برمی‌دارد.
› 🔒 قفل پیوی همه — همه پی‌وی‌ها قفل می‌شوند.
› 🔓 باز پی همه — قفل همگانی برداشته می‌شود.
› ⛔ بلاک — کاربر را بلاک می‌کند (با ریپلای).""",
        'comment_help': """📖 راهنمای کامنت خودکار

› 💬 کامنت [متن] — برای کانال فعلی متن کامنت خودکار تنظیم می‌کند.
› 📊 کانال‌ها — لیست کانال‌های تنظیم‌شده را نشان می‌دهد.
› 🗑️ حذف کانال — تنظیمات کانال فعلی را حذف می‌کند.
› 🔍 تست کانال — وضعیت تنظیمات کانال فعلی را چک می‌کند.

نکته: در کانال/گروه مرتبط دستور `کامنت متن شما` را بزنید.""",
        'general_help': """📖 راهنمای عمومی

› 📊 وضعیت — وضعیت فعلی سلف‌بات و تنظیمات.
› ℹ️ درباره — نسخه و سازنده.
› ⏱️ پینگ — تأخیر پاسخ ربات.
› 👤 پنل کاربر — روی پیام هر کاربر ریپلای کنید و بنویسید: پنل کاربر
  عکس پروفایل + اطلاعات + دکمه‌های قفل/دشمن برای همان کاربر می‌آید.
  (در گروه و پیوی کار می‌کند)""",
        'action_help': """📖 راهنمای اکشن

› 🎮 اکشن [نام] — وضعیت در حال انجام را شبیه‌سازی می‌کند.
› ⏹️ اکشن خاموش — اکشن فعال را قطع می‌کند.
› 📋 اکشن لیست — لیست اکشن‌های موجود.

اکشن‌ها: تایپ، ویس، ویدیو، عکس، فیلم، فایل، بازی، استیکر، موقعیت، تماس، صحبت، لغو""",
        'games_help': """📖 راهنمای بازی‌ها

› 🎲 تاس ۱ تا ۶ — تاس می‌اندازد تا عدد هدف بیاید.
› 🎯 دارت — تا ۶ بیاید.
› 🏀 بسکتبال — تا ۵ بیاید.
› ⚽️ فوتبال — تا ۵ بیاید.
› 🎳 بولینگ — تا ۶ بیاید.
› 🎨 سه رنگ — بازی شانسی رنگ.
› دستور متنی: `شانس [عدد]` و `تاس [عدد]`""",
        'translate_help': """📖 راهنمای ترجمه خودکار

با روشن کردن هر زبان، پیام‌های خروجی شما به آن زبان ترجمه و ارسال می‌شوند.
› 🇬🇧 انگلیسی | 🇸🇦 عربی | 🇮🇱 عبری | 🇷🇺 روسی | 🇹🇷 ترکی

› روی دکمه بزنید تا روشن/خاموش شود (تیک ✓).""",
        'info_help': """📖 راهنمای اطلاعاتی

› 📋 اطلاعات — اطلاعات کاربر با ریپلای.
› ⬇️ دانلود پروفایل — عکس پروفایل کاربر (ریپلای).
› 📅 تاریخ ساخت اکانت — از ربات creationdatebot.
› 📱 نشست‌های فعال — لیست دستگاه‌های لاگین.
› 🖥️ اطلاعات سیستم — RAM/CPU سرور.
› 💰 قیمت ارز — دستور: `قیمت ارز BTC`
› 💵 نرخ ارز — نرخ ارزهای جهانی.
› 🔍 تشخیص متن — OCR روی عکس (ریپلای).""",
        'profile_help': """📖 راهنمای پروفایل

› 📸 ست پروف — عکس ریپلای‌شده را پروفایل می‌کند.
› ✏️ ست بیو — متن ریپلای را بیو می‌کند.
› 🗑️ حذف ست پروف / بیو — پروفایل یا بیو را پاک می‌کند.""",
        'style_help': """📖 راهنمای استایل متن

با فعال کردن هر استایل، پیام‌های خروجی شما با آن فرمت ارسال می‌شوند:
› بولد، زیرخط، خط خورده، نقل قول، اسپویلر، کج، کد، پیش

› دوباره زدن همان دکمه = خاموش.""",
        'message_help': """📖 راهنمای مدیریت پیام

› 🧹 حذف کامل — همه پیام‌های شما در چت.
› 🧹 حذف کامل ۵۰ — ۵۰ پیام آخر شما.
› 🗑️ حذف ۱۰ — ۱۰ پیام آخر.
› 👁️ فعال اتوسین — پیام‌های دریافتی خودکار سین می‌شوند.
› 🙈 غیرفعال اتوسین
› 📸 اسکرین‌شات — نوتیفیکیشن اسکرین‌شات شبیه‌سازی.""",
        'reaction_help': """📖 راهنمای ریکشن

› 👍 ریکت — با ریپلای روی پیام کاربر + دستور `ریکت 🔥` ریکت خودکار تنظیم می‌شود.
› در گروه و پی‌وی کار می‌کند.
› ❌ حذف ریکت — با ریپلای، ریکت آن کاربر را حذف می‌کند.

› ایموجی‌های مجاز در لیست ALLOWED_EMOJIS هستند.""",
        'spam_help': """📖 راهنمای اسپم

› 📩 اسپم — دستور: `اسپم [تعداد] [متن]`
مثال: `اسپم 5 سلام`

› برای دشمنان از بخش مدیریت دشمنان استفاده کنید.""",
        'change_help': """📖 راهنمای تغییر پروفایل

› ✏️ تغییر اسم [نام] — اسم پروفایل را عوض می‌کند.
› ✏️ تغییر بیو [متن] — بیو را عوض می‌کند.
› 📸 تغییر پروفایل / پروف — با ریپلای روی عکس.""",
        'enemy_help': """📖 راهنمای دشمنان

› 📋 لیست دشمن — دشمنان پیوی/گروه.
› 📝 اضافه اسپم — متن‌های اسپم دشمن.
› ⚠️ دشمن پیوی پیام را پاک نمی‌کند؛ فقط یک اسپم به ازای هر پیام می‌فرستد.
› ✅ اتمام اسپم — خروج از حالت افزودن.
› 📜 لیست اسپم — متن‌های اسپم ذخیره‌شده.
› 🗑️ پاک کردن / حذف اسپم — مدیریت لیست اسپم.""",
        'filter_help': """📖 راهنمای فیلتر کلمات

› 🚫 .فیلتر [کلمه] — کلمه را به لیست فیلتر اضافه می‌کند.
› ✅ فیلتر روشن — فیلتر فعال می‌شود (پیام حاوی کلمه حذف می‌شود).
› ❌ فیلتر خاموش
› 📜 لیست / مدیریت — روشن/خاموش یا حذف هر کلمه.""",
        'protection_help': """📖 راهنمای حفاظت اسپم

› 🛡️ اسپم روشن/خاموش — محافظت در برابر اسپم دیگران.
› ⚙️ تنظیم اسپم [تعداد] [ثانیه] — محدودیت و زمان میوت.
› 📊 وضعیت اسپم — تنظیمات فعلی.""",
        'ai_help': """📖 راهنمای هوش مصنوعی

پیوی ۱/۲/۳ و گروه ۱/۲/۳:
› ۱ = Gemini
› ۲ = Paxsenix
› ۳ = DeepSeek

با روشن کردن، پیام‌های دریافتی در آن محیط با AI پاسخ داده می‌شوند.
› خاموش پیوی / خاموش گروه همه را قطع می‌کند.""",
        'report_help': """📖 راهنمای گزارش

› 📍 تنظیم گزارش — گروه گزارش را تنظیم می‌کند.
› ℹ️ گروه گزارش — آیدی گروه فعلی را نشان می‌دهد.

› پس از عضویت، یک گروه خصوصی «گزارش دهی» به‌صورت خودکار ساخته و سنجاق می‌شود.
› می‌توانید گروه یا کانال دیگری (مثلاً سیو مسیج) را هم با دستور `تنظیم گزارش` جایگزین کنید.
› پیام‌های حذف‌شده/ویرایش‌شده و مدیا به گروه گزارش ارسال می‌شوند.""",
        'tools_help': """📖 راهنمای ابزار

› 📊 امار گپ — آمار گفتگو با کاربر (ریپلای یا پی‌وی).
› 🝰 کد QR — ساخت QR از متن/عکس (ریپلای).
› 👑 تگ ادمین — منشن ادمین‌های گروه.
› 📌 پین — پین کردن پیام ریپلای‌شده.
› 🤖 سلف روشن/خاموش — فعال/غیرفعال کردن سلف‌بات.
› 🎨 ساخت استیکر — ریپلای روی پیام کاربر + دستور `ساخت استیکر` → استیکر نقل‌قول از @QuotLyBot بدون فوروارد و بدون متن.""",
        'monshi_help': """📖 راهنمای منشی هوشمند

› 🤖 منشی — با دستور `منشی [پاسخ]` فعال می‌شود.
› ⛔ خاموش — منشی را قطع می‌کند.
› 📝 افزودن پاسخ — فرمت: `افزودن پاسخ سوال:جواب`
› 🗑️ حذف پاسخ — `حذف پاسخ سوال`
› 📋 لیست پاسخ‌ها
› 🧹 پاک کردن پاسخ‌ها""",
        'mention_help': """📖 راهنمای تگ همه

› 🏷️ تگ همه [متن] — همه اعضای گروه را ۱۳نفره منشن می‌کند.
› ⛔ لغو تگ — عملیات تگ را متوقف می‌کند.

فقط در گروه کار می‌کند.""",
        'fortune_help': """📖 راهنمای فال

› 🌟 فال عمومی — یک فال تصادفی.
› 🕌 فال حافظ — بیت حافظ.
› ☕ فال قهوه — فال قهوه.""",
    }
    HELP_BACK = {
        'google_help': f'google_menu_{user_id}',
        'time_help': f'time_menu_{user_id}',
        'animation_help': f'animation_menu_{user_id}',
        'user_help': f'user_menu_{user_id}',
        'lock_help': f'lock_menu_{user_id}',
        'comment_help': f'comment_menu_{user_id}',
        'general_help': f'general_menu_{user_id}',
        'action_help': f'action_menu_{user_id}',
        'games_help': f'games_menu_{user_id}',
        'translate_help': f'translate_menu_{user_id}',
        'info_help': f'info_menu_{user_id}',
        'profile_help': f'profile_menu_{user_id}',
        'style_help': f'style_menu_{user_id}',
        'message_help': f'message_menu_{user_id}',
        'reaction_help': f'reaction_menu_{user_id}',
        'spam_help': f'spam_menu_{user_id}',
        'change_help': f'change_menu_{user_id}',
        'enemy_help': f'enemy_menu_{user_id}',
        'filter_help': f'filter_menu_{user_id}',
        'protection_help': f'protection_menu_{user_id}',
        'ai_help': f'ai_menu_{user_id}',
        'report_help': f'report_menu_{user_id}',
        'tools_help': f'tools_menu_{user_id}',
        'monshi_help': f'monshi_menu_{user_id}',
        'mention_help': f'mention_menu_{user_id}',
        'fortune_help': f'fortune_menu_{user_id}',
    }
    if cmd in HELP_TEXTS or (cmd.endswith('_help') and cmd in HELP_TEXTS):
        help_body = HELP_TEXTS.get(cmd, "راهنما موجود نیست")
        back_cb = HELP_BACK.get(cmd, 'back_main')
        try:
            import html as _html
            quoted = "<blockquote>" + _html.escape(help_body) + "</blockquote>"
            ok = await safe_edit_panel(
                query,
                quoted,
                reply_markup=get_help_back_keyboard(user_id, back_cb),
                parse_mode='HTML'
            )
            if not ok:
                await query.answer("راهنما", show_alert=False)
        except Exception:
            try:
                await query.edit_message_caption(
                    caption=help_body[:1024],
                    reply_markup=get_help_back_keyboard(user_id, back_cb)
                )
            except Exception:
                await msg.edit_text(help_body, reply_markup=get_help_back_keyboard(user_id, back_cb))
        try:
            await msg.delete()
        except Exception:
            pass
        return

    translate_commands = {
        'translate_en': 'english',
        'translate_ar': 'arabic',
        'translate_he': 'hebrew',
        'translate_ru': 'russian',
        'translate_tr': 'turkish'
    }
    for cmd_prefix, lang in translate_commands.items():
        if cmd.startswith(cmd_prefix):
            manager.translate_mode[lang] = not manager.translate_mode[lang]
            db.update_selfbot_setting(user_id, f'translate_{lang}', 1 if manager.translate_mode[lang] else 0)
            status = "✓ روشن" if manager.translate_mode[lang] else "✗ خاموش"
            await msg.edit_text(f"✅ ترجمه {lang} {status} شد")
            try:
                await refresh_panel_keyboard(query, user_id, "🌐 ترجمه — به‌روز شد", get_translate_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            return
    
    if cmd == 'advanced_heart':
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            heart_msg = await manager.client.send_message(query.message.chat_id, "❤️")
            await advanced_heart_animation(heart_msg)
        except Exception as e:
            logger.error(f"advanced_heart: {e}")
        return
    if cmd == 'love':
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            love_msg = await manager.client.send_message(query.message.chat_id, "💝")
            await advanced_heart_animation(love_msg)
        except Exception as e:
            logger.error(f"love anim: {e}")
        return
    if cmd == 'santet':
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            santet_msg = await manager.client.send_message(query.message.chat_id, "🕯️")
            for i in range(101):
                bar_len = int(i / 100 * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                await santet_msg.edit(f"🕯️ {i}% [{bar}]")
                await asyncio.sleep(0.03)
            await asyncio.sleep(1)
            await santet_msg.edit("✅ انجام شد 🥴")
        except Exception as e:
            logger.error(f"santet: {e}")
        return
    if cmd == 'hack':
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            hack_msg = await manager.client.send_message(query.message.chat_id, "💻")
            await asyncio.sleep(2)
            await hack_msg.edit("User online: True\nTelegram access: True\nRead Storage: True")
            await asyncio.sleep(2)
            await hack_msg.edit("Hacking... 0%\n[░░░░░░░░░░░░░░░░░░░░]")
            await asyncio.sleep(2)
            await hack_msg.edit("Hacking... 25%\n[█████░░░░░░░░░░░░░░░]")
            await asyncio.sleep(2)
            await hack_msg.edit("Hacking... 50%\n[██████████░░░░░░░░░░]")
            await asyncio.sleep(2)
            await hack_msg.edit("Hacking... 75%\n[███████████████░░░░░]")
            await asyncio.sleep(2)
            await hack_msg.edit("Hacking... 100%\n[████████████████████]")
            await asyncio.sleep(2)
            await hack_msg.edit("✅ هک کامل شد")
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    
    if cmd == 'user_panel_help':
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        help_txt = (
            "👤 پنل کاربر\n\n"
            "روی پیام هر کاربر (در گروه یا پیوی) ریپلای کنید و بنویسید:\n"
            "`پنل کاربر`\n\n"
            "سپس عکس پروفایل + اطلاعات + دکمه‌های قفل/دشمن برای همان کاربر می‌آید."
        )
        try:
            await context.bot.send_message(chat_id=chat_id, text=help_txt, parse_mode='Markdown')
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=help_txt.replace('`', ''))
            except Exception:
                pass
        return

    if cmd == 'status':
        settings = db.get_selfbot_settings(user_id)
        await msg.edit_text(manager.format_status_info(settings))
        return
    if cmd == 'about':
        await msg.edit_text(f"ℹ️ درباره بات\n\n🤖 نسخه: v{BOT_VERSION}\n👨‍💻 سازنده: {BOT_CREATOR}")
        return
    if cmd == 'ping':
        start = time.time()
        await msg.edit_text("🏓 پینگ: ...")
        end = time.time()
        ping = round((end - start) * 1000, 2)
        await msg.edit_text(f"› 🏓 پینگ: {ping} ms")
        return
    if cmd == 'music':
        await msg.edit_text("🎵 دستور اهنگ\n\nبرای جستجو و پخش آهنگ از فرمت زیر استفاده کنید:\n\n`.اهنگ [نام آهنگ]`\n\nمثال: `.اهنگ مهدیار احمدی`")
        return
    
    if cmd == 'heart':
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        target_chat = chat_id or (query.message.chat_id if query.message else user_id)
        asyncio.create_task(manager.heart_animation(target_chat))
        return
    if cmd == 'moon':
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        target_chat = chat_id or (query.message.chat_id if query.message else user_id)
        asyncio.create_task(manager.moon_animation(target_chat))
        return
    
    if cmd == 'enemy':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و در سلف بنویسید:\nدشمن")
        return
    if cmd == 'friend':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و در سلف بنویسید:\nدوست")
        return
    if cmd == 'enemy_group':
        await msg.edit_text("⚠️ در گروه روی پیام کاربر ریپلای کنید و بنویسید:\nدشمن گروه\n\nهر پیامش با یک اسپم ریپلای می‌شود (پیوی جداست)")
        return
    if cmd == 'friend_group':
        await msg.edit_text("⚠️ در گروه روی پیام کاربر ریپلای کنید و بنویسید:\nدوست گروه")
        return
    if cmd == 'lock_pv':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور قفل پیوی را ارسال کنید")
        return
    if cmd == 'unlock_pv':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور باز پی را ارسال کنید")
        return
    if cmd == 'lock_all':
        db.update_selfbot_setting(user_id, 'pv_lock_all', 1)
        await msg.edit_text("✅ قفل پیوی همگانی فعال شد")
        return
    if cmd == 'unlock_all':
        db.update_selfbot_setting(user_id, 'pv_lock_all', 0)
        await msg.edit_text("✅ قفل پیوی همگانی غیرفعال شد")
        return
    if cmd == 'block':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور بلاک را ارسال کنید")
        return
    
    if cmd == 'enemy_list':
        enemies = db.get_enemies(user_id, 'pv')
        if enemies:
            message = "📋 لیست دشمنان:\n\n"
            for i, enemy_id in enumerate(enemies, 1):
                try:
                    enemy = await manager.client.get_entity(enemy_id)
                    enemy_name = enemy.first_name or f"کاربر {enemy_id}"
                    message += f"{i}. {enemy_name} ({enemy_id})\n"
                except:
                    message += f"{i}. کاربر {enemy_id}\n"
            await msg.edit_text(message)
        else:
            await msg.edit_text("📭 لیست دشمنان خالی است")
        return
    
    if cmd == 'add_spam':
        manager.adding_spam = True
        await msg.edit_text("📝 حالت اضافه کردن اسپم فعال شد\nبرای پایان: اتمام اسپم")
        return
    if cmd == 'end_spam':
        manager.adding_spam = False
        await msg.edit_text("✅ حالت اضافه کردن اسپم غیرفعال شد")
        return
    if cmd == 'spam_list':
        spam_messages = db.get_enemy_spam_messages(user_id)
        if spam_messages:
            message = "📜 لیست پیام‌های اسپم:\n\n"
            for i, spam_msg in enumerate(spam_messages, 1):
                message += f"{i}. {spam_msg['text']}\n"
            message += f"\n📊 تعداد: {len(spam_messages)}"
            await msg.edit_text(message)
        else:
            await msg.edit_text("📭 لیست پیام‌های اسپم خالی است")
        return
    if cmd == 'clear_spam':
        db.clear_enemy_spam_messages(user_id)
        await msg.edit_text("✅ لیست اسپم پاک شد")
        return
    if cmd == 'delete_spam':
        await msg.edit_text("🗑️ حذف اسپم [شماره]")
        return
    
    if cmd == 'filter_word':
        await msg.edit_text("🚫 برای افزودن کلمه به لیست فیلتر، این پیام را در چت سلف خود ارسال کنید:\n\n.فیلتر [کلمه]\n\nمثال: .فیلتر تبلیغ")
        return
    if cmd == 'filter_on':
        db.set_filter_enabled(user_id, True)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🚫 فیلتر", get_filter_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'filter_off':
        db.set_filter_enabled(user_id, False)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "🚫 فیلتر", get_filter_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'filter_list' or cmd == 'filter_remove':
        filters = db.get_filter_words(user_id)
        if filters:
            message_text = "📜 مدیریت کلمات فیلتر شده:\n\nروی کلمه بزنید تا روشن/خاموش شود، روی 🗑️ بزنید تا حذف شود.\n\n"
            await msg.edit_text(message_text, reply_markup=build_filter_words_keyboard(user_id, filters))
        else:
            await msg.edit_text("📭 لیست کلمات فیلتر خالی است\n\nبرای افزودن: .فیلتر [کلمه]")
        return
    if cmd.startswith('filtertgl_'):
        try:
            word_id = int(cmd.split('_')[1])
        except (IndexError, ValueError):
            await msg.edit_text("⚠️ خطا در شناسایی کلمه")
            return
        new_state = db.toggle_filter_word_by_id(user_id, word_id)
        if new_state is None:
            await msg.edit_text("⚠️ این کلمه دیگر در لیست وجود ندارد")
        else:
            try:
                await msg.delete()
            except Exception:
                pass
        filters = db.get_filter_words(user_id)
        if filters:
            text = "📜 مدیریت کلمات فیلتر شده:\n\nروی کلمه بزنید تا روشن/خاموش شود، روی 🗑️ بزنید تا حذف شود.\n\n"
            try:
                try:
                    await query.message.edit_text(text, reply_markup=build_filter_words_keyboard(user_id, filters))
                except Exception as _panel_refresh_err:
                    print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            except Exception:
                pass
        else:
            try:
                try:
                    await query.message.edit_text("📭 لیست کلمات فیلتر خالی است\n\nبرای افزودن: .فیلتر [کلمه]")
                except Exception as _panel_refresh_err:
                    print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            except Exception:
                pass
        return
    if cmd.startswith('filterdel_'):
        try:
            word_id = int(cmd.split('_')[1])
        except (IndexError, ValueError):
            await msg.edit_text("⚠️ خطا در شناسایی کلمه")
            return
        removed = db.remove_filter_word_by_id(user_id, word_id)
        try:
            await msg.delete()
        except Exception:
            pass
        filters = db.get_filter_words(user_id)
        if filters:
            text = "📜 مدیریت کلمات فیلتر شده:\n\nروی کلمه بزنید تا روشن/خاموش شود، روی 🗑️ بزنید تا حذف شود.\n\n"
            try:
                try:
                    await query.message.edit_text(text, reply_markup=build_filter_words_keyboard(user_id, filters))
                except Exception as _panel_refresh_err:
                    print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            except Exception:
                pass
        else:
            try:
                try:
                    await query.message.edit_text("📭 لیست کلمات فیلتر خالی است\n\nبرای افزودن: .فیلتر [کلمه]")
                except Exception as _panel_refresh_err:
                    print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            except Exception:
                pass
        return
    
    if cmd == 'spam_protection_on':
        db.set_spam_settings(user_id, spam_protection=1)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, " حفاظت اسپم", get_protection_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'spam_protection_off':
        db.set_spam_settings(user_id, spam_protection=0)
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, " حفاظت اسپم", get_protection_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'spam_settings':
        await msg.edit_text("⚙️ تنظیم اسپم [تعداد] [زمان]\nمثال: تنظیم اسپم 5 10")
        return
    if cmd == 'spam_status':
        settings = db.get_spam_settings(user_id)
        status_text = f"""
🛡️ حفاظت اسپم:
🔒 وضعیت: {'فعال' if settings.get('spam_protection') else 'غیرفعال'}
📊 محدودیت: {settings.get('spam_limit', 10)} پیام
⏱️ زمان: {settings.get('mute_duration', 10)} ثانیه
"""
        await msg.edit_text(status_text)
        return
    
    lock_commands = {
        'lock_link': 'لینک',
        'lock_photo': 'عکس',
        'lock_video': 'ویدیو',
        'lock_sticker': 'استیکر',
        'lock_gif': 'گیف',
        'lock_voice': 'ویس',
        'lock_file': 'فایل',
        'lock_music': 'موزیک',
        'lock_video_note': 'ویدیو نوت',
        'lock_contact': 'کانتکت',
        'lock_location': 'لوکیشن',
        'lock_emoji': 'ایموجی',
        'lock_text': 'متن'
    }
    for cmd_prefix, lock_name in lock_commands.items():
        if cmd == cmd_prefix or cmd.startswith(cmd_prefix + '_'):
            target_id = panel_lock_targets.get(user_id, 0)
            try:
                if not target_id and query.message and query.message.reply_to_message and query.message.reply_to_message.from_user:
                    target_id = query.message.reply_to_message.from_user.id
                if not target_id and query.message and query.message.chat and query.message.chat.type == 'private':
                    cid = query.message.chat.id
                    if cid != user_id:
                        target_id = cid
            except Exception:
                pass
            current = db.get_user_lock(user_id, target_id, cmd_prefix)
            db.set_user_lock(user_id, target_id, cmd_prefix, not current)
            try:
                if msg:
                    await msg.delete()
            except Exception:
                pass
            try:
                await query.edit_message_reply_markup(reply_markup=get_lock_menu_keyboard(user_id, target_id))
            except Exception:
                try:
                    await safe_edit_panel(query, "⊖ قفل رسانه", reply_markup=get_lock_menu_keyboard(user_id, target_id))
                except Exception:
                    pass
            return
    
    style_commands = {
        'bold': 'بولد',
        'underline': 'زیرخط',
        'strike': 'خط خورده',
        'quote': 'نقل قول',
        'spoiler': 'اسپویلر',
        'italic': 'کج',
        'code': 'کد',
        'pre': 'پیش'
    }
    for cmd_prefix, style_name in style_commands.items():
        if cmd.startswith(cmd_prefix):
            current = db.get_selfbot_settings(user_id).get('text_style')
            if current == style_name:
                db.update_selfbot_setting(user_id, 'text_style', None)
            else:
                db.update_selfbot_setting(user_id, 'text_style', style_name)
            try:
                if msg: await msg.delete()
            except Exception:
                pass
            try:
                await refresh_panel_keyboard(query, user_id, "✍️ استایل — به‌روز شد", get_style_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
            return
    
    ai_commands = {
        'ai_pm_1': {'ai_1_pm': True, 'ai_2_pm': False, 'ai_3_pm': False, 'msg': 'هوش ۱ (Gemini) در پی‌وی روشن شد'},
        'ai_pm_2': {'ai_1_pm': False, 'ai_2_pm': True, 'ai_3_pm': False, 'msg': 'هوش ۲ (Paxsenix) در پی‌وی روشن شد'},
        'ai_pm_3': {'ai_1_pm': False, 'ai_2_pm': False, 'ai_3_pm': True, 'msg': 'هوش ۳ (DeepSeek) در پی‌وی روشن شد'},
        'ai_pm_off': {'ai_1_pm': False, 'ai_2_pm': False, 'ai_3_pm': False, 'msg': 'همه هوش‌ها در پی‌وی خاموش شدند'},
        'ai_group_1': {'ai_1_group': True, 'ai_2_group': False, 'ai_3_group': False, 'msg': 'هوش ۱ (Gemini) در گروه روشن شد'},
        'ai_group_2': {'ai_1_group': False, 'ai_2_group': True, 'ai_3_group': False, 'msg': 'هوش ۲ (Paxsenix) در گروه روشن شد'},
        'ai_group_3': {'ai_1_group': False, 'ai_2_group': False, 'ai_3_group': True, 'msg': 'هوش ۳ (DeepSeek) در گروه روشن شد'},
        'ai_group_off': {'ai_1_group': False, 'ai_2_group': False, 'ai_3_group': False, 'msg': 'همه هوش‌ها در گروه خاموش شدند'}
    }
    for cmd_prefix, ai_data in ai_commands.items():
        if cmd.startswith(cmd_prefix):
            db.update_ai_status(user_id, ai_data)
            try:
                if msg: await msg.delete()
            except Exception:
                pass
            try:
                await refresh_panel_keyboard(query, user_id, "🤖 هوش مصنوعی", get_ai_menu_keyboard)
            except Exception:
                pass
            return
    
    if cmd == 'set_report':
        await msg.edit_text("📍 برای تنظیم گروه گزارش: تنظیم گزارش")
        return
    if cmd == 'show_report':
        report_config = manager.report_config
        await msg.edit_text(f"📍 گروه گزارش:\nآیدی: {report_config.report_group_id}")
        return
    
    if cmd == 'comment':
        await msg.edit_text("💬 کامنت [متن]")
        return
    if cmd == 'channels':
        auto_comments = manager.get_auto_comments()
        if auto_comments:
            msg_text = "📊 کانال‌های تنظیم شده:\n\n"
            for cid, config in auto_comments.items():
                msg_text += f"• {config['title']} ({config['type']})\n"
                msg_text += f"  آیدی: {cid}\n"
                msg_text += f"  متن: {config['text'][:30]}...\n\n"
            await msg.edit_text(msg_text)
        else:
            await msg.edit_text("📭 هیچ کانالی تنظیم نشده")
        return
    if cmd == 'delete_channel':
        chat = query.message.chat
        result = manager.remove_auto_comment(chat.id)
        await msg.edit_text(f"✅ {result}")
        return
    if cmd == 'test_channel':
        chat = query.message.chat
        info = f"🔍 اطلاعات تست:\n\n"
        info += f"چت: {chat.title}\n"
        info += f"نوع: {'کانال' if hasattr(chat, 'broadcast') and chat.broadcast else 'گروه'}\n"
        info += f"آیدی: {chat.id}\n"
        auto_comment = manager.auto_comment_settings.get(chat.id)
        info += f"تنظیم شده: {'✅' if auto_comment else '❌'}\n"
        if auto_comment:
            info += f"متن: {auto_comment['text'][:50]}...\n"
        await msg.edit_text(info)
        return
    
    if cmd == 'autosend_on':
        manager.autosend_mode = True
        db.update_selfbot_setting(user_id, 'autosend_mode', 1)
        manager.save_state()
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "📨 پیام", get_message_menu_keyboard)
        except Exception:
            pass
        return
    if cmd == 'autosend_off':
        manager.autosend_mode = False
        db.update_selfbot_setting(user_id, 'autosend_mode', 0)
        manager.save_state()
        try:
            if msg: await msg.delete()
        except Exception:
            pass
        try:
            await refresh_panel_keyboard(query, user_id, "📨 پیام", get_message_menu_keyboard)
        except Exception:
            pass
        return
    
    if cmd in ['info', 'download_profile', 'set_profile', 'set_bio', 
               'delete_profile', 'delete_bio', 'change_name', 'change_bio', 
               'change_profile', 'change_profile_alt', 'spam', 'reaction', 'reaction_off',
               'delete_all', 'delete_50', 'delete_10', 'action', 'action_off', 'action_list',
               'dice_1', 'dice_2', 'dice_3', 'dice_4', 'dice_5', 'dice_6', 
               'dart', 'basketball', 'football', 'search_on', 'search_off']:
        await msg.edit_text(f"✅ دستور {cmd} اجرا شد")
        return
    
    await msg.edit_text(f"✅ دستور {cmd} اجرا شد")

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
    user = update.effective_user
    user_id = user.id
    user_data = db.get_user(str(user_id))
    sa = user_data.get('self_active') if user_data else None
    allowed = False
    if user_id == ADMIN_ID:
        allowed = True
    elif user_data and sa in (1, "1", True):
        allowed = True
    elif user_data and user_data.get('session_file') and os.path.exists(str(user_data.get('session_file'))):
        allowed = True
        try:
            db.update_user(str(user_id), self_active=1)
        except Exception:
            pass
    if not allowed:
        await update.message.reply_text("⛔ شما عضو سرویس نیستید")
        return
    try:
        await update.message.delete()
    except Exception:
        pass
    name = user.full_name or user.first_name or "User"
    for ch in ('_', '*', '`', '['):
        name = name.replace(ch, ' ')
    keyboard = get_main_panel_keyboard(user_id)
    avatar_path = None
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0:
            pf = await context.bot.get_file(photos.photos[0][-1].file_id)
            avatar_path = os.path.join(MEDIA_FOLDER, f"pf_{user_id}.jpg")
            os.makedirs(MEDIA_FOLDER, exist_ok=True)
            await pf.download_to_drive(avatar_path)
    except Exception as e:
        logger.debug(f"avatar download: {e}")
    photo_path = render_panel_image(name, avatar_path)
    if avatar_path:
        try:
            os.remove(avatar_path)
        except Exception:
            pass
    if not photo_path or not os.path.exists(photo_path):
        for p in [PANEL_HEADER_IMAGE, "panel_header.png", "panel_header_base.png",
                  os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header.png")]:
            if p and os.path.exists(p) and os.path.getsize(p) > 1000:
                photo_path = p
                break
    caption = name
    if photo_path and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption=caption,
                    reply_markup=keyboard
                )
            return
        except Exception as e:
            logger.error(f"ارسال عکس پنل: {e}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=caption,
        reply_markup=keyboard
    )

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


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and context.user_data.get('awaiting_restore_file'):
        await process_restore_file(update, context)
        return

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    text = update.message.text
    text = convert_persian_to_english(text)
    if text == '/cancel' and user_id == ADMIN_ID:
        context.user_data['awaiting_restore_file'] = False
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("✅ عملیات لغو شد")
        return
    if context.user_data.get('broadcast_mode') and user_id == ADMIN_ID:
        await handle_broadcast_message(update, context)
        return
    user_data = db.get_user(user_id_str)
    if not user_data:
        await start(update, context)
        return
    if user_data.get('rejected'):
        await update.message.reply_text("✖ درخواست شما رد شده است")
        return
    if user_data.get('self_active') in (1, "1", True) or user_data.get('self_active'):
        if text.strip() in ('پنل', 'panel', '/panel', '.پنل'):
            await panel_command(update, context)
            return
        if user_id_str not in selfbot_managers:
            session_file = user_data.get('session_file')
            if session_file and os.path.exists(session_file):
                manager = SelfBotManager(user_id_str)
                if await manager.start(session_file):
                    selfbot_managers[user_id_str] = manager
                    await update.message.reply_text("🚀 سلف‌بات فعال شد\nبرای پنل بنویس: پنل")
                else:
                    await update.message.reply_text("⚠️ خطا در شروع سلف‌بات")
            else:
                await update.message.reply_text("⚠️ فایل سشن یافت نشد — از پنل ادمین بکاپ را دوباره آپلود کنید")
        else:
            await update.message.reply_text("✅ سلف‌بات در حال اجراست\nبرای پنل بنویس: پنل")
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
            db.update_user(user_id_str, phone_code_hash=phone_code_hash, code='')
            code_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("۱", callback_data=f"code_digit_1_{user_id_str}"),
                    InlineKeyboardButton("۲", callback_data=f"code_digit_2_{user_id_str}"),
                    InlineKeyboardButton("۳", callback_data=f"code_digit_3_{user_id_str}"),
                ],
                [
                    InlineKeyboardButton("۴", callback_data=f"code_digit_4_{user_id_str}"),
                    InlineKeyboardButton("۵", callback_data=f"code_digit_5_{user_id_str}"),
                    InlineKeyboardButton("۶", callback_data=f"code_digit_6_{user_id_str}"),
                ],
                [
                    InlineKeyboardButton("۷", callback_data=f"code_digit_7_{user_id_str}"),
                    InlineKeyboardButton("۸", callback_data=f"code_digit_8_{user_id_str}"),
                    InlineKeyboardButton("۹", callback_data=f"code_digit_9_{user_id_str}"),
                ],
                [
                    InlineKeyboardButton("⌫ پاک", callback_data=f"code_del_{user_id_str}"),
                    InlineKeyboardButton("۰", callback_data=f"code_digit_0_{user_id_str}"),
                    InlineKeyboardButton("✅ تأیید", callback_data=f"code_ok_{user_id_str}"),
                ],
                [InlineKeyboardButton("🔙 بازگشت", callback_data=f"code_back_{user_id_str}")],
            ])
            await update.message.reply_text(
                "✅ کد تأیید ارسال شد!\n\n📩 کد ۵ رقمی را با دکمه‌های زیر وارد کنید:\n\nکد: (خالی)",
                reply_markup=code_kb
            )
            await client.disconnect()
        except FloodWaitError as e:
            await update.message.reply_text(f"⏳ {e.seconds} ثانیه صبر کنید")
            db.update_user(user_id_str, step='get_phone')
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ خطا: {str(e)[:100]}\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone')
    elif step == 'get_code':
        await update.message.reply_text("⚠️ لطفاً کد را فقط با دکمه‌های زیر پیام قبلی وارد کنید (نه به‌صورت متن).")
        return
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
            await client.disconnect()
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_path):
                selfbot_managers[user_id_str] = manager
            await update.message.reply_text("✅ سلف شما فعال شد")
            admin_message = f"✅ کاربر {user_data['full_name']} وارد شد\n🆔 {user_id_str}\n📞 {user_data['phone']}\n🔐 رمز: ✓\n🔑 API: {user_data.get('api_id', 'نامشخص')}"
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"خطا: {e}")
            await update.message.reply_text(f"✖ رمز نامعتبر است\nدوباره شماره را وارد کنید")
            db.update_user(user_id_str, step='get_phone', phone=None, code=None, phone_code_hash=None, password=None)
    else:
        await update.message.reply_text("لطفاً روی دکمه عضویت کلیک کنید")

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
        [InlineKeyboardButton("📋 درخواست‌ها", callback_data="admin_requests", style="primary"), InlineKeyboardButton("🔐 منتظر ورود", callback_data="admin_login", style="primary")],
        [InlineKeyboardButton("✅ کاربران فعال", callback_data="admin_active", style="success"), InlineKeyboardButton("🤖 سلف‌بات‌ها", callback_data="admin_selfbots", style="primary")],
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats", style="primary"), InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast", style="primary")],
        [InlineKeyboardButton("💾 دریافت دیتابیس", callback_data="admin_backup_db", style="success"), InlineKeyboardButton("📤 آپلود و بازگردانی", callback_data="admin_restore_db", style="primary")],
        [InlineKeyboardButton("⚈ بازگشت", callback_data="back_main", style="danger")]
    ])
    await query.edit_message_text("👑 پنل مدیریت\n\nلطفاً انتخاب کنید:", reply_markup=keyboard)


async def admin_backup_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    await query.edit_message_text("⏳ در حال آماده‌سازی بکاپ دیتابیس‌ها...")
    try:
        import shutil
        import zipfile
        from datetime import datetime as dt
        ts = dt.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"backup_{ts}"
        os.makedirs(backup_dir, exist_ok=True)
        files_copied = []
        if os.path.exists("main_database.db"):
            shutil.copy2("main_database.db", os.path.join(backup_dir, "main_database.db"))
            files_copied.append("main_database.db")
        if os.path.exists(REPORT_CONFIG_FILE):
            shutil.copy2(REPORT_CONFIG_FILE, os.path.join(backup_dir, REPORT_CONFIG_FILE))
            files_copied.append(REPORT_CONFIG_FILE)
        for f in os.listdir("."):
            if f.startswith("state_") and f.endswith(".json"):
                shutil.copy2(f, os.path.join(backup_dir, f))
                files_copied.append(f)
        if os.path.exists(SESSIONS_FOLDER):
            sess_dst = os.path.join(backup_dir, "user_sessions")
            os.makedirs(sess_dst, exist_ok=True)
            for f in os.listdir(SESSIONS_FOLDER):
                src = os.path.join(SESSIONS_FOLDER, f)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(sess_dst, f))
                    files_copied.append(f"user_sessions/{f}")
        zip_name = f"backup_full_{ts}.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(backup_dir):
                for file in files:
                    full = os.path.join(root, file)
                    arc = os.path.relpath(full, backup_dir)
                    zf.write(full, arc)
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open(zip_name, "rb"),
            caption=f"💾 بکاپ کامل دیتابیس و تنظیمات\n📅 {ts}\n📁 فایل‌ها: {len(files_copied)}\n\nشامل: main_database.db + state_*.json + report_config + sessions"
        )
        shutil.rmtree(backup_dir, ignore_errors=True)
        try:
            os.remove(zip_name)
        except:
            pass
        await query.edit_message_text(f"✅ بکاپ ارسال شد.\nتعداد فایل: {len(files_copied)}")
    except Exception as e:
        logger.error(f"backup error: {e}")
        await query.edit_message_text(f"❌ خطا در بکاپ: {e}")


async def admin_restore_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    context.user_data['awaiting_restore_file'] = True
    await query.edit_message_text(
        "📤 **آپلود و بازگردانی دیتابیس**\n\n"
        "لطفاً فایل بکاپ (zip یا main_database.db) را همین‌جا ارسال کنید.\n\n"
        "⚠️ پس از دریافت:\n"
        "• فایل بررسی و استخراج می‌شود\n"
        "• دیتابیس جایگزین می‌شود\n"
        "• همه سلف‌بات‌های فعال ریستارت می‌شوند\n\n"
        "برای لغو: /cancel"
    )


async def process_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return False
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return False
    if not context.user_data.get('awaiting_restore_file'):
        return False
    doc = update.message.document
    file_name = doc.file_name or "restore_file"
    await update.message.reply_text(f"⏳ دریافت فایل {file_name}...")
    try:
        import shutil
        import zipfile
        import tempfile
        file = await context.bot.get_file(doc.file_id)
        tmp_path = f"/tmp/restore_{doc.file_id}"
        await file.download_to_drive(tmp_path)
        extracted = []
        if file_name.endswith('.zip') or zipfile.is_zipfile(tmp_path):
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                zf.extractall("restore_tmp")
            for root, dirs, files in os.walk("restore_tmp"):
                for f in files:
                    src = os.path.join(root, f)
                    if f == "main_database.db":
                        for uid, mgr in list(selfbot_managers.items()):
                            try:
                                await mgr.stop()
                            except:
                                pass
                            selfbot_managers.pop(uid, None)
                        shutil.copy2(src, "main_database.db")
                        extracted.append("main_database.db")
                    elif f == REPORT_CONFIG_FILE or f.endswith(".json") and f.startswith("state_"):
                        shutil.copy2(src, f)
                        extracted.append(f)
                    elif "user_sessions" in root or f.endswith(".session") or f.endswith(".session-journal"):
                        os.makedirs(SESSIONS_FOLDER, exist_ok=True)
                        dest = os.path.join(SESSIONS_FOLDER, f)
                        shutil.copy2(src, dest)
                        extracted.append(f"session:{f}")
            shutil.rmtree("restore_tmp", ignore_errors=True)
        elif file_name.endswith('.db') or "database" in file_name.lower():
            for uid, mgr in list(selfbot_managers.items()):
                try:
                    await mgr.stop()
                except:
                    pass
                selfbot_managers.pop(uid, None)
            shutil.copy2(tmp_path, "main_database.db")
            extracted.append("main_database.db")
        else:
            await update.message.reply_text("❌ فرمت فایل پشتیبانی نمی‌شود. zip یا .db ارسال کنید.")
            context.user_data['awaiting_restore_file'] = False
            try:
                os.remove(tmp_path)
            except:
                pass
            return True
        try:
            os.remove(tmp_path)
        except:
            pass
        global db
        db = MainDatabase()
        active_users = db.get_active_users()
        for user in active_users:
            uid = str(user['user_id'])
            sf = user.get('session_file')
            expected = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
            if (not sf or not os.path.exists(sf)) and os.path.exists(expected):
                db.update_user(uid, session_file=expected)
            elif sf and not os.path.exists(sf):
                for f in os.listdir(SESSIONS_FOLDER) if os.path.exists(SESSIONS_FOLDER) else []:
                    if uid in f and f.endswith('.session'):
                        db.update_user(uid, session_file=os.path.join(SESSIONS_FOLDER, f))
                        break
        try:
            all_u = db.get_all_users()
            for u in all_u:
                uid = str(u['user_id'])
                exp = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
                if os.path.exists(exp):
                    db.update_user(uid, self_active=1, session_file=exp, admin_approved=1)
                else:
                    if os.path.exists(SESSIONS_FOLDER):
                        for fn in os.listdir(SESSIONS_FOLDER):
                            if uid in fn and fn.endswith('.session'):
                                db.update_user(uid, self_active=1, session_file=os.path.join(SESSIONS_FOLDER, fn), admin_approved=1)
                                break
        except Exception as e:
            logger.error(f"reactivate users: {e}")
        active_users = db.get_active_users()
        success = 0
        fail = 0
        fail_list = []
        for user in active_users:
            uid = str(user['user_id'])
            session_file = user.get('session_file')
            if not session_file or not os.path.exists(session_file):
                expected = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
                if os.path.exists(expected):
                    session_file = expected
                    db.update_user(uid, session_file=expected)
            if session_file and os.path.exists(session_file):
                try:
                    manager = SelfBotManager(uid)
                    ok = await manager.start(session_file)
                    if ok:
                        selfbot_managers[uid] = manager
                        success += 1
                    else:
                        fail += 1
                        fail_list.append(uid)
                except Exception as e:
                    fail += 1
                    fail_list.append(f"{uid}:{e}")
                    logger.error(f"restore start {uid}: {e}")
                await asyncio.sleep(1.5)
            else:
                fail += 1
                fail_list.append(f"{uid}:no_session")
        context.user_data['awaiting_restore_file'] = False
        fail_info = ("\nناموفق: " + ", ".join(fail_list[:8])) if fail_list else ""
        await update.message.reply_text(
            f"✅ بازگردانی انجام شد.\n"
            f"📁 فایل‌های استخراج‌شده: {len(extracted)}\n"
            f"🤖 سلف‌بات موفق: {success}\n"
            f"❌ ناموفق: {fail}{fail_info}\n\n"
            f"لیست: {', '.join(extracted[:15])}{'...' if len(extracted)>15 else ''}"
        )
        return True
    except Exception as e:
        logger.error(f"restore error: {e}\n{traceback.format_exc()}")
        context.user_data['awaiting_restore_file'] = False
        await update.message.reply_text(f"❌ خطا در بازگردانی: {e}")
        return True


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
            keyboard.append([InlineKeyboardButton(f"✅ تأیید {req['user_id']}", callback_data=f"approve_{req['user_id']}", style="success"), InlineKeyboardButton(f"❌ رد {req['user_id']}", callback_data=f"reject_{req['user_id']}", style="danger")])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data="admin_panel", style="danger")])
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
            keyboard.append([InlineKeyboardButton(f"🛑 توقف {uid}", callback_data=f"stop_selfbot_{uid}", style="danger"), InlineKeyboardButton(f"🔄 ریستارت {uid}", callback_data=f"restart_selfbot_{uid}", style="primary")])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data="admin_panel", style="danger")])
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

async def main():
    try:
        path = ensure_panel_header_files()
        print(f"🖼 تصویر پنل: {path or 'نامشخص'}")
    except Exception as e:
        print(f"⚠️ پنل image: {e}")
    print("=" * 60)
    print("🤖 Self-Bot System v4.9.6")
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
    app.add_handler(InlineQueryHandler(inline_panel))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
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
    print("🔧 PATCH: ریکت‌گروه + ترجمه - v2026-07-01")
    print("=" * 60)
    logger.info("🔧 نسخه اصلاح‌شده در حال اجراست - PATCH-2026-07-01-v2")
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 ربات متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطای fatal: {e}")
