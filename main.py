import os
import re
import html
import time
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from flask import Flask
import requests
import telebot
from telebot.apihelper import ApiTelegramException
from groq import Groq
from google import genai
from google.genai import types

# ==========================================
# ۱. وب‌سرور سبک برای زنده نگه‌داشتن سرویس در رندر
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Personal AI Assistant (Telegram + Bale) is Online & Active!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ==========================================
# ۲. کلیدها و پیکربندی متغیرها
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

MODEL_FAST = "qwen/qwen3.8-27b"
MODEL_SMART = "openai/gpt-oss-120b"
MODEL_GEMINI = "gemini-3.5-flash-lite"

# سقف توکن خروجی در حالت بلند (Groq)
LONG_MODE_MAX_TOKENS = 4096

# سقف کاراکتر هر پیام (محدودیت واقعی تلگرام و بله ۴۰۹۶ است؛
# در تلگرام حاشیه بیشتری می‌گذاریم چون تگ‌های HTML هم به طول پیام اضافه می‌شوند)
TG_CHUNK_SIZE = 3500
BALE_CHUNK_SIZE = 3800

# متغیرهای وضعیت تلگرام
chat_memory = {}
memory_status = {}
user_model = {}
exam_mode_status = {}
long_mode_status = {}

# متغیرهای وضعیت بله
bale_chat_memory = {}
bale_memory_status = {}
bale_user_model = {}
bale_exam_status = {}
bale_long_status = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ==========================================
# ۳. پرامپت‌ها و راهنما
# ==========================================
BASE_SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، متصل به اینترنت، باهوش و بسیار صریح هستی.

قوانین کاری:
۱. اگر اطلاعات زنده وب در اختیارت قرار گرفت، مستقیماً به آن استناد کن و آخرین فکت‌ها، قیمت‌ها و اخبار را بگو.
۲. اگر اطلاعات وب ضمیمه نشده بود، با دانش درونی خودت پاسخ بده اما برای افراد و حوادث روز حدس نزن.
۳. تحت هیچ شرایطی جملاتی مثل "در نتایج وب یافت نشد" را تکرار نکن؛ کاملاً طبیعی و مثل یک انسان مطلع جواب بده.
۴. استفاده از فرمت LaTeX و علامت دلار ($) اکیداً ممنوع است؛ تمام فرمول‌ها و اعداد را به صورت متن ساده بنویس.
۵. زبان پیش‌فرض فارسی سلیس است.
"""

EXAM_SYSTEM_PROMPT = """
دستورالعمل آزمون زبان انگلیسی (Autonomous English Exam Protocol):
پاسخ قطعی، بدون معطلی و تک‌گزینه‌ای برای پر کردن پاسخ‌نامه.
قالب سطر آخر (اجباری): RESULT: [Correct Word] -> [Option Letter]
"""

LONG_SYSTEM_PROMPT = """
دستور مهم: پاسخ را با نهایت جزئیات بنویس. اگر کد برنامه‌نویسی است، تمام فایل‌ها و خطوط را بدون خلاصه کردن یا حذف توابع به صورت کامل ارائه بده.
"""

HELP_TEXT = """
🤖 <b>راهنمای دستیار شخصی:</b>

<b>موتورهای هوش مصنوعی:</b>
• /fast : فوق‌سریع Qwen
• /smart : فوق‌هوشمند 120B
• /gemini : مدل Gemini متصل به وب زنده

<b>حالت آزمون زبان:</b>
• /exam_on : فعال‌سازی حل سریع و تک‌گزینه‌ای تست
• /exam_off : غیرفعال‌سازی حالت آزمون

<b>حالت خروجی بلند (کدنویسی و تحلیل مفصل):</b>
• /long_on : پاسخ کامل و بدون خلاصه‌سازی (تا ۴۰۹۶ توکن، ارسال خودکار در چند پیام)
• /long_off : بازگشت به پاسخ‌های کوتاه و سریع

