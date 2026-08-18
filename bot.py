
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
                name = getattr(target, 'first_name', '') or ''
                if getattr(target, 'last_name', None):
                    name += ' ' + target.last_name
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
                    f"\nروی دکمه‌ها بزن تا قفل/دشمن را تغییر دهی."
                )
                avatar_path = None
                try:
                    photos = await self.client.get_profile_photos(target, limit=1)
                    if photos:
                        avatar_path = os.path.join(MEDIA_FOLDER, f"uav_{tid}.jpg")
                        os.makedirs(MEDIA_FOLDER, exist_ok=True)
                        await self.client.download_media(photos[0], file=avatar_path)
                except Exception as e:
                    logger.debug(f"avatar dl: {e}")
                photo_path = render_user_panel_image(name, avatar_path)
                if not photo_path:
                    # fallback: فقط آواتار خام
                    photo_path = avatar_path
                kb = get_user_manage_keyboard(self.user_id, tid)
                kb_dict = {
                    'inline_keyboard': [
                        [{'text': b.text, 'callback_data': b.callback_data} for b in row]
                        for row in kb.inline_keyboard
                    ]
                }
                api = f"https://api.telegram.org/bot{BOT_TOKEN}"
                sent = False
                # 1) تلاش Bot API در همین چت (اگر ربات عضو باشد)
                for dest in (chat_id, int(self.user_id)):
                    try:
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
                                    timeout=25
                                )
                        else:
                            r = requests.post(
                                f"{api}/sendMessage",
                                json={'chat_id': dest, 'text': caption, 'reply_markup': kb_dict},
                                timeout=15
                            )
                        if r.status_code == 200 and r.json().get('ok'):
                            sent = True
                            break
                        else:
                            logger.warning(f"user panel botapi dest={dest}: {r.text[:180]}")
                    except Exception as e:
                        logger.warning(f"user panel botapi dest={dest}: {e}")
                # 2) fallback با سلف (عکس در همین چت)
                if not sent:
                    try:
                        if photo_path and os.path.exists(photo_path):
                            await self.client.send_file(chat_id, photo_path, caption=caption)
                        else:
                            await self.client.send_message(chat_id, caption)
                        # دکمه‌ها را به پیوی با ربات بفرست
                        try:
                            requests.post(
                                f"{api}/sendMessage",
                                json={
                                    'chat_id': int(self.user_id),
                                    'text': f"👤 مدیریت {name}\nID: {tid}\n\nاز دکمه‌ها برای قفل/دشمن استفاده کن:",
                                    'reply_markup': kb_dict
                                },
                                timeout=12
                            )
                        except Exception:
                            pass
                        sent = True
                    except Exception as e:
                        logger.error(f"user panel telethon fallback: {e}")
                for path in (avatar_path, photo_path):
                    if path and path != avatar_path or True:
                        try:
                            if path and os.path.exists(path) and 'uav_' in str(path) or (path and 'up_' in str(path)):
                                os.remove(path)
                        except Exception:
                            pass
                try:
                    await event.delete()
                except Exception:
                    pass
                if not sent:
                    await self.client.send_message(chat_id, "❌ ارسال پنل کاربر ناموفق بود")
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




