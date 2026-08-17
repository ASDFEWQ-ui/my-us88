
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
from currency_converter import CurrencyConverter
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import urllib.parse

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "T.7",
        "version": "4.9.2"
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

BOT_VERSION = "4.9.2"
BOT_CREATOR = "T.7"
PANEL_HEADER_IMAGE = "panel_header.png"  # تصویر بالای پنل

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

COMMAND_KEYWORDS = ('لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال', 'حذف', 'ست', 'بولد', 'زیرخط', 'خط خورده', 'نقل قول', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک', 'ریکت', 'پیوی', 'گروه', 'درباره', 'من کی ام', 'قفل', 'باز', 'تنظیم', 'گروه گزارش', 'دشمن', 'دوست', 'دشمن گروه', 'دوست گروه', 'کانال', 'کامنت', 'تست', 'لیست دشمن', 'لیست اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'اضافه اسپم', 'اتمام اسپم', 'تغییر اسم', 'تغییر بیو', 'تغییر پروفایل', 'پروف', 'اسپم روشن', 'اسپم خاموش', 'پینگ', 'سرچ', 'خروج سرچ', 'قلب پیشرفته', 'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', '/panel', '.اهنگ', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش', 'پین', 'تگ ادمین', 'امار گپ', '.کد', 'تقویم', 'فونت', 'انگلیسی', 'عربی', 'عبری', 'روسی', 'ترکی', 'اتوسین', 'تگ همه', 'لغو تگ', 'منشی', 'افزودن پاسخ', 'حذف پاسخ', 'لیست پاسخ', 'پاک کردن پاسخ‌ها', 'بولینگ', 'تاس', 'سه رنگ', 'شانس', 'تاریخ ساخت اکانت', 'نشست‌های فعال', 'اطلاعات سیستم', 'قیمت ارز', 'نرخ ارز', 'استیکر متن', 'اسکرین‌شات', 'تشخیص متن', 'ساعت در بیو', 'ساعت در بیو ۲', 'بیو تاریخ', 'بیو کامل', 'بیو عاشقانه')

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
    
    async def update_bio_with_settings(self):
        try:
            if not self.client or not self.client.is_connected():
                logger.warning(f"کلاینت برای کاربر {self.user_id} متصل نیست")
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
            custom_text = self.get_bio_setting('بیو_متن_دلخواه') == 'روشن'
            
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
            elif custom_text:
                custom = self.get_bio_setting('بیو_متن_دلخواه_متن')
                new_bio = f'{custom} | {bio_text} | {create_time()}'
            
            if new_bio:
                await self.client(UpdateProfileRequest(about=new_bio))
                logger.info(f"بیو به‌روزرسانی شد: {new_bio[:50]}...")
        except Exception as e:
            logger.error(f"خطا در به‌روزرسانی بیو: {e}")
    
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
                    if status == 'روشن':
                        await self.update_bio_with_settings()
                        await event.edit(f"✅ {bio_cmd} **{status}** شد و بیو به‌روزرسانی شد")
                    else:
                        await event.edit(f"✅ {bio_cmd} **{status}** شد")
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
            await event.edit(f"🏓 پینگ: {ping} ms")
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
            try:
                # تصویر هدر + متن راهنما از طریق سلف
                me = await self.client.get_me()
                name = (me.first_name or "User")
                caption = get_main_panel_text(me)
                photo_path = render_panel_image(name)
                # سعی برای آواتار
                try:
                    if photo_path and me.photo:
                        from PIL import Image, ImageDraw, ImageOps
                        pf = await self.client.download_profile_photo(me, file=f"{MEDIA_FOLDER}/pf_self_{self.user_id}.jpg")
                        if pf and os.path.exists(pf):
                            base = Image.open(photo_path).convert('RGBA')
                            avatar = Image.open(pf).convert('RGBA')
                            size = min(base.size) // 3
                            avatar = ImageOps.fit(avatar, (size, size), centering=(0.5, 0.5))
                            mask = Image.new('L', (size, size), 0)
                            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
                            avatar.putalpha(mask)
                            pos = ((base.size[0] - size) // 2, (base.size[1] - size) // 2 + 10)
                            base.paste(avatar, pos, avatar)
                            base.convert('RGB').save(photo_path)
                            try:
                                os.remove(pf)
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"self panel avatar: {e}")
                bot_username = BOT_USERNAME.replace('@', '')
                # یک پیام واحد: عکس + توضیح — دکمه‌ها فقط از ربات با /panel
                extra = f"\n\n⬛ دکمه‌های کنترل:\nدر ربات @{bot_username} بنویس: پنل\nیا /panel"
                if photo_path and os.path.exists(photo_path):
                    await self.client.send_file(chat_id, photo_path, caption=caption + extra)
                else:
                    await self.client.send_message(chat_id, caption + extra)
                # تلاش برای اینلاین (متن+دکمه) در صورت امکان
                try:
                    results = await self.client.inline_query(bot_username, '')
                    if results:
                        await results[0].click(chat_id)
                except Exception as e:
                    logger.debug(f"inline panel: {e}")
            except Exception as e:
                try:
                    await self.client.send_message(chat_id, f"❌ خطا در باز کردن پنل: {str(e)[:100]}")
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
        
        # ========== اسپم دشمن (پیوی / گروه) — یک اسپم به ازای هر پیام، بدون حذف ==========
        if not event.message.out and event.sender_id:
            try:
                sender_id = event.sender_id
                is_pv = isinstance(event.message.peer_id, PeerUser)
                chat_type = 'pv' if is_pv else 'group'
                if db.is_enemy(self.user_id, sender_id, chat_type):
                    spam_list = db.get_enemy_spam_messages(self.user_id)
                    if spam_list:
                        import random as _rnd
                        spam_text = _rnd.choice(spam_list)['text']
                    else:
                        spam_text = _rnd.choice(SPAM_MESSAGES) if SPAM_MESSAGES else "..."
                    try:
                        settings_e = db.get_selfbot_settings(self.user_id)
                        text_s, entities = await apply_text_style(spam_text, settings_e.get('text_style'))
                        await event.reply(text_s, formatting_entities=entities if entities else None)
                    except Exception as e:
                        try:
                            await self.client.send_message(event.chat_id, spam_text, reply_to=event.message.id)
                        except Exception as e2:
                            logger.error(f"اسپم دشمن: {e} | {e2}")
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
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="⬛ T.7 CONTROL",
                description="پنل مدیریت سلف‌بات",
                input_message_content=InputTextMessageContent(get_main_panel_text(query.from_user)),
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
            ("🛠 ابزار", "tools", "امار گپ / کد QR / تگ ادمین / پین / سلف روشن/خاموش"),
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




def render_panel_image(username: str) -> str:
    """هدر پنل T.7 با نام کاربر — فونت درشت و تم تیره"""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        W, H = 1280, 720
        img = Image.new('RGB', (W, H), (6, 8, 12))
        draw = ImageDraw.Draw(img)
        # گرادیان ساده
        for y in range(H):
            c = int(6 + (y / H) * 22)
            draw.line([(0, y), (W, y)], fill=(c, c + 3, c + 10))
        blue = (0, 200, 255)
        # قاب
        draw.rectangle([16, 16, W-16, H-16], outline=blue, width=4)
        draw.rectangle([32, 32, W-32, H-32], outline=(0, 90, 140), width=2)
        try:
            font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        except Exception:
            font_xl = ImageFont.load_default()
            font_lg = font_xl
            font_md = font_xl
        draw.text((70, 50), "T.7", font=font_xl, fill=blue)
        draw.text((70, 180), "CONTROL PANEL", font=font_lg, fill=(200, 220, 240))
        # دایره مرکز
        cx, cy, r = W // 2, H // 2 + 30, 170
        draw.ellipse([cx-r-6, cy-r-6, cx+r+6, cy+r+6], outline=blue, width=5)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(30, 50, 80), width=2)
        safe_name = (username or "User")[:28]
        for ch in ('_', '*', '`'):
            safe_name = safe_name.replace(ch, ' ')
        draw.text((70, H - 110), safe_name, font=font_md, fill=(240, 245, 255))
        draw.text((70, H - 160), "USER", font=font_md, fill=(100, 130, 160))
        out = os.path.join(MEDIA_FOLDER, f"panel_{abs(hash(safe_name)) % 10**8}.png")
        os.makedirs(MEDIA_FOLDER, exist_ok=True)
        img.save(out, 'PNG')
        return out
    except Exception as e:
        logger.error(f"render_panel_image: {e}")
        if os.path.exists(PANEL_HEADER_IMAGE):
            return PANEL_HEADER_IMAGE
        return None

