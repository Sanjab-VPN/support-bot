import os
import re
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException
from groq import Groq

# ۱. وب‌سرور سبک برای زنده نگه‌داشتن سرویس در رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Personal AI Assistant is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی متغیرها از رندر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. مدیریت حافظه و وضعیت چت‌ها
chat_memory = {}
memory_status = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ۴. پرامپت سیستمی و دستورات
SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، دقیق و مسلط به تمام زمینه‌ها هستی.
تو در بستر پیام‌رسان تلگرام با کاربر گفتگو می‌کنی.

دستورات فعال در بات:
اگر کاربر درباره دستورات، امکانات یا فرامین ربات پرسید، دقیقاً این موارد را معرفی کن:
- /help : نمایش راهنمای کامل
- /memory_on : فعال‌سازی حافظه پیوسته
- /memory_off : غیرفعال کردن حافظه و پردازش مستقل
- /clear : پاکسازی تاریخچه مکالمه فعلی
- /start : بررسی وضعیت و شروع مجدد

قوانین نگارشی:
۱. پاسخ‌ها سریع، بدون حاشیه و مستقیم به اصل موضوع باشند.
۲. تحت هیچ شرایطی از فرمت LaTeX و علامت دلار ($) استفاده نکن؛ تمام فرمول‌ها و محاسبات را به صورت متن ساده بنویس (مثال: ۱۵ × ۴۲ = ۶۳۰).
۳. زبان پیش‌فرض فارسی سلیس است، مگر اینکه کاربر به زبان دیگری پیام بدهد.
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار شخصی:</b>

• /help : نمایش همین راهنما
• /start : بررسی وضعیت و شروع ربات
• /memory_on : فعال‌سازی حافظه (به خاطر سپردن گفتگوها)
• /memory_off : غیرفعال‌سازی حافظه (پاسخ‌های مستقل و صرفه‌جویی در توکن)
• /clear : پاکسازی سابقه گفتگوی فعلی
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    chat_memory[chat_id] = []
    
    # حفظ تنظیم قبلی کاربر و جلوگیری از ریست شدن حالت خاموش
    if chat_id not in memory_status:
        memory_status[chat_id] = True

    state_text = "فعال است" if memory_status[chat_id] else "غیرفعال است"

    welcome_text = (
        f"سلام! دستیار شخصی شما آماده است.\n\n"
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
    bot.reply_to(message, "✅ <b>حافظه فعال شد.</b> پیام‌های قبلی ذخیره و پیگیری می‌شوند.", parse_mode='HTML')

@bot.message_handler(commands=['memory_off'])
def disable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    bot.reply_to(message, "❌ <b>حافظه غیرفعال شد.</b> تمام پیام‌ها مستقل و بدون تاریخچه پردازش می‌شوند.", parse_mode='HTML')

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

        is_memory_active = memory_status.get(chat_id, True)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_system = f"{SYSTEM_PROMPT}\nاطلاعات سیستمی: زمان سرور: {current_time}"

        if is_memory_active:
            if chat_id not in chat_memory:
                chat_memory[chat_id] = []

            chat_memory[chat_id].append({"role": "user", "content": message.text})

            # نگهداری حداکثر ۶ پیام آخر (۳ سوال و ۳ جواب)
            if len(chat_memory[chat_id]) > 6:
                chat_memory[chat_id] = chat_memory[chat_id][-6:]

            payload_messages = [{"role": "system", "content": full_system}] + chat_memory[chat_id]
        else:
            # حالت تک‌پاسخی بدون بارگذاری تاریخچه
            payload_messages = [
                {"role": "system", "content": full_system},
                {"role": "user", "content": message.text}
            ]

        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=payload_messages,
            temperature=0.6,
            max_tokens=800
        )

        reply_text = response.choices[0].message.content

        if reply_text and reply_text.strip():
            raw_text = reply_text.strip()

            # تبدیل عبارات مارک‌داون به تگ‌های HTML معتبر تلگرام
            formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
            formatted_text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', formatted_text, flags=re.DOTALL)
            formatted_text = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted_text)

            if is_memory_active:
                chat_memory[chat_id].append({"role": "assistant", "content": raw_text})

            try:
                bot.reply_to(message, formatted_text, parse_mode='HTML')
            except ApiTelegramException:
                bot.reply_to(message, raw_text)
        else:
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً مجدداً بپرسید.")

    except Exception as e:
        print(f"Error details: {e}")
        bot.reply_to(message, "در پردازش پیام مشکلی رخ داد؛ لطفاً چند لحظه بعد تلاش کنید.")

print("ربات با امکانات کامل و حافظه پایدار فعال شد...")
bot.infinity_polling()