<b>ابزارهای وب:</b>
• <code>/web متن</code> : استعلام فوری از وب
• <code>/testweb عبارت</code> : تست خروجی خام موتور جستجو

<b>مدیریت حافظه:</b>
• /memory_on : فعال‌سازی حافظه
• /memory_off : غیرفعال‌سازی حافظه
• /clear : پاکسازی سابقه مکالمه
"""

# ==========================================
# ۴. توابع جستجوی وب
# ==========================================
def should_search_web(text):
    clean = text.strip().lower()
    explicit = ['سرچ کن', 'جستجو کن', 'گوگل کن', 'بگرد', 'پیدا کن', 'توی نت ببین', 'تو نت ببین', 'search', 'سرچ', 'جستجو']
    if any(cmd in clean for cmd in explicit):
        return True

    greetings = ['سلام', 'درود', 'خوبی', 'چطوری', 'چه خبر', 'مرسی', 'ممنون', 'تشکر', 'دمت گرم', 'صبح بخیر', 'شب بخیر', 'hi', 'hello', 'hey', 'thanks', 'اوکی', 'باشه']
    if clean in greetings or len(clean) < 4:
        return False

    triggers = ['قیمت', 'نرخ', 'دلار', 'ارز', 'طلا', 'سکه', 'بورس', 'تومان', 'بیت‌کوین', 'اخبار', 'خبر', 'آخرین', 'جدیدترین', 'امروز', 'الان', 'کیه', 'کیست', 'کجاست', 'وضعیت', 'سلامت', 'بیمارستان', 'تصادف', 'فوت', 'چند سالشه']
    return any(word in clean for word in triggers)

def clean_query_for_search(text):
    cleaned = re.sub(r'[؟?!\.,]', '', text)
    remove_words = ['سرچ کن ببین', 'لطفا سرچ کن', 'سرچ کن', 'جستجو کن', 'گوگل کن', 'بگرد', 'سرچ', 'جستجو', 'چیشده', 'چی شده', 'کیه', 'کیست', 'کجاست', 'چه خبر']
    for word in remove_words:
        cleaned = cleaned.replace(word, '')
    return cleaned.strip() or text

def fetch_web_context(query):
    search_term = clean_query_for_search(query)
    snippets = []

    if TAVILY_API_KEY:
        try:
            res = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": search_term, "search_depth": "basic", "max_results": 4},
                timeout=7
            )
            if res.status_code == 200:
                data = res.json()
                if "answer" in data and data["answer"]:
                    snippets.append(f"• پاسخ سریع: {data['answer']}")
                for r in data.get("results", []):
                    snippets.append(f"• {r.get('title', '')}: {r.get('content', '')}")
                if snippets:
                    return "\n".join(snippets)
        except Exception as e:
            print(f"Tavily Error: {e}")

    try:
        encoded = urllib.parse.quote(search_term)
        rss_url = f"https://news.google.com/rss/search?q={encoded}&hl=fa&gl=IR&ceid=IR:fa"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"}
        resp = requests.get(rss_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall('./channel/item')[:3]:
                title = item.find('title').text if item.find('title') is not None else ""
                snippets.append(f"• خبر: {title}")
    except Exception as e:
        print(f"Google News RSS Error: {e}")

    return "\n".join(snippets)

# ==========================================
# ۵. موتور پردازشگر مرکزی هوش مصنوعی (همراه با حالت آزمون و خروجی بلند)
# ==========================================
def process_ai_query(user_text, model_name=MODEL_FAST, use_memory=False, history_list=None, is_exam=False, is_long=False):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    sys_prompt = BASE_SYSTEM_PROMPT
    if is_exam:
        sys_prompt += f"\n\n{EXAM_SYSTEM_PROMPT}"
    elif is_long:
        sys_prompt += f"\n{LONG_SYSTEM_PROMPT}"
    sys_prompt += f"\nزمان فعلی سرور: {current_time}"

    # اگر مدل روی جمینای تنظیم شده باشد
    if model_name == MODEL_GEMINI and gemini_client:
        web_info = ""
        if not is_exam and should_search_web(user_text):
            web_info = fetch_web_context(user_text)

        enriched = f"{user_text}\n\n[داده‌های زنده وب]:\n{web_info}" if web_info else user_text

        contents = []
        if use_memory and history_list and not is_exam:
            for item in history_list:
                role = "user" if item["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": item["content"]}]})
            contents.append({"role": "user", "parts": [{"text": enriched}]})
        else:
            contents = [{"role": "user", "parts": [{"text": enriched}]}]

        resp = gemini_client.models.generate_content(
            model=MODEL_GEMINI,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=sys_prompt,
                temperature=0.1 if (is_exam or is_long) else 0.2
            )
        )
        return resp.text.strip()

    # حالت مدل‌های Groq
    if groq_client:
        if is_exam:
            max_tok = 300
        elif is_long:
            max_tok = LONG_MODE_MAX_TOKENS  # سقف آزاد برای کدهای بلند
        else:
            max_tok = 1500 if model_name == MODEL_SMART else 800

        if use_memory and history_list and not is_exam:
            messages = [{"role": "system", "content": sys_prompt}] + history_list + [{"role": "user", "content": user_text}]
        else:
            messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_text}]

        resp = groq_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1 if (is_exam or is_long) else 0.2,
            max_tokens=max_tok
        )
        return resp.choices[0].message.content.strip()

    return "سرویس‌های هوش مصنوعی پیکربندی نشده‌اند."

# ==========================================
# ۶. توابع کمکی ارسال چندتکه‌ای (Auto-Chunking)
# ==========================================
def split_message(text, limit=TG_CHUNK_SIZE):
    """
    متن بلند را روی مرز خطوط به تکه‌هایی کوتاه‌تر از limit می‌شکند.
    اگر برش وسط یک بلاک کد (```) بیفتد، بلاک در همان تکه بسته و در تکه بعدی دوباره باز می‌شود
    تا فرمت کد خراب نشود.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return [text]

    reserve = 10                      # فضای لازم برای بستن بلاک کد
    max_piece = limit - 2 * reserve   # حداکثر طول یک خط (خط‌های خیلی بلند هم شکسته می‌شوند)
    chunks, current, current_len, in_code = [], [], 0, False

    for line in text.split("\n"):
        pieces = [line[i:i + max_piece] for i in range(0, len(line), max_piece)] or [""]
        for piece in pieces:
            if current and current_len + len(piece) + 1 > limit - reserve:
                body = "\n".join(current)
                chunks.append(body + "\n```" if in_code else body)
                current = ["```"] if in_code else []
                current_len = 4 if in_code else 0
            current.append(piece)
            current_len += len(piece) + 1
        if line.count("```") % 2 == 1:
            in_code = not in_code

    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c.strip()]

