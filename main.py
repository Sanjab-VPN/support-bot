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

# ۲. دریافت متغیرها از رندر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. حافظه و وضعیت چت‌ها
chat_memory = {}
memory_status = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ۴. پرامپت سیستمی حاوی لیست دستورات و قوانین تلگرام
SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، دقیق و مسلط به تمام زمینه‌ها هستی.
تو در بستر یک ربات تلگرام در حال مکالمه هستی.

دستورات فعال در ربات:
اگر کاربر درباره دستورات، فرامین یا تنظیمات پرسید، دقیقاً این دستورات را معرفی کن:
- /help : نمایش لیست دستورات و راهنما
- /memory_on : فعال‌سازی حافظه پیوسته مکالمه
- /memory_off : غیرفعال‌سازی حافظه و بررسی مستقل هر پیام
- /clear : پاک کردن تاریخچه مکالمه فعلی
- /start : شروع و بازنشانی ربات

قوانین نگارشی و فرمت:
۱. در موضوعات عمومی، کدنویسی، تحلیل، ترجمه و تولید محتوا دقیق و بدون حاشیه پاسخ بده.
۲. تحت هیچ شرایطی از فرمت LaTeX و نماد دلار ($) استفاده نکن و فرمول‌ها را ساده بنویس (مانند: ۱۵ × ۴۲ = ۶۳۰).
۳. زبان پیش‌فرض فارسی سلیس است، مگر کاربر انگلیسی یا فینگلیش بنویسد.
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار هوشمند:</b>

• /help : نمایش همین راهنما
• /start : راه‌اندازی ربات
• /memory_on : فعال‌سازی حافظه گفتگو
• /memory_off : خاموش کردن حافظه (صرفه‌جویی در مصرف توکن)
• /clear : پاک کردن تاریخچه فعلی
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return

    chat_memory[message.chat.id] = []
    memory_status[message.chat.id] = True
    welcome_text = (
        "سلام! دستیار پرسرعت شخصی شما آماده است.\n\n"
        "وضعیت فعلی: <b>حافظه فعال است</b>.\n\n"
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
    bot.reply_to(message, "✅ <b>حافظه فعال شد.</b> سوابق پیام‌ها ذخیره می‌شود.", parse_mode='HTML')

@bot.message_handler(commands=['memory_off'])
def disable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    bot.reply_to(message, "❌ <b>حافظه غیرفعال شد.</b> هر پیام به صورت مستقل پردازش می‌شود.", parse_mode='HTML')

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
        full_system = f"{SYSTEM_PROMPT}\nاطلاعات سیستمی: زمان فعلی سرور: {current_time}"

        if is_memory_active:
            if chat_id not in chat_memory:
                chat_memory[chat_id] = []
            
            chat_memory[chat_id].append({"role": "user", "content": message.text})
            
            if len(chat_memory[chat_id]) > 6:
                chat_memory[chat_id] = chat_memory[chat_id][-6:]
                
            payload_messages = [{"role": "system", "content": full_system}] + chat_memory[chat_id]
        else:
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

            # تبدیل خودکار مارک‌داون به تگ‌های رسمی HTML تلگرام
            formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
            formatted_text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', formatted_text, flags=re.DOTALL)
            formatted_text = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted_text)

            if is_memory_active:
                chat_memory[chat_id].append({"role": "assistant", "content": raw_text})

            try:
                bot.reply_to(message, formatted_text, parse_mode='HTML')
            except ApiTelegramException:
                # سوپاپ اطمینان: ارسال متن خام در صورت ناسازگاری تگ‌ها
                bot.reply_to(message, raw_text)
        else:
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً مجدداً سوال خود را بفرستید.")

    except Exception as e:
        print(f"Error details: {e}")
        bot.reply_to(message, "در پردازش پیام خطایی رخ داد؛ لطفاً چند لحظه دیگر امتحان کنید.")

print("ربات با هوش اصلاح‌شده و پردازش استایل تلگرام آماده است...")
bot.infinity_polling()
