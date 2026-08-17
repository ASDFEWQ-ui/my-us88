
import os
import sqlite3
import logging
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
import pytz
import jdatetime
from hijridate import Gregorian
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler
from telegram.request import HTTPXRequest
from telethon import TelegramClient, events, types
from telethon.tl.types import PeerUser, PeerChannel, PeerChat, MessageMediaPhoto, MessageMediaDocument, ReactionEmoji, MessageEntityBold, MessageEntityUnderline, MessageEntityStrike, MessageEntityBlockquote, MessageEntitySpoiler, MessageEntityItalic, MessageEntityCode, MessageEntityPre, InputPeerChat, InputPeerChannel, InputPeerUser, KeyboardButtonSwitchInline
from telethon.tl.functions.messages import SendReactionRequest, DeleteMessagesRequest, SetTypingRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateStatusRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.functions.contacts import BlockRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.errors import MessageDeleteForbiddenError, FloodWaitError, SessionPasswordNeededError, FloodWaitError as TelethonFloodWaitError
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsAdmins

# ========== تنظیمات وب سرور برای Render (پورت 10000) ==========
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot": "Gap_5_bot",
        "version": "4.6.0"
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

# ========== تنظیم زمان ایران برای کل سیستم ==========
os.environ['TZ'] = 'Asia/Tehran'
try:
    time.tzset()
except:
    pass

# ========== تنظیمات گوگل سرچ ==========
GOOGLE_SEARCH_API_KEY = "AIzaSyCMYOU0NpU5xfu7GrffyywVUugd1yD2uDU"
GOOGLE_CSE_ID = "3185e48756dfd482f"
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# ========== تنظیمات هوش مصنوعی ==========
GEMINI_KEY = "AIzaSyBhlSytH4Zfe-ww1D8HsrgJfCf5TRY1SLc"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PAXSENIX_API_KEY = "sk-paxsenix-Xo_BAFNGgWVZ_ymWd02Rk1JHbyoDSEzfPhiolJ3F12cY6XZG"
PAXSENIX_API_URL = "https://api.paxsenix.org/v1/chat/completions"
DEEPSEEK_FREE_URL = "https://deepseek.api-sina-free.workers.dev/?text="

# ========== تنظیمات لاگ ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== لیست API های ثابت ==========
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

BOT_TOKEN = "8364377115:AAGJ06TejpBbe_TNQdgKn0vrrAYs-TxUR_0"
ADMIN_ID = 6443963679
BOT_USERNAME = "Self_free4bot"
MUSIC_BOT = "Gap_4_bot"

# ========== پوشه سشن‌ها ==========
SESSIONS_FOLDER = 'user_sessions'
if not os.path.exists(SESSIONS_FOLDER):
    os.makedirs(SESSIONS_FOLDER)

# ========== تنظیمات سلف‌بات ==========
GROUP_ID = -1002817019483

# ========== فایل‌های تنظیمات ==========
MEDIA_FOLDER = 'media_storage'
if not os.path.exists(MEDIA_FOLDER):
    os.makedirs(MEDIA_FOLDER)

REPORT_CONFIG_FILE = "report_config.json"
REPORT_MEDIA_FOLDER = 'reported_media'
if not os.path.exists(REPORT_MEDIA_FOLDER):
    os.makedirs(REPORT_MEDIA_FOLDER)

# ========== لیست ایموجی‌های مجاز ==========
ALLOWED_EMOJIS = [
    "🤯", "🐳", "😍", "💩", "👏", "🍌", "🤓", "😢", "🙉", "🤩",
    "🤝", "👀", "🌚", "🗿", "🤡", "😐", "👨‍💻", "😭", "🙈", "❤",
    "🙏", "😴", "💋", "🥰", "🤪", "✍️", "🥱", "👻", "🤣", "🌭",
    "😨", "🍓", "🔥", "🖕", "🤗", "🤔", "🤬", "😁", "🎄", "🫡",
    "⚡", "🥴", "😈", "🏆", "😇", "🎃", "☃️", "🤮", "👍", "👎",
    "😱", "😖", "🕊", "💯", "💔", "🤨", "❤️‍🔥", "💘", "😘", "💊",
    "🆒", "🤷‍♂", "🤷‍♀", "🎅"
]

# ========== لیست فونت‌های کلاسیک (با فونت‌های جدید) ==========
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
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
    "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
    "０１２３４５６７８９",
    "₀₁₂₃₄₅₆₇₈₉",
    "⁰¹²³⁴⁵⁶⁷⁸⁹",
    "0123456789",
    "⓪①②③④⑤⑥⑦⑧⑨",
    "⓿❶❷❸❹❺❻❼❽❾",
    "🄀🄁🄂🄃🄄🄅🄆🄇🄈🄉",
    "🄞🄟🄠🄡🄢🄣🄤🄥🄦🄧🄨",
    "０１２３４５６７８９",
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
    "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
    "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
    "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫",
    "０１２３４５６۷۸۹",
    "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
    "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
    "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
    "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
    {'0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9', ':': ':'},
    {'0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑', '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗', ':': ':'},
    {'0': '𝟶', '1': '𝟷', '2': '𝟸', '3': '𝟹', '4': '𝟺', '5': '𝟻', '6': '𝟼', '7': '𝟽', '8': '𝟾', '9': '𝟿', ':': ':'},
    {'0': '⓪', '1': '①', '2': '②', '3': '③', '4': '④', '5': '⑤', '6': '⑥', '7': '⑦', '8': '⑧', '9': '⑨', ':': ':'},
    {'0': '🄋', '1': '➊', '2': '➋', '3': '➌', '4': '➍', '5': '➎', '6': '➏', '7': '➐', '8': '➑', '9': '➒', ':': ':'},
    {'0': '⓿', '1': '❶', '2': '❷', '3': '❸', '4': '❹', '5': '❺', '6': '❻', '7': '❼', '8': '❽', '9': '❾', ':': ':'},
    {'0': '𝟘', '1': '𝟙', '2': '𝟚', '3': '𝟛', '4': '𝟜', '5': '𝟝', '6': '𝟞', '7': '𝟟', '8': '𝟠', '9': '𝟡', ':': ':'},
    {'0': '⒒', '1': '⑴', '2': '⑵', '3': '⑶', '4': '⑷', '5': '⑸', '6': '⑹', '7': '⑺', '8': '⑻', '9': '⑼', ':': ':'},
    {'0': '０', '1': '１', '2': '２', '3': '３', '4': '４', '5': '５', '6': '６', '7': '７', '8': '８', '9': '９', ':': '：'},
    {'0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵', ':': ':'},
    {'0': '〇', '1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六', '7': '七', '8': '八', '9': '九', ':': ':'},
    # فونت‌های جدید
    {'0': '⨁', '1': '⨂', '2': '⨃', '3': '⨄', '4': '⨅', '5': '⨆', '6': '⨇', '7': '⨈', '8': '⨉', '9': '⨊', ':': ':'},  # دایره‌ای توپر
    {'0': '▢', '1': '▣', '2': '▤', '3': '▥', '4': '▦', '5': '▧', '6': '▨', '7': '▩', '8': '▪', '9': '▫', ':': ':'},  # مربعی
    {'0': '✦', '1': '✧', '2': '✦', '3': '✧', '4': '✦', '5': '✧', '6': '✦', '7': '✧', '8': '✦', '9': '✧', ':': ':'},  # ستاره‌ای
    {'0': 'ᚠ', '1': 'ᚡ', '2': 'ᚢ', '3': 'ᚣ', '4': 'ᚤ', '5': 'ᚥ', '6': 'ᚦ', '7': 'ᚧ', '8': 'ᚨ', '9': 'ᚩ', ':': ':'},  # آینه‌ای
    {'0': '△', '1': '▲', '2': '△', '3': '▲', '4': '△', '5': '▲', '6': '△', '7': '▲', '8': '△', '9': '▲', ':': ':'},  # مثلثی
]

# ========== لیست پرچم‌ها ==========
flags = [
    "🇦🇱", "🇩🇿", "🇦🇸", "🇦🇩", "🇦🇼", "🇦🇼", "🇦🇹", "🇦🇿", "🇧🇸", "🇧🇭",
    "🇧🇩", "🇧🇧", "🇧🇾", "🇧🇪", "🇧🇿", "🇧🇯", "🇧??", "🇧🇴", "🇧🇦", "🇧🇼",
    "🇧🇷", "🇮🇴", "🇻🇬", "🇧🇳", "🇧🇬", "🇧🇫", "🇧🇮", "🇰🇭", "🇨🇲", "🇨🇦",
    "🇨🇻", "🇰🇾", "🇨🇫", "🇹🇩", "🇨🇱", "🇨🇴", "🇰🇲", "🇨🇬", "🇨🇩", "🇨🇽",
    "🇨🇨", "🇨🇴", "🇰🇲", "🇨🇬", "🇨🇩", "🇨🇰", "🇨🇰", "🕋"
]

# ========== لیست پیام‌های اسپم ==========
SPAM_MESSAGES = [
    "مادربزرگت کسده، کسشو تو قبرم اجاره داده",
    "پدربزرگت کونی، هنوزم تو گور کونشو به شیاطین می‌سپره",
    "کس ننت چنان بازه، کل شهر توش چادر زدن",
    "بابات کسکش، تو خیابون کونشو به موتورسوارا نشون می‌ده",
    "خواهرت فاحشه، تو کلوپ شبانه کسشو به حراج گذاشته",
    "برادرت کیرکش، تو کوچه کونشو به گربه‌ها می‌ده",
    "بچه‌هات جنده‌ان، تو پارک کسشونو به نیمکت‌ها می‌مالن",
    "عمه‌ت کس‌کش، کسشو تو حموم عمومی به همه نشون می‌ده",
    "خاله‌ت کونی، کیر هر غریبه‌ای رو تو کوچه می‌گیره",
    "جدت کسده، تو گور هم کسشو به فرشته‌ها اجاره می‌ده",
    "یا الله کیرم به قلب مادرت",
    "مادرتو میدم سگ بگاد",
    "با کیرم ناموستو پاره میکنم",
    "کیرمو حلقه میکنم دور گردن مادرت",
    "کسخارتو بتن ریزی کردم",
    "ننتو تو پورن هاب دیدم",
    "کیر و خایه هام به کل اجدادت",
    "فیلم ننت فروشی",
    "کسننت پدرتم",
    "میرم تو کسمادرت با بیل پارش میکنم",
    "کیر به ناموس گشادت",
    "خسته نشدی ننتو گاییدم؟",
    "کیرم شلاقی به ناموس جندت",
    "با ناموست تریسام زدم",
    "برج خلیفه تو مادرت",
    "دو پایی میرم تو کسمادرت",
    "داگی استایل ننتو گاییدم",
    "هندل زدم به کون مادرت گاییدمش",
    "یگام دو گام ننتو میگام",
    "کیرمو نکن تو کسمادرت",
    "کیر و خایم به توان دو تو کسمادرت",
    "قمه تو کسمادرت",
    "نود ننتو دارم مادرکسده",
    "با کله میرم تو کسمادرت",
    "دستام تو کسمادرت",
    "کیرم به استخون های ننت",
    "مادرتو حراج زدم مادرجنده",
    "بریم برای راند بعد با ننت",
    "کیرم به رحم نجس ننت",
    "کیرم به چش و چال ننت",
    "کیروم به فرق سر ناموست",
    "مادرجنده کیری ناموس",
    "با کون ننت ناگت درست کردم",
    "خایه هام به کسمادرت",
    "برج میلاد تو کسمادرت",
    "یخچال تو کسمادرت",
    "کیرم به پوزه مادرت",
    "مادرتو زدم به سیخ",
    "کسمادرت","کیر شتر تو ناموست","نودا ننت فروشی","خایه با پرزش تو ننت","چشای ننت تو کون خارت بره","ننتو ریدم","لال شو مادرجنده اوبنه ای","اوب از کون ننت میباره","ماهی تو کسمادرت","کیر هرچی خره تو کسمادرت","کیر رونالدو به کس خار و مادرت","مادرت زیر کیرم شهید شد","اسپنک زدم به کون مادر جندت","کیرم یهویی به مردع و زندت","کیر به فیس ننت","برو مادرجنده بی غیرت","استخون های مرده هات تو کسمادرت","اسپرمم تو نوامیست","مادرتو با پوزیشن های مختلف گاییدم","میز و صندلی تو کسمادرت","کیر به ناموس دلقکت","دمپایی تو کون ننت","دماغ پینوکیو رو گذاشتم جلو کص مادرت و بهش گفتم که بگه مادرت جنده نیست تا با دراز شدن دماغش کص مادرت پاره بشه","مادر فلش شده جوری با کیر میزنم ب فرق سر ننت ک حافظش بپره","كيرم شيك تو كس ننت","مادرتو کردم تو بشکه نفت از بالا کوه قل دادم پایین","با کیرم مادرتو هیپنوتیزم کردم","ناموستو تو کوچه موقع عید دیدنی دیدم رفتم خونه به یادش جق زدم","با خیسی عرق کون مادرت جقیدم","با سرعت نور تو فضا حرکت میکنم تا پیر نشم و بزارم آبجی کوچیکت بزرگ بشه تا وقتی بزرگ شد باهاش سکس کنم","مادرتو پودر میکنم ازش سنگ توالت میسازم هر روز صبح رو مادرت میرینم","مادرتو مجبور میکنم خودکشی کوانتومی کنه تا در بی نهایت جهان موازی یتیم بشی","دیدی چه لگدی به مادرت زدم ؟","فرشی که مادرت روش کونشو گذاشته بو کردم","مادرتو جوری گاییدم که همسایه ها فکر کردن اسب ترکمن اومده خونتون"
]

# ========== تنظیمات پیش‌فرض قفل رسانه ==========
DEFAULT_LOCK_SETTINGS = {
    'link': False,
    'photo': False,
    'video': False,
    'sticker': False,
    'gif': False,
    'voice': False,
    'file': False,
    'music': False,
    'video_note': False,
    'contact': False,
    'location': False,
    'emoji': False,
    'text': False
}

# ========== اطلاعات بات ==========
BOT_VERSION = "4.6.0"
BOT_CREATOR = "Self-Bot AI Assistant"

# ========== لیست‌های انیمیشن ==========
HEARTS = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🤍"]
MOONS = ["🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘", "🌑"]

# ========== متغیرهای گزارش‌گیری ==========
media_cache = {}
message_cache = {}
user_inline_messages = {}

# ========== لیست اکشن‌ها ==========
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

# ========== متغیرهای انیمیشن قلب پیشرفته ==========
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

HEART_MATRIX_SIZES = [3, 5, 7, 9, 11, 13]
JOINED_HEART = create_heart_matrix(7)
HEARTLET_LEN = JOINED_HEART.count(R)

# ========== کلاس مدیریت تنظیمات گزارش ==========
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

