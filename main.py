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

# ۲. فراخوانی متغیرهای محیطی
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ۳. مدل‌ها و وضعیت چت‌ها
MODEL_FAST = "qwen/qwen3.8-27b"
MODEL_SMART = "openai/gpt-oss-120b"

chat_memory = {}
memory_status = {}
user_model = {}
exam_mode_status = {}

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ۴. پرامپت‌های سیستمی
BASE_SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، صریح و بدون حاشیه هستی که در تلگرام فعالیت می‌کنی.

دستورات بات:
- /fast : سوئیچ به مدل سریع
- /smart : سوئیچ به مدل فوق‌هوشمند (120B)
- /exam_on : فعال‌سازی حالت تخصصی حل تست زبان
- /exam_off : غیرفعال‌سازی حالت تست
- /memory_on : فعال‌سازی حافظه
- /memory_off : غیرفعال‌سازی حافظه
- /clear : پاکسازی تاریخچه
- /help : راهنمای کامل

قوانین عمومی:
۱. پاسخ‌ها مستقیم، بدون تعارف و دقیقاً به اصل موضوع باشند.
۲. فرمت LaTeX و علامت دلار ($) اکیداً ممنوع است؛ تمام فرمول‌ها و عبارات را به صورت متن ساده بنویس.
۳. زبان پیش‌فرض فارسی سلیس است، مگر پیام کاربر انگلیسی باشد.
"""

EXAM_SYSTEM_PROMPT = """
دستورالعمل آزمون زبان انگلیسی (Autonomous English Exam Protocol):
کاربر در جلسه آزمون تستی است و نیاز به یک پاسخ قطعی، بدون معطلی و بدون سردرگمی برای پر کردن پاسخ‌نامه دارد.

قوانین عملیاتی:
۱. تعهد قطعی به انتخاب یک گزینه: تحت هیچ شرایطی خروجی را با عباراتی مثل "Missing Option" یا "سوال غلط است پس جوابی نیست" رها نکن. در هر شرایطی باید دقیقاً یکی از حروف گزینه‌های موجود در سوال (A یا B یا C یا D) به عنوان پاسخ نهایی تعیین شود.
۲. سوالات معیوب، دارای غلط املایی یا چندجوابی:
   - اگر سوال دارای اشتباه طراحی یا ترجمه تحت‌اللفظی بود، ذهنیت طراح کنکور/آزمون و کلید محتمل مصحح را در یک جمله کوتاه توضیح بده و همان گزینه کلید را برگزین.
   - اگر دو گزینه از نظر گرامری هر دو درست بودند (مانند worst و best)، هرگز برای رد یکی از آن‌ها قاعده گرامری جعلی و من‌درآوردی نساز؛ بلکه طبق عرف کتاب‌های درسی و سوالات پرتکرار، گزینه استانداردتر را انتخاب کن.
