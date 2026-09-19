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

# ۲. فراخوانی متغیرها از متغیرهای محیطی
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. مدل‌ها، وضعیت حافظه و انتخاب موتور هوش مصنوعی
MODEL_FAST = "qwen/qwen3.8-27b"
MODEL_SMART = "openai/gpt-oss-120b"

chat_memory = {}
memory_status = {}
user_model = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ۴. پرامپت سیستمی تجمیع‌شده
SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، دقیق و مسلط به تمام زمینه‌ها هستی که در بستر پیام‌رسان تلگرام فعالیت می‌کنی.

دستورات فعال در بات:
اگر کاربر درباره دستورات، امکانات یا فرامین ربات پرسید، این موارد را معرفی کن:
- /help : نمایش راهنمای کامل
- /fast : فعال‌سازی مدل فوق‌سریع و سبک
- /smart : فعال‌سازی مدل عمیق، پیشرفته و تحلیلی (120B)
- /memory_on : فعال‌سازی حافظه پیوسته
- /memory_off : غیرفعال کردن حافظه و پردازش مستقل
- /clear : پاکسازی تاریخچه مکالمه فعلی
- /start : بررسی وضعیت و شروع مجدد

قوانین نگارشی و ساختاری عمومی:
۱. پاسخ‌ها سریع، بدون حاشیه و مستقیم به اصل موضوع باشند.
۲. تحت هیچ شرایطی از فرمت LaTeX و علامت دلار ($) استفاده نکن؛ تمام فرمول‌ها و محاسبات را به صورت متن ساده بنویس (مثال: ۱۵ × ۴۲ = ۶۳۰).
۳. زبان پیش‌فرض فارسی سلیس است، مگر اینکه کاربر به زبان انگلیسی یا زبان دیگری پیام بدهد یا سوال تست زبان مطرح کرده باشد.

دستورالعمل ویژه حل سوالات چهارگزینه‌ای و آزمون‌های زبان (Autonomous English Exam Protocol):
اگر کاربر سوال یا تستی به زبان انگلیسی یا تست چهارگزینه‌ای ارسال کرد، این پروتکل ضدخطا را رعایت کن:
۱. صورت‌های سوال منفی: اگر سوال به دنبال گزینه غلط یا دارای خطا بود (مانند GRAMMATICAL ERROR یا INCORRECT)، حتماً آن را مشخص کن.
۲. تله‌های نحوی حساس:
   - در عبارات وصفی/وجهی (Dangling Modifiers)، توجه داشته باش که فاعل جمله پایه باید عامل واقعی عمل باشد. (اسم‌های دارای آپاستروف ملکی مانند "The officer's license" فاعل دستوری‌شان کلمه license است نه شخص).
   - تفاوت بین وارونگی صفت (Adjective Fronting) و قیود منفی را رعایت کن.
   - وجه التزامی (Subjunctive) را در حالت منفی فقط با "not be + pp" یا شکل پایه بدون افعال کمکی به کار ببر.
۳. مهار مصرف توکن: تحلیل هر سوال یا گزینه را حداکثر در ۲ تا ۳ سطر فشرده نگه دار تا پاسخ قطع نشود.
۴. سوالات دارای نقص طراحی: اگر سوال آزمون نقص فنی داشت یا همه گزینه‌ها غلط بودند، نقص را در یک خط بگو و محتمل‌ترین گزینه مدنظر طراح را برگزین.
۵. خروجی ضدخطا: سطر آخر هر تست باید دقیقاً در این قالب درج شود تا حرف گزینه اشتباه اعلام نشود:
   RESULT: [Correct Phrase/Word] -> [Option Letter]
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار شخصی:</b>

<b>مدیریت مدل‌ها:</b>
• /fast : سوئیچ به مدل فوق‌سریع (مناسب کارهای روزمره و پاسخ‌های آنی)
• /smart : سوئیچ به مدل فوق‌هوشمند (120B) (استدلال عمیق، تست‌های دشوار، کدنویسی و تحلیل تخصصی)

