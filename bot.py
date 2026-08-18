
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
        # map digits 0-9; if font shorter/longer, use modulo or keep original
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

# نگاشت زبان‌های فارسی به کدهای استاندارد ISO که deep_translator تضمینی می‌شناسد
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
        """اولین بار بیو اصلی اکانت را ذخیره کن تا موقع خاموش کردن برگردد"""
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
            # فقط اگر هیچ افزونه بیویی روشن نباشد، این را به‌عنوان بیو اصلی ذخیره کن
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
                # همه خاموش → بیو اصلی یا خالی (حذف افزودنی‌ها از بیوگرافی)
                new_bio = bio_text or ""
                await self.client(UpdateProfileRequest(about=new_bio[:70] if new_bio else " "))
                # یک فاصله اجباری سپس خالی برای اطمینان از پاک شدن در برخی کلاینت‌ها
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
            
            # ساخت خودکار گروه گزارش در صورت نیاز (اولین ورود)
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
        """اگر گروه گزارش پیش‌فرض است، یک گروه خصوصی «گزارش دهی» می‌سازد،
        آن را سنجاق می‌کند و راهنمای کوتاه می‌فرستد."""
        try:
            current = self.report_config.report_group_id
            # فقط وقتی هنوز گروه پیش‌فرض است یا گروهی وجود ندارد
            if current and current != GROUP_ID and current != 0:
                # بررسی کن گروه هنوز در دسترس است
                try:
                    await self.client.get_entity(current)
                    return  # گروه شخصی از قبل وجود دارد
                except Exception:
                    pass  # گروه قبلی از بین رفته → دوباره بساز
            
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
            # آیدی کامل سوپرگروه
            full_id = int(f"-100{new_chat.id}")
            self.report_config.set_report_group(full_id)
            # ذخیره در تنظیمات سلف‌بات هم
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
            
            # سنجاق کردن چت (اگر لیست پین پر بود یکی را از پین دربیاور)
            try:
                peer = await self.client.get_input_entity(full_id)
                # ابتدا سعی در پین
                try:
                    await self.client(ToggleDialogPinRequest(peer=peer, pinned=True))
                except Exception as pin_err:
                    # احتمالاً سقف پین پر است → یکی از پین‌های موجود را باز کن
                    logger.debug(f"پین اول ناموفق: {pin_err}")
                    try:
                        dialogs = await self.client.get_dialogs(limit=30)
                        pinned = [d for d in dialogs if getattr(d, 'pinned', False)]
                        if pinned:
                            # قدیمی‌ترین پین را باز کن
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
                    # همیشه بیو را به‌روز کن (روشن یا خاموش)
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
                # wrap text
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
                # دانلود رسانه
                buf = BytesIO()
                path = await self.client.download_media(reply_msg, file=buf)
                buf.seek(0)
                is_video = bool(reply_msg.video or reply_msg.gif or (reply_msg.document and getattr(reply_msg.document, 'mime_type', '').startswith('video')))
                if is_video:
                    # ارسال به عنوان گیف/انیمیشن
                    buf.name = "anim.mp4"
                    await self.client.send_file(chat_id, buf, force_document=False, supports_streaming=True, video_note=False)
                    # تلاش برای ارسال به صورت gif-like
                    try:
                        buf.seek(0)
                        await self.client.send_file(chat_id, buf, attributes=[types.DocumentAttributeAnimated()], force_document=False)
                    except Exception:
                        pass
                else:
                    # تبدیل به استیکر webp 512
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
                # فوروارد پیام به ربات
                sent_to_bot = await self.client.forward_messages(quotly, reply_msg)
                sent_id = sent_to_bot[0].id if isinstance(sent_to_bot, (list, tuple)) else sent_to_bot.id
                # صبر برای پاسخ استیکر
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
                    # ارسال استیکر بدون متن و بدون فوروارد، با ریپلای روی همان پیام کاربر
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
                # پاک کردن کامل چت با ربات (حذف پیام‌های اخیر تا اثری نماند)
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
                # اسپم مداوم حذف شد — فقط روی هر پیام یک اسپم
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
                    # ذخیره با full chat_id هم برای سازگاری گروه/سوپرگروه
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
                # شمارش دقیق: اگر PhotosSlice باشد فیلد count دارد
                photos = await self.client(GetUserPhotosRequest(user_id=user.id, offset=0, max_id=0, limit=100))
                if hasattr(photos, 'count') and photos.count is not None:
                    photo_count = int(photos.count)
                elif photos.photos:
                    photo_count = len(photos.photos)
                    # اگر cap روی limit خورد، ادامه بده
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
                # حتی بدون عکس پروفایل، اطلاعات متنی ارسال شود
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
            # فقط اینلاین → یک پیام واحد (عکس + نام + دکمه‌ها)
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
                    f"🆔 `{tid}`\n"
                    f"📎 {uname}\n"
                    f"🤖 ربات: {is_bot} | ⭐ پرمیوم: {is_premium}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"دشمن پیوی: {'✅' if is_enemy_pv else '❌'} | دشمن گروه: {'✅' if is_enemy_g else '❌'}\n"
                    f"قفل پیوی: {'✅' if is_pv_locked else '❌'}"
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
                sent_photo = False
                sent_kb = False

                # مسیر ۱: Bot API عکس+دکمه به پیوی کاربر (قابل اعتمادترین)
                try:
                    dest = int(self.user_id)
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, 'rb') as f:
                            r = requests.post(
                                f"{api}/sendPhoto",
                                data={
                                    'chat_id': dest,
                                    'caption': caption.replace('`', ''),
                                    'reply_markup': json.dumps(kb_dict),
                                },
                                files={'photo': ('panel.jpg', f, 'image/jpeg')},
                                timeout=30
                            )
                    else:
                        r = requests.post(
                            f"{api}/sendMessage",
                            json={'chat_id': dest, 'text': caption.replace('`', ''), 'reply_markup': kb_dict},
                            timeout=15
                        )
                    body = r.json() if r.content else {}
                    if r.status_code == 200 and body.get('ok'):
                        sent_photo = True
                        sent_kb = True
                        logger.info(f"پنل کاربر → PV bot OK for {self.user_id} target={tid}")
                    else:
                        logger.warning(f"پنل کاربر bot PV fail: {r.text[:220]}")
                except Exception as e:
                    logger.warning(f"پنل کاربر bot PV: {e}")

                # مسیر ۲: در همین چت با سلف (عکس)، دکمه در پیوی اگر قبلاً نرفته
                try:
                    if photo_path and os.path.exists(photo_path):
                        await self.client.send_file(chat_id, photo_path, caption=caption.replace('`', ''))
                        sent_photo = True
                    else:
                        await self.client.send_message(chat_id, caption.replace('`', ''))
                        sent_photo = True
                    logger.info(f"پنل کاربر → telethon chat OK chat={chat_id}")
                except Exception as e:
                    logger.warning(f"پنل کاربر telethon: {e}")

                if sent_photo and not sent_kb:
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
                        sent_kb = True
                    except Exception as e:
                        logger.warning(f"پنل کاربر kb only: {e}")

                for path in (avatar_path, photo_path):
                    try:
                        if path and os.path.exists(path):
                            # فقط فایل‌های موقت ساخته‌شده
                            bn = os.path.basename(path)
                            if bn.startswith('uav_') or bn.startswith('panel_') or bn.startswith('up_'):
                                os.remove(path)
                    except Exception:
                        pass
                try:
                    await event.delete()
                except Exception:
                    pass
                if not sent_photo:
                    await self.client.send_message(chat_id, "❌ ارسال پنل کاربر ناموفق بود. ربات را استارت کنید و دوباره امتحان کنید.")
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
        # اسپم مداوم غیرفعال شد — اسپم فقط روی هر پیام ورودی دشمن انجام می‌شود
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
                    # جلوگیری از تکرار پشت‌سرهم همان متن برای یک دشمن
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
                # chat_id ممکن است short یا full باشد؛ هر دو را چک می‌کنیم
                reaction = db.get_reaction(self.user_id, chat_id, sender_id)
                if not reaction:
                    # fallback: full chat id (مثلاً -100xxx)
                    try:
                        full_cid = event.chat_id
                        if full_cid and full_cid != chat_id:
                            reaction = db.get_reaction(self.user_id, full_cid, sender_id)
                            if reaction:
                                chat_id = full_cid  # برای سازگاری بعدی
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
            # ========== ترجمه - اصلاح شده ==========
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
        # sqlite ممکن است 1 / "1" / True برگرداند
        if sa in (1, "1", True, "true", "True"):
            has_access = True
        elif user_data.get('admin_approved') in (1, "1", True) and user_data.get('session_file'):
            # بعد از بکاپ اگر سشن هست دسترسی بده
            sf = user_data.get('session_file')
            if sf and os.path.exists(sf):
                has_access = True
                # فعال‌سازی خودکار
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
        # یک پیام واحد: عکس + نام + دکمه‌ها
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
    """بارگذاری قالب پنل (از فایل یا base64 embed)"""
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
    """
    قالب VROOM:
    - عکس پروفایل فقط داخل دایره سیاه
    - پاک کردن کامل متن «اسم کاربر رو اینجا بزار»
    - گذاشتن اسم همان کاربر روی قاب
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
        img, base_path = _load_panel_base_image()
        if img is None:
            return None
        W, H = img.size

        # --- آواتار داخل دایره سیاه ---
        cx = int(round(W * 0.6125))
        cy = int(round(H * 0.4860))
        radius = int(round(min(W, H) * 0.280))
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
                    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.8))
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

        # --- پاک کردن کامل متن قالب از روی قاب فلزی ---
        # ناحیه متن روی بنر (اندازه‌گیری روی قالب)
        plate_cx = int(W * 0.603)
        plate_cy = int(H * 0.884)
        y0 = max(0, int(H * 0.825))
        y1 = min(H, int(H * 0.955))
        x0 = max(0, int(W * 0.28))
        x1 = min(W, int(W * 0.92))

        region = img.crop((x0, y0, x1, y1)).convert('RGB')
        pix = region.load()
        rw, rh = region.size

        # رنگ پایه فلز از لبه‌های تیره (بدون متن)
        samples = []
        for sy in range(rh):
            for sx in list(range(0, max(1, rw // 12))) + list(range(rw - max(1, rw // 12), rw)):
                pr, pg, pb = pix[sx, sy]
                if pr + pg + pb < 160:
                    samples.append((pr, pg, pb))
        if samples:
            mr = sum(s[0] for s in samples) // len(samples)
            mg = sum(s[1] for s in samples) // len(samples)
            mb = sum(s[2] for s in samples) // len(samples)
        else:
            mr, mg, mb = 20, 24, 32

        # هر پیکسل روشن / آبی / فیروزه‌ای = متن نئون → جایگزین با فلز
        for yy in range(rh):
            for xx in range(rw):
                pr, pg, pb = pix[xx, yy]
                bright = pr + pg + pb
                # نئون آبی، سفید روشن، یا هر چیزی که از فلز تیره روشن‌تر است در ناحیه متن
                is_text = (
                    (pb > 90 and pg > 80 and pr < 190) or
                    (bright > 280) or
                    (pb > pr + 30 and pb > 80)
                )
                if is_text:
                    j = ((xx * 13 + yy * 29) % 9) - 4
                    pix[xx, yy] = (
                        max(0, min(255, mr + j)),
                        max(0, min(255, mg + j)),
                        max(0, min(255, mb + j)),
                    )

        # بلور خیلی ملایم فقط روی ناحیه پاک‌شده برای یکدست شدن
        try:
            region = region.filter(ImageFilter.GaussianBlur(radius=0.6))
        except Exception:
            pass
        img.paste(region, (x0, y0))

        # --- اسم کاربر (بدون پس‌زمینه) ---
        draw = ImageDraw.Draw(img, 'RGBA')
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        max_text_w = int(W * 0.44)
        max_text_h = int(H * 0.08)
        font = ImageFont.load_default()
        tw = th = 0
        for fs in range(max(54, W // 15), 18, -1):
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
        text_y = plate_cy - th // 2 - 1
        for ox, oy, col in (
            (3, 3, (0, 5, 12, 140)),
            (2, 2, (15, 50, 100, 110)),
            (1, 1, (50, 130, 200, 90)),
            (0, -1, (100, 200, 255, 50)),
        ):
            draw.text((text_x + ox, text_y + oy), safe_name, font=font, fill=col)
        draw.text((text_x, text_y), safe_name, font=font, fill=(175, 245, 255, 255))

        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        out = os.path.join(
            MEDIA_FOLDER,
            f"panel_{abs(hash(safe_name + str(avatar_path or '') + str(W) + 'v8')) % 10**9}.jpg"
        )
        img.convert('RGB').save(out, 'JPEG', quality=94)
        return out
    except Exception as e:
        logger.error(f"_composite_panel: {e}\n{traceback.format_exc()}")
        return None


def render_panel_image(username: str, avatar_path: str = None) -> str:
    """هدر پنل اصلی: آواتار کاربر در دایره + نام پایین"""
    return _composite_panel(username, avatar_path)


def render_user_panel_image(username: str, avatar_path: str = None) -> str:
    """تصویر پنل کاربر: همان قالب + آواتار همان کاربر + نام"""
    return _composite_panel(username, avatar_path)


async def get_panel_photo_file_id(bot, user, force_refresh=False):
    """ساخت تصویر پنل با آواتار کاربر و آپلود برای گرفتن file_id (اینلاین یک‌پیامه)"""
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
        # آپلود به چت ادمین برای گرفتن file_id پایدار
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
    """فقط نام کاربر — بدون متن اضافه بین عکس و دکمه‌ها"""
    try:
        name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None) or "User"
    except Exception:
        name = "User"
    for ch in ('_', '*', '`', '['):
        name = name.replace(ch, ' ')
    return name

def get_help_back_keyboard(user_id, back_callback):
    """دکمه بازگشت برای صفحات راهنما"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback, style="danger")]
    ])