def get_main_panel_text(user):
    """متن اصلی پنل بدون Markdown تا خطای parse entities ندهد"""
    try:
        name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None) or "User"
    except Exception:
        name = "User"
    # کاراکترهای مشکل‌ساز مارک‌داون را خنثی می‌کنیم
    for ch in ('_', '*', '`', '['):
        name = name.replace(ch, ' ')
    return (
        f"⬛ T.7 CONTROL\n"
        f"👤 {name}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"سلف‌بات آنلاین • دسترسی خصوصی\n"
        f"نسخه {BOT_VERSION}"
    )

def get_help_back_keyboard(user_id, back_callback):
    """دکمه بازگشت برای صفحات راهنما"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data=back_callback, style="danger")]
    ])

async def refresh_panel_keyboard(query, user_id, menu_text, keyboard_func):
    """به‌روزرسانی فوری کیبورد پنل با تیک‌های جدید"""
    try:
        await query.edit_message_text(menu_text, reply_markup=keyboard_func(user_id))
    except Exception as e1:
        try:
            await query.edit_message_reply_markup(reply_markup=keyboard_func(user_id))
        except Exception as e2:
            print(f"⚠️ refresh_panel failed: {e1} | {e2}")

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
    if selected == 'all':
        selected_set = set()
        all_selected = True
    else:
        selected_set = set(selected) if isinstance(selected, list) else set()
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
    bio_time1 = db.get_bio_setting(user_id, 'ساعت_در_بیو')
    bio_time2 = db.get_bio_setting(user_id, 'ساعت_در_بیو_۲')
    bio_date = db.get_bio_setting(user_id, 'بیو_تاریخ')
    bio_full = db.get_bio_setting(user_id, 'بیو_کامل')
    bio_love = db.get_bio_setting(user_id, 'بیو_عاشقانه')
    bio_emoji = db.get_bio_setting(user_id, 'بیو_ایموجی')
    bio_season = db.get_bio_setting(user_id, 'بیو_فصل')
    bio_weekday = db.get_bio_setting(user_id, 'بیو_روز_هفته')
    bio_countdown = db.get_bio_setting(user_id, 'بیو_شمارش_معکوس')
    bio_custom = db.get_bio_setting(user_id, 'بیو_متن_دلخواه')
    
    keyboard = [
        [
            InlineKeyboardButton(f"🕐 ساعت در بیو {'' if bio_time1 != 'روشن' else '✓'}", callback_data=f"exec_bio_time1_{user_id}", style="success" if bio_time1 != 'روشن' else "primary"),
            InlineKeyboardButton(f"🕐 ساعت در بیو ۲ {'' if bio_time2 != 'روشن' else '✓'}", callback_data=f"exec_bio_time2_{user_id}", style="success" if bio_time2 != 'روشن' else "primary")
        ],
        [
            InlineKeyboardButton(f"📅 بیو تاریخ {'' if bio_date != 'روشن' else '✓'}", callback_data=f"exec_bio_date_{user_id}", style="success" if bio_date != 'روشن' else "primary"),
            InlineKeyboardButton(f"📅 بیو کامل {'' if bio_full != 'روشن' else '✓'}", callback_data=f"exec_bio_full_{user_id}", style="success" if bio_full != 'روشن' else "primary")
        ],
        [
            InlineKeyboardButton(f"💕 بیو عاشقانه {'' if bio_love != 'روشن' else '✓'}", callback_data=f"exec_bio_love_{user_id}", style="success" if bio_love != 'روشن' else "primary"),
            InlineKeyboardButton(f"🎨 بیو ایموجی {'' if bio_emoji != 'روشن' else '✓'}", callback_data=f"exec_bio_emoji_{user_id}", style="success" if bio_emoji != 'روشن' else "primary")
        ],
        [
            InlineKeyboardButton(f"🌸 بیو فصل {'' if bio_season != 'روشن' else '✓'}", callback_data=f"exec_bio_season_{user_id}", style="success" if bio_season != 'روشن' else "primary"),
            InlineKeyboardButton(f"📆 بیو روز هفته {'' if bio_weekday != 'روشن' else '✓'}", callback_data=f"exec_bio_weekday_{user_id}", style="success" if bio_weekday != 'روشن' else "primary")
        ],
        [
            InlineKeyboardButton(f"⏳ بیو شمارش معکوس {'' if bio_countdown != 'روشن' else '✓'}", callback_data=f"exec_bio_countdown_{user_id}", style="success" if bio_countdown != 'روشن' else "primary"),
            InlineKeyboardButton(f"✏️ بیو متن دلخواه {'' if bio_custom != 'روشن' else '✓'}", callback_data=f"exec_bio_custom_{user_id}", style="success" if bio_custom != 'روشن' else "primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"time_menu_{user_id}", style="danger")
        ]
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

def get_lock_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🔗 قفل لینک", callback_data=f"exec_lock_link_{user_id}", style="danger"),
            InlineKeyboardButton("📸 قفل عکس", callback_data=f"exec_lock_photo_{user_id}", style="danger"),
            InlineKeyboardButton("🎥 قفل ویدیو", callback_data=f"exec_lock_video_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("🎨 قفل استیکر", callback_data=f"exec_lock_sticker_{user_id}", style="danger"),
            InlineKeyboardButton("🎞️ قفل گیف", callback_data=f"exec_lock_gif_{user_id}", style="danger"),
            InlineKeyboardButton("🎤 قفل ویس", callback_data=f"exec_lock_voice_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📁 قفل فایل", callback_data=f"exec_lock_file_{user_id}", style="danger"),
            InlineKeyboardButton("🎵 قفل موزیک", callback_data=f"exec_lock_music_{user_id}", style="danger"),
            InlineKeyboardButton("📹 قفل ویدیو نوت", callback_data=f"exec_lock_video_note_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📞 قفل کانتکت", callback_data=f"exec_lock_contact_{user_id}", style="danger"),
            InlineKeyboardButton("📍 قفل لوکیشن", callback_data=f"exec_lock_location_{user_id}", style="danger"),
            InlineKeyboardButton("😀 قفل ایموجی", callback_data=f"exec_lock_emoji_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📝 قفل متن", callback_data=f"exec_lock_text_{user_id}", style="danger")
        ],
        [
            InlineKeyboardButton("📖 راهنمای کامل قفل رسانه", callback_data=f"exec_lock_help_{user_id}", style="primary")
        ],
        [
            InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main", style="danger")
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
            InlineKeyboardButton("⏱️ پینگ", callback_data=f"exec_ping_{user_id}", style="primary")
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
    if '_' in data and not data.startswith(('admin_', 'approve_', 'reject_', 'stop_selfbot_', 'restart_selfbot_', 'desc_', 'menu_')):
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
    if data == "back_main":
        try:
            await query.edit_message_text(
                get_main_panel_text(query.from_user),
                reply_markup=get_main_panel_keyboard(user_id)
            )
        except Exception as e:
            # اگر پیام عکس‌دار بود و فقط caption قابل ویرایش است
            try:
                await query.edit_message_caption(
                    caption=get_main_panel_text(query.from_user),
                    reply_markup=get_main_panel_keyboard(user_id)
                )
            except Exception as e2:
                logger.error(f"back_main edit failed: {e} | {e2}")
                await query.answer("پنل به‌روز شد", show_alert=False)
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
    if data.startswith("exec_"):
        await exec_command_handler(update, context)
        return
    if data.startswith("bio_menu_"):
        await query.edit_message_text("📝 **تنظیمات بیو**\n\nانتخاب کنید:", reply_markup=get_bio_menu_keyboard(user_id))
        return
    if data.startswith("font_menu_"):
        await query.edit_message_text("🔤 **انتخاب فونت تایم**\n\nفونت‌های انتخاب‌شده به ترتیب در پروفایل چرخش می‌کنند.\nروی هر فونت بزنید تا تیک بخورد (چندتایی هم می‌شود).\n«همه فونت‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_font_menu_keyboard(user_id))
        return
    if data.startswith("flag_menu_"):
        await query.edit_message_text("🏳️ **انتخاب پرچم**\n\nپرچم‌های انتخاب‌شده در تایمر پرچم استفاده می‌شوند.\nروی هر پرچم بزنید تا تیک بخورد.\n«همه پرچم‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_flag_menu_keyboard(user_id))
        return
    
    parts = data.split('_')
    if len(parts) > 1:
        action = parts[0]
        menu_keyboards = {
            "time": ("⚈ دستورات زمان و پروفایل\n\n• تایم روشن\n• تایمر پرچم روشن\n• تایم خاموش\n• تایم [اعداد]\n• تقویم\n• انتخاب فونت تایم\n• انتخاب پرچم", get_time_menu_keyboard),
            "bio": ("📝 **تنظیمات بیو**\n\nانتخاب کنید:", get_bio_menu_keyboard),
            "font": ("🔤 **انتخاب فونت تایم**\n\nفونت‌های انتخاب‌شده به ترتیب در پروفایل چرخش می‌کنند.", get_font_menu_keyboard),
            "flag": ("🏳️ **انتخاب پرچم**\n\nپرچم‌های انتخاب‌شده در تایمر پرچم استفاده می‌شوند.", get_flag_menu_keyboard),
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
            "tools": ("🛠 ابزارها\n\n• امار گپ\n• کد QR\n• تگ ادمین\n• پین\n• سلف روشن/خاموش", get_tools_menu_keyboard),
            "monshi": ("🤖 **منشی هوشمند**\n\nمدیریت پاسخ‌های خودکار", get_monshi_menu_keyboard),
            "mention": ("🏷️ **تگ همه**\n\nتگ کردن همه اعضای گروه به صورت ۱۳ نفره", get_mention_menu_keyboard),
            "fortune": ("🔮 **فال و طالع‌بینی**\n\nانتخاب کنید:", get_fortune_menu_keyboard)
        }
        if action in menu_keyboards and parts[1] == "menu":
            text, keyboard_func = menu_keyboards[action]
            await query.edit_message_text(text, reply_markup=keyboard_func(user_id))
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
    cmd = data.replace(f'exec_', '').replace(f'_{user_id}', '')
    
    msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ در حال اجرا...")
    
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
        if cmd.startswith(cmd_key):
            current = manager.get_bio_setting(setting_name)
            new_status = 'خاموش' if current == 'روشن' else 'روشن'
            manager.set_bio_setting(setting_name, new_status)
            if new_status == 'روشن':
                await manager.update_bio_with_settings()
            await msg.edit_text(f"✅ {setting_name}: **{new_status}**")
            try:
                await refresh_panel_keyboard(query, user_id, "📝 تنظیمات بیو — به‌روز شد", get_bio_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
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
        await msg.edit_text("✅ منشی فعال شد")
        try:
            await refresh_panel_keyboard(query, user_id, "🗣 منشی — به‌روز شد", get_monshi_menu_keyboard)
        except Exception as _panel_refresh_err:
            print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
        return
    if cmd == 'monshi_off':
        db.set_monshi_status(user_id, False)
        manager.monshi_mode = False
        await msg.edit_text("✅ منشی غیرفعال شد")
        try:
            await refresh_panel_keyboard(query, user_id, "🗣 منشی — به‌روز شد", get_monshi_menu_keyboard)
        except Exception as _panel_refresh_err:
            print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
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
        await msg.edit_text("✅ سلف‌بات فعال شد")
        return
    
    if cmd == 'self_off':
        db.update_selfbot_setting(user_id, 'selfbot_enabled', 0)
        await msg.edit_text("✅ سلف‌بات غیرفعال شد")
        return
    
    if cmd.startswith('time_on'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.update_profile_name()
        await msg.edit_text("✅ تایم روشن شد")
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل — وضعیت به‌روز شد", get_time_menu_keyboard)
        return
    if cmd.startswith('time_flag'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)
        await manager.update_profile_name()
        await msg.edit_text("✅ تایمر پرچم روشن شد")
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل — وضعیت به‌روز شد", get_time_menu_keyboard)
        return
    if cmd.startswith('time_off'):
        db.update_selfbot_setting(user_id, 'time_enabled', 0)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.restore_profile_name()
        await msg.edit_text("✅ تایم خاموش شد")
        await refresh_panel_keyboard(query, user_id, "⚫️ زمان و پروفایل — وضعیت به‌روز شد", get_time_menu_keyboard)
        return
    
    # ========== فونت تایم ==========
    if cmd == 'font_all':
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = 'all'
        await msg.edit_text("✅ همه فونت‌ها فعال شد (چرخش خودکار)")
        try:
            await query.message.edit_text("🔤 **انتخاب فونت تایم**\n\nفونت‌های انتخاب‌شده به ترتیب در پروفایل چرخش می‌کنند.\nروی هر فونت بزنید تا تیک بخورد (چندتایی هم می‌شود).\n«همه فونت‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_font_menu_keyboard(user_id))
        except Exception as e:
            print(f"refresh font: {e}")
        return
    if cmd == 'font_clear':
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        if user_id_str in selfbot_managers:
            selfbot_managers[user_id_str].time_font_indices = 'all'
        await msg.edit_text("✅ انتخاب فونت پاک شد → همه فونت‌ها")
        try:
            await query.message.edit_text("🔤 **انتخاب فونت تایم**\n\nفونت‌های انتخاب‌شده به ترتیب در پروفایل چرخش می‌کنند.\nروی هر فونت بزنید تا تیک بخورد (چندتایی هم می‌شود).\n«همه فونت‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_font_menu_keyboard(user_id))
        except Exception as e:
            print(f"refresh font: {e}")
        return
    if cmd.startswith('font_sel_'):
        try:
            idx = int(cmd.split('_')[2])
        except:
            await msg.edit_text("❌ ایندکس نامعتبر")
            return
        settings = db.get_selfbot_settings(user_id)
        current = settings.get('time_font_indices', 'all')
        if current == 'all':
            new_list = [idx]
        else:
            new_list = list(current) if isinstance(current, list) else []
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
        await msg.edit_text(f"✅ فونت {idx} به‌روزرسانی شد")
        try:
            await query.message.edit_text("🔤 **انتخاب فونت تایم**\n\nفونت‌های انتخاب‌شده به ترتیب در پروفایل چرخش می‌کنند.\nروی هر فونت بزنید تا تیک بخورد (چندتایی هم می‌شود).\n«همه فونت‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_font_menu_keyboard(user_id))
        except Exception as e:
            print(f"refresh font: {e}")
        return
    
    # ========== پرچم ==========
    if cmd == 'flag_all':
        db.update_selfbot_setting(user_id, 'selected_flags', 'all')
        await msg.edit_text("✅ همه پرچم‌ها فعال شد")
        try:
            await query.message.edit_text("🏳️ **انتخاب پرچم**\n\nپرچم‌های انتخاب‌شده در تایمر پرچم استفاده می‌شوند.\nروی هر پرچم بزنید تا تیک بخورد.\n«همه پرچم‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_flag_menu_keyboard(user_id))
        except Exception as e:
            print(f"refresh flag: {e}")
        return
    if cmd == 'flag_clear':
        db.update_selfbot_setting(user_id, 'selected_flags', 'all')
        await msg.edit_text("✅ انتخاب پرچم پاک شد → همه پرچم‌ها")
        try:
            await query.message.edit_text("🏳️ **انتخاب پرچم**\n\nپرچم‌های انتخاب‌شده در تایمر پرچم استفاده می‌شوند.\nروی هر پرچم بزنید تا تیک بخورد.\n«همه پرچم‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_flag_menu_keyboard(user_id))
        except Exception as e:
            print(f"refresh flag: {e}")
        return
    if cmd.startswith('flag_sel_'):
        try:
            idx = int(cmd.split('_')[2])
            fl = flags[idx]
        except:
            await msg.edit_text("❌ ایندکس نامعتبر")
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
        await msg.edit_text(f"✅ پرچم {fl} به‌روزرسانی شد")
        try:
            await query.message.edit_text("🏳️ **انتخاب پرچم**\n\nپرچم‌های انتخاب‌شده در تایمر پرچم استفاده می‌شوند.\nروی هر پرچم بزنید تا تیک بخورد.\n«همه پرچم‌ها» یعنی چرخش خودکار روی همه.", reply_markup=get_flag_menu_keyboard(user_id))
        except Exception as e:
            print(f"refresh flag: {e}")
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
        'google_help': """📖 **راهنمای گوگل و آهنگ**

