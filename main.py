import os
import re
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

# ۱. وب‌سرور سبک برای زنده نگه‌داشتن سرویس در رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Personal AI Assistant is Online & Active!"

@app.route('/test-bale')
def test_bale_http():
    token = os.environ.get("BALE_BOT_TOKEN")
    if not token:
        return "BALE_BOT_TOKEN is not set in Render environment variables."
    try:
        res = requests.get(f"https://tapi.bale.ai/bot{token}/getMe", timeout=8)
        return f"Status: {res.status_code}<br>Response: {res.text}"
    except Exception as e:
        return f"Connection to Bale failed: {e}"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی متغیرهای محیطی
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
BALE_BOT_TOKEN = os.environ.get("BALE_BOT_TOKEN")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

MODEL_FAST = "qwen/qwen3.8-27b"
MODEL_SMART = "openai/gpt-oss-120b"
MODEL_GEMINI = "gemini-3.5-flash-lite"

chat_memory = {}
memory_status = {}
user_model = {}
exam_mode_status = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

BASE_SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، متصل به اینترنت، باهوش و بسیار صریح هستی که در تلگرام پاسخ می‌دهی.

قوانین کاری:
۱. اگر اطلاعات زنده وب در اختیارت قرار گرفت، مستقیماً به آن استناد کن و آخرین فکت‌ها، قیمت‌ها و اخبار را بگو.
۲. اگر اطلاعات وب ضمیمه نشده بود، با دانش درونی خودت پاسخ بده اما برای افراد و حوادث روز حدس نزن.
۳. تحت هیچ شرایطی جملاتی مثل "در نتایج وب یافت نشد" یا "بر اساس داده‌های وب" را تکرار نکن؛ کاملاً طبیعی و مثل یک انسان مطلع جواب بده.
۴. استفاده از فرمت LaTeX و علامت دلار ($) اکیداً ممنوع است؛ تمام فرمول‌ها و اعداد را به صورت متن ساده بنویس.
۵. زبان پیش‌فرض فارسی سلیس است.
"""

EXAM_SYSTEM_PROMPT = """
دستورالعمل آزمون زبان انگلیسی (Autonomous English Exam Protocol):
پاسخ قطعی، بدون معطلی و تک‌گزینه‌ای برای پر کردن پاسخ‌نامه.
قالب سطر آخر (اجباری): RESULT: [Correct Word] -> [Option Letter]
"""

HELP_TEXT = """
🤖 <b>راهنمای دستیار شخصی:</b>

<b>موتورهای هوش مصنوعی:</b>
• /fast : فوق‌سریع Qwen
• /smart : فوق‌هوشمند 120B
• /gemini : مدل Gemini متصل به اینترنت زنده

<b>ابزارهای وب و اتصالات:</b>
• <code>/web متن</code> : استعلام فوری از وب
• <code>/testweb عبارت</code> : تست خروجی خام Tavily
• <code>/checkbale</code> : تست وضعیت اتصال سرور رندر به پیام‌رسان بله