async def safe_edit_panel(query, text, reply_markup=None, parse_mode=None):
    """ویرایش پیام پنل — هم متن هم کپشن عکس؛ در نهایت فقط کیبورد را هم امتحان می‌کند"""
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
            # اگر فقط کیبورد عوض شده، همین کافی است
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
    """به‌روزرسانی فوری کیبورد پنل با تیک‌های جدید"""
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
    # All fonts button
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

# target_id برای قفل رسانه از پنل کاربر (user_id -> target_id)
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
    """پنل مدیریت یک کاربر خاص (قفل/دشمن/پیوی) با تیک وضعیت"""
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
        ],
        [
            _lk("lock_sticker", "🎨 استیکر"),
            _lk("lock_photo", "📸 عکس"),
            _lk("lock_video", "🎥 ویدیو"),
        ],
        [
            _lk("lock_link", "🔗 لینک"),
            _lk("lock_voice", "🎤 ویس"),
            _lk("lock_text", "📝 متن"),
        ],
        [
            _lk("lock_gif", "🎞️ گیف"),
            _lk("lock_file", "📁 فایل"),
            _lk("lock_music", "🎵 موزیک"),
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
            # um_lock_sticker_TARGET_OWNER  or um_enemy_pv_TARGET_OWNER or um_lockpv_TARGET_OWNER
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
    # پارس امن cmd بدون خراب شدن ایندکس فونت/پرچم وقتی user_id در رشته باشد
    _raw = data[5:] if data.startswith('exec_') else data  # بعد از exec_
    if _raw.endswith(f'_{user_id}'):
        cmd = _raw[: -(len(str(user_id)) + 1)]
    else:
        cmd = _raw.replace(f'_{user_id}', '')
    
    # پیام موقت «در حال اجرا» فقط برای دستوراتی که واقعاً نیاز دارند (نه toggle)
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
            # فقط یکی روشن بماند (اختیاری ولی تمیزتر)
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
    # نقشه بازگشت راهنما به منوی والد
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
        # نمایش راهنما به صورت نقل‌قول (بدون **)
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
            # اولویت: target از پنل کاربر > ریپلای > پی‌وی طرف مقابل > عمومی (0)
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
    """ارسال پنل: فقط عکس + دکمه‌ها زیر آن (بدون متن میانی)"""
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
    # دانلود آواتار
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
    # اگر رندر نشد، خود تصویر طراحی‌شده را بفرست
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
    """Handle document uploads (mainly for admin restore)"""
    if not update.message or not update.message.document:
        return
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and context.user_data.get('awaiting_restore_file'):
        await process_restore_file(update, context)
        return
    # otherwise ignore documents for non-admin / non-restore

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
        # باز کردن پنل با تصویر + دکمه‌ها یکجا
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
            # کیبورد فارسی برای ورود کد
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
        # ورود متنی کد نادیده گرفته می‌شود — فقط از دکمه‌ها استفاده شود
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
        # main database
        if os.path.exists("main_database.db"):
            shutil.copy2("main_database.db", os.path.join(backup_dir, "main_database.db"))
            files_copied.append("main_database.db")
        # report config
        if os.path.exists(REPORT_CONFIG_FILE):
            shutil.copy2(REPORT_CONFIG_FILE, os.path.join(backup_dir, REPORT_CONFIG_FILE))
            files_copied.append(REPORT_CONFIG_FILE)
        # state files
        for f in os.listdir("."):
            if f.startswith("state_") and f.endswith(".json"):
                shutil.copy2(f, os.path.join(backup_dir, f))
                files_copied.append(f)
        # sessions folder (optional, can be large)
        if os.path.exists(SESSIONS_FOLDER):
            sess_dst = os.path.join(backup_dir, "user_sessions")
            os.makedirs(sess_dst, exist_ok=True)
            for f in os.listdir(SESSIONS_FOLDER):
                src = os.path.join(SESSIONS_FOLDER, f)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(sess_dst, f))
                    files_copied.append(f"user_sessions/{f}")
        # zip it
        zip_name = f"backup_full_{ts}.zip"
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(backup_dir):
                for file in files:
                    full = os.path.join(root, file)
                    arc = os.path.relpath(full, backup_dir)
                    zf.write(full, arc)
        # send to admin
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open(zip_name, "rb"),
            caption=f"💾 بکاپ کامل دیتابیس و تنظیمات\n📅 {ts}\n📁 فایل‌ها: {len(files_copied)}\n\nشامل: main_database.db + state_*.json + report_config + sessions"
        )
        # cleanup
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
    """Process uploaded backup file from admin"""
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
                    # map to correct places
                    if f == "main_database.db":
                        # stop all selfbots first
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
        # re-init db
        global db
        db = MainDatabase()
        # اصلاح مسیر session_file در صورت نیاز
        active_users = db.get_active_users()
        for user in active_users:
            uid = str(user['user_id'])
            sf = user.get('session_file')
            # اگر مسیر قدیمی/اشتباه بود، مسیر استاندارد را ست کن
            expected = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
            if (not sf or not os.path.exists(sf)) and os.path.exists(expected):
                db.update_user(uid, session_file=expected)
            elif sf and not os.path.exists(sf):
                # جستجو در پوشه sessions
                for f in os.listdir(SESSIONS_FOLDER) if os.path.exists(SESSIONS_FOLDER) else []:
                    if uid in f and f.endswith('.session'):
                        db.update_user(uid, session_file=os.path.join(SESSIONS_FOLDER, f))
                        break
        # همه کاربرانی که سشن دارند را فعال علامت بزن
        try:
            all_u = db.get_all_users()
            for u in all_u:
                uid = str(u['user_id'])
                exp = os.path.join(SESSIONS_FOLDER, f"user_{uid}.session")
                if os.path.exists(exp):
                    db.update_user(uid, self_active=1, session_file=exp, admin_approved=1)
                else:
                    # جستجو
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
                # آخرین تلاش
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