🔍 **سرچ** — حالت جستجوی گوگل را روشن می‌کند. بعد از روشن شدن، هر متنی بفرستید جستجو می‌شود.
❌ **خروج جستجو** — حالت سرچ را خاموش می‌کند.
🎵 **آهنگ** — برای پخش آهنگ از دستور `.اهنگ [نام]` استفاده کنید.

مثال: `.اهنگ شادمهر`""",
        'time_help': """📖 **راهنمای زمان و پروفایل**

🕐 **تایم روشن** — ساعت را در اسم پروفایل نمایش می‌دهد.
🏳️ **تایمر پرچم** — علاوه بر ساعت، پرچم هم در اسم می‌چرخد.
🚫 **تایم خاموش** — نمایش ساعت/پرچم را قطع می‌کند.
📅 **تقویم** — تاریخ شمسی و میلادی را نشان می‌دهد.
🔤 **انتخاب فونت تایم** — فونت‌های ساعت را انتخاب کنید (چندتایی با تیک).
🏳️ **انتخاب پرچم** — پرچم‌های مورد نظر را برای چرخش انتخاب کنید.
📝 **تنظیمات بیو** — ساعت/تاریخ/فصل و ... را در بیو قرار دهید.""",
        'animation_help': """📖 **راهنمای انیمیشن**