<b>مدیریت حافظه:</b>
• /memory_on : فعال‌سازی حافظه
• /memory_off : غیرفعال‌سازی حافظه
• /clear : پاکسازی تاریخچه گفتگو
"""

def should_search_web(text):
    clean = text.strip().lower()
    explicit_search_commands = [
        'سرچ کن', 'جستجو کن', 'گوگل کن', 'بگرد', 'پیدا کن', 'توی نت ببین',
        'تو نت ببین', 'سرچ بزن', 'search', 'سرچ', 'جستجو'
    ]
    if any(cmd in clean for cmd in explicit_search_commands):
        return True

    greetings = [
        'سلام', 'درود', 'خوبی', 'چطوری', 'چه خبر', 'مرسی', 'ممنون', 'تشکر',
        'دمت گرم', 'دستت درد نکنه', 'قربونت', 'فدات', 'خسته نباشی', 'صبح بخیر',
        'شب بخیر', 'عصر بخیر', 'روز بخیر', 'hi', 'hello', 'hey', 'thanks',
        'thx', 'ok', 'اوکی', 'باشه', 'آره', 'نه', 'درسته', 'خوب', 'عالیه',
        'اسمت چیه', 'تو کی هستی', 'کی هستی', 'who are you'
    ]
    if clean in greetings or len(clean) < 4:
        return False

    live_triggers = [
        'قیمت', 'نرخ', 'چنده', 'چند شده', 'دلار', 'یورو', 'ارز', 'طلا', 'سکه',
        'بورس', 'تومان', 'ریال', 'بیت‌کوین', 'بیت کوین', 'اتریوم', 'کریپتو',
        'اخبار', 'خبر', 'آخرین', 'جدیدترین', 'امروز', 'الان', 'دیشب', 'امشب',
        'کیه', 'کیست', 'کجاست', 'وضعیت', 'حالش', 'سلامت', 'بیمارستان', 'تصادف',
        'فوت', 'درگذشت', 'زنده‌ست', 'زنده است', 'چند سالشه', 'متولد'
    ]
    return any(word in clean for word in live_triggers)

def clean_query_for_search(text):
    cleaned = re.sub(r'[؟?!\.,]', '', text)
    remove_words = [
        'سرچ کن ببین', 'لطفا سرچ کن', 'سرچ کن', 'جستجو کن', 'گوگل کن', 'بگرد',
        'سرچ', 'جستجو', 'چیشده', 'چی شده', 'کیه', 'کیست', 'کجاست', 'چیکار کرده',
        'چه خبر از', 'چه خبر', 'حالش چطوره', 'درباره', 'در مورد'
    ]
    for word in remove_words:
        cleaned = cleaned.replace(word, '')
    return cleaned.strip() or text

def fetch_web_context(query):
    search_term = clean_query_for_search(query)
    snippets = []

    if TAVILY_API_KEY:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": TAVILY_API_KEY,
                "query": search_term,
                "search_depth": "basic",
                "max_results": 4
            }
            res = requests.post(url, json=payload, timeout=7)
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
        encoded_query = urllib.parse.quote(search_term)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fa&gl=IR&ceid=IR:fa"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "fa,en;q=0.9"
        }
        resp = requests.get(rss_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall('./channel/item')[:3]:
                title = item.find('title').text if item.find('title') is not None else ""
                desc = item.find('description').text if item.find('description') is not None else ""
                clean_desc = re.sub('<[^<]+?>', '', desc)
                snippets.append(f"• {title}: {clean_desc}")
    except Exception as e:
        print(f"Google News RSS Error: {e}")

    return "\n".join(snippets)

def reply_formatted(message, text):
    if not text or not text.strip():
        bot.reply_to(message, "پاسخی دریافت نشد.")
        return
    clean = text.strip()
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean)
    formatted = re.sub(r'```(.*?)```', r'<pre>\1</pre>', formatted, flags=re.DOTALL)
    formatted = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted)
    try:
        bot.reply_to(message, formatted, parse_mode='HTML')
    except ApiTelegramException:
        bot.reply_to(message, clean)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return
    chat_id = message.chat.id
    chat_memory[chat_id] = []
    memory_status.setdefault(chat_id, True)
    user_model.setdefault(chat_id, MODEL_FAST)
    exam_mode_status.setdefault(chat_id, False)
    reply_formatted(message, f"سلام! دستیار آماده است.\nموتور فعال: <b>{user_model[chat_id]}</b>\n\n" + HELP_TEXT)

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
def enable_exam_mode(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = True
    reply_formatted(message, "🎯 <b>حالت آزمون فعال شد.</b>")

@bot.message_handler(commands=['exam_off'])
def disable_exam_mode(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = False
    reply_formatted(message, "⚪️ <b>حالت آزمون غیرفعال شد.</b>")

@bot.message_handler(commands=['clear'])
def clear_history(message):
    if not is_authorized(message.from_user.id):
        return
    chat_memory[message.chat.id] = []
    reply_formatted(message, "حافظه مکالمه پاک شد.")

@bot.message_handler(commands=['memory_on'])
def enable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = True
    reply_formatted(message, "✅ حافظه فعال شد.")

@bot.message_handler(commands=['memory_off'])
def disable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    reply_formatted(message, "❌ حافظه غیرفعال شد.")

# دستور تست اتصال سرور رندر به بله
@bot.message_handler(commands=['checkbale'])
def check_bale_conn(message):
    if not is_authorized(message.from_user.id):
        return
    
    token = os.environ.get("BALE_BOT_TOKEN")
    if not token:
        reply_formatted(message, "⚠️ متغیر BALE_BOT_TOKEN در تب Environment رندر هنوز تعریف نشده است.")
        return

    bot.reply_to(message, "در حال بررسی دسترسی شبکه از رندر به دیتاسنتر بله...")
    try:
        res = requests.get(f"https://tapi.bale.ai/bot{token}/getMe", timeout=8)
        reply_formatted(message, f"📡 <b>نتیجه تست اتصال به بله:</b>\n\nوضعیت: {res.status_code}\nپاسخ سرور:\n<code>{res.text}</code>")
    except Exception as e:
        reply_formatted(message, f"❌ <b>خطا در اتصال به بله از سرور رندر:</b>\n{e}")

@bot.message_handler(commands=['testweb'])
def test_web(message):
    if not is_authorized(message.from_user.id):
        return
    query = message.text.replace('/testweb', '').strip() or "قیمت دلار"
    bot.send_chat_action(message.chat.id, 'typing')
    data = fetch_web_context(query)
    if data:
        reply_formatted(message, f"🔍 <b>داده‌های وب:</b>\n\n{data[:2000]}")
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
        reply_formatted(message, response.text)
    except Exception as e:
        reply_formatted(message, f"خطا: {e}")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    user_text = message.text
    selected_model = user_model.get(chat_id, MODEL_FAST)
    is_mem = memory_status.get(chat_id, True)

    bot.send_chat_action(chat_id, 'typing')

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        sys_prompt = BASE_SYSTEM_PROMPT
        if exam_mode_status.get(chat_id, False):
            sys_prompt += f"\n\n{EXAM_SYSTEM_PROMPT}"
        sys_prompt += f"\nزمان فعلی سرور: {current_time}"

        if selected_model == MODEL_GEMINI:
            web_info = ""
            if should_search_web(user_text):
                web_info = fetch_web_context(user_text)

            enriched_text = f"{user_text}\n\n[داده‌های زنده وب]:\n{web_info}" if web_info else user_text

            gemini_contents = []
            if is_mem:
                if chat_id not in chat_memory:
                    chat_memory[chat_id] = []
                for item in chat_memory[chat_id]:
                    role = "user" if item["role"] == "user" else "model"
                    gemini_contents.append({"role": role, "parts": [{"text": item["content"]}]})
                gemini_contents.append({"role": "user", "parts": [{"text": enriched_text}]})
            else:
                gemini_contents = [{"role": "user", "parts": [{"text": enriched_text}]}]

            response = gemini_client.models.generate_content(
                model=MODEL_GEMINI,
                contents=gemini_contents,
                config=types.GenerateContentConfig(system_instruction=sys_prompt, temperature=0.2)
            )
            ans = response.text.strip()

            if is_mem:
                chat_memory[chat_id].append({"role": "user", "content": user_text})
                chat_memory[chat_id].append({"role": "assistant", "content": ans})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]

            reply_formatted(message, ans)

        else:
            if is_mem:
                if chat_id not in chat_memory:
                    chat_memory[chat_id] = []
                chat_memory[chat_id].append({"role": "user", "content": user_text})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]
                messages = [{"role": "system", "content": sys_prompt}] + chat_memory[chat_id]
            else:
                messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_text}]

            resp = groq_client.chat.completions.create(
                model=selected_model,
                messages=messages,
                temperature=0.2,
                max_tokens=1500 if selected_model == MODEL_SMART else 800
            )
            ans = resp.choices[0].message.content.strip()

            if is_mem:
                chat_memory[chat_id].append({"role": "assistant", "content": ans})

            reply_formatted(message, ans)

    except Exception as e:
        print(f"Chat Error: {e}")
        reply_formatted(message, "در پردازش مشکلی رخ داد؛ لطفاً دوباره تلاش کنید.")

print("ربات با ابزار تست اتصال بله آماده است...")
bot.infinity_polling()