# ========== دیتابیس اصلی ==========
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
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                is_from_user BOOLEAN,
                ai_type INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_memory (user_id)
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
                filter_enabled BOOLEAN DEFAULT 0,
                selfbot_enabled BOOLEAN DEFAULT 1,
                selected_flag_index INTEGER DEFAULT 0,
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
        
        conn.commit()
        conn.close()
        logger.info("✓ دیتابیس اصلی ایجاد شد")
    
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
            settings.setdefault('selfbot_enabled', 1)
            settings.setdefault('selected_flag_index', 0)
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
                'filter_enabled': 0,
                'selfbot_enabled': 1,
                'selected_flag_index': 0,
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
    
    def get_filter_words(self, owner_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT word, enabled FROM filter_words WHERE owner_id = ?', (owner_id,))
        results = cursor.fetchall()
        conn.close()
        return [{'word': row[0], 'enabled': bool(row[1])} for row in results]
    
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

def get_full_date_info():
    tehran_tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran_tz)
    
    try:
        jdate = jdatetime.date.fromgregorian(date=now.date())
        hijri = Gregorian(now.year, now.month, now.day).to_hijri()
        
        persian_weekdays = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یک‌شنبه"]
        gregorian_weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        return f"""
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
        """
    except:
        return f"📅 تاریخ: {now.strftime('%Y/%m/%d %H:%M:%S')}"

def is_channel_post(message):
    try:
        if not message:
            return False
        
        if hasattr(message, 'post') and message.post:
            return True
        
        if hasattr(message, 'is_channel') and message.is_channel:
            if hasattr(message, 'is_group') and not message.is_group:
                return True
            if not message.from_id:
                return True
        
        if hasattr(message, 'chat') and message.chat:
            chat = message.chat
            if hasattr(chat, 'broadcast') and chat.broadcast:
                return True
            if hasattr(chat, 'megagroup') and not chat.megagroup:
                if hasattr(chat, 'broadcast') and chat.broadcast:
                    return True
        
        if hasattr(message, 'fwd_from') and message.fwd_from:
            if hasattr(message.fwd_from, 'from_id'):
                if hasattr(message.fwd_from.from_id, 'channel_id'):
                    return True
        
        if hasattr(message, 'peer_id'):
            if isinstance(message.peer_id, PeerChannel):
                if not message.sender_id or message.sender_id == message.chat_id:
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

async def is_premium_emoji(message):
    try:
        if message.media and hasattr(message.media, 'document'):
            document = message.media.document
            if hasattr(document, 'attributes'):
                for attr in document.attributes:
                    if hasattr(attr, 'alt') and attr.alt:
                        return True
    except:
        pass
    return False

def convert_to_classic_font(text, font_index):
    if isinstance(classic_fonts[font_index], dict):
        font = classic_fonts[font_index]
        return ''.join(font.get(c, c) for c in text)
    else:
        font = classic_fonts[font_index]
        return ''.join(font[int(c)] if c.isdigit() else c for c in text)

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

def extract_name_from_message(text):
    patterns = [
        r'من\s+([\u0600-\u06FF\s]+)\s+هستم',
        r'اسمم\s+([\u0600-\u06FF\s]+)\s+است',
        r'نامم\s+([\u0600-\u06FF\s]+)\s+است',
        r'من\s+([\u0600-\u06FF\s]+)\s+ام',
        r'([\u0600-\u06FF\s]+)\s+هستم'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            stop_words = ['من', 'هستم', 'اسمم', 'است', 'نامم', 'ام']
            words = name.split()
            filtered_words = [word for word in words if word.lower() not in stop_words]
            return ' '.join(filtered_words).strip()
    
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

# ==================== کلاس سلف‌بات ====================
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
        self.autosend_enabled = False
    
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
                system_version="4.6.0",
                app_version="4.6.0"
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
            self.autosend_enabled = settings.get('autosend_mode', False)
            
            if not self._handlers_set:
                self.setup_handlers()
                self._handlers_set = True
                logger.info(f"هندلرها برای کاربر {self.user_id} تنظیم شدند")
            
            asyncio.create_task(self.update_profile_task())
            
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
        """پس‌زمینه برای نگه داشتن اتصال سلف‌بات با بررسی قوی‌تر"""
        while self.running and self.keepalive_running:
            try:
                await asyncio.sleep(60)  # هر 1 دقیقه
                
                if not self.running:
                    break
                
                # بررسی وضعیت اتصال
                if self.client and self.client.is_connected():
                    try:
                        # درخواست سبک برای بررسی اتصال
                        await self.client.get_me()
                        self.last_ping = time.time()
                        self.error_count = 0
                        logger.debug(f"Keepalive برای کاربر {self.user_id} موفق")
                    except Exception as e:
                        self.error_count += 1
                        self.last_error_time = time.time()
                        logger.warning(f"خطا در keepalive برای کاربر {self.user_id} ({self.error_count}): {e}")
                        
                        if self.error_count >= 3:
                            logger.warning(f"تلاش مجدد برای کاربر {self.user_id} بعد از {self.error_count} خطا")
                            await self.reconnect()
                else:
                    logger.warning(f"اتصال کاربر {self.user_id} قطع شده، تلاش برای reconnect...")
                    await self.reconnect()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"خطا در keep_alive_task برای کاربر {self.user_id}: {e}")
                await asyncio.sleep(60)
    
    async def reconnect(self):
        """تلاش مجدد برای اتصال سلف‌بات با بازیابی کامل"""
        try:
            logger.info(f"شروع reconnect برای کاربر {self.user_id}")
            
            user_data = db.get_user(str(self.user_id))
            if not user_data or not user_data.get('session_file'):
                logger.error(f"فایل سشن برای کاربر {self.user_id} یافت نشد")
                return False
            
            session_file = user_data['session_file']
            
            # قطع اتصال قبلی
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            
            self.running = False
            self._handlers_set = False
            
            # صبر برای اطمینان از بسته شدن کامل
            await asyncio.sleep(3)
            
            # شروع مجدد
            if await self.start(session_file):
                logger.info(f"✅ reconnect برای کاربر {self.user_id} موفقیت‌آمیز بود")
                return True
            else:
                logger.error(f"❌ reconnect برای کاربر {self.user_id} ناموفق بود")
                return False
                
        except Exception as e:
            logger.error(f"خطا در reconnect برای کاربر {self.user_id}: {e}")
            return False
    
    async def stop(self):
        try:
            self.running = False
            self.keepalive_running = False
            
            # ذخیره تنظیمات
            settings = db.get_selfbot_settings(self.user_id)
            settings['panel_mode'] = self.panel_mode
            db.set_selfbot_settings(self.user_id, settings)
            
            if self.client:
                # لغو همه تسک‌ها
                for task in self.spam_tasks.values():
                    task.cancel()
                
                self.spam_tasks.clear()
                
                # قطع اتصال
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
            
            @self.client.on(events.NewMessage(pattern=r'^(?:شروع|تایم روشن|تایمر پرچم روشن|تایم خاموش|قلب|ماه|اطلاعات|دانلود پروفایل|تاریخ کامل|فعال اتوسین|غیرفعال اتوسین|حذف کامل|ست پروف|ست بیو|حذف ست پروف|حذف ست بیو|بولد روشن|بولد خاموش|زیرخط روشن|زیرخط خاموش|خط خورده روشن|خط خورده خاموش|نقل قول روشن|نقل قول خاموش|اسپویلر روشن|اسپویلر خاموش|کج روشن|کج خاموش|کد روشن|کد خاموش|پیش روشن|پیش خاموش|بلاک|پیوی ۱|پیوی ۲|پیوی ۳|خاموش پیوی|گروه ۱|گروه ۲|گروه ۳|خاموش گروه|درباره|من کی ام|قفل پیوی همه|باز پی همه|قفل لینک روشن|قفل لینک خاموش|قفل عکس روشن|قفل عکس خاموش|قفل ویدیو روشن|قفل ویدیو خاموش|قفل استیکر روشن|قفل استیکر خاموش|قفل گیف روشن|قفل گیف خاموش|قفل ویس روشن|قفل ویس خاموش|قفل فایل روشن|قفل فایل خاموش|قفل موزیک روشن|قفل موزیک خاموش|قفل ویدیو نوت روشن|قفل ویدیو نوت خاموش|قفل کانتکت روشن|قفل کانتکت خاموش|قفل لوکیشن روشن|قفل لوکیشن خاموش|قفل ایموجی روشن|قفل ایموجی خاموش|قفل متن روشن|قفل متن خاموش|تنظیم گزارش|گروه گزارش|کانال‌ها|حذف کانال|تست کانال|لیست دشمن|پاک کردن اسپم|لیست اسپم|تغییر اسم|تغییر بیو|تغییر پروفایل|پروف|اضافه اسپم|اتمام اسپم|فیلتر روشن|فیلتر خاموش|لیست فیلتر|اسپم روشن|اسپم خاموش|پینگ|سرچ|خروج سرچ|وضعیت|قلب پیشرفته|عشق|سنتت|هک|حذف ریکت|سلف روشن|سلف خاموش|پین|تگ ادمین|امار گپ|\.کد)(?:\s*$|\s+(.+)$)|^حذف\s+(\d+)$|^دشمن\s*(@\w+|-\d+|\d+)?$|^دوست\s*(@\w+|-\d+|\d+)?$|^قفل پیوی\s*(@\w+|-\d+|\d+)?$|^باز پی\s*(@\w+|-\d+|\d+)?$|^اسپم\s+(\d+)\s+(.+)$|^ریکت\s*([\U0001F300-\U0001F9FF]+)?$|^کامنت\s+(.+)$|^حذف اسپم\s+(\d+)$|^تایم\s+([\d\.]+)$|^\.فیلتر\s+(.+)$|^حذف فیلتر\s+(.+)$|^\.پنل$|^پنل$|^/panel$|^\.اهنگ\s+(.+)$|^تنظیم اسپم\s+(\d+)\s+(\d+)$'))
            async def handle_commands(event):
                if not self.running:
                    return
                await self.handle_commands(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_outgoing_message(event):
                if not self.running:
                    return
                await self.handle_outgoing_message(event)
            
            @self.client.on(events.NewMessage(outgoing=True))
            async def handle_action_commands(event):
                if not self.running:
                    return
                await self.handle_action_commands(event)
            
            @self.client.on(events.NewMessage())
            async def auto_comment_handler(event):
                if not self.running:
                    return
                await self.handle_auto_comment(event)
            
            @self.client.on(events.NewMessage())
            async def report_handler(event):
                if not self.running:
                    return
                await self.handle_report_message(event)
                
        except Exception as e:
            logger.error(f"خطا در تنظیم هندلرها برای کاربر {self.user_id}: {e}")
    
    async def force_dice(self, chat_id, emoji, target):
        while True:
            msg = await self.client.send_message(chat_id, file=types.InputMediaDice(emoji))
            if msg.media.value == target:
                break
            await msg.delete()
            await asyncio.sleep(0.3)
    
    async def handle_translate_commands(self, event):
        text = event.raw_text.strip()
        
        langs = ["انگلیسی", "عربی", "عبری", "روسی", "ترکی"]
        for l in langs:
            if text.startswith(l):
                cmd = text.split()[1] if len(text.split()) > 1 else ""
                key = l.lower()
                if key == "انگلیسی": key = "english"
                if key == "عربی": key = "arabic"
                if key == "عبری": key = "hebrew"
                if key == "روسی": key = "russian"
                if key == "ترکی": key = "turkish"
                
                self.translate_mode[key] = True if cmd == "روشن" else False
                
                db.update_selfbot_setting(self.user_id, f'translate_{key}', 1 if self.translate_mode[key] else 0)
                
                status = "✓ روشن" if self.translate_mode[key] else "✗ خاموش"
                await event.edit(f"✅ ترجمه {l} {status} شد")
                return
        
        if text.startswith("تاس"):
            try:
                n = int(text.split()[1])
                if 1 <= n <= 6:
                    await event.delete()
                    await self.force_dice(event.chat_id, "🎲", n)
            except:
                await event.delete()
            return
        elif text == "دارت":
            await event.delete()
            await self.force_dice(event.chat_id, "🎯", 6)
            return
        elif text == "بسکتبال":
            await event.delete()
            await self.force_dice(event.chat_id, "🏀", 5)
            return
        elif text == "فوتبال":
            await event.delete()
            await self.force_dice(event.chat_id, "⚽️", 5)
            return
    
    async def translate_text(self, text):
        try:
            from deep_translator import GoogleTranslator
            
            for lang, status in self.translate_mode.items():
                if status:
                    try:
                        return GoogleTranslator(source='auto', target=lang).translate(text)
                    except:
                        return text
        except:
            pass
        return text
    
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
    
    async def stop_all_actions(self):
        stopped = []
        for chat_id in list(self.action_tasks.keys()):
            action_name = await self.stop_action(chat_id)
            if action_name:
                stopped.append(action_name)
        return stopped
    
    async def handle_action_commands(self, event):
        msg = event.text.strip()
        chat_id = event.chat_id
        
        await self.handle_translate_commands(event)
        
        if msg in ["دارت", "بسکتبال", "فوتبال"] or msg.startswith("تاس") or \
           any(msg.startswith(f"{lang}") and ("روشن" in msg or "خاموش" in msg) for lang in ["انگلیسی", "عربی", "عبری", "روسی", "ترکی"]):
            return
        
        if msg.startswith('اکشن '):
            command = msg.replace('اکشن ', '').strip()
            
            if command == 'خاموش':
                if chat_id in self.active_actions:
                    action_name = await self.stop_action(chat_id)
                    await event.edit(f'✅ اکشن {action_name} خاموش شد')
                else:
                    await event.edit('❌ هیچ اکشن فعالی در این چت وجود ندارد')
                return
                
            elif command == 'لیست':
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
                
            else:
                if command in action_types:
                    if chat_id in self.active_actions:
                        old_action = self.active_actions[chat_id]
                        await self.stop_action(chat_id)
                        await event.edit(f'⏹️ اکشن قبلی {old_action} خاموش شد\n✅ اکشن جدید {command} فعال شد')
                    else:
                        await event.edit(f'✅ اکشن {command} فعال شد')
                    
                    await self.start_action(chat_id, command)
                    
                    await asyncio.sleep(3)
                    await event.delete()
                    return
                else:
                    available = "\n".join([f"• {name}" for name in action_types.keys()])
                    await event.edit(f'❌ اکشن "{command}" پشتیبانی نمی‌شود\n\n✅ اکشن‌های موجود:\n{available}')
                    return
        
        if msg == 'سرچ':
            self.search_mode = True
            await event.edit('🔍 حالت سرچ فعال شد.\n\nاکنون هر متنی که ارسال کنید در گوگل جستجو می‌شود.\nبرای خروج از حالت سرچ، دستور خروج سرچ را ارسال کنید.')
            return
        
        elif msg == 'خروج سرچ':
            self.search_mode = False
            self.last_search_results = []
            await event.edit('✅ حالت سرچ غیرفعال شد.')
            return
        
        if self.search_mode and msg:
            await self.handle_google_search(event, msg)
            return
        
        active_lang_code = None
        lang_mapping = {
            "english": "en",
            "arabic": "ar",
            "hebrew": "he",
            "russian": "ru",
            "turkish": "tr"
        }
        
        for lang_key, status in self.translate_mode.items():
            if status and lang_key in lang_mapping:
                active_lang_code = lang_mapping[lang_key]
                break
        
        if active_lang_code and msg:
            try:
                from deep_translator import GoogleTranslator
                translated = GoogleTranslator(source='auto', target=active_lang_code).translate(msg)
                await event.edit(translated)
                return
            except Exception as e:
                logger.error(f"خطا در ترجمه: {e}")
    
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
                        
                        message += f"{i}. {title}\n"
                        message += f"   {snippet}...\n"
                        message += f"   🔗 {link}\n\n"
                    
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
    
    async def get_user_info(self, user_id):
        try:
            entity = await self.client.get_entity(user_id)
            if entity.username:
                user_info = f"@{entity.username} ({user_id})"
            elif entity.first_name:
                user_info = f"{entity.first_name} {entity.last_name or ''}".strip() + f" ({user_id})"
            else:
                user_info = f"کاربر {user_id}"
            return user_info
        except Exception as e:
            logger.error(f"خطا در دریافت اطلاعات کاربر {user_id}: {e}")
            return f"کاربر ناشناس ({user_id})"
    
    async def get_chat_title(self, chat_id):
        try:
            entity = await self.client.get_entity(chat_id)
            return entity.title if hasattr(entity, 'title') else (entity.first_name or f"چت {chat_id}")
        except:
            return f"چت {chat_id}"
    
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
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"{media_type}_{message.sender_id}_{message.id}_{timestamp}"
            file_extension = self.get_file_extension(media_type)
            file_path = os.path.join(REPORT_MEDIA_FOLDER, file_name + file_extension)
            
            downloaded_path = await self.client.download_media(
                message.media,
                file=file_path
            )
            
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
                    await self.client.send_file(
                        self.report_config.report_group_id,
                        media_path,
                        caption=caption or report_text
                    )
                    logger.info(f"گزارش با فایل ارسال شد: {media_path}")
                else:
                    await self.client.send_message(self.report_config.report_group_id, report_text)
                    logger.info(f"گزارش متنی ارسال شد")
                return True
            return False
        except Exception as e:
            logger.error(f"خطا در ارسال گزارش: {e}")
            return False
    
    async def handle_media_lock_delete(self, event):
        if not event.message or event.message.out:
            return False
        
        target_id = event.sender_id
        if target_id == self.my_id:
            return False
        
        message = event.message
        message_text = message.text or ""
        
        # بررسی قفل‌های اختصاصی کاربر
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
        
        # بررسی قفل عمومی (target_id = 0)
        for lock_type, check_func in lock_types.items():
            if db.get_user_lock(self.user_id, 0, lock_type):
                if check_func(message_text):
                    try:
                        await message.delete()
                        logger.info(f"قفل عمومی {lock_type} از کاربر {target_id} حذف شد")
                        return True
                    except:
                        pass
        
        # بررسی قفل اختصاصی کاربر
        for lock_type, check_func in lock_types.items():
            if db.get_user_lock(self.user_id, target_id, lock_type):
                if check_func(message_text):
                    try:
                        await message.delete()
                        logger.info(f"قفل اختصاصی {lock_type} از کاربر {target_id} حذف شد")
                        return True
                    except:
                        pass
        
        return False
    
    async def handle_new_message(self, event):
        if not self.my_id:
            return
        
        settings = db.get_selfbot_settings(self.user_id)
        
        # بررسی فعال بودن سلف‌بات
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
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            if settings.get('pv_lock_all'):
                try:
                    await event.message.delete()
                    logger.info(f"پیام از کاربر {event.sender_id} به دلیل قفل پیوی همه حذف شد")
                    return
                except:
                    pass
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            if db.is_pv_locked(self.user_id, event.sender_id):
                try:
                    await event.message.delete()
                    logger.info(f"پیام از کاربر {event.sender_id} به دلیل قفل پیوی اختصاصی حذف شد")
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
                            logger.info(f"پیام حاوی کلمه فیلتر شده {word_info['word']} از {event.sender_id} حذف شد")
                            return
                        except:
                            pass
        
        if isinstance(event.message.peer_id, PeerUser) and not event.message.out:
            sender_id = event.sender_id
            try:
                reaction = db.get_reaction(self.user_id, chat_id, sender_id)
                if reaction and reaction in ALLOWED_EMOJIS:
                    try:
                        await self.client(SendReactionRequest(
                            peer=event.message.peer_id,
                            msg_id=event.message.id,
                            reaction=[ReactionEmoji(emoticon=reaction)]
                        ))
                        logger.info(f"✅ ریکت {reaction} به پیام {sender_id} زده شد")
                    except Exception as e:
                        logger.error(f"خطا در ارسال ریکت: {e}")
            except Exception as e:
                logger.error(f"خطا در دریافت ریکت: {e}")
        
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
                        logger.info(f"✅ پاسخ هوش مصنوعی {ai_type} به کاربر {sender_id} ارسال شد")
                    else:
                        await event.reply("❌ خطا در ارتباط با هوش مصنوعی. لطفاً بعداً تلاش کنید.")
                except Exception as e:
                    logger.error(f"خطا در پاسخ هوش مصنوعی: {e}")
        
        spam_settings = db.get_spam_settings(self.user_id)
        if spam_settings.get('spam_protection') and not event.message.out:
            sender_id = event.sender_id
            chat_key = f"{chat_id}_{sender_id}"
            
            if chat_key not in self.spam_counters:
                self.spam_counters[chat_key] = []
            
            now = time.time()
            self.spam_counters[chat_key].append(now)
            
            mute_duration = spam_settings.get('mute_duration', 10)
            self.spam_counters[chat_key] = [t for t in self.spam_counters[chat_key] if now - t <= mute_duration]
            
            spam_limit = spam_settings.get('spam_limit', 10)
            if len(self.spam_counters[chat_key]) > spam_limit:
                try:
                    await event.message.delete()
                    logger.info(f"پیام اسپم از کاربر {sender_id} در {chat_id} حذف شد (ارسال بیش از {spam_limit} پیام در {mute_duration} ثانیه)")
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
    
    async def handle_auto_comment(self, event):
        try:
            message = event.message
            if not message:
                return
            
            if message.out:
                return
            
            if not is_channel_post(message):
                return
            
            chat = await message.get_chat()
            channel_id = chat.id
            
            auto_comment = db.get_auto_comment(self.user_id, channel_id)
            if not auto_comment:
                return
            
            if db.is_comment_sent(self.user_id, channel_id, message.id):
                return
            
            logger.info(f"🎯 ارسال نظر به کانال: {auto_comment['channel_title']}")
            
            await asyncio.sleep(0.3)
            
            result = await self.client.send_message(
                chat.id,
                auto_comment['comment_text'],
                reply_to=message.id
            )
            
            db.mark_comment_sent(self.user_id, channel_id, message.id)
            
            logger.info(f"✅ نظر ارسال شد به پست {message.id} در کانال {auto_comment['channel_title']}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ خطا در ارسال نظر اتوماتیک: {error_msg[:80]}")
    
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
                        f"🕒 زمان: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
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
                        f"🕒 زمان حذف: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
                    )
                    
                    if file_exists:
                        await self.send_report(
                            report_text,
                            media_info['path'],
                            f"🗑️ {media_info['type']} حذف‌شده از {sender_info}"
                        )
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
                            f"🕒 زمان: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
                        )
                        
                        await self.send_report(report_text)
                        
                        del message_cache[(chat_id, msg_id)]
                        
                    except Exception as e:
                        logger.error(f"خطا در گزارش حذف پیام: {e}")
                        if (chat_id, msg_id) in message_cache:
                            del message_cache[(chat_id, msg_id)]
    
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
        
        comment_channels = len(db.get_auto_comments(self.user_id))
        
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
        
        return f"""
وضعیت کامل سلف‌بات
━━━━━━━━━━━━━━━━━━━━
🤖 وضعیت سلف‌بات: {selfbot_status}
🔍 حالت سرچ: {'فعال' if self.search_mode else 'غیرفعال'}
🕐 تایم روی پروفایل: {'فعال' if settings.get('time_enabled') else 'غیرفعال'}
🏳️ پرچم در تایم: {'فعال' if settings.get('flag_enabled') else 'غیرفعال'}
🎨 فونت تایم: {font_info}

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

📊 گروه گزارش: {self.report_config.report_group_id}
💾 ذخیره خودکار رسانه: {'فعال' if self.report_config.auto_save_media else 'غیرفعال'}
━━━━━━━━━━━━━━━━━━━━
✅ Self-Bot v{BOT_VERSION}
        """
    
    # ========== توابع کمکی جدید ==========