❤️ **قلب** — انیمیشن ساده قلب
🌙 **ماه** — انیمیشن ماه
💖 **قلب پیشرفته** — انیمیشن چندمرحله‌ای قلب
💝 **عشق** — انیمیشن I Love You
🕯️ **سنتت** — نوار پیشرفت تقلبی
💻 **هک** — انیمیشن هک تقلبی
🎨 **استیکر متن** — ساخت استیکر از متن با دستور `استیکر متن [متن]`""",
        'user_help': """📖 **راهنمای مدیریت کاربران**

🥷 **دشمن** — ریپلای در پیوی: هر پیام دشمن با یک اسپم جواب داده می‌شود (پیام پاک نمی‌شود).
🧸 **دوست** — پایان دشمن پیوی.
👥 **دشمن گروه** — ریپلای در گروه: فقط در گروه روی همان کاربر اسپم ریپلای می‌شود.
🧸 **دوست گروه** — پایان دشمن گروه.
🔒 **قفل پیوی** — پیام‌های آن کاربر در پی‌وی حذف می‌شود.
🔓 **باز پی** — قفل پی‌وی را برمی‌دارد.
🔒 **قفل پیوی همه** — همه پی‌وی‌ها قفل می‌شوند.
🔓 **باز پی همه** — قفل همگانی برداشته می‌شود.
⛔ **بلاک** — کاربر را بلاک می‌کند (با ریپلای).""",
        'comment_help': """📖 **راهنمای کامنت خودکار**

