import os
import re
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException
from google import genai
from google.genai import types

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# ۱. وب‌سرور سبک برای زنده نگه‌داشتن سرویس در رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Personal Gemini Assistant is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی متغیرها از رندر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# ۳. مدیریت حافظه و وضعیت چت‌ها
chat_memory = {}
memory_status = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ۴. پرامپت سیستمی و دستورالعمل‌ها
SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، دقیق، متصل به وب و مسلط به تمام زمینه‌ها هستی.
تو در بستر پیام‌رسان تلگرام با کاربر گفتگو می‌کنی.

قوانین اصلی:
۱. اگر اطلاعات زنده وب در اختیارت قرار گرفت، به طور مستقیم از آن برای پاسخ‌های موثق و بدون توهم استفاده کن.
۲. اگر اطلاعات وب نامرتبط بود، فقط به دانش عمومی خودت تکیه کن.
۳. در معرفی افراد و اخبار، حدس نزن و داستان‌سرایی نکن.
۴. تحت هیچ شرایطی از فرمت LaTeX و نماد دلار ($) استفاده نکن؛ محاسبات ریاضی را به شکل متن ساده بنویس (مثال: ۱۵ × ۴۲ = ۶۳۰).
۵. پاسخ‌ها شسته‌رفته، سریع و با لحن محترمانه باشند.

دستورات فعال در ربات:
- /help : نمایش راهنما
- /memory_on : فعال‌سازی حافظه گفتگو
- /memory_off : غیرفعال کردن حافظه
- /clear : پاکسازی سابقه مکالمه فعلی
- /start : شروع مجدد
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار شخصی:</b>

• /help : نمایش راهنما
• /start : بررسی وضعیت و راه‌اندازی
• /memory_on : فعال‌سازی حافظه گفتگو
• /memory_off : غیرفعال‌سازی حافظه (حالت مستقل و سبک)
• /clear : پاکسازی سابقه مکالمه جاری
"""

def fetch_web_context(query):
    """جستجوی زنده در وب برای جلوگیری کامل از توهم"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return ""
            context_snippets = []
            for item in results:
                title = item.get("title", "")
                body = item.get("body", "")
                context_snippets.append(f"• {title}: {body}")
            return "\n".join(context_snippets)
    except Exception as e:
        print(f"Web search error: {e}")
        return ""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    chat_memory[chat_id] = []
    
    if chat_id not in memory_status:
        memory_status[chat_id] = True

    state_text = "فعال است" if memory_status[chat_id] else "غیرفعال است"
    welcome_text = (
        f"سلام! دستیار مجهز به موتور Gemini و سرچ وب آماده است.\n\n"
        f"وضعیت فعلی: <b>حافظه {state_text}</b>.\n\n"
        + HELP_TEXT
    )
    bot.reply_to(message, welcome_text, parse_mode='HTML')

@bot.message_handler(commands=['help'])
def send_help(message):
    if not is_authorized(message.from_user.id):
        return
    bot.reply_to(message, HELP_TEXT, parse_mode='HTML')

@bot.message_handler(commands=['memory_on'])
def enable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = True
    bot.reply_to(message, "✅ <b>حافظه فعال شد.</b> سابقه پیام‌ها ذخیره و پیگیری می‌شود.", parse_mode='HTML')

@bot.message_handler(commands=['memory_off'])
def disable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    bot.reply_to(message, "❌ <b>حافظه غیرفعال شد.</b> تمام پیام‌ها مستقل بررسی می‌شوند.", parse_mode='HTML')

@bot.message_handler(commands=['clear'])
def clear_history(message):
    if not is_authorized(message.from_user.id):
        return
    chat_memory[message.chat.id] = []
    bot.reply_to(message, "حافظه مکالمه جاری پاک شد.")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if not is_authorized(message.from_user.id):
        return

    try:
        bot.send_chat_action(message.chat.id, 'typing')
        chat_id = message.chat.id
        user_query = message.text

        # جستجوی وب برای سوالات متنی
        web_info = fetch_web_context(user_query)
        if web_info:
            enriched_prompt = (
                f"{user_query}\n\n"
                f"[اطلاعات زنده وب برای استناد]:\n{web_info}"
            )
        else:
            enriched_prompt = user_query

        is_memory_active = memory_status.get(chat_id, True)

        # آماده‌سازی پرامپت و تاریخچه برای SDK رسمی گوگل
        contents_payload = []
        if is_memory_active:
            if chat_id not in chat_memory:
                chat_memory[chat_id] = []

            for entry in chat_memory[chat_id]:
                role_label = "user" if entry["role"] == "user" else "model"
                contents_payload.append({
                    "role": role_label,
                    "parts": [{"text": entry["content"]}]
                })

            contents_payload.append({
                "role": "user",
                "parts": [{"text": enriched_prompt}]
            })
        else:
            contents_payload = [{
                "role": "user",
                "parts": [{"text": enriched_prompt}]
            }]

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_system_instruction = f"{SYSTEM_PROMPT}\nزمان فعلی سرور: {current_time}"

        # فراخوانی رسمی مدل Gemini 3.5 Flash Lite
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=contents_payload,
            config=types.GenerateContentConfig(
                system_instruction=full_system_instruction,
                temperature=0.3,
                max_output_tokens=800
            )
        )

        reply_text = response.text

        if reply_text and reply_text.strip():
            raw_text = reply_text.strip()

            # تبدیل فرمت‌های متنی به استایل‌های رسمی تلگرام
            formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
            formatted_text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', formatted_text, flags=re.DOTALL)
            formatted_text = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted_text)

            if is_memory_active:
                chat_memory[chat_id].append({"role": "user", "content": user_query})
                chat_memory[chat_id].append({"role": "model", "content": raw_text})

                # نگهداری حداکثر ۱۰ پیام آخر (۵ تبادل)
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]

            try:
                bot.reply_to(message, formatted_text, parse_mode='HTML')
            except ApiTelegramException:
                bot.reply_to(message, raw_text)
        else:
            bot.reply_to(message, "پاسخی از سمت مدل دریافت نشد؛ لطفاً دوباره بپرسید.")

    except Exception as e:
        print(f"Error details: {e}")
        bot.reply_to(message, "در پردازش پیام خطایی رخ داد؛ لطفاً چند لحظه بعد تلاش کنید.")

print("ربات با هوش Gemini و اتصال وب فعال شد...")
bot.infinity_polling()