async def get_chat_stats(self, chat_id, target_user_id=None):
    """دریافت آمار چت برای کاربر خاص"""
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
        
        if not target_user_id:
            logger.error("target_user_id is None")
            return None
        
        target_user_id = int(target_user_id)
        
        limit = 5000
        async for message in self.client.iter_messages(chat_id, limit=limit):
            sender_id = message.sender_id
            if not sender_id:
                if hasattr(message, 'from_id') and message.from_id:
                    if hasattr(message.from_id, 'user_id'):
                        sender_id = message.from_id.user_id
                    elif hasattr(message.from_id, 'channel_id'):
                        sender_id = message.from_id.channel_id
                    elif hasattr(message.from_id, 'chat_id'):
                        sender_id = message.from_id.chat_id
            
            if not sender_id:
                continue
            
            sender_id = int(sender_id)
            
            if sender_id == self.my_id:
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
            
            elif sender_id == target_user_id:
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
    """تولید کد QR از متن یا عکس"""
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
    """دریافت لیست ادمین‌های گروه"""
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
    """پین کردن پیام"""
    try:
        await self.client.pin_message(chat_id, message_id)
        return True
    except Exception as e:
        logger.error(f"خطا در پین کردن پیام: {e}")
        return False
    
    # ========== ادامه هندلرهای دستورات ==========
    
    async def handle_commands(self, event):
        if event.sender_id != self.my_id:
            return
        
        command_text = event.text.strip()
        
        # ========== دستورات ویژه (قبل از بررسی وضعیت) ==========
        
        # سلف روشن / خاموش
        if command_text == 'سلف روشن':
            db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 1)
            await event.edit("✅ سلف‌بات فعال شد")
            return
        
        if command_text == 'سلف خاموش':
            db.update_selfbot_setting(self.user_id, 'selfbot_enabled', 0)
            await event.edit("✅ سلف‌بات غیرفعال شد")
            return
        
        # ========== بررسی فعال بودن سلف‌بات ==========
        
        settings = db.get_selfbot_settings(self.user_id)
        
        if not settings.get('selfbot_enabled', 1):
            await event.edit("⚠️ سلف‌بات غیرفعال است. برای فعال کردن: سلف روشن")
            return
        
        chat_id = None
        
        if isinstance(event.message.peer_id, PeerUser):
            chat_id = event.message.peer_id.user_id
        elif isinstance(event.message.peer_id, PeerChannel):
            chat_id = event.message.peer_id.channel_id
        elif isinstance(event.message.peer_id, PeerChat):
            chat_id = event.message.peer_id.chat_id
        
        # ========== ادامه سایر دستورات =========
        
        # تگ ادمین‌ها
        if command_text == 'تگ ادمین':
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
        
        # پین کردن پیام
        if command_text == 'پین':
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                if await self.pin_message(chat_id, reply_msg.id):
                    await event.edit("📌 پیام پین شد")
                else:
                    await event.edit("⚠️ خطا در پین کردن پیام")
            else:
                await event.edit("⚠️ روی پیام مورد نظر ریپلای کنید")
            return
        
        # کد QR
        if command_text.startswith('.کد'):
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
                    # استفاده از متن خود دستور
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
        
        # آمار گپ
        if command_text == 'امار گپ':
            await event.delete()
            
            target_user_id = None
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_user_id = reply_msg.sender_id
            
            if not target_user_id:
                target_user_id = chat_id if isinstance(event.message.peer_id, PeerUser) else None
            
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
                
                # تعیین برنده
                if total_my > total_target:
                    winner = my_name
                elif total_target > total_my:
                    winner = target_name
                else:
                    winner = "مساوی"
                
                # نسبت پیام‌ها
                if total_target > 0:
                    ratio = f"{total_my} به {total_target}"
                else:
                    ratio = f"{total_my} به 0"
                
                stats_text = f"""
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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                """
                
                await self.client.send_message(chat_id, stats_text)
                
            except Exception as e:
                await event.respond(f"⚠️ خطا: {str(e)[:100]}")
            return
        
        # ========== دستورات پنل ==========
        
        if command_text in ['.پنل', 'پنل', '/panel']:
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
        
        # ========== ادامه دستورات قبلی ==========
        
        # دستور اهنگ
        if command_text.startswith('.اهنگ '):
            song_name = command_text[6:].strip()
            if not song_name:
                await event.edit("❌ لطفاً نام آهنگ را وارد کنید\nمثال: .اهنگ مهدیار احمدی")
                return
            
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
        
        # دستور تنظیم تایم فونت
        if command_text.startswith('تایم ') and not command_text.startswith('تایم روشن') and not command_text.startswith('تایم خاموش') and not command_text.startswith('تایمر'):
            match = re.match(r'^تایم\s+([\d\.]+)$', command_text)
            if match:
                indices_str = match.group(1)
                indices = []
                for part in indices_str.split('.'):
                    try:
                        idx = int(part)
                        if 0 <= idx < len(classic_fonts):
                            indices.append(idx)
                    except:
                        pass
                
                if indices:
                    self.time_font_indices = indices
                    db.update_selfbot_setting(self.user_id, 'time_font_indices', ','.join(map(str, indices)))
                    await event.edit(f"✅ فونت‌های تایم تنظیم شد: {indices}")
                else:
                    await event.edit(f"❌ ایندکس نامعتبر. محدوده مجاز: 0 تا {len(classic_fonts)-1}")
                return
        
        # دستورات فیلتر
        if command_text.startswith('.فیلتر '):
            word = command_text[8:].strip()
            if word:
                db.add_filter_word(self.user_id, word)
                await event.edit(f"✅ کلمه {word} به لیست فیلتر اضافه شد")
            else:
                await event.edit("❌ لطفاً یک کلمه وارد کنید")
            return
        
        if command_text.startswith('حذف فیلتر '):
            word = command_text[11:].strip()
            if word:
                db.remove_filter_word(self.user_id, word)
                await event.edit(f"✅ کلمه {word} از لیست فیلتر حذف شد")
            else:
                await event.edit("❌ لطفاً یک کلمه وارد کنید")
            return
        
        if command_text == 'لیست فیلتر':
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
        
        if command_text == 'فیلتر روشن':
            db.set_filter_enabled(self.user_id, True)
            await event.edit("✅ فیلتر کلمات فعال شد")
            return
        
        if command_text == 'فیلتر خاموش':
            db.set_filter_enabled(self.user_id, False)
            await event.edit("✅ فیلتر کلمات غیرفعال شد")
            return
        
        # دستورات قفل رسانه
        lock_commands = {
            'قفل لینک': 'lock_link',
            'قفل عکس': 'lock_photo',
            'قفل ویدیو': 'lock_video',
            'قفل استیکر': 'lock_sticker',
            'قفل گیف': 'lock_gif',
            'قفل ویس': 'lock_voice',
            'قفل فایل': 'lock_file',
            'قفل موزیک': 'lock_music',
            'قفل ویدیو نوت': 'lock_video_note',
            'قفل کانتکت': 'lock_contact',
            'قفل لوکیشن': 'lock_location',
            'قفل ایموجی': 'lock_emoji',
            'قفل متن': 'lock_text'
        }
        
        for cmd, lock_type in lock_commands.items():
            if command_text == f'{cmd} روشن':
                target_id = 0
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    target_id = reply_msg.sender_id
                elif isinstance(event.message.peer_id, PeerUser):
                    target_id = event.message.peer_id.user_id
                
                db.set_user_lock(self.user_id, target_id, lock_type, True)
                target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                await event.edit(f"✅ {cmd} برای {target_name} فعال شد")
                return
            
            if command_text == f'{cmd} خاموش':
                target_id = 0
                if event.is_reply:
                    reply_msg = await event.get_reply_message()
                    target_id = reply_msg.sender_id
                elif isinstance(event.message.peer_id, PeerUser):
                    target_id = event.message.peer_id.user_id
                
                db.set_user_lock(self.user_id, target_id, lock_type, False)
                target_name = "همه کاربران" if target_id == 0 else f"کاربر {target_id}"
                await event.edit(f"✅ {cmd} برای {target_name} غیرفعال شد")
                return
        
        if command_text == 'وضعیت':
            settings = db.get_selfbot_settings(self.user_id)
            await event.edit(self.format_status_info(settings))
            return
        
        if re.match(r'^حذف\s+(\d+)$', command_text):
            match = re.match(r'^حذف\s+(\d+)$', command_text)
            num = int(match.group(1))
            messages = []
            async for msg in self.client.iter_messages(event.chat_id, limit=num):
                if msg.sender_id == self.my_id:
                    messages.append(msg.id)
            if messages:
                await self.client.delete_messages(event.chat_id, messages)
                await event.edit(f"✅ {len(messages)} پیام حذف شد")
            else:
                await event.edit("⚠️ هیچ پیامی یافت نشد")
            return
        
        # حذف کامل
        if command_text == 'حذف کامل':
            await event.edit("⏳ در حال حذف پیام‌ها...")
            
            deleted_count = 0
            error_count = 0
            batch = []
            
            try:
                async for msg in self.client.iter_messages(event.chat_id, limit=None, from_user='me'):
                    batch.append(msg.id)
                    
                    if len(batch) >= 50:
                        try:
                            await self.client.delete_messages(event.chat_id, batch)
                            deleted_count += len(batch)
                            batch = []
                            await asyncio.sleep(0.5)
                        except FloodWaitError as e:
                            await asyncio.sleep(e.seconds + 1)
                            try:
                                await self.client.delete_messages(event.chat_id, batch)
                                deleted_count += len(batch)
                                batch = []
                            except:
                                error_count += len(batch)
                                batch = []
                        except Exception as e:
                            error_count += len(batch)
                            batch = []
                
                if batch:
                    try:
                        await self.client.delete_messages(event.chat_id, batch)
                        deleted_count += len(batch)
                    except:
                        error_count += len(batch)
                
                if deleted_count > 0:
                    await event.edit(f"✅ {deleted_count} پیام حذف شدند" + (f"\n❌ {error_count} پیام حذف نشدند" if error_count > 0 else ""))
                else:
                    await event.edit("⚠️ هیچ پیامی یافت نشد")
                    
            except Exception as e:
                await event.edit(f"⚠️ خطا: {str(e)[:100]}")
            return
        
        if command_text == 'پینگ':
            start = time.time()
            await event.edit("🏓 پینگ: ...")
            end = time.time()
            ping = round((end - start) * 1000, 2)
            await event.edit(f"🏓 پینگ: {ping} ms")
            return
        
        # دستورات استایل
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
        
        for cmd, style in style_commands.items():
            if command_text == f'{cmd} روشن':
                db.update_selfbot_setting(self.user_id, 'text_style', style)
                await event.edit(f"✅ استایل {cmd} فعال شد")
                return
            
            if command_text == f'{cmd} خاموش':
                current = db.get_selfbot_settings(self.user_id).get('text_style')
                if current == style:
                    db.update_selfbot_setting(self.user_id, 'text_style', None)
                    await event.edit(f"✅ استایل {cmd} غیرفعال شد")
                else:
                    await event.edit(f"⚠️ استایل {cmd} فعال نیست")
                return
        
        # تایم روشن/خاموش
        if command_text == 'تایم روشن':
            db.update_selfbot_setting(self.user_id, 'time_enabled', 1)
            db.update_selfbot_setting(self.user_id, 'flag_enabled', 0)
            await self.update_profile_name()
            await event.delete()
            return
        
        if command_text == "تایمر پرچم روشن":
            db.update_selfbot_setting(self.user_id, 'time_enabled', 1)
            db.update_selfbot_setting(self.user_id, 'flag_enabled', 1)
            await self.update_profile_name()
            await event.delete()
            return
        
        if command_text == "تایم خاموش":
            db.update_selfbot_setting(self.user_id, 'time_enabled', 0)
            db.update_selfbot_setting(self.user_id, 'flag_enabled', 0)
            await self.restore_profile_name()
            await event.delete()
            return
        
        # اتوسین
        if command_text == "فعال اتوسین":
            db.update_selfbot_setting(self.user_id, 'autosend_mode', 1)
            self.autosend_enabled = True
            await event.edit("✅ اتوسین فعال شد")
            return
        
        if command_text == "غیرفعال اتوسین":
            db.update_selfbot_setting(self.user_id, 'autosend_mode', 0)
            self.autosend_enabled = False
            await event.edit("✅ اتوسین غیرفعال شد")
            return
        
        # انیمیشن‌ها
        if command_text == 'قلب پیشرفته':
            await event.delete()
            try:
                msg = await self.client.send_message(event.chat_id, "❤️ شروع...")
                await advanced_heart_animation(msg)
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if command_text == 'عشق':
            await event.delete()
            try:
                msg = await event.respond("💝 شروع...")
                await advanced_heart_animation(msg)
            except Exception as e:
                logger.error(f"خطا: {e}")
            return
        
        if command_text == 'سنتت':
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
        
        if command_text == 'هک':
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
        
        if command_text == 'شروع':
            await event.delete()
            try:
                await event.respond("🌟 سلف‌بات شروع شد")
            except:
                pass
        
        # لیست دشمن
        if command_text == 'لیست دشمن':
            await self.handle_list_enemies_command(event)
            return
        
        # اسپم
        if command_text == 'لیست اسپم':
            await self.handle_list_spam_command(event)
            return
        
        if command_text == 'پاک کردن اسپم':
            await self.handle_clear_spam_command(event)
            return
        
        if re.match(r'^حذف اسپم\s+(\d+)$', command_text):
            await self.handle_delete_spam_command(event)
            return
        
        if command_text == 'اضافه اسپم':
            await self.handle_add_spam_command(event)
            return
        
        if command_text == 'اتمام اسپم':
            await self.handle_end_spam_command(event)
            return
        
        # تغییر نام و بیو
        if re.match(r'^تغییر اسم\s+(.+)$', event.text):
            await self.handle_change_name_command(event)
            return
        
        if re.match(r'^تغییر بیو\s+(.+)$', event.text):
            await self.handle_change_bio_command(event)
            return
        
        # کامنت
        if re.match(r'^کامنت\s+(.+)$', event.text):
            await self.handle_comment_command(event)
            return
        
        # کانال‌ها
        if command_text == 'کانال‌ها':
            await self.handle_channels_command(event)
            return
        
        if command_text == 'حذف کانال':
            await self.handle_delete_channel_command(event)
            return
        
        if command_text == 'تست کانال':
            await self.handle_test_channel_command(event)
            return
        
        # دشمن/دوست
        if re.match(r'^دشمن\s*(@\w+|-\d+|\d+)?$', command_text):
            await self.handle_enemy_command(event, 'add')
            return
        
        if re.match(r'^دوست\s*(@\w+|-\d+|\d+)?$', command_text):
            await self.handle_enemy_command(event, 'remove')
            return
        
        # قفل پیوی
        if re.match(r'^قفل پیوی\s*(@\w+|-\d+|\d+)?$', command_text):
            await self.handle_lock_pv_command(event, 'lock')
            return
        
        if re.match(r'^باز پی\s*(@\w+|-\d+|\d+)?$', command_text):
            await self.handle_lock_pv_command(event, 'unlock')
            return
        
        if command_text == "قفل پیوی همه":
            await self.handle_lock_all_pv_command(event, True)
            return
        
        if command_text == "باز پی همه":
            await self.handle_lock_all_pv_command(event, False)
            return
        
        # قلب و ماه
        if command_text == "قلب":
            await event.delete()
            await self.heart_animation(event.chat_id)
            return
        
        if command_text == "ماه":
            await event.delete()
            await self.moon_animation(event.chat_id)
            return
        
        # اطلاعات
        if command_text == "اطلاعات":
            await self.handle_info_command(event)
            return
        
        if command_text == "دانلود پروفایل":
            await self.handle_download_profile_command(event)
            return
        
        if command_text == "ست پروف":
            await self.handle_set_profile_command(event, 'photo')
            return
        
        if command_text == "ست بیو":
            await self.handle_set_profile_command(event, 'bio')
            return
        
        if command_text == "حذف ست پروف":
            await self.handle_delete_profile_command(event, 'photo')
            return
        
        if command_text == "حذف ست بیو":
            await self.handle_delete_profile_command(event, 'bio')
            return
        
        if command_text == "تاریخ کامل":
            await self.handle_full_date_command(event)
            return
        
        # اسپم
        if re.match(r'^اسپم\s+(\d+)\s+(.+)$', command_text):
            await self.handle_spam_command(event)
            return
        
        if command_text == "بلاک":
            await self.handle_block_command(event)
            return
        
        # ریکت
        if re.match(r'^ریکت\s*([\U0001F300-\U0001F9FF]+)?$', command_text):
            await self.handle_reaction_command(event, 'set')
            return
        
        if command_text == "حذف ریکت":
            await self.handle_reaction_command(event, 'remove')
            return
        
        # هوش مصنوعی
        if command_text in ['پیوی ۱', 'پیوی ۲', 'پیوی ۳', 'خاموش پیوی']:
            await self.handle_ai_command(event, 'pm')
            return
        
        if command_text in ['گروه ۱', 'گروه ۲', 'گروه ۳', 'خاموش گروه']:
            await self.handle_ai_command(event, 'group')
            return
        
        # من کی ام
        if command_text == 'من کی ام':
            await self.handle_whoami_command(event)
            return
        
        # گزارش
        if command_text == "تنظیم گزارش":
            await self.handle_report_group_command(event, 'set')
            return
        
        if command_text == "گروه گزارش":
            await self.handle_report_group_command(event, 'get')
            return
        
        # سرچ
        if command_text == 'سرچ':
            await self.handle_search_command(event)
            return
        
        if command_text == 'خروج سرچ':
            await self.handle_exit_search_command(event)
            return
        
        # ========== اگر هیچ دستوری شناسایی نشد ==========
        # هیچ کاری نکن (خطا نده)
        return
    
    # ========== توابع کمکی برای دستورات ==========
    
    async def handle_list_enemies_command(self, event):
        try:
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
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_list_spam_command(self, event):
        try:
            spam_messages = db.get_enemy_spam_messages(self.user_id)
            
            if spam_messages:
                message = "📜 لیست پیام‌های اسپم:\n\n"
                for i, spam_msg in enumerate(spam_messages, 1):
                    message += f"{i}. {spam_msg['text']}\n"
                
                message += f"\n📊 تعداد: {len(spam_messages)}\n"
                message += "🗑️ حذف اسپم [شماره]\n"
                message += "🧹 پاک کردن اسپم"
                
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
                await event.edit("📭 لیست پیام‌های اسپم خالی است")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_clear_spam_command(self, event):
        try:
            db.clear_enemy_spam_messages(self.user_id)
            await event.edit("✅ لیست پیام‌های اسپم پاک شد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_delete_spam_command(self, event):
        try:
            match = re.match(r'^حذف اسپم\s+(\d+)$', event.text.lower())
            message_id = int(match.group(1))
            
            spam_messages = db.get_enemy_spam_messages(self.user_id)
            
            if 1 <= message_id <= len(spam_messages):
                spam_msg = spam_messages[message_id - 1]
                db.delete_enemy_spam_message(self.user_id, spam_msg['id'])
                await event.edit(f"✅ پیام شماره {message_id} حذف شد")
            else:
                await event.edit(f"⚠️ پیام شماره {message_id} وجود ندارد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_add_spam_command(self, event):
        try:
            self.adding_spam = True
            await event.edit("📝 حالت اضافه کردن اسپم فعال شد\nبرای پایان: اتمام اسپم")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_end_spam_command(self, event):
        try:
            self.adding_spam = False
            await event.edit("✅ حالت اضافه کردن اسپم غیرفعال شد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_change_name_command(self, event):
        try:
            match = re.match(r'^تغییر اسم\s+(.+)$', event.text)
            new_name = match.group(1)
            
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
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_change_bio_command(self, event):
        try:
            match = re.match(r'^تغییر بیو\s+(.+)$', event.text)
            new_bio = match.group(1)
            
            await self.client(UpdateProfileRequest(about=new_bio))
            
            await event.edit(f"✅ بیو به {new_bio} تغییر کرد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_comment_command(self, event):
        try:
            comment_text = event.text[7:].strip()
            
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
            
            logger.info(f"✅ کامنت در {chat_type}: {chat.title}")
            
            try:
                await event.edit(comment_text)
            except:
                pass
                
        except Exception as e:
            logger.error(f"❌ خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_channels_command(self, event):
        try:
            auto_comments = db.get_auto_comments(self.user_id)
            
            if auto_comments:
                msg = "📊 کانال‌های تنظیم شده:\n\n"
                for comment in auto_comments:
                    msg += f"• {comment['channel_title']} ({comment['channel_type']})\n"
                    msg += f"  آیدی: {comment['channel_id']}\n"
                    msg += f"  متن: {comment['comment_text'][:30]}...\n\n"
            else:
                msg = "📭 هیچ کانالی تنظیم نشده"
            
            await event.edit(msg)
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_delete_channel_command(self, event):
        try:
            chat = await event.get_chat()
            channel_id = chat.id
            
            auto_comment = db.get_auto_comment(self.user_id, channel_id)
            
            if auto_comment:
                db.remove_auto_comment(self.user_id, channel_id)
                await event.edit(f"✅ تنظیمات {auto_comment['channel_title']} حذف شد")
            else:
                await event.edit("⚠️ این کانال تنظیم نشده است")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_test_channel_command(self, event):
        try:
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                chat = await reply_msg.get_chat()
                msg = reply_msg
            else:
                chat = await event.get_chat()
                msg = event.message
            
            info = f"🔍 اطلاعات تست:\n\n"
            info += f"چت: {chat.title}\n"
            info += f"نوع: {'کانال' if hasattr(chat, 'broadcast') and chat.broadcast else 'گروه'}\n"
            info += f"آیدی: {chat.id}\n"
            
            auto_comment = db.get_auto_comment(self.user_id, chat.id)
            info += f"تنظیم شده: {'✅' if auto_comment else '❌'}\n"
            
            if auto_comment:
                info += f"متن: {auto_comment['comment_text'][:50]}...\n"
            
            info += f"\n📨 اطلاعات پیام:\n"
            info += f"پست کانال: {is_channel_post(msg)}\n"
            
            await event.edit(info)
                
        except Exception as e:
            logger.error(f"⚠️ خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_enemy_command(self, event, action):
        try:
            target_id = await get_target_user(event, self.client)
            
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            
            if target_id:
                if action == 'add':
                    db.add_enemy(self.user_id, target_id, 'pv')
                    await event.edit(f"✅ دشمن اضافه شد")
                    await self.spam_enemy(target_id)
                else:
                    db.remove_enemy(self.user_id, target_id, 'pv')
                    await event.edit(f"✅ دوست حذف شد")
                    
                    if target_id in self.spam_tasks:
                        self.spam_tasks[target_id].cancel()
                        del self.spam_tasks[target_id]
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_lock_pv_command(self, event, action):
        try:
            target_id = await get_target_user(event, self.client)
            
            if not target_id and isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
            
            if target_id:
                if action == 'lock':
                    db.add_locked_pv(self.user_id, target_id)
                    await event.edit(f"✅ قفل پیوی برای کاربر {target_id} فعال شد")
                else:
                    db.remove_locked_pv(self.user_id, target_id)
                    await event.edit(f"✅ قفل پیوی برای کاربر {target_id} غیرفعال شد")
            else:
                await event.edit("⚠️ کاربر هدف مشخص نشد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_lock_all_pv_command(self, event, lock):
        try:
            db.update_selfbot_setting(self.user_id, 'pv_lock_all', 1 if lock else 0)
            
            if lock:
                await event.edit("✅ قفل پیوی همگانی فعال شد")
            else:
                await event.edit("✅ قفل پیوی همگانی غیرفعال شد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
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
    
    async def handle_info_command(self, event):
        try:
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
            
            user_id = user.id
            
            try:
                photos = await self.client(GetUserPhotosRequest(user_id=user.id, offset=0, max_id=0, limit=1))
                photo_count = len(photos.photos) if photos.photos else 0
            except:
                photo_count = 0
            
            info_text = f"📋 اطلاعات کاربر:\n\n"
            info_text += f"👤 یوزرنیم: {username}\n"
            info_text += f"🆔 ID: {user_id}\n"
            info_text += f"📛 نام: {name}\n"
            info_text += f"📝 بیو: {bio}\n"
            info_text += f"📸 تعداد عکس: {photo_count}"
            
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user_id}.jpg")
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
            
        except Exception as e:
            logger.error(f"خطا: {str(e)}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_download_profile_command(self, event):
        try:
            if event.is_reply:
                reply_message = await event.get_reply_message()
                user = await reply_message.get_sender()
            else:
                user = await self.client.get_me()
            
            user_id = user.id
            user_name = user.first_name or user.username or "کاربر"
            
            if user.photo:
                try:
                    photo = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user_id}.jpg")
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
            
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_set_profile_command(self, event, type_):
        try:
            if event.is_reply:
                reply_message = await event.get_reply_message()
                user = await reply_message.get_sender()
                
                if type_ == 'photo':
                    if user.photo:
                        photo_path = await self.client.download_profile_photo(user, file=f"{MEDIA_FOLDER}/profile_{user.id}.jpg")
                        if photo_path and os.path.exists(photo_path):
                            try:
                                me = await self.client.get_me()
                                if me.photo:
                                    photos = await self.client.get_profile_photos(me.id, limit=1)
                                    if photos:
                                        await self.client(DeletePhotosRequest(id=[photos[0]]))
                                
                                file = await self.client.upload_file(photo_path)
                                await self.client(UploadProfilePhotoRequest(file=file))
                                await event.edit("✅ عکس پروفایل ست شد")
                                os.remove(photo_path)
                            except FloodWaitError as e:
                                await event.edit(f"⚠️ {e.seconds} ثانیه صبر کنید")
                            except:
                                await event.edit("⚠️ خطا")
                        else:
                            await event.edit("⚠️ خطا در دانلود")
                    else:
                        await event.edit("⚠️ این کاربر عکس پروفایل ندارد")
                else:
                    try:
                        full_user = await self.client(GetFullUserRequest(user.id))
                        bio = full_user.full_user.about or ""
                        await self.client(UpdateProfileRequest(about=bio))
                        await event.edit("✅ بیو ست شد")
                    except:
                        await event.edit("⚠️ خطا")
            else:
                await event.edit("⚠️ روی پیام کاربر ریپلای کنید")
            
            await event.delete()
            
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_delete_profile_command(self, event, type_):
        try:
            if type_ == 'photo':
                me = await self.client.get_me()
                if me.photo:
                    try:
                        photos = await self.client.get_profile_photos(me.id, limit=1)
                        if photos:
                            await self.client(DeletePhotosRequest(id=[photos[0]]))
                        await event.edit("✅ عکس پروفایل حذف شد")
                    except FloodWaitError as e:
                        await event.edit(f"⚠️ {e.seconds} ثانیه صبر کنید")
                    except:
                        await event.edit("⚠️ خطا")
                else:
                    await event.edit("⚠️ عکس پروفایلی وجود ندارد")
            else:
                try:
                    await self.client(UpdateProfileRequest(about=""))
                    await event.edit("✅ بیو خالی شد")
                except:
                    await event.edit("⚠️ خطا")
            
            await event.delete()
            
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_full_date_command(self, event):
        try:
            date_info = get_full_date_info()
            settings = db.get_selfbot_settings(self.user_id)
            text, entities = await apply_text_style(date_info, settings.get('text_style'))
            await self.client.send_message(event.chat_id, text, formatting_entities=entities)
            await event.delete()
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_spam_command(self, event):
        try:
            match = re.match(r'^اسپم\s+(\d+)\s+(.+)$', event.text.lower())
            num = int(match.group(1))
            message = match.group(2)
            
            if event.is_reply:
                reply_message = await event.get_reply_message()
                message = reply_message.text or message
            
            for _ in range(num):
                settings = db.get_selfbot_settings(self.user_id)
                text, entities = await apply_text_style(message, settings.get('text_style'))
                await self.client.send_message(event.chat_id, text, formatting_entities=entities)
                await asyncio.sleep(0.05)
            
            await event.edit(f"✅ {num} پیام اسپم ارسال شد")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_block_command(self, event):
        try:
            if isinstance(event.message.peer_id, PeerUser):
                target_id = event.message.peer_id.user_id
                await self.client(BlockRequest(id=target_id))
                await event.edit("✅ کاربر بلاک شد")
            else:
                await event.edit("⚠️ فقط در پی‌وی")
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_reaction_command(self, event, action):
        try:
            chat_id = None
            if isinstance(event.message.peer_id, PeerUser):
                chat_id = event.message.peer_id.user_id
            elif isinstance(event.message.peer_id, PeerChannel):
                chat_id = event.message.peer_id.channel_id
            elif isinstance(event.message.peer_id, PeerChat):
                chat_id = event.message.peer_id.chat_id
            
            target_id = await get_target_user(event, self.client)
            
            if action == 'set':
                match = re.match(r'^ریکت\s*([\U0001F300-\U0001F9FF]+)?$', event.text.lower())
                emoji = match.group(1) if match and match.group(1) else None
                
                if not emoji:
                    await event.edit("⚠️ ایموجی وارد کنید")
                    return
                
                if emoji in ALLOWED_EMOJIS:
                    db.set_reaction(self.user_id, chat_id, target_id, emoji)
                    await event.edit(f"✅ ریکت {emoji} برای کاربر {target_id} تنظیم شد")
                else:
                    await event.edit(f"⚠️ ایموجی {emoji} مجاز نیست")
            
            else:
                if target_id:
                    db.remove_reaction(self.user_id, chat_id, target_id)
                    await event.edit(f"✅ ریکت برای کاربر {target_id} حذف شد")
                else:
                    await event.edit("⚠️ کاربر هدف مشخص نشد")
        
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_ai_command(self, event, ai_type):
        try:
            command_text = event.text.lower()
            settings = db.get_selfbot_settings(self.user_id)
            ai_status = settings.get('ai_status', {})
            
            if ai_type == 'pm':
                if command_text == 'پیوی ۱':
                    ai_status['ai_1_pm'] = True
                    ai_status['ai_2_pm'] = False
                    ai_status['ai_3_pm'] = False
                    message = '✅ هوش ۱ (Gemini) در پی‌وی روشن شد'
                elif command_text == 'پیوی ۲':
                    ai_status['ai_1_pm'] = False
                    ai_status['ai_2_pm'] = True
                    ai_status['ai_3_pm'] = False
                    message = '✅ هوش ۲ (Paxsenix) در پی‌وی روشن شد'
                elif command_text == 'پیوی ۳':
                    ai_status['ai_1_pm'] = False
                    ai_status['ai_2_pm'] = False
                    ai_status['ai_3_pm'] = True
                    message = '✅ هوش ۳ (DeepSeek) در پی‌وی روشن شد'
                else:
                    ai_status['ai_1_pm'] = False
                    ai_status['ai_2_pm'] = False
                    ai_status['ai_3_pm'] = False
                    message = '✅ همه هوش‌ها در پی‌وی خاموش شدند'
            else:
                if command_text == 'گروه ۱':
                    ai_status['ai_1_group'] = True
                    ai_status['ai_2_group'] = False
                    ai_status['ai_3_group'] = False
                    message = '✅ هوش ۱ (Gemini) در گروه روشن شد'
                elif command_text == 'گروه ۲':
                    ai_status['ai_1_group'] = False
                    ai_status['ai_2_group'] = True
                    ai_status['ai_3_group'] = False
                    message = '✅ هوش ۲ (Paxsenix) در گروه روشن شد'
                elif command_text == 'گروه ۳':
                    ai_status['ai_1_group'] = False
                    ai_status['ai_2_group'] = False
                    ai_status['ai_3_group'] = True
                    message = '✅ هوش ۳ (DeepSeek) در گروه روشن شد'
                else:
                    ai_status['ai_1_group'] = False
                    ai_status['ai_2_group'] = False
                    ai_status['ai_3_group'] = False
                    message = '✅ همه هوش‌ها در گروه خاموش شدند'
            
            db.update_ai_status(self.user_id, ai_status)
            await event.edit(message)
        
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_whoami_command(self, event):
        try:
            if isinstance(event.message.peer_id, PeerUser):
                user_id = event.sender_id
                user_name = db.get_user_name(user_id)
                user_info = db.get_user_info(user_id)
                
                info_text = f"👤 اطلاعات شما:\n"
                info_text += f"• نام: {user_name}\n"
                info_text += f"• آی‌دی: {user_id}\n"
                
                if user_info:
                    info_text += f"\n📝 اطلاعات ذخیره شده:\n"
                    for key, value in user_info.items():
                        info_text += f"• {key}: {value}\n"
                else:
                    info_text += f"\nℹ️ اطلاعات اضافی ذخیره نشده\n"
                
                await event.edit(info_text)
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_report_group_command(self, event, action):
        try:
            if action == 'set':
                if isinstance(event.message.peer_id, (PeerChannel, PeerChat)):
                    chat_id = event.message.peer_id.channel_id if isinstance(event.message.peer_id, PeerChannel) else event.message.peer_id.chat_id
                    self.report_config.set_report_group(chat_id)
                    await event.edit(f"✅ گروه گزارش تنظیم شد\nآیدی: {chat_id}")
                else:
                    await event.edit("⚠️ این دستور فقط در گروه کار می‌کند")
            else:
                await event.edit(f"📍 گروه گزارش فعلی:\nآیدی: {self.report_config.report_group_id}")
        
        except Exception as e:
            logger.error(f"خطا: {e}")
            try:
                await event.delete()
            except:
                pass
    
    async def handle_search_command(self, event):
        self.search_mode = True
        await event.edit('🔍 حالت سرچ فعال شد.\n\nاکنون هر متنی که ارسال کنید در گوگل جستجو می‌شود.\nبرای خروج از حالت سرچ، دستور خروج سرچ را ارسال کنید.')
    
    async def handle_exit_search_command(self, event):
        self.search_mode = False
        self.last_search_results = []
        await event.edit('✅ حالت سرچ غیرفعال شد.')
    
    async def handle_outgoing_message(self, event):
        message_text = event.text or ""
        
        if self.adding_spam and message_text and not message_text.startswith(('لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال', 'حذف', 'ست', 'بولد', 'زیرخط', 'خط خورده', 'نقل قول', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک', 'ریکت', 'پیوی', 'گروه', 'درباره', 'من کی ام', 'قفل', 'باز', 'تنظیم', 'گروه گزارش', 'دشمن', 'دوست', 'کانال', 'کامنت', 'تست', 'لیست دشمن', 'لیست اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'اضافه اسپم', 'اتمام اسپم', 'تغییر اسم', 'تغییر بیو', 'تغییر پروفایل', 'پروف', 'اسپم روشن', 'اسپم خاموش', 'پینگ', 'سرچ', 'خروج سرچ', 'قلب پیشرفته', 'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', '/panel', '.اهنگ', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش', 'پین', 'تگ ادمین', 'امار گپ', '.کد')):
            db.add_enemy_spam_message(self.user_id, message_text)
            try:
                await event.delete()
            except:
                pass
            return
        
        if event.text:
            settings = db.get_selfbot_settings(self.user_id)
            text_style = settings.get('text_style')
            
            if text_style and not message_text.startswith(('لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال', 'حذف', 'ست', 'بولد', 'زیرخط', 'خط خورده', 'نقل قول', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک', 'ریکت', 'پیوی', 'گروه', 'درباره', 'من کی ام', 'قفل', 'باز', 'تنظیم', 'گروه گزارش', 'دشمن', 'دوست', 'کانال', 'کامنت', 'تست', 'لیست دشمن', 'لیست اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'اضافه اسپم', 'اتمام اسپم', 'تغییر اسم', 'تغییر بیو', 'تغییر پروفایل', 'پروف', 'اسپم روشن', 'اسپم خاموش', 'پینگ', 'سرچ', 'خروج سرچ', 'قلب پیشرفته', 'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', '/panel', '.اهنگ', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش', 'پین', 'تگ ادمین', 'امار گپ', '.کد')):
                try:
                    text, entities = await apply_text_style(message_text, text_style)
                    if entities:
                        await event.message.edit(text, formatting_entities=entities)
                except:
                    pass
        
        if self.search_mode and message_text and not message_text.startswith(('لیست', 'شروع', 'تایم', 'قلب', 'ماه', 'اطلاعات', 'دانلود', 'تاریخ', 'فعال', 'غیرفعال', 'حذف', 'ست', 'بولد', 'زیرخط', 'خط خورده', 'نقل قول', 'اسپویلر', 'کج', 'کد', 'پیش', 'اسپم', 'بلاک', 'ریکت', 'پیوی', 'گروه', 'درباره', 'من کی ام', 'قفل', 'باز', 'تنظیم', 'گروه گزارش', 'دشمن', 'دوست', 'کانال', 'کامنت', 'تست', 'لیست دشمن', 'لیست اسپم', 'پاک کردن اسپم', 'حذف اسپم', 'اضافه اسپم', 'اتمام اسپم', 'تغییر اسم', 'تغییر بیو', 'تغییر پروفایل', 'پروف', 'اسپم روشن', 'اسپم خاموش', 'پینگ', 'سرچ', 'خروج سرچ', 'قلب پیشرفته', 'عشق', 'سنتت', 'هک', 'وضعیت', '.پنل', 'پنل', '/panel', '.اهنگ', 'تنظیم اسپم', 'سلف روشن', 'سلف خاموش', 'پین', 'تگ ادمین', 'امار گپ', '.کد')):
            await self.handle_google_search(event, message_text)
            return
        
        if event.text:
            translated_text = await self.translate_text(event.text)
            if translated_text != event.text:
                try:
                    await event.edit(translated_text)
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
    
    async def update_profile_name(self):
        settings = db.get_selfbot_settings(self.user_id)
        
        if settings.get('time_enabled'):
            now = datetime.now()
            current_minute = now.minute
            
            if self.time_font_indices == 'all':
                font_index = current_minute % len(classic_fonts)
                font = classic_fonts[font_index]
            elif isinstance(self.time_font_indices, list) and self.time_font_indices:
                if hasattr(self, 'time_font_cycle'):
                    self.time_font_cycle = (self.time_font_cycle + 1) % len(self.time_font_indices)
                else:
                    self.time_font_cycle = 0
                font_index = self.time_font_indices[self.time_font_cycle]
                if font_index < len(classic_fonts):
                    font = classic_fonts[font_index]
                else:
                    font = classic_fonts[0]
            else:
                font = classic_fonts[0]
            
            time_now = now.strftime("%H:%M")
            time_now_classic = convert_to_classic_font(time_now, font_index if isinstance(font_index, int) else 0)
            
            try:
                current_name = db.get_current_name(self.user_id)
                if not current_name:
                    current_name = self.BASE_NAME
                
                if settings.get('flag_enabled'):
                    flag_index = settings.get('selected_flag_index', 0)
                    if 0 <= flag_index < len(flags):
                        flag = flags[flag_index]
                    else:
                        flag = flags[current_minute % len(flags)]
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

# ========== توابع کیبورد ==========

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
            InlineKeyboardButton("🛠 ابزار", callback_data=f"tools_menu_{user_id}")
        ],
        [
            InlineKeyboardButton("❌ بستن پنل", callback_data=f"close_panel_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_broadcast_menu_keyboard(user_id):
    # فقط برای ادمین
    if user_id != ADMIN_ID:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]])
    
    keyboard = [
        [
            InlineKeyboardButton("☖ پیام همگانی", callback_data=f"exec_broadcast_{user_id}"),
            InlineKeyboardButton("✿ آمار کاربران", callback_data=f"exec_user_stats_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== توابع کیبورد جدید برای تایم و پرچم ==========

def get_time_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    time_enabled = settings.get('time_enabled', False)
    flag_enabled = settings.get('flag_enabled', False)
    
    keyboard = [
        [
            InlineKeyboardButton(f"🕐 تایم روشن {'' if not time_enabled else '✓'}", callback_data=f"exec_time_on_{user_id}"),
            InlineKeyboardButton(f"🏳️ تایمر پرچم {'' if not flag_enabled else '✓'}", callback_data=f"exec_time_flag_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🚫 تایم خاموش {'' if time_enabled else '✓'}", callback_data=f"exec_time_off_{user_id}"),
            InlineKeyboardButton("📅 تاریخ کامل", callback_data=f"exec_full_date_{user_id}")
        ],
        [
            InlineKeyboardButton("🎨 انتخاب فونت", callback_data=f"font_menu_{user_id}"),
            InlineKeyboardButton("🏳️ انتخاب پرچم", callback_data=f"flag_menu_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_font_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    selected_indices = settings.get('time_font_indices', 'all')
    if selected_indices == 'all':
        selected_indices = list(range(len(classic_fonts)))
    elif not isinstance(selected_indices, list):
        selected_indices = []
    
    keyboard = []
    row = []
    # نمایش فونت‌ها به صورت دکمه‌های کوچک با شماره
    for i, font in enumerate(classic_fonts):
        if i > 0 and i % 5 == 0:
            keyboard.append(row)
            row = []
        # نمایش نمونه فونت
        sample = font[0] if isinstance(font, str) else list(font.values())[0]
        label = f"{sample} {i}"
        if i in selected_indices:
            label = f"✓ {label}"
        row.append(InlineKeyboardButton(label, callback_data=f"exec_font_toggle_{i}_{user_id}"))
    if row:
        keyboard.append(row)
    
    # دکمه‌های عمومی
    keyboard.append([
        InlineKeyboardButton("📌 همه فونت‌ها", callback_data=f"exec_font_all_{user_id}"),
        InlineKeyboardButton("🗑️ پاک کردن انتخاب‌ها", callback_data=f"exec_font_clear_{user_id}")
    ])
    keyboard.append([InlineKeyboardButton("⚈ بازگشت به زمان", callback_data=f"time_menu_{user_id}")])
    return InlineKeyboardMarkup(keyboard)

def get_flag_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    selected_index = settings.get('selected_flag_index', 0)
    flag_enabled = settings.get('flag_enabled', False)
    
    keyboard = []
    row = []
    for i, flag in enumerate(flags):
        if i > 0 and i % 10 == 0:
            keyboard.append(row)
            row = []
        label = f"{flag}"
        if i == selected_index and flag_enabled:
            label = f"✓ {label}"
        row.append(InlineKeyboardButton(label, callback_data=f"exec_flag_select_{i}_{user_id}"))
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⚈ بازگشت به زمان", callback_data=f"time_menu_{user_id}")])
    return InlineKeyboardMarkup(keyboard)

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
            InlineKeyboardButton("📝 قفل متن", callback_data=f"exec_lock_text_{user_id}"),
            InlineKeyboardButton("📖 راهنمای کامل قفل‌ها", callback_data=f"exec_lock_help_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_panel_keyboard(user_id):
    if user_id != ADMIN_ID:
        return InlineKeyboardMarkup([[InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]])
    
    keyboard = [
        [
            InlineKeyboardButton("📋 درخواست‌ها", callback_data=f"admin_requests"),
            InlineKeyboardButton("🔐 منتظر ورود", callback_data=f"admin_login")
        ],
        [
            InlineKeyboardButton("✅ کاربران فعال", callback_data=f"admin_active"),
            InlineKeyboardButton("🤖 سلف‌بات‌ها", callback_data=f"admin_selfbots")
        ],
        [
            InlineKeyboardButton("📊 آمار کلی", callback_data=f"admin_stats"),
            InlineKeyboardButton("📢 پیام همگانی", callback_data=f"admin_broadcast")
        ],
        [
            InlineKeyboardButton("📥 دریافت دیتابیس", callback_data=f"exec_admin_get_db_{user_id}"),
            InlineKeyboardButton("📤 آپلود دیتابیس", callback_data=f"exec_admin_upload_db_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== بقیه توابع کیبورد مشابه قبل ==========

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_general_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📊 وضعیت", callback_data=f"exec_status_{user_id}"),
            InlineKeyboardButton("ℹ️ درباره", callback_data=f"exec_about_{user_id}")
        ],
        [
            InlineKeyboardButton("⏱️ پینگ", callback_data=f"exec_ping_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_action_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🎮 اکشن [نام]", callback_data=f"exec_action_{user_id}"),
            InlineKeyboardButton("⏹️ اکشن خاموش", callback_data=f"exec_action_off_{user_id}")
        ],
        [
            InlineKeyboardButton("📋 اکشن لیست", callback_data=f"exec_action_list_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_translate_menu_keyboard(user_id):
    translate_mode = {}
    if str(user_id) in selfbot_managers:
        translate_mode = selfbot_managers[str(user_id)].translate_mode
    
    keyboard = [
        [
            InlineKeyboardButton(f"🇬🇧 انگلیسی {'' if not translate_mode.get('english') else '✓'}", callback_data=f"exec_translate_en_{user_id}"),
            InlineKeyboardButton(f"🇸🇦 عربی {'' if not translate_mode.get('arabic') else '✓'}", callback_data=f"exec_translate_ar_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🇮🇱 عبری {'' if not translate_mode.get('hebrew') else '✓'}", callback_data=f"exec_translate_he_{user_id}"),
            InlineKeyboardButton(f"🇷🇺 روسی {'' if not translate_mode.get('russian') else '✓'}", callback_data=f"exec_translate_ru_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🇹🇷 ترکی {'' if not translate_mode.get('turkish') else '✓'}", callback_data=f"exec_translate_tr_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_google_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🔍 سرچ", callback_data=f"exec_search_on_{user_id}"),
            InlineKeyboardButton("❌ خروج جستجو", callback_data=f"exec_search_off_{user_id}"),
            InlineKeyboardButton("🎵 اهنگ", callback_data=f"exec_music_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_info_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📋 اطلاعات", callback_data=f"exec_info_{user_id}"),
            InlineKeyboardButton("⬇️ دانلود پروفایل", callback_data=f"exec_download_profile_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_style_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    current = settings.get('text_style', 'هیچ')
    
    keyboard = [
        [
            InlineKeyboardButton(f"بولد {'' if current != 'بولد' else '✓'}", callback_data=f"exec_bold_{user_id}"),
            InlineKeyboardButton(f"زیرخط {'' if current != 'زیرخط' else '✓'}", callback_data=f"exec_underline_{user_id}"),
            InlineKeyboardButton(f"خط خورده {'' if current != 'خط خورده' else '✓'}", callback_data=f"exec_strike_{user_id}")
        ],
        [
            InlineKeyboardButton(f"نقل قول {'' if current != 'نقل قول' else '✓'}", callback_data=f"exec_quote_{user_id}"),
            InlineKeyboardButton(f"اسپویلر {'' if current != 'اسپویلر' else '✓'}", callback_data=f"exec_spoiler_{user_id}"),
            InlineKeyboardButton(f"کج {'' if current != 'کج' else '✓'}", callback_data=f"exec_italic_{user_id}")
        ],
        [
            InlineKeyboardButton(f"کد {'' if current != 'کد' else '✓'}", callback_data=f"exec_code_{user_id}"),
            InlineKeyboardButton(f"پیش {'' if current != 'پیش' else '✓'}", callback_data=f"exec_pre_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_reaction_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("👍 ریکت", callback_data=f"exec_reaction_{user_id}"),
            InlineKeyboardButton("❌ حذف ریکت", callback_data=f"exec_reaction_off_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_spam_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📩 اسپم", callback_data=f"exec_spam_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_filter_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("🚫 .فیلتر [کلمه]", callback_data=f"exec_filter_word_{user_id}"),
            InlineKeyboardButton("✅ فیلتر روشن", callback_data=f"exec_filter_on_{user_id}")
        ],
        [
            InlineKeyboardButton("❌ فیلتر خاموش", callback_data=f"exec_filter_off_{user_id}"),
            InlineKeyboardButton("📜 لیست فیلتر", callback_data=f"exec_filter_list_{user_id}")
        ],
        [
            InlineKeyboardButton("🗑️ حذف فیلتر", callback_data=f"exec_filter_remove_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_ai_menu_keyboard(user_id):
    settings = db.get_selfbot_settings(user_id)
    ai = settings['ai_status']
    
    keyboard = [
        [
            InlineKeyboardButton(f"🟢 پیوی ۱ {'' if not ai['ai_1_pm'] else '✓'}", callback_data=f"exec_ai_pm_1_{user_id}"),
            InlineKeyboardButton(f"🔵 پیوی ۲ {'' if not ai['ai_2_pm'] else '✓'}", callback_data=f"exec_ai_pm_2_{user_id}"),
            InlineKeyboardButton(f"🟣 پیوی ۳ {'' if not ai['ai_3_pm'] else '✓'}", callback_data=f"exec_ai_pm_3_{user_id}")
        ],
        [
            InlineKeyboardButton("⚫ خاموش پیوی", callback_data=f"exec_ai_pm_off_{user_id}")
        ],
        [
            InlineKeyboardButton(f"🟢 گروه ۱ {'' if not ai['ai_1_group'] else '✓'}", callback_data=f"exec_ai_group_1_{user_id}"),
            InlineKeyboardButton(f"🔵 گروه ۲ {'' if not ai['ai_2_group'] else '✓'}", callback_data=f"exec_ai_group_2_{user_id}"),
            InlineKeyboardButton(f"🟣 گروه ۳ {'' if not ai['ai_3_group'] else '✓'}", callback_data=f"exec_ai_group_3_{user_id}")
        ],
        [
            InlineKeyboardButton("⚫ خاموش گروه", callback_data=f"exec_ai_group_off_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_report_menu_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton("📍 تنظیم گزارش", callback_data=f"exec_set_report_{user_id}"),
            InlineKeyboardButton("ℹ️ گروه گزارش", callback_data=f"exec_show_report_{user_id}")
        ],
        [InlineKeyboardButton("⚈ بازگشت", callback_data=f"back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== توابع ربات اصلی ==========

async def inline_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    if not query:
        return
    
    user_id = query.from_user.id
    
    user_data = db.get_user(str(user_id))
    if not user_data or not user_data.get('self_active'):
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="⛔ دسترسی محدود",
                description="شما عضو سرویس نیستید",
                input_message_content=InputTextMessageContent("⛔ شما به این پنل دسترسی ندارید\n\nبرای عضویت: /start")
            )
        ]
        await query.answer(results, cache_time=1, is_personal=True)
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
                    reply_markup=get_admin_panel_keyboard(user_id)
                )
            )
    else:
        search = query.query.lower()
        results = []
        
        all_commands = [
            ("⚈ زمان و پروفایل", "time", "مدیریت زمان و پروفایل"),
            ("☻ انیمیشن", "animation", "انیمیشن قلب و ماه و سنتت"),
            ("☗ مدیریت کاربران", "user", "مدیریت دشمن/دوست/بلاک"),
            ("⊖ قفل رسانه", "lock", "قفل لینک/عکس/ویدیو/استیکر/ویس/فایل/موزیک/ویدیو نوت/کانتکت/لوکیشن/ایموجی/متن"),
            ("✼ کامنت", "comment", "کامنت خودکار در کانال"),
            ("✿ عمومی", "general", "وضعیت/درباره/پینگ"),
            ("☥ اکشن", "action", "اکشن‌های تایپ و ..."),
            ("⚕ بازی‌ها", "games", "تاس/دارت/بسکتبال/فوتبال"),
            ("❍ ترجمه", "translate", "ترجمه به زبان‌های مختلف"),
            ("𖢅 گوگل", "google", "جستجوی گوگل/اهنگ"),
            ("֍ اطلاعاتی", "info", "اطلاعات کاربر و دانلود پروفایل"),
            ("𖢨 پروفایل", "profile", "کپی پروفایل و بیو"),
            ("⩐ استایل متن", "style", "بولد/زیرخط/خط خورده/نقل قول/اسپویلر/کج/کد/پیش"),
            ("𑪡 مدیریت پیام", "message", "حذف پیام و اتوسین"),
            ("☖ ریکشن", "reaction", "ریکت خودکار"),
            ("𖥞 اسپم", "spam", "ارسال اسپم"),
            ("☗ تغییر پروفایل", "change", "تغییر نام/بیو/پروفایل"),
            ("⚇ مدیریت دشمنان", "enemy", "لیست دشمن/اضافه اسپم"),
            ("✿ فیلتر کلمات", "filter", "فیلتر کلمات"),
            ("⚉ حفاظت اسپم", "protection", "محافظت در برابر اسپم"),
            ("☥ هوش مصنوعی", "ai", "مدیریت هوش مصنوعی"),
            ("֎ گزارش", "report", "تنظیم گروه گزارش"),
            ("🛠 ابزار", "tools", "امار گپ / کد QR / تگ ادمین / پین / سلف روشن/خاموش")
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
    
    await query.answer(results, cache_time=1, is_personal=True)

# ========== توابع ادمین ==========

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ دسترسی غیرمجاز")
        return
    
    await query.edit_message_text(
        "👑 پنل مدیریت\n\nلطفاً انتخاب کنید:",
        reply_markup=get_admin_panel_keyboard(user_id)
    )

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
            keyboard.append([
                InlineKeyboardButton(f"✅ تأیید {req['user_id']}", callback_data=f"approve_{req['user_id']}"),
                InlineKeyboardButton(f"❌ رد {req['user_id']}", callback_data=f"reject_{req['user_id']}")
            ])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"admin_panel")])
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
            keyboard.append([
                InlineKeyboardButton(f"🛑 توقف {uid}", callback_data=f"stop_selfbot_{uid}"),
                InlineKeyboardButton(f"🔄 ریستارت {uid}", callback_data=f"restart_selfbot_{uid}")
            ])
        keyboard.append([InlineKeyboardButton("⚈ بازگشت", callback_data=f"admin_panel")])
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
        await context.bot.send_message(
            chat_id=int(target_id),
            text="🎉 درخواست عضویت شما تأیید شد!\n\nلطفاً شماره تلفن خود را وارد کنید:\nمثال: +989123456789"
        )
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
        await context.bot.send_message(
            chat_id=int(target_id),
            text="⚠ درخواست عضویت شما رد شد.\n\nمی‌توانید دوباره درخواست دهید"
        )
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

# ========== اجرای دستورات ==========

async def exec_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    
    if not data.startswith('exec_'):
        return
    
    await query.answer()
    
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
        await query.edit_message_text("❌ سلف‌بات شما فعال نیست")
        return
    
    manager = selfbot_managers[user_id_str]
    cmd = data.replace(f'exec_', '').replace(f'_{user_id}', '')
    
    msg = await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"⏳ در حال اجرا..."
    )
    
    # ========== دستورات جدید ==========
    
    if cmd == 'lock_help':
        help_text = """
📖 **راهنمای کامل قفل رسانه‌ها**

با استفاده از این قابلیت می‌توانید انواع مختلف رسانه‌ها و پیام‌ها را در پی‌وی و گروه‌ها قفل کنید.

**نحوه کار:**
• روی دکمه مورد نظر کلیک کنید تا قفل آن فعال/غیرفعال شود.
• برای قفل کردن برای همه کاربران، بدون ریپلای کلیک کنید.
• برای قفل کردن برای یک کاربر خاص، روی پیام آن کاربر ریپلای کنید و سپس دکمه را بزنید.

**انواع قفل‌ها:**

🔗 **قفل لینک** : جلوگیری از ارسال لینک‌ها (https, t.me, ...)
📸 **قفل عکس** : جلوگیری از ارسال عکس
🎥 **قفل ویدیو** : جلوگیری از ارسال ویدیو
🎨 **قفل استیکر** : جلوگیری از ارسال استیکر
🎞️ **قفل گیف** : جلوگیری از ارسال گیف
🎤 **قفل ویس** : جلوگیری از ارسال پیام صوتی
📁 **قفل فایل** : جلوگیری از ارسال هر نوع فایل
🎵 **قفل موزیک** : جلوگیری از ارسال فایل موسیقی
📹 **قفل ویدیو نوت** : جلوگیری از ارسال ویدیو نوت (دایره‌ای)
📞 **قفل کانتکت** : جلوگیری از ارسال مخاطب
📍 **قفل لوکیشن** : جلوگیری از ارسال موقعیت مکانی
😀 **قفل ایموجی** : جلوگیری از ارسال پیام‌های فقط ایموجی
📝 **قفل متن** : جلوگیری از ارسال پیام متنی (غیر لینک و غیر ایموجی)

💡 **نکته:** هر قفل را می‌توانید برای همه کاربران یا یک کاربر خاص فعال کنید.
"""
        await msg.edit_text(help_text, parse_mode='Markdown')
        return
    
    if cmd.startswith('font_toggle_'):
        # استخراج ایندکس فونت از cmd: font_toggle_5_123456
        parts_cmd = cmd.split('_')
        try:
            font_idx = int(parts_cmd[2])
            user_id_param = parts_cmd[3] if len(parts_cmd) > 3 else user_id_str
        except:
            await msg.edit_text("⚠️ خطا در انتخاب فونت")
            return
        
        settings = db.get_selfbot_settings(user_id)
        selected = settings.get('time_font_indices', 'all')
        if selected == 'all':
            selected = []
        elif not isinstance(selected, list):
            selected = []
        
        if font_idx in selected:
            selected.remove(font_idx)
        else:
            selected.append(font_idx)
            selected = sorted(selected)
        
        # ذخیره تنظیمات
        db.update_selfbot_setting(user_id, 'time_font_indices', ','.join(map(str, selected)) if selected else 'all')
        manager.time_font_indices = selected if selected else 'all'
        
        # به‌روزرسانی کیبورد منوی فونت
        await query.message.edit_text(
            "🎨 انتخاب فونت‌های تایم\n\nکلیک کنید تا انتخاب/حذف شوند.\nاگر هیچ فونتی انتخاب نشود، همه فونت‌ها به ترتیب چرخش می‌خورند.",
            reply_markup=get_font_menu_keyboard(user_id)
        )
        await msg.delete()
        return
    
    if cmd.startswith('font_all_'):
        # انتخاب همه فونت‌ها
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        manager.time_font_indices = 'all'
        await query.message.edit_text(
            "🎨 انتخاب فونت‌های تایم\n\nکلیک کنید تا انتخاب/حذف شوند.\nاگر هیچ فونتی انتخاب نشود، همه فونت‌ها به ترتیب چرخش می‌خورند.",
            reply_markup=get_font_menu_keyboard(user_id)
        )
        await msg.delete()
        return
    
    if cmd.startswith('font_clear_'):
        # پاک کردن انتخاب‌ها (یعنی همه فونت‌ها)
        db.update_selfbot_setting(user_id, 'time_font_indices', 'all')
        manager.time_font_indices = 'all'
        await query.message.edit_text(
            "🎨 انتخاب فونت‌های تایم\n\nکلیک کنید تا انتخاب/حذف شوند.\nاگر هیچ فونتی انتخاب نشود، همه فونت‌ها به ترتیب چرخش می‌خورند.",
            reply_markup=get_font_menu_keyboard(user_id)
        )
        await msg.delete()
        return
    
    if cmd.startswith('flag_select_'):
        parts_cmd = cmd.split('_')
        try:
            flag_idx = int(parts_cmd[2])
        except:
            await msg.edit_text("⚠️ خطا در انتخاب پرچم")
            return
        
        # ذخیره تنظیمات
        db.update_selfbot_setting(user_id, 'selected_flag_index', flag_idx)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)  # فعال کردن پرچم
        settings = db.get_selfbot_settings(user_id)
        manager.time_font_indices = settings.get('time_font_indices', 'all')
        
        # به‌روزرسانی کیبورد منوی پرچم
        await query.message.edit_text(
            "🏳️ انتخاب پرچم\n\nپرچم انتخاب‌شده در تایم نمایش داده می‌شود.",
            reply_markup=get_flag_menu_keyboard(user_id)
        )
        await msg.delete()
        return
    
    if cmd == 'stats':
        # امار گپ
        await msg.edit_text("📊 در حال دریافت آمار گفتگو...")
        
        target_user_id = None
        
        if query.message.reply_to_message:
            target_user_id = query.message.reply_to_message.from_user.id
            if not target_user_id:
                target_user_id = query.message.reply_to_message.sender_id
        
        if not target_user_id and query.message.chat.type == 'private':
            target_user_id = query.message.chat.id
        
        if not target_user_id:
            await msg.edit_text("⚠️ لطفاً روی پیام کاربر ریپلای کنید یا در پی‌وی از این دستور استفاده کنید")
            return
        
        target_user_id = int(target_user_id)
        
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
📊 آمار گفتگو
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
نوع                {my_name[:15]}        {target_name[:15]}
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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
                await manager.client.send_file(
                    query.message.chat_id,
                    qr_path,
                    caption=f"🝰 کد QR\n📝 متن: {text[:100]}{'...' if len(text) > 100 else ''}"
                )
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
    
    # ========== ادامه دستورات قبلی ==========
    
    # دستورات زمان
    if cmd.startswith('time_on'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.update_profile_name()
        await msg.edit_text("✅ تایم روشن شد")
        await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        return
    
    if cmd.startswith('time_flag'):
        db.update_selfbot_setting(user_id, 'time_enabled', 1)
        db.update_selfbot_setting(user_id, 'flag_enabled', 1)
        await manager.update_profile_name()
        await msg.edit_text("✅ تایمر پرچم روشن شد")
        await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        return
    
    if cmd.startswith('time_off'):
        db.update_selfbot_setting(user_id, 'time_enabled', 0)
        db.update_selfbot_setting(user_id, 'flag_enabled', 0)
        await manager.restore_profile_name()
        await msg.edit_text("✅ تایم خاموش شد")
        await query.message.edit_text(query.message.text, reply_markup=get_time_menu_keyboard(user_id))
        return
    
    if cmd.startswith('full_date'):
        await msg.edit_text(get_full_date_info())
        return
    
    # دستورات ترجمه
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
            await query.message.edit_text(query.message.text, reply_markup=get_translate_menu_keyboard(user_id))
            return
    
    # دستورات انیمیشن
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
    
    # دستورات عمومی
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
    
    if cmd == 'broadcast':
        if user_id != ADMIN_ID:
            await msg.edit_text("⛔ دسترسی غیرمجاز")
            return
        await msg.edit_text("📢 ارسال پیام همگانی\n\nلطفاً پیام خود را به صورت مستقیم برای ربات ارسال کنید.")
        return
    
    if cmd == 'user_stats':
        if user_id != ADMIN_ID:
            await msg.edit_text("⛔ دسترسی غیرمجاز")
            return
        all_users = db.get_all_users()
        active_users = db.get_active_users()
        stats = f"""
📊 آمار کاربران:
━━━━━━━━━━━━━━━━━━━━
👥 کل کاربران ثبت‌نام: {len(all_users)}
✅ کاربران فعال: {len(active_users)}
📋 در انتظار تأیید: {len(db.get_pending_requests())}
🔐 در مرحله ورود: {len(db.get_pending_login())}
🤖 سلف‌بات فعال: {len(selfbot_managers)}
━━━━━━━━━━━━━━━━━━━━
        """
        await msg.edit_text(stats)
        return
    
    # قلب و ماه
    if cmd == 'heart':
        asyncio.create_task(manager.heart_animation(query.message.chat_id))
        await msg.edit_text("❤️ انیمیشن قلب شروع شد")
        return
    
    if cmd == 'moon':
        asyncio.create_task(manager.moon_animation(query.message.chat_id))
        await msg.edit_text("🌙 انیمیشن ماه شروع شد")
        return
    
    # مدیریت کاربران
    if cmd == 'enemy':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور دشمن را ارسال کنید")
        return
    
    if cmd == 'friend':
        await msg.edit_text("⚠️ روی پیام کاربر ریپلای کنید و دستور دوست را ارسال کنید")
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
    
    # لیست دشمن
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
    
    # اسپم
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
    
    # فیلتر
    if cmd == 'filter_word':
        await msg.edit_text("🚫 .فیلتر [کلمه]")
        return
    
    if cmd == 'filter_on':
        db.set_filter_enabled(user_id, True)
        await msg.edit_text("✅ فیلتر کلمات فعال شد")
        return
    
    if cmd == 'filter_off':
        db.set_filter_enabled(user_id, False)
        await msg.edit_text("✅ فیلتر کلمات غیرفعال شد")
        return
    
    if cmd == 'filter_list':
        filters = db.get_filter_words(user_id)
        if filters:
            message_text = "📜 لیست کلمات فیلتر شده:\n\n"
            for i, word_info in enumerate(filters, 1):
                status = "فعال" if word_info['enabled'] else "غیرفعال"
                message_text += f"{i}. {word_info['word']} - {status}\n"
            await msg.edit_text(message_text)
        else:
            await msg.edit_text("📭 لیست کلمات فیلتر خالی است")
        return
    
    if cmd == 'filter_remove':
        await msg.edit_text("🗑️ حذف فیلتر [کلمه]")
        return
    
    # ========== دستورات اسپم ==========
    
    # اسپم روشن
    if cmd == 'spam_protection_on':
        db.set_spam_settings(user_id, spam_protection=1)
        await msg.edit_text("✅ حفاظت اسپم فعال شد")
        return
    
    # اسپم خاموش
    if cmd == 'spam_protection_off':
        db.set_spam_settings(user_id, spam_protection=0)
        await msg.edit_text("✅ حفاظت اسپم غیرفعال شد")
        return
    
    # تنظیم اسپم
    if cmd == 'spam_settings':
        await msg.edit_text("⚙️ تنظیم اسپم [تعداد] [زمان]\nمثال: تنظیم اسپم 5 10")
        return
    
    # وضعیت اسپم
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
    
    # ========== دستورات اتوسین ==========
    
    # فعال کردن اتوسین
    if cmd == 'autosend_on':
        db.update_selfbot_setting(user_id, 'autosend_mode', 1)
        manager.autosend_enabled = True
        await msg.edit_text("✅ اتوسین فعال شد")
        return
    
    # غیرفعال کردن اتوسین
    if cmd == 'autosend_off':
        db.update_selfbot_setting(user_id, 'autosend_mode', 0)
        manager.autosend_enabled = False
        await msg.edit_text("✅ اتوسین غیرفعال شد")
        return
    
    # قفل رسانه
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
            await query.message.edit_text(query.message.text, reply_markup=get_lock_menu_keyboard(user_id))
            return
    
    # استایل متن
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
            await query.message.edit_text(query.message.text, reply_markup=get_style_menu_keyboard(user_id))
            return
    
    # هوش مصنوعی
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
            await query.message.edit_text(query.message.text, reply_markup=get_ai_menu_keyboard(user_id))
            return
    
    # گزارش
    if cmd == 'set_report':
        await msg.edit_text("📍 برای تنظیم گروه گزارش: تنظیم گزارش")
        return
    
    if cmd == 'show_report':
        report_config = manager.report_config
        await msg.edit_text(f"📍 گروه گزارش:\nآیدی: {report_config.report_group_id}")
        return
    
    # دستورات ادمین برای دیتابیس
    if cmd.startswith('admin_get_db'):
        if user_id != ADMIN_ID:
            await msg.edit_text("⛔ دسترسی غیرمجاز")
            return
        
        await msg.edit_text("📥 در حال آماده‌سازی دیتابیس...")
        
        # لیست فایل‌های دیتابیس
        db_files = ['main_database.db', REPORT_CONFIG_FILE]
        sent_count = 0
        
        for file_name in db_files:
            if os.path.exists(file_name):
                try:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=open(file_name, 'rb'),
                        caption=f"📄 {file_name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                    sent_count += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"خطا در ارسال {file_name}: {e}")
                    await msg.edit_text(f"⚠️ خطا در ارسال {file_name}")
        
        if sent_count == 0:
            await msg.edit_text("⚠️ هیچ فایل دیتابیسی یافت نشد")
        else:
            await msg.edit_text(f"✅ {sent_count} فایل دیتابیس ارسال شد")
        return
    
    if cmd.startswith('admin_upload_db'):
        if user_id != ADMIN_ID:
            await msg.edit_text("⛔ دسترسی غیرمجاز")
            return
        
        context.user_data['upload_db_mode'] = True
        await msg.edit_text(
            "📤 لطفاً فایل دیتابیس (main_database.db) را ارسال کنید.\n\n"
            "⚠️ توجه: این کار باعث بازنشانی کامل دیتابیس و ری‌استارت همه سلف‌بات‌ها می‌شود.\n"
            "برای لغو: /cancel"
        )
        return
    
    # سایر دستورات
    if cmd in ['comment', 'channels', 'delete_channel', 'test_channel', 
               'info', 'download_profile', 'set_profile', 'set_bio', 
               'delete_profile', 'delete_bio', 'change_name', 'change_bio', 
               'change_profile', 'change_profile_alt', 'spam', 'reaction', 'reaction_off',
               'delete_all', 'delete_50', 'delete_10', 'autosend_on', 'autosend_off',
               'action', 'action_off', 'action_list', 'dice_1', 'dice_2', 'dice_3',
               'dice_4', 'dice_5', 'dice_6', 'dart', 'basketball', 'football',
               'search_on', 'search_off']:
        await msg.edit_text(f"✅ دستور {cmd} اجرا شد")
        return
    
    # دستورات ناشناخته
    await msg.edit_text(f"✅ دستور {cmd} اجرا شد")

# ========== توابع شروع و عضویت ==========

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
        
        keyboard = [
            [InlineKeyboardButton("📊 وضعیت عضویت", callback_data=f"membership_status_{user_id}")]
        ]
        
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
        [
            InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{user_id_str}"),
            InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id_str}")
        ]
    ])
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_text,
        reply_markup=keyboard
    )
    
    await query.edit_message_text(
        "✅ درخواست عضویت شما ثبت شد!\n\n"
        "⏳ منتظر تأیید ادمین باشید"
    )

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.effective_user.id
    user_id_str = str(user_id)
    text = update.message.text

    text = convert_persian_to_english(text)
    
    # بررسی حالت broadcast
    if context.user_data.get('broadcast_mode') and user_id == ADMIN_ID:
        await handle_broadcast_message(update, context)
        return
    
    # بررسی حالت آپلود دیتابیس
    if context.user_data.get('upload_db_mode') and user_id == ADMIN_ID:
        if text.lower() == '/cancel':
            context.user_data['upload_db_mode'] = False
            await update.message.reply_text("✅ آپلود دیتابیس لغو شد")
            return
        
        # اگر فایل ارسال شده باشد، در بخش فایل‌ها مدیریت می‌شود
        # اینجا فقط متن را مدیریت می‌کنیم
        await update.message.reply_text("⚠️ لطفاً فایل دیتابیس (main_database.db) را ارسال کنید.")
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
            await update.message.reply_text("✅ سلف‌بات در حال اجراست")
        
        return

    step = user_data.get('step')
    
    if step == 'get_phone':
        if not user_data.get('admin_approved'):
            await update.message.reply_text("⏳ درخواست شما تأیید نشده است")
            return
        
        db.update_user(user_id_str, phone=text, step='get_code')
        
        await update.message.reply_text(
            f"✅ شماره {text} ذخیره شد\n"
            "⏳ در حال ارسال کد..."
        )
        
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
            
            await update.message.reply_text(
                "✅ کد تأیید ارسال شد!\n\n"
                "📩 کد ۵ رقمی را وارد کنید:"
            )
            
            await client.disconnect()
            
        except TelethonFloodWaitError as e:
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
            
            await client.sign_in(
                phone=user_data['phone'],
                code=code_for_telegram,
                phone_code_hash=user_data['phone_code_hash']
            )
            
            expiration_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            
            db.update_user(user_id_str,
                          self_active=1,
                          session_file=session_path,
                          expiration_date=expiration_date,
                          step=None)
            
            await update.message.reply_text(
                f"🎉 عضویت کامل شد!\n\n"
                f"✅ اکانت فعال شد\n"
                f"📅 انقضا: {expiration_date}"
            )
            
            await client.disconnect()
            
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_path):
                selfbot_managers[user_id_str] = manager
                await update.message.reply_text("🚀 سلف‌بات فعال شد")
            
            admin_message = (
                f"✅ کاربر {user_data['full_name']} وارد شد\n"
                f"🆔 {user_id_str}\n"
                f"📞 {user_data['phone']}\n"
                f"🔑 API: {user_data.get('api_id', 'نامشخص')}"
            )
            
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
            
            db.update_user(user_id_str,
                          self_active=1,
                          session_file=session_path,
                          expiration_date=expiration_date,
                          step=None)
            
            await update.message.reply_text(
                f"🎉 عضویت کامل شد!\n\n"
                f"✅ اکانت فعال شد\n"
                f"📅 انقضا: {expiration_date}"
            )
            
            await client.disconnect()
            
            manager = SelfBotManager(user_id_str)
            if await manager.start(session_path):
                selfbot_managers[user_id_str] = manager
                await update.message.reply_text("🚀 سلف‌بات فعال شد")
            
            admin_message = (
                f"✅ کاربر {user_data['full_name']} وارد شد\n"
                f"🆔 {user_id_str}\n"
                f"📞 {user_data['phone']}\n"
                f"🔐 رمز: ✓\n"
                f"🔑 API: {user_data.get('api_id', 'نامشخص')}"
            )
            
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

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر برای دریافت فایل دیتابیس از ادمین"""
    if not update.message or not update.message.document:
        return
    
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ دسترسی غیرمجاز")
        return
    
    if not context.user_data.get('upload_db_mode'):
        return
    
    document = update.message.document
    file_name = document.file_name
    
    if not file_name.endswith('.db'):
        await update.message.reply_text("⚠️ لطفاً فایل دیتابیس با پسوند .db ارسال کنید.")
        return
    
    await update.message.reply_text("⏳ در حال دریافت و پردازش فایل...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        temp_path = f"temp_{file_name}"
        await file.download_to_drive(temp_path)
        
        # بررسی اینکه فایل دیتابیس معتبر است
        try:
            conn = sqlite3.connect(temp_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                await update.message.reply_text("❌ فایل دیتابیس معتبر نیست (جدول users یافت نشد)")
                os.remove(temp_path)
                return
            conn.close()
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در بررسی دیتابیس: {e}")
            os.remove(temp_path)
            return
        
        # پشتیبان‌گیری از دیتابیس فعلی
        backup_path = f"main_database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        if os.path.exists('main_database.db'):
            os.rename('main_database.db', backup_path)
            await update.message.reply_text(f"✅ پشتیبان از دیتابیس فعلی گرفته شد: {backup_path}")
        
        # جایگزینی با فایل جدید
        os.rename(temp_path, 'main_database.db')
        
        # ری‌استارت همه سلف‌بات‌ها
        await update.message.reply_text("🔄 در حال ری‌استارت سلف‌بات‌ها...")
        
        # توقف همه
        for uid, manager in list(selfbot_managers.items()):
            await manager.stop()
        selfbot_managers.clear()
        
        # راه‌اندازی مجدد سلف‌بات‌های فعال از دیتابیس جدید
        active_users = db.get_active_users()
        success_count = 0
        for user in active_users:
            user_id_str = user['user_id']
            session_file = user.get('session_file')
            if session_file and os.path.exists(session_file):
                manager = SelfBotManager(user_id_str)
                if await manager.start(session_file):
                    selfbot_managers[user_id_str] = manager
                    success_count += 1
        
        await update.message.reply_text(
            f"✅ دیتابیس با موفقیت آپلود و جایگزین شد.\n"
            f"🔁 {success_count} سلف‌بات راه‌اندازی مجدد شدند."
        )
        
        context.user_data['upload_db_mode'] = False
        
    except Exception as e:
        logger.error(f"خطا در آپلود دیتابیس: {e}")
        await update.message.reply_text(f"❌ خطا در آپلود دیتابیس: {str(e)[:100]}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

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
            await context.bot.send_message(
                chat_id=int(user['user_id']),
                text=f"📢 **پیام همگانی**\n━━━━━━━━━━━━━━━━━━━━\n\n{message_text}\n\n━━━━━━━━━━━━━━━━━━━━\n🕐 {datetime.now().strftime('%Y/%m/%d %H:%M')}",
                parse_mode='Markdown'
            )
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

# ========== توابع دکمه‌ها ==========

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    data = query.data
    user_id = query.from_user.id
    user_id_str = str(user_id)
    
    # بررسی مالکیت پنل
    if '_' in data and not data.startswith(('admin_', 'approve_', 'reject_', 'stop_selfbot_', 'restart_selfbot_', 'desc_', 'menu_')):
        parts = data.split('_')
        for part in parts:
            if part.isdigit() and len(part) >= 5:
                if part != user_id_str:
                    await query.answer("⛔ این پنل مال شما نیست", show_alert=True)
                    return
                break
    
    # بستن پنل
    if data.startswith("close_panel_"):
        await query.answer("❌ بستن پنل")
        try:
            await query.message.delete()
        except:
            await query.edit_message_text("✅ پنل بسته شد")
        return
    
    if data == "back_main":
        await query.edit_message_text(
            "🌟 پنل مدیریت سلف‌بات\n\n⚠️ توجه: این پنل فقط مخصوص شماست\n\n✅ سلف‌بات به صورت ۲۴ ساعته فعال می‌ماند",
            reply_markup=get_main_panel_keyboard(user_id)
        )
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
    
    # منوها
    parts = data.split('_')
    if len(parts) > 1:
        action = parts[0]
        
        menu_keyboards = {
            "time": ("⚈ دستورات زمان و پروفایل\n\n• تایم روشن\n• تایمر پرچم روشن\n• تایم خاموش\n• تایم [اعداد]\n• تاریخ کامل", get_time_menu_keyboard),
            "animation": ("☻ انیمیشن‌ها\n\n• قلب\n• ماه\n• قلب پیشرفته\n• عشق\n• سنتت\n• هک", get_animation_menu_keyboard),
            "user": ("☗ مدیریت کاربران\n\n• دشمن (ریپلای)\n• دوست (ریپلای)\n• قفل پیوی (ریپلای)\n• باز پی (ریپلای)\n• قفل پیوی همه\n• باز پی همه\n• بلاک", get_user_menu_keyboard),
            "lock": ("⊖ قفل رسانه (با ریپلای برای کاربر خاص)\n\n• قفل لینک\n• قفل عکس\n• قفل ویدیو\n• قفل استیکر\n• قفل گیف\n• قفل ویس\n• قفل فایل\n• قفل موزیک\n• قفل ویدیو نوت\n• قفل کانتکت\n• قفل لوکیشن\n• قفل ایموجی\n• قفل متن", get_lock_menu_keyboard),
            "comment": ("✼ کامنت خودکار\n\n• کامنت [متن]\n• کانال‌ها\n• حذف کانال\n• تست کانال", get_comment_menu_keyboard),
            "general": ("✿ دستورات عمومی\n\n• وضعیت\n• درباره\n• پینگ", get_general_menu_keyboard),
            "action": ("☥ اکشن‌ها\n\n• اکشن [نام]\n• اکشن خاموش\n• اکشن لیست\n\nلیست اکشن‌ها:\n• تایپ\n• ویس\n• ویدیو\n• عکس\n• فیلم\n• فایل\n• بازی\n• استیکر\n• موقعیت\n• تماس\n• صحبت\n• لغو", get_action_menu_keyboard),
            "games": ("⚕ بازی‌ها\n\n• تاس [1-6]\n• دارت\n• بسکتبال\n• فوتبال", get_games_menu_keyboard),
            "translate": ("❍ ترجمه خودکار\n\n• انگلیسی روشن/خاموش\n• عربی روشن/خاموش\n• عبری روشن/خاموش\n• روسی روشن/خاموش\n• ترکی روشن/خاموش", get_translate_menu_keyboard),
            "google": ("𖢅 گوگل و اهنگ\n\n• سرچ [موضوع]\n• خروج جستجو\n• .اهنگ [نام آهنگ]", get_google_menu_keyboard),
            "info": ("֍ دستورات اطلاعاتی\n\n• اطلاعات (ریپلای)\n• دانلود پروفایل (ریپلای)", get_info_menu_keyboard),
            "profile": ("𖢨 مدیریت پروفایل\n\n• ست پروف (ریپلای)\n• ست بیو (ریپلای)\n• حذف ست پروف\n• حذف ست بیو", get_profile_menu_keyboard),
            "style": ("⩐ استایل متن\n\n• بولد\n• زیرخط\n• خط خورده\n• نقل قول\n• اسپویلر\n• کج\n• کد\n• پیش", get_style_menu_keyboard),
            "message": ("𑪡 مدیریت پیام\n\n• حذف کامل\n• حذف کامل ۵۰\n• حذف ۱۰\n• فعال اتوسین\n• غیرفعال اتوسین", get_message_menu_keyboard),
            "reaction": ("☖ ریکشن خودکار\n\n• ریکت [ایموجی] (ریپلای)\n• حذف ریکت (ریپلای)", get_reaction_menu_keyboard),
            "spam": ("𖥞 ارسال اسپم\n\n• اسپم [تعداد] [متن]", get_spam_menu_keyboard),
            "change": ("☗ تغییر پروفایل\n\n• تغییر اسم [نام]\n• تغییر بیو [متن]\n• تغییر پروفایل (ریپلای)\n• پروف (ریپلای)", get_change_menu_keyboard),
            "enemy": ("⚇ مدیریت دشمنان\n\n• لیست دشمن\n• اضافه اسپم\n• اتمام اسپم\n• لیست اسپم\n• پاک کردن اسپم\n• حذف اسپم [شماره]", get_enemy_menu_keyboard),
            "filter": ("✿ فیلتر کلمات\n\n• .فیلتر [کلمه]\n• فیلتر روشن\n• فیلتر خاموش\n• لیست فیلتر\n• حذف فیلتر [کلمه]", get_filter_menu_keyboard),
            "protection": ("⚉ حفاظت اسپم\n\n• اسپم روشن\n• اسپم خاموش\n• تنظیم اسپم [تعداد] [زمان]\n• وضعیت اسپم", get_protection_menu_keyboard),
            "ai": ("☥ هوش مصنوعی\n\n• پیوی ۱/۲/۳\n• خاموش پیوی\n• گروه ۱/۲/۳\n• خاموش گروه", get_ai_menu_keyboard),
            "report": ("֎ گزارش\n\n• تنظیم گزارش\n• گروه گزارش", get_report_menu_keyboard),
            "broadcast": ("☖ پیام همگانی\n\n• ارسال پیام به همه کاربران\n• مشاهده آمار کاربران", get_broadcast_menu_keyboard),
            "tools": ("🛠 ابزارها\n\n• امار گپ - آمار پیام‌ها در چت\n• کد QR - تولید کد QR از متن یا عکس\n• تگ ادمین - نمایش ادمین‌های گروه\n• پین - پین کردن پیام\n• سلف روشن/خاموش - فعال/غیرفعال کردن سلف‌بات", get_tools_menu_keyboard),
            "font": ("🎨 انتخاب فونت‌های تایم\n\nکلیک کنید تا انتخاب/حذف شوند.\nاگر هیچ فونتی انتخاب نشود، همه فونت‌ها به ترتیب چرخش می‌خورند.", get_font_menu_keyboard),
            "flag": ("🏳️ انتخاب پرچم\n\nپرچم انتخاب‌شده در تایم نمایش داده می‌شود.", get_flag_menu_keyboard)
        }
        
        if action in menu_keyboards and parts[1] == "menu":
            text, keyboard_func = menu_keyboards[action]
            await query.edit_message_text(
                text,
                reply_markup=keyboard_func(user_id)
            )
            return

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
        "📢 ارسال پیام همگانی\n\n"
        "لطفاً پیام خود را ارسال کنید.\n\n"
        "⚠️ توجه: این پیام برای همه کاربران فعال ارسال خواهد شد.\n\n"
        "برای لغو: /cancel"
    )
    
    context.user_data['broadcast_mode'] = True

# ========== تابع اصلی ==========

async def main():
    print("=" * 60)
    print("🤖 سیستم جامع عضویت و سلف‌بات")
    print(f"👑 ادمین: {ADMIN_ID}")
    print(f"📁 پوشه سشن‌ها: {SESSIONS_FOLDER}")
    print("=" * 60)
    
    # بررسی فایل‌های سشن
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
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, timeout=30)
    
    print("✅ ربات شروع شد")
    print("=" * 60)
    
    # راه‌اندازی سلف‌بات‌های فعال
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
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 ربات متوقف شد")
    except Exception as e:
        logger.error(f"❌ خطای fatal: {e}")
[file content end]