💬 **کامنت [متن]** — برای کانال فعلی متن کامنت خودکار تنظیم می‌کند.
📊 **کانال‌ها** — لیست کانال‌های تنظیم‌شده را نشان می‌دهد.
🗑️ **حذف کانال** — تنظیمات کانال فعلی را حذف می‌کند.
🔍 **تست کانال** — وضعیت تنظیمات کانال فعلی را چک می‌کند.

نکته: در کانال/گروه مرتبط دستور `کامنت متن شما` را بزنید.""",
        'general_help': """📖 **راهنمای عمومی**

📊 **وضعیت** — وضعیت فعلی سلف‌بات و تنظیمات.
ℹ️ **درباره** — نسخه و سازنده.
⏱️ **پینگ** — تأخیر پاسخ ربات.""",
        'action_help': """📖 **راهنمای اکشن**

🎮 **اکشن [نام]** — وضعیت در حال انجام را شبیه‌سازی می‌کند.
⏹️ **اکشن خاموش** — اکشن فعال را قطع می‌کند.
📋 **اکشن لیست** — لیست اکشن‌های موجود.

اکشن‌ها: تایپ، ویس، ویدیو، عکس، فیلم، فایل، بازی، استیکر، موقعیت، تماس، صحبت، لغو""",
        'games_help': """📖 **راهنمای بازی‌ها**