def render_panel_image(username: str, avatar_path: str = None) -> str:
    """هدر پنل: تصویر کامل طراحی‌شده VROOM + آواتار در دایره + نام کاربر به‌جای VROOM پایین"""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
        ensured = ensure_panel_header_files()
        base_candidates = [
            ensured,
            PANEL_HEADER_IMAGE,
            "panel_header.png",
            "panel_header_base.png",
            "/app/panel_header.png",
            "/app/panel_header_base.png",
            os.path.join("media_storage", "panel_header.png"),
            os.path.join("media_storage", "panel_header_base.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header_base.png"),
        ]
        base_path = None
        for p in base_candidates:
            try:
                if p and os.path.exists(p) and os.path.getsize(p) > 1000:
                    base_path = p
                    break
            except Exception:
                continue
        if not base_path:
            logger.error("هیچ تصویر پنل یافت نشد!")
            return None
        img = Image.open(base_path).convert('RGBA')
        draw = ImageDraw.Draw(img)
        W, H = img.size
        try:
            font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(40, W // 24))
        except Exception:
            try:
                font_name = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", max(40, W // 24))
            except Exception:
                font_name = ImageFont.load_default()
        safe_name = (username or "User")[:28]
        for ch in ('_', '*', '`', '[', ']'):
            safe_name = safe_name.replace(ch, ' ')
        # آواتار داخل دایره پورتال مرکزی
        if avatar_path and os.path.exists(avatar_path):
            try:
                avatar = Image.open(avatar_path).convert('RGBA')
                size = int(min(W, H) * 0.20)
                avatar = ImageOps.fit(avatar, (size, size), centering=(0.5, 0.5))
                mask = Image.new('L', (size, size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
                avatar.putalpha(mask)
                pos_x = (W - size) // 2
                pos_y = int(H * 0.30) - size // 2
                img.paste(avatar, (pos_x, pos_y), avatar)
            except Exception as e:
                logger.debug(f"avatar overlay: {e}")
        # پوشش فقط ناحیه بنر VROOM پایین با نام کاربر (طراحی کامل حفظ می‌شود)
        bar_h = int(H * 0.11)
        overlay = Image.new('RGBA', (W, bar_h), (5, 8, 14, 200))
        img.paste(overlay, (0, H - bar_h), overlay)
        try:
            bbox = draw.textbbox((0, 0), safe_name, font=font_name)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw = len(safe_name) * 20
            th = 36
        draw = ImageDraw.Draw(img)
        text_x = max(0, (W - tw) // 2)
        text_y = H - bar_h + max(0, (bar_h - th) // 2 - 2)
        draw.text((text_x + 2, text_y + 2), safe_name, font=font_name, fill=(0, 15, 35, 160))
        draw.text((text_x, text_y), safe_name, font=font_name, fill=(160, 220, 255, 255))
        out = os.path.join(MEDIA_FOLDER, f"panel_{abs(hash(safe_name + str(avatar_path or ''))) % 10**9}.png")
        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        img.convert('RGB').save(out, 'PNG', quality=95)
        return out
    except Exception as e:
        logger.error(f"render_panel_image: {e}\n{traceback.format_exc()}")
        for p in [PANEL_HEADER_IMAGE, "panel_header.png", "panel_header_base.png"]:
            if os.path.exists(p):
                return p
        return None



def render_user_panel_image(username: str, avatar_path: str = None) -> str:
    """تصویر پنل کاربر: طراحی VROOM + آواتار همان کاربر + نام کاربر پایین"""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
        ensured = ensure_panel_header_files()
        base_candidates = [
            ensured,
            "user_panel_header.png",
            PANEL_HEADER_IMAGE,
            "panel_header.png",
            "panel_header_base.png",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_panel_header.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel_header.png"),
            os.path.join("media_storage", "user_panel_header.png"),
            os.path.join("media_storage", "panel_header.png"),
        ]
        base_path = None
        for pth in base_candidates:
            try:
                if pth and os.path.exists(pth) and os.path.getsize(pth) > 1000:
                    base_path = pth
                    break
            except Exception:
                continue
        if not base_path:
            return None
        img = Image.open(base_path).convert('RGBA')
        W, H = img.size
        try:
            font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(36, W // 24))
        except Exception:
            font_name = ImageFont.load_default()
        safe_name = (username or "User")[:28]
        for ch in ('_', '*', '`', '[', ']'):
            safe_name = safe_name.replace(ch, ' ')
        if avatar_path and os.path.exists(avatar_path):
            try:
                avatar = Image.open(avatar_path).convert('RGBA')
                size = int(min(W, H) * 0.22)
                avatar = ImageOps.fit(avatar, (size, size), centering=(0.5, 0.5))
                mask = Image.new('L', (size, size), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
                avatar.putalpha(mask)
                pos_x = (W - size) // 2
                pos_y = int(H * 0.30) - size // 2
                img.paste(avatar, (pos_x, pos_y), avatar)
            except Exception as e:
                logger.debug(f"user panel avatar: {e}")
        bar_h = int(H * 0.11)
        overlay = Image.new('RGBA', (W, bar_h), (5, 8, 14, 210))
        img.paste(overlay, (0, H - bar_h), overlay)
        draw = ImageDraw.Draw(img)
        try:
            bbox = draw.textbbox((0, 0), safe_name, font=font_name)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = len(safe_name) * 18, 32
        text_x = max(0, (W - tw) // 2)
        text_y = H - bar_h + max(0, (bar_h - th) // 2 - 2)
        draw.text((text_x + 2, text_y + 2), safe_name, font=font_name, fill=(0, 15, 35, 160))
        draw.text((text_x, text_y), safe_name, font=font_name, fill=(160, 220, 255, 255))
        out = os.path.join(MEDIA_FOLDER, f"up_{abs(hash(safe_name + str(avatar_path or ''))) % 10**9}.png")
        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        img.convert('RGB').save(out, 'PNG', quality=95)
        return out
    except Exception as e:
        logger.error(f"render_user_panel_image: {e}")
        return None


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
› ⏱️ پینگ — تأخیر پاسخ ربات.""",
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