def to_telegram_html(text, escape=False):
    """
    مارک‌داون ساده (**bold**، `code`، ```pre```) را به HTML تلگرام تبدیل می‌کند.
    escape=True برای خروجی هوش مصنوعی: کاراکترهای < > & خنثی می‌شوند تا کدها پیام را خراب نکنند.
    بلاک‌های کد قبل از bold جدا می‌شوند تا ** داخل کد (مثل **kwargs) تبدیل نشود.
    """
    if escape:
        text = html.escape(text, quote=False)
    stash = []

    def keep(template):
        def _inner(m):
            stash.append(template.format(m.group(1)))
            return f"\x00{len(stash) - 1}\x00"
        return _inner

    text = re.sub(r'```[\w+#.-]*\n(.*?)```', keep("<pre>{}</pre>"), text, flags=re.DOTALL)
    text = re.sub(r'```(.*?)```', keep("<pre>{}</pre>"), text, flags=re.DOTALL)
    text = re.sub(r'`([^`\n]+)`', keep("<code>{}</code>"), text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    return re.sub(r'\x00(\d+)\x00', lambda m: stash[int(m.group(1))], text)

# ==========================================
# ۷. بخش پلتفرم تلگرام
# ==========================================
def _tg_send(message, text, first, **kwargs):
    # تکه اول به‌صورت ریپلای، بقیه به‌صورت پیام معمولی
    if first:
        return bot.reply_to(message, text, **kwargs)
    return bot.send_message(message.chat.id, text, **kwargs)

def reply_formatted(message, text, escape=False):
    if not text or not text.strip():
        bot.reply_to(message, "پاسخی دریافت نشد.")
        return

    chunks = split_message(text, TG_CHUNK_SIZE)
    for index, chunk in enumerate(chunks):
        formatted = to_telegram_html(chunk, escape=escape)
        try:
            _tg_send(message, formatted, index == 0, parse_mode='HTML')
        except ApiTelegramException:
            try:
                _tg_send(message, chunk, index == 0)
            except ApiTelegramException as e:
                print(f"Telegram send error: {e}")
        if index < len(chunks) - 1:
            time.sleep(0.4)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return
    chat_id = message.chat.id
    chat_memory.setdefault(chat_id, [])
    memory_status.setdefault(chat_id, True)
    user_model.setdefault(chat_id, MODEL_FAST)
    exam_mode_status.setdefault(chat_id, False)
    long_mode_status.setdefault(chat_id, False)

    mem_state = "✅ روشن" if memory_status[chat_id] else "❌ خاموش"
    exam_state = "🎯 فعال" if exam_mode_status[chat_id] else "⚪️ غیرفعال"
    long_state = "📜 فعال" if long_mode_status[chat_id] else "⚪️ غیرفعال"

    welcome_text = (
        f"سلام! دستیار هوش مصنوعی در تلگرام آماده است.\n\n"
        f"⚙️ <b>موتور فعال:</b> <code>{user_model[chat_id]}</code>\n"
        f"💾 <b>وضعیت حافظه:</b> {mem_state}\n"
        f"🎯 <b>حالت آزمون:</b> {exam_state}\n"
        f"📜 <b>خروجی بلند:</b> {long_state}\n\n"
        f"<b>دستورات:</b>\n"
        f"• /fast : فوق‌سریع Qwen\n"
        f"• /smart : فوق‌هوشمند (120B)\n"
        f"• /gemini : مدل Gemini متصل به وب\n"
        f"• /exam_on : فعال‌سازی حل آزمون زبان\n"
        f"• /exam_off : غیرفعال‌سازی آزمون زبان\n"
        f"• /long_on : فعال‌سازی خروجی بلند (کدنویسی کامل)\n"
        f"• /long_off : غیرفعال‌سازی خروجی بلند\n"
        f"• /memory_on : روشن کردن حافظه\n"
        f"• /memory_off : خاموش کردن حافظه\n"
        f"• /clear : پاکسازی سابقه مکالمه"
    )
    reply_formatted(message, welcome_text)

@bot.message_handler(commands=['help'])
def send_help(message):
    if not is_authorized(message.from_user.id):
        return
    reply_formatted(message, HELP_TEXT)

@bot.message_handler(commands=['fast'])
def switch_fast(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_FAST
    reply_formatted(message, "⚡️ <b>مدل فوق‌سریع Qwen فعال شد.</b>")

@bot.message_handler(commands=['smart'])
def switch_smart(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_SMART
    reply_formatted(message, "🧠 <b>مدل فوق‌هوشمند (120B) فعال شد.</b>")

@bot.message_handler(commands=['gemini'])
def switch_gemini(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_GEMINI
    reply_formatted(message, "🌐 <b>مدل Gemini متصل به وب فعال شد.</b>")

@bot.message_handler(commands=['exam_on'])
def enable_exam_tg(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = True
    reply_formatted(message, "🎯 <b>حالت آزمون زبان در تلگرام فعال شد.</b> پاسخ‌ها تک‌گزینه‌ای خواهند بود.")

@bot.message_handler(commands=['exam_off'])
def disable_exam_tg(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = False
    reply_formatted(message, "⚪️ <b>حالت آزمون زبان غیرفعال شد.</b>")

@bot.message_handler(commands=['long_on'])
def enable_long_tg(message):
    if not is_authorized(message.from_user.id):
        return
    long_mode_status[message.chat.id] = True
    reply_formatted(message, "📜 <b>حالت خروجی بلند و بدون محدودیت فعال شد.</b> (مناسب برنامه‌نویسی کامل)")

@bot.message_handler(commands=['long_off'])
def disable_long_tg(message):
    if not is_authorized(message.from_user.id):
        return
    long_mode_status[message.chat.id] = False
    reply_formatted(message, "⚪️ <b>حالت خروجی بلند غیرفعال شد.</b>")

@bot.message_handler(commands=['memory_on'])
def enable_mem_tg(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = True
    reply_formatted(message, "✅ حافظه فعال شد.")

@bot.message_handler(commands=['memory_off'])
def disable_mem_tg(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    reply_formatted(message, "❌ حافظه غیرفعال شد.")

@bot.message_handler(commands=['clear'])
def clear_history(message):
    if not is_authorized(message.from_user.id):
        return
    chat_memory[message.chat.id] = []
    reply_formatted(message, "حافظه مکالمه پاک شد.")

@bot.message_handler(commands=['testweb'])
def test_web(message):
    if not is_authorized(message.from_user.id):
        return
    query = message.text.replace('/testweb', '').strip() or "قیمت دلار"
    bot.send_chat_action(message.chat.id, 'typing')
    data = fetch_web_context(query)
    if data:
        safe_data = html.escape(data[:2000], quote=False)
        reply_formatted(message, f"🔍 <b>داده‌های وب:</b>\n\n{safe_data}")
    else:
        reply_formatted(message, "❌ موتور وب‌سرچ پاسخی برنگرداند.")

@bot.message_handler(commands=['web', 'search'])
def handle_quick_search(message):
    if not is_authorized(message.from_user.id):
        return
    query = message.text.replace('/web', '').replace('/search', '').strip()
    if not query:
        reply_formatted(message, "لطفاً عبارت مد نظر را بنویسید.")
        return

    bot.send_chat_action(message.chat.id, 'typing')
    web_data = fetch_web_context(query)
    prompt = f"پرسش کاربر: {query}\n\n[داده‌های زنده وب]:\n{web_data}" if web_data else query

    try:
        response = gemini_client.models.generate_content(
            model=MODEL_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=BASE_SYSTEM_PROMPT, temperature=0.2)
        )
        reply_formatted(message, response.text, escape=True)
    except Exception as e:
        reply_formatted(message, f"خطا: {e}", escape=True)

@bot.message_handler(func=lambda message: True)
def handle_telegram_chat(message):
    if not is_authorized(message.from_user.id):
        return
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')
    selected_model = user_model.get(chat_id, MODEL_FAST)
    is_mem = memory_status.get(chat_id, True)
    is_exam = exam_mode_status.get(chat_id, False)
    is_long = long_mode_status.get(chat_id, False)
    history = chat_memory.get(chat_id, [])

    try:
        ans = process_ai_query(
            message.text,
            model_name=selected_model,
            use_memory=is_mem,
            history_list=history,
            is_exam=is_exam,
            is_long=is_long
        )
        if is_mem and not is_exam:
            if chat_id not in chat_memory:
                chat_memory[chat_id] = []
            chat_memory[chat_id].append({"role": "user", "content": message.text})
            chat_memory[chat_id].append({"role": "assistant", "content": ans})
            if len(chat_memory[chat_id]) > 10:
                chat_memory[chat_id] = chat_memory[chat_id][-10:]
        reply_formatted(message, ans, escape=True)
    except Exception as e:
        reply_formatted(message, f"خطا در پردازش: {e}", escape=True)

# ==========================================
# ۸. بخش پلتفرم پیام‌رسان بله
# ==========================================
def bale_send(base_url, chat_id, text):
    """ارسال پیام در بله؛ پیام‌های بلند خودکار به چند پیام پشت‌سرهم شکسته می‌شوند."""
    if not text or not text.strip():
        text = "پاسخی دریافت نشد."
    chunks = split_message(text, BALE_CHUNK_SIZE)
    for index, chunk in enumerate(chunks):
        try:
            requests.post(f"{base_url}/sendMessage", json={"chat_id": chat_id, "text": chunk}, timeout=10)
        except Exception as e:
            print(f"Bale send error: {e}")
        if index < len(chunks) - 1:
            time.sleep(0.4)

def run_bale_listener():
    if not BALE_BOT_TOKEN:
        print("BALE_BOT_TOKEN is not provided. Bale listener disabled.")
        return

    base_bale_url = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}"
    try:
        requests.get(f"{base_bale_url}/deleteWebhook", timeout=8)
    except Exception:
        pass

    offset = 0
    print("Bale bot background listener started...")

    while True:
        try:
            resp = requests.get(
                f"{base_bale_url}/getUpdates",
                params={"offset": offset, "timeout": 12},
                timeout=18
            )
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    from_user_id = msg.get("from", {}).get("id", chat_id)
                    user_text = msg.get("text", "").strip()

                    if not chat_id or not user_text:
                        continue

                    # بررسی دسترسی کاربر
                    if ALLOWED_USERS and (from_user_id not in ALLOWED_USERS and chat_id not in ALLOWED_USERS):
                        bale_send(base_bale_url, chat_id, f"⛔️ دسترسی غیرمجاز!\nشناسه عددی بله شما: {from_user_id}")
                        continue

                    # پیش‌فرض‌های کاربر بله
                    bale_user_model.setdefault(chat_id, MODEL_FAST)
                    bale_chat_memory.setdefault(chat_id, [])
                    bale_memory_status.setdefault(chat_id, True)
                    bale_exam_status.setdefault(chat_id, False)
                    bale_long_status.setdefault(chat_id, False)

                    # دستورات اختصاصی بله
                    if user_text == '/start':
                        mem_state = "✅ روشن" if bale_memory_status[chat_id] else "❌ خاموش"
                        exam_state = "🎯 فعال" if bale_exam_status[chat_id] else "⚪️ غیرفعال"
                        long_state = "📜 فعال" if bale_long_status[chat_id] else "⚪️ غیرفعال"
                        welcome = (
                            f"سلام! دستیار هوش مصنوعی در بله آماده است.\n"
                            f"موتور فعال: {bale_user_model[chat_id]}\n"
                            f"وضعیت حافظه: {mem_state}\n"
                            f"حالت آزمون: {exam_state}\n"
                            f"خروجی بلند: {long_state}\n\n"
                            f"دستورات:\n"
                            f"• /fast : فوق‌سریع Qwen\n"
                            f"• /smart : فوق‌هوشمند (120B)\n"
                            f"• /gemini : مدل Gemini متصل به وب\n"
                            f"• /exam_on : فعال‌سازی حل آزمون زبان\n"
                            f"• /exam_off : غیرفعال‌سازی آزمون زبان\n"
                            f"• /long_on : فعال‌سازی خروجی بلند (کدنویسی کامل)\n"
                            f"• /long_off : غیرفعال‌سازی خروجی بلند\n"
                            f"• /memory_on : روشن کردن حافظه\n"
                            f"• /memory_off : خاموش کردن حافظه\n"
                            f"• /clear : پاکسازی تاریخچه مکالمه"
                        )
                        bale_send(base_bale_url, chat_id, welcome)
                        continue

                    elif user_text == '/fast':
                        bale_user_model[chat_id] = MODEL_FAST
                        bale_send(base_bale_url, chat_id, "⚡️ مدل فوق‌سریع Qwen فعال شد.")
                        continue

                    elif user_text == '/smart':
                        bale_user_model[chat_id] = MODEL_SMART
                        bale_send(base_bale_url, chat_id, "🧠 مدل فوق‌هوشمند (120B) فعال شد.")
                        continue

                    elif user_text == '/gemini':
                        bale_user_model[chat_id] = MODEL_GEMINI
                        bale_send(base_bale_url, chat_id, "🌐 مدل Gemini متصل به وب فعال شد.")
                        continue

                    elif user_text == '/exam_on':
                        bale_exam_status[chat_id] = True
                        bale_send(base_bale_url, chat_id, "🎯 حالت آزمون زبان فعال شد. پاسخ‌ها تک‌گزینه‌ای خواهند بود.")
                        continue

                    elif user_text == '/exam_off':
                        bale_exam_status[chat_id] = False
                        bale_send(base_bale_url, chat_id, "⚪️ حالت آزمون زبان غیرفعال شد.")
                        continue

                    elif user_text == '/long_on':
                        bale_long_status[chat_id] = True
                        bale_send(base_bale_url, chat_id, "📜 حالت خروجی بلند و بدون محدودیت فعال شد. (مناسب برنامه‌نویسی کامل)")
                        continue

                    elif user_text == '/long_off':
                        bale_long_status[chat_id] = False
                        bale_send(base_bale_url, chat_id, "⚪️ حالت خروجی بلند غیرفعال شد.")
                        continue

                    elif user_text == '/memory_on':
                        bale_memory_status[chat_id] = True
                        bale_send(base_bale_url, chat_id, "✅ حافظه مکالمه در بله روشن شد.")
                        continue

                    elif user_text == '/memory_off':
                        bale_memory_status[chat_id] = False
                        bale_chat_memory[chat_id] = []
                        bale_send(base_bale_url, chat_id, "❌ حافظه خاموش و سابقه گفتگو پاک شد.")
                        continue

                    elif user_text == '/clear':
                        bale_chat_memory[chat_id] = []
                        bale_send(base_bale_url, chat_id, "حافظه مکالمه پاک شد.")
                        continue

                    # پاسخ‌دهی به متن کاربر با لحاظ وضعیت‌های انتخابی
                    current_model = bale_user_model[chat_id]
                    is_mem = bale_memory_status.get(chat_id, True)
                    is_exam = bale_exam_status.get(chat_id, False)
                    is_long = bale_long_status.get(chat_id, False)
                    history = bale_chat_memory[chat_id] if is_mem else []

                    try:
                        answer = process_ai_query(
                            user_text,
                            model_name=current_model,
                            use_memory=is_mem,
                            history_list=history,
                            is_exam=is_exam,
                            is_long=is_long
                        )
                    except Exception as e:
                        bale_send(base_bale_url, chat_id, f"خطا در پردازش: {e}")
                        continue

                    if is_mem and not is_exam:
                        bale_chat_memory[chat_id].append({"role": "user", "content": user_text})
                        bale_chat_memory[chat_id].append({"role": "assistant", "content": answer})
                        if len(bale_chat_memory[chat_id]) > 10:
                            bale_chat_memory[chat_id] = bale_chat_memory[chat_id][-10:]

                    bale_send(base_bale_url, chat_id, answer)

            time.sleep(0.5)
        except Exception as e:
            time.sleep(2)

# اجرای موازی بخش بله در پس‌زمینه
threading.Thread(target=run_bale_listener, daemon=True).start()

# ==========================================
# ۹. اجرای بات تلگرام روی Thread اصلی
# ==========================================
print("ربات دوگانه (تلگرام + بله) با پشتیبانی از حالت آزمون و خروجی بلند فعال شد...")
bot.infinity_polling()