🎲 **تاس ۱ تا ۶** — تاس می‌اندازد تا عدد هدف بیاید.
🎯 **دارت** — تا ۶ بیاید.
🏀 **بسکتبال** — تا ۵ بیاید.
⚽️ **فوتبال** — تا ۵ بیاید.
🎳 **بولینگ** — تا ۶ بیاید.
🎨 **سه رنگ** — بازی شانسی رنگ.
دستور متنی: `شانس [عدد]` و `تاس [عدد]`""",
        'translate_help': """📖 **راهنمای ترجمه خودکار**

با روشن کردن هر زبان، پیام‌های خروجی شما به آن زبان ترجمه و ارسال می‌شوند.
🇬🇧 انگلیسی | 🇸🇦 عربی | 🇮🇱 عبری | 🇷🇺 روسی | 🇹🇷 ترکی

روی دکمه بزنید تا روشن/خاموش شود (تیک ✓).""",
        'info_help': """📖 **راهنمای اطلاعاتی**

📋 **اطلاعات** — اطلاعات کاربر با ریپلای.
⬇️ **دانلود پروفایل** — عکس پروفایل کاربر (ریپلای).
📅 **تاریخ ساخت اکانت** — از ربات creationdatebot.
📱 **نشست‌های فعال** — لیست دستگاه‌های لاگین.
🖥️ **اطلاعات سیستم** — RAM/CPU سرور.
💰 **قیمت ارز** — دستور: `قیمت ارز BTC`
💵 **نرخ ارز** — نرخ ارزهای جهانی.
🔍 **تشخیص متن** — OCR روی عکس (ریپلای).""",
        'profile_help': """📖 **راهنمای پروفایل**

📸 **ست پروف** — عکس ریپلای‌شده را پروفایل می‌کند.
✏️ **ست بیو** — متن ریپلای را بیو می‌کند.
🗑️ **حذف ست پروف / بیو** — پروفایل یا بیو را پاک می‌کند.""",
        'style_help': """📖 **راهنمای استایل متن**

با فعال کردن هر استایل، پیام‌های خروجی شما با آن فرمت ارسال می‌شوند:
بولد، زیرخط، خط خورده، نقل قول، اسپویلر، کج، کد، پیش

دوباره زدن همان دکمه = خاموش.""",
        'message_help': """📖 **راهنمای مدیریت پیام**

🧹 **حذف کامل** — همه پیام‌های شما در چت.
🧹 **حذف کامل ۵۰** — ۵۰ پیام آخر شما.
🗑️ **حذف ۱۰** — ۱۰ پیام آخر.
👁️ **فعال اتوسین** — پیام‌های دریافتی خودکار سین می‌شوند.
🙈 **غیرفعال اتوسین**
📸 **اسکرین‌شات** — نوتیفیکیشن اسکرین‌شات شبیه‌سازی.""",
        'reaction_help': """📖 **راهنمای ریکشن**