۳. تله‌های ساختاری پیشرفته:
   - فاعل ملکی (Possessive Trap): در ساختارهای Dangling Modifier، اگر گزینه با اسم ملکی شروع شده (مثل The officer's license)، فاعل دستوری کلمه license است و فاعل معلق رفع نشده است.
   - افعال حسی و سببی مجهول: افعالی مثل see, hear, make در ساختار مجهول حتماً باید مصدر با to بگیرند (مانند was seen to enter).
   - شرطی ترکیبی: در ساختارهای شرطی Had + pp اگر انتهای جمله قید زمان حال (today, now) دارد، بخش دوم جمله would + base form است.
۴. نهایت ایجاز: کل تحلیل برای هر سوال حداکثر در ۲ سطر کوتاه باشد.
۵. قالب سطر آخر (اجباری و بدون تغییر):
   RESULT: [Correct Phrase/Word] -> [Option Letter]
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار شخصی:</b>

<b>موتورهای هوش مصنوعی:</b>
• /fast : مدل فوق‌سریع (کارهای روزمره)
• /smart : مدل فوق‌هوشمند 120B (استدلال سنگین و تست‌های دشوار)

<b>حالت تخصصی آزمون (Exam Mode):</b>
• /exam_on : فعال‌سازی حل تست زبان با خروجی تک‌گزینه‌ای و قطعی
• /exam_off : غیرفعال‌سازی حالت تست و بازگشت به دستیار سبک

<b>مدیریت حافظه:</b>
• /memory_on : ذخیره و ادامه پیوسته گفتگو
• /memory_off : پاسخ‌های مستقل (صرفه‌جویی در توکن)
• /clear : پاکسازی تاریخچه مکالمه فعلی

<b>سیستمی:</b>
• /start : بررسی وضعیت فعلی
• /help : نمایش همین راهنما
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    chat_memory[chat_id] = []
    
    memory_status.setdefault(chat_id, True)
    user_model.setdefault(chat_id, MODEL_FAST)
    exam_mode_status.setdefault(chat_id, False)

    mem_text = "فعال" if memory_status[chat_id] else "غیرفعال"
    exam_text = "فعال 🎯" if exam_mode_status[chat_id] else "غیرفعال"
    current_m = "فوق‌سریع ⚡️" if user_model[chat_id] == MODEL_FAST else "فوق‌هوشمند (120B) 🧠"

    welcome_text = (
        f"سلام! دستیار شخصی آماده است.\n\n"
        f"وضعیت فعال:\n"
        f"• <b>مدل:</b> {current_m}\n"
        f"• <b>حافظه:</b> {mem_text}\n"
        f"• <b>حالت آزمون (Exam Mode):</b> {exam_text}\n\n"
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
    bot.reply_to(message, "⚡️ <b>مدل فوق‌سریع فعال شد.</b>", parse_mode='HTML')

@bot.message_handler(commands=['smart'])
def switch_to_smart(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_SMART
    bot.reply_to(message, "🧠 <b>مدل فوق‌هوشمند (120B) فعال شد.</b>", parse_mode='HTML')

@bot.message_handler(commands=['exam_on'])
def enable_exam_mode(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = True
    bot.reply_to(
        message, 
        "🎯 <b>حالت تخصصی آزمون فعال شد.</b>\nتحلیل فشرده، خروجی بدون معطلی و تعیین قطعی یک گزینه برای پاسخ‌نامه.", 
        parse_mode='HTML'
    )

@bot.message_handler(commands=['exam_off'])
def disable_exam_mode(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = False
    bot.reply_to(message, "⚪️ <b>حالت آزمون غیرفعال شد.</b> بات به حالت سبک عمومی بازگشت.", parse_mode='HTML')

@bot.message_handler(commands=['memory_on'])
def enable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = True
    bot.reply_to(message, "✅ <b>حافظه فعال شد.</b>", parse_mode='HTML')

@bot.message_handler(commands=['memory_off'])
def disable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    bot.reply_to(message, "❌ <b>حافظه غیرفعال شد.</b>", parse_mode='HTML')

@bot.message_handler(commands=['clear'])
def clear_history(message):
    if not is_authorized(message.from_user.id):
        return
    chat_memory[message.chat.id] = []
    bot.reply_to(message, "حافظه مکالمه پاک شد.")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if not is_authorized(message.from_user.id):
        return

    try:
        bot.send_chat_action(message.chat.id, 'typing')
        chat_id = message.chat.id

        is_memory_active = memory_status.get(chat_id, True)
        is_exam_active = exam_mode_status.get(chat_id, False)
        selected_model = user_model.get(chat_id, MODEL_FAST)
        
        max_output_tokens = 1500 if selected_model == MODEL_SMART else 800

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        assembled_prompt = BASE_SYSTEM_PROMPT
        if is_exam_active:
            assembled_prompt += f"\n\n{EXAM_SYSTEM_PROMPT}"
        assembled_prompt += f"\nاطلاعات سیستمی: زمان سرور: {current_time}"

        if is_memory_active:
            if chat_id not in chat_memory:
                chat_memory[chat_id] = []

            chat_memory[chat_id].append({"role": "user", "content": message.text})

            if len(chat_memory[chat_id]) > 10:
                chat_memory[chat_id] = chat_memory[chat_id][-6:]

            payload_messages = [{"role": "system", "content": assembled_prompt}] + chat_memory[chat_id]
        else:
            payload_messages = [
                {"role": "system", "content": assembled_prompt},
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
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً دوباره بپرسید.")

    except Exception as e:
        print(f"Error details: {e}")
        bot.reply_to(message, "در پردازش مشکلی رخ داد؛ لطفاً کمی بعد تلاش کنید.")

print("ربات با موتور دوگانه، مدیریت حافظه و Exam Mode فعال شد...")
bot.infinity_polling()
