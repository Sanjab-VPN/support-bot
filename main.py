import os
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

# پردازش شناسه‌های عددی مجاز (جدا شده با کاما در رندر)
ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. متغیرهای حافظه و وضعیت
chat_memory = {}
memory_status = {}

# ۴. بررسی دسترسی کاربر
def is_authorized(user_id):
    # اگر متغیر در رندر خالی باشد همه مجازند، اگر مقداردهی شده باشد فقط شناسه‌های لیست
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ۵. پرامپت سیستمی
SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع و بسیار باهوش هستی.
خروجی تو مستقیماً در تلگرام ارسال می‌شود؛ بنابراین فقط از تگ‌های مجاز HTML تلگرام استفاده کن:

قوانین نگارشی و ساختاری:
۱. برای بولد کردن فقط از <b>متن</b> استفاده کن (به هیچ عنوان از ستاره ** استفاده نکن).
۲. برای کج نوشتن از <i>متن</i> استفاده کن.
۳. برای کدهای چندخطی از <pre>کد</pre> و برای عبارات کوتاه/دستورات از <code>کد</code> استفاده کن.
۴. همیشه تگ‌های باز شده را با دقت ببند.
۵. به هیچ وجه از فرمت LaTeX و علامت دلار ($) استفاده نکن؛ تمام فرمول‌ها و محاسبات را به شکل متن ساده بنویس (مثال: ۱۵ × ۴۲ = ۶۳۰).
۶. در موضوعات مختلف (کدنویسی، تولید محتوا، ترجمه، تحلیل و سوالات عمومی) سریع، دقیق و بدون تعارفات اضافی پاسخ بده.
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار هوشمند:</b>

• /help : نمایش همین راهنما
• /start : راه‌اندازی اولیه ربات
• /memory_on : فعال‌سازی حافظه گفتگو (یادآوری پیام‌های قبلی)
• /memory_off : خاموش کردن حافظه (صرفه‌جویی بالا و پاسخ‌های مستقل)
• /clear : پاک کردن تاریخچه گفتگوی فعلی
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return

    chat_memory[message.chat.id] = []
    memory_status[message.chat.id] = True
    welcome_text = (
        "سلام! دستیار شخصی شما آماده است.\n\n"
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
    bot.reply_to(message, "✅ <b>حافظه فعال شد.</b> ربات پیام‌های قبلی را به خاطر می‌سپارد.", parse_mode='HTML')

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
    bot.reply_to(message, "حافظه گفتگوی فعلی پاک شد.")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    # مسدودسازی افراد غیرمجاز به صورت کاملاً بی‌صدا
    if not is_authorized(message.from_user.id):
        return

    try:
        bot.send_chat_action(message.chat.id, 'typing')
        chat_id = message.chat.id

        is_memory_active = memory_status.get(chat_id, True)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_system = f"{SYSTEM_PROMPT}\nزمان فعلی سرور: {current_time}"

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
            clean_text = reply_text.strip()
            
            if is_memory_active:
                chat_memory[chat_id].append({"role": "assistant", "content": clean_text})

            try:
                bot.reply_to(message, clean_text, parse_mode='HTML')
            except ApiTelegramException:
                bot.reply_to(message, clean_text)
        else:
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً دوباره تلاش کنید.")

    except Exception as e:
        # ثبت جزئیات کامل ارور در لاگ‌های سرور برای خودتان
        print(f"Server Internal Error: {e}")
        # ارسال پیام عمومی و تمیز برای کاربر بدون لو رفتن متغیرها یا کدها
        bot.reply_to(message, "متأسفانه در برقراری ارتباط مشکلی پیش آمد. لطفاً چند لحظه بعد مجدداً پیام دهید.")

print("ربات با سطح دسترسی اختصاصی فعال شد...")
bot.infinity_polling()