👍 **ریکت** — با ریپلای روی پیام کاربر + دستور `ریکت 🔥` ریکت خودکار تنظیم می‌شود.
در گروه و پی‌وی کار می‌کند.
❌ **حذف ریکت** — با ریپلای، ریکت آن کاربر را حذف می‌کند.

ایموجی‌های مجاز در لیست ALLOWED_EMOJIS هستند.""",
        'spam_help': """📖 **راهنمای اسپم**

📩 **اسپم** — دستور: `اسپم [تعداد] [متن]`
مثال: `اسپم 5 سلام`

برای دشمنان از بخش مدیریت دشمنان استفاده کنید.""",
        'change_help': """📖 **راهنمای تغییر پروفایل**

✏️ **تغییر اسم [نام]** — اسم پروفایل را عوض می‌کند.
✏️ **تغییر بیو [متن]** — بیو را عوض می‌کند.
📸 **تغییر پروفایل / پروف** — با ریپلای روی عکس.""",
        'enemy_help': """📖 **راهنمای دشمنان**

📋 **لیست دشمن** — دشمنان پیوی/گروه.
📝 **اضافه اسپم** — متن‌های اسپم دشمن.
⚠️ دشمن پیوی پیام را پاک نمی‌کند؛ فقط یک اسپم به ازای هر پیام می‌فرستد.
✅ **اتمام اسپم** — خروج از حالت افزودن.
📜 **لیست اسپم** — متن‌های اسپم ذخیره‌شده.
🗑️ **پاک کردن / حذف اسپم** — مدیریت لیست اسپم.""",
        'filter_help': """📖 **راهنمای فیلتر کلمات**

🚫 **.فیلتر [کلمه]** — کلمه را به لیست فیلتر اضافه می‌کند.
✅ **فیلتر روشن** — فیلتر فعال می‌شود (پیام حاوی کلمه حذف می‌شود).
❌ **فیلتر خاموش**
📜 **لیست / مدیریت** — روشن/خاموش یا حذف هر کلمه.""",
        'protection_help': """📖 **راهنمای حفاظت اسپم**

🛡️ **اسپم روشن/خاموش** — محافظت در برابر اسپم دیگران.
⚙️ **تنظیم اسپم [تعداد] [ثانیه]** — محدودیت و زمان میوت.
📊 **وضعیت اسپم** — تنظیمات فعلی.""",
        'ai_help': """📖 **راهنمای هوش مصنوعی**

پیوی ۱/۲/۳ و گروه ۱/۲/۳:
• ۱ = Gemini
• ۲ = Paxsenix
• ۳ = DeepSeek

با روشن کردن، پیام‌های دریافتی در آن محیط با AI پاسخ داده می‌شوند.
خاموش پیوی / خاموش گروه همه را قطع می‌کند.""",
        'report_help': """📖 **راهنمای گزارش**

📍 **تنظیم گزارش** — گروه گزارش را تنظیم می‌کند.
ℹ️ **گروه گزارش** — آیدی گروه فعلی را نشان می‌دهد.

پیام‌های حذف‌شده/ویرایش‌شده و مدیا می‌توانند به گروه گزارش ارسال شوند.""",
        'tools_help': """📖 **راهنمای ابزار**

📊 **امار گپ** — آمار گفتگو با کاربر (ریپلای یا پی‌وی).
🝰 **کد QR** — ساخت QR از متن/عکس (ریپلای).
👑 **تگ ادمین** — منشن ادمین‌های گروه.
📌 **پین** — پین کردن پیام ریپلای‌شده.
🤖 **سلف روشن/خاموش** — فعال/غیرفعال کردن سلف‌بات.""",
        'monshi_help': """📖 **راهنمای منشی هوشمند**

🤖 **منشی** — با دستور `منشی [پاسخ]` فعال می‌شود.
⛔ **خاموش** — منشی را قطع می‌کند.
📝 **افزودن پاسخ** — فرمت: `افزودن پاسخ سوال:جواب`
🗑️ **حذف پاسخ** — `حذف پاسخ سوال`
📋 **لیست پاسخ‌ها**
🧹 **پاک کردن پاسخ‌ها**""",
        'mention_help': """📖 **راهنمای تگ همه**

🏷️ **تگ همه [متن]** — همه اعضای گروه را ۱۳نفره منشن می‌کند.
⛔ **لغو تگ** — عملیات تگ را متوقف می‌کند.

فقط در گروه کار می‌کند.""",
        'fortune_help': """📖 **راهنمای فال**