<b>مدیریت حافظه:</b>
• /memory_on : فعال‌سازی حافظه (دنبال کردن مکالمه)
• /memory_off : غیرفعال‌سازی حافظه (پاسخ‌های مستقل و صرفه‌جویی)
• /clear : پاکسازی سابقه گفتگوی جاری

<b>عمومی:</b>
• /start : بررسی وضعیت کلی
• /help : نمایش همین راهنما
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    chat_memory[chat_id] = []
    
    if chat_id not in memory_status:
        memory_status[chat_id] = True
    if chat_id not in user_model:
        user_model[chat_id] = MODEL_FAST

    state_text = "فعال" if memory_status[chat_id] else "غیرفعال"
    current_m = "فوق‌سریع ⚡️" if user_model[chat_id] == MODEL_FAST else "فوق‌هوشمند (120B) 🧠"

    welcome_text = (
        f"سلام! دستیار شخصی شما آماده است.\n\n"
        f"وضعیت فعلی:\n"
        f"• <b>مدل فعال:</b> {current_m}\n"
        f"• <b>حافظه:</b> {state_text}\n\n"
        + HELP_TEXT
    )
    bot.reply_to(message, welcome_text, parse_mode='HTML')

@bot.message_handler(commands=['help'])
def send_help(message):
    if not is_authorized(message.from_user.id):
        return
    bot.reply_to(message, HELP_TEXT, parse_mode='HTML')

@bot.message_handler(commands=['fast'])
def switch_to_fast(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_FAST
    bot.reply_to(
        message,
        "⚡️ <b>سوئیچ به مدل فوق‌سریع انجام شد.</b>\nسرعت پاسخ‌دهی بالا و مصرف بهینه توکن.",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['smart'])
def switch_to_smart(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_SMART
    bot.reply_to(
        message,
        "🧠 <b>سوئیچ به مدل فوق‌هوشمند (120B) انجام شد.</b>\nبالاترین قدرت استدلال، مناسب تست‌های پیچیده، کدنویسی و تحلیل عمیق.",
        parse_mode='HTML'
    )

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
        selected_model = user_model.get(chat_id, MODEL_FAST)
        
        # تنظیم سقف توکن بر اساس مدل فعال
        max_output_tokens = 1500 if selected_model == MODEL_SMART else 800

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_system = f"{SYSTEM_PROMPT}\nاطلاعات سیستمی: زمان سرور: {current_time}"

        if is_memory_active:
            if chat_id not in chat_memory:
                chat_memory[chat_id] = []

            chat_memory[chat_id].append({"role": "user", "content": message.text})

            # نگهداری حداکثر ۱۰ پیام آخر (۵ سوال و ۵ پاسخ)
            if len(chat_memory[chat_id]) > 10:
                chat_memory[chat_id] = chat_memory[chat_id][-6:]

            payload_messages = [{"role": "system", "content": full_system}] + chat_memory[chat_id]
        else:
            payload_messages = [
                {"role": "system", "content": full_system},
                {"role": "user", "content": message.text}
            ]

        response = client.chat.completions.create(
            model=selected_model,
            messages=payload_messages,
            temperature=0.2,
            max_tokens=max_output_tokens
        )

        reply_text = response.choices[0].message.content

        if reply_text and reply_text.strip():
            raw_text = reply_text.strip()

            # تبدیل عبارات متداول مارک‌داون به تگ‌های امن تلگرام
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
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً مجدداً پیام دهید.")

    except Exception as e:
        print(f"Error details: {e}")
        bot.reply_to(message, "در پردازش پیام مشکلی رخ داد؛ لطفاً چند لحظه بعد تلاش کنید.")

print("ربات با موتور دوگانه (Fast + Smart 120B) و وب‌سرور آماده به کار است...")
bot.infinity_polling()