🌟 **فال عمومی** — یک فال تصادفی.
🕌 **فال حافظ** — بیت حافظ.
☕ **فال قهوه** — فال قهوه.""",
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
        # نمایش راهنما داخل خود پنل + دکمه بازگشت
        try:
            await query.edit_message_text(
                help_body,
                reply_markup=get_help_back_keyboard(user_id, back_cb)
            )
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
        await msg.edit_text("❤️ شروع...")
        try:
            heart_msg = await manager.client.send_message(query.message.chat_id, "❤️")
            await advanced_heart_animation(heart_msg)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    if cmd == 'love':
        await msg.edit_text("💝 شروع...")
        try:
            love_msg = await manager.client.send_message(query.message.chat_id, "💝")
            await advanced_heart_animation(love_msg)
        except Exception as e:
            await msg.edit_text(f"❌ خطا: {e}")
        return
    if cmd == 'santet':
        await msg.edit_text("🕯️ در حال اجرا...")
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
            await msg.edit_text(f"❌ خطا: {e}")
        return
    if cmd == 'hack':
        await msg.edit_text("💻 در حال هک...")
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
        await msg.edit_text(f"🏓 پینگ: {ping} ms")
        return
    if cmd == 'music':
        await msg.edit_text("🎵 دستور اهنگ\n\nبرای جستجو و پخش آهنگ از فرمت زیر استفاده کنید:\n\n`.اهنگ [نام آهنگ]`\n\nمثال: `.اهنگ مهدیار احمدی`")
        return
    
    if cmd == 'heart':
        asyncio.create_task(manager.heart_animation(query.message.chat_id))
        await msg.edit_text("❤️ انیمیشن قلب شروع شد")
        return
    if cmd == 'moon':
        asyncio.create_task(manager.moon_animation(query.message.chat_id))
        await msg.edit_text("🌙 انیمیشن ماه شروع شد")
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
        await msg.edit_text("✅ فیلتر کلمات فعال شد")
        try:
            await refresh_panel_keyboard(query, user_id, "🚫 فیلتر — به‌روز شد", get_filter_menu_keyboard)
        except Exception as _panel_refresh_err:
            print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
        return
    if cmd == 'filter_off':
        db.set_filter_enabled(user_id, False)
        await msg.edit_text("✅ فیلتر کلمات غیرفعال شد")
        try:
            await refresh_panel_keyboard(query, user_id, "🚫 فیلتر — به‌روز شد", get_filter_menu_keyboard)
        except Exception as _panel_refresh_err:
            print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
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
        await msg.edit_text("✅ حفاظت اسپم فعال شد")
        return
    if cmd == 'spam_protection_off':
        db.set_spam_settings(user_id, spam_protection=0)
        await msg.edit_text("✅ حفاظت اسپم غیرفعال شد")
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
        if cmd.startswith(cmd_prefix):
            target_id = 0
            if query.message.reply_to_message:
                target_id = query.message.reply_to_message.from_user.id
            elif query.message.chat.type == 'private':
                target_id = query.message.chat.id
            current = db.get_user_lock(user_id, target_id, cmd_prefix)
            db.set_user_lock(user_id, target_id, cmd_prefix, not current)
            target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
            status = "فعال" if not current else "غیرفعال"
            await msg.edit_text(f"✅ قفل {lock_name} برای {target_name} {status} شد")
            try:
                await query.message.edit_text(query.message.text, reply_markup=get_lock_menu_keyboard(user_id))
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
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
                await msg.edit_text(f"✅ استایل {style_name} غیرفعال شد")
            else:
                db.update_selfbot_setting(user_id, 'text_style', style_name)
                await msg.edit_text(f"✅ استایل {style_name} فعال شد")
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
            await msg.edit_text(f"✅ {ai_data['msg']}")
            try:
                await refresh_panel_keyboard(query, user_id, "🤖 هوش مصنوعی — به‌روز شد", get_ai_menu_keyboard)
            except Exception as _panel_refresh_err:
                print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
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
        await msg.edit_text("✅ اتوسین فعال شد")
        try:
            await refresh_panel_keyboard(query, user_id, "📨 پیام — به‌روز شد", get_message_menu_keyboard)
        except Exception as _panel_refresh_err:
            print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
        return
    if cmd == 'autosend_off':
        manager.autosend_mode = False
        db.update_selfbot_setting(user_id, 'autosend_mode', 0)
        manager.save_state()
        await msg.edit_text("✅ اتوسین غیرفعال شد")
        try:
            await refresh_panel_keyboard(query, user_id, "📨 پیام — به‌روز شد", get_message_menu_keyboard)
        except Exception as _panel_refresh_err:
            print(f"⚠️ [DEBUG پنل] رفرش دکمه‌های پنل قدیمی fail شد (احتمالاً پیام قدیمی/غیرقابل‌دسترسه، مشکلی نیست چون خود عملیات انجام شده): {type(_panel_refresh_err).__name__}: {_panel_refresh_err}")
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
    caption = get_main_panel_text(user)
    keyboard = get_main_panel_keyboard(user_id)
    name = user.full_name or user.first_name or "User"
    photo_path = render_panel_image(name)
    # سعی برای قرار دادن عکس پروفایل کاربر در مرکز
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos and photos.total_count > 0 and photo_path and os.path.exists(photo_path):
            from PIL import Image, ImageDraw, ImageOps
            pf = await context.bot.get_file(photos.photos[0][-1].file_id)
            tmp_pf = os.path.join(MEDIA_FOLDER, f"pf_{user_id}.jpg")
            await pf.download_to_drive(tmp_pf)
            base = Image.open(photo_path).convert('RGBA')
            avatar = Image.open(tmp_pf).convert('RGBA')
            # دایره در مرکز
            size = min(base.size) // 3
            avatar = ImageOps.fit(avatar, (size, size), centering=(0.5, 0.5))
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
            avatar.putalpha(mask)
            pos = ((base.size[0] - size) // 2, (base.size[1] - size) // 2 + 10)
            base.paste(avatar, pos, avatar)
            base.convert('RGB').save(photo_path)
            try:
                os.remove(tmp_pf)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"avatar overlay: {e}")
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
    print("=" * 60)
    print("🤖 T.7 Self-Bot System v4.9.1")
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
    print("🔧 T.7 - PATCH: ریکت‌گروه + ترجمه - v2026-07-01")
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
