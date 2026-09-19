import os
import re
import threading
from datetime import datetime
from flask import Flask
import telebot
from telebot.apihelper import ApiTelegramException
from groq import Groq
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
    return "Personal AI Assistant (Groq + Gemini) is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی متغیرهای محیطی
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ۳. مدل‌ها و وضعیت چت‌ها
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

# ۴. پرامپت‌های سیستمی
BASE_SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، سریع، صریح و بدون حاشیه هستی که در تلگرام فعالیت می‌کنی.

دستورات بات:
- /fast : سوئیچ به مدل فوق‌سریع
- /smart : سوئیچ به مدل فوق‌هوشمند (120B)
- /gemini : سوئیچ به مدل زنده متصل به اینترنت (Gemini Web)
- /exam_on : فعال‌سازی حالت تخصصی حل تست زبان
- /exam_off : غیرفعال‌سازی حالت تست
- /memory_on : فعال‌سازی حافظه
- /memory_off : غیرفعال‌سازی حافظه
- /clear : پاکسازی تاریخچه
- /help : راهنمای کامل

قوانین عمومی:
۱. پاسخ‌ها مستقیم، بدون تعارف و دقیقاً به اصل موضوع باشند.
۲. اگر اطلاعات وب در اختیارت قرار گرفت، مستقیماً به آن استناد کن و از توهم و اطلاعات ساختگی پرهیز کن.
۳. فرمت LaTeX و علامت دلار ($) اکیداً ممنوع است؛ تمام فرمول‌ها و عبارات را به صورت متن ساده بنویس.
۴. زبان پیش‌فرض فارسی سلیس است، مگر پیام کاربر انگلیسی باشد.
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
• /fast : مدل فوق‌سریع (کارهای روزمره و کدنویسی)
• /smart : مدل فوق‌هوشمند 120B (استدلال سنگین و تست‌های دشوار)
• /gemini : مدل زنده متصل به اینترنت (Gemini 3.5 Flash Lite + سرچ وب)

<b>جستجوی فوری در وب:</b>
• <code>/web متن</code> یا <code>/search متن</code> : جستجوی مستقل در وب بدون نیاز به تغییر مدل فعلی

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

def fetch_web_context(query):
    """جستجوی زنده در اینترنت برای جلوگیری از توهم"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return ""
            snippets = [f"• {r.get('title', '')}: {r.get('body', '')}" for r in results]
            return "\n".join(snippets)
    except Exception as e:
        print(f"Web search error: {e}")
        return ""

def format_and_send(chat_id, message_id, raw_text):
    """تبدیل فرمت‌های Markdown به تگ‌های رسمی HTML تلگرام"""
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
    formatted = re.sub(r'```(.*?)```', r'<pre>\1</pre>', formatted, flags=re.DOTALL)
    formatted = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted)
    try:
        bot.reply_to(telebot.types.Message(message_id=message_id, chat=telebot.types.Chat(chat_id, 'private')), formatted, parse_mode='HTML')
    except ApiTelegramException:
        bot.send_message(chat_id, raw_text)

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
    
    curr = user_model[chat_id]
    if curr == MODEL_FAST:
        current_m = "فوق‌سریع ⚡️"
    elif curr == MODEL_SMART:
        current_m = "فوق‌هوشمند (120B) 🧠"
    else:
        current_m = "جمینای متصل به وب 🌐"

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
    bot.reply_to(message, "⚡️ <b>مدل فوق‌سریع (Qwen) فعال شد.</b>", parse_mode='HTML')

@bot.message_handler(commands=['smart'])
def switch_to_smart(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_SMART
    bot.reply_to(message, "🧠 <b>مدل فوق‌هوشمند (120B) فعال شد.</b>", parse_mode='HTML')

@bot.message_handler(commands=['gemini'])
def switch_to_gemini(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_GEMINI
    bot.reply_to(message, "🌐 <b>مدل Gemini (متصل به وب) فعال شد.</b> پاسخ‌ها با بررسی زنده اینترنت داده می‌شوند.", parse_mode='HTML')

# جستجوی تکی و سریع در اینترنت
@bot.message_handler(commands=['web', 'search'])
def handle_quick_search(message):
    if not is_authorized(message.from_user.id):
        return
    
    query = message.text.replace('/web', '').replace('/search', '').strip()
    if not query:
        bot.reply_to(message, "لطفاً عبارت مورد نظر را بنویسید:\nمثال: <code>/web سام صابری کیست</code>", parse_mode='HTML')
        return

    bot.send_chat_action(message.chat.id, 'typing')
    web_data = fetch_web_context(query)
    prompt = f"با توجه به اطلاعات وب، دقیق و مستند به پرسش پاسخ بده:\n\n[اطلاعات وب]:\n{web_data}\n\nپرسش: {query}"
    
    try:
        response = gemini_client.models.generate_content(
            model=MODEL_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=BASE_SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=800
            )
        )
        format_and_send(message.chat.id, message.message_id, response.text.strip())
    except Exception as e:
        print(f"Quick Search Error: {e}")
        bot.reply_to(message, "در جستجوی اینترنتی خطایی رخ داد.")

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
    bot.reply_to(message, "⚪️ <b>حالت آزمون غیرفعال شد.</b> بات به حالت عمومی بازگشت.", parse_mode='HTML')

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
        user_text = message.text

        is_memory_active = memory_status.get(chat_id, True)
        is_exam_active = exam_mode_status.get(chat_id, False)
        selected_model = user_model.get(chat_id, MODEL_FAST)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        assembled_prompt = BASE_SYSTEM_PROMPT
        if is_exam_active:
            assembled_prompt += f"\n\n{EXAM_SYSTEM_PROMPT}"
        assembled_prompt += f"\nاطلاعات سیستمی: زمان سرور: {current_time}"

        # مسیر ۱ و ۲: مدل‌های Groq (Fast و Smart)
        if selected_model in [MODEL_FAST, MODEL_SMART]:
            max_output_tokens = 1500 if selected_model == MODEL_SMART else 800

            if is_memory_active:
                if chat_id not in chat_memory:
                    chat_memory[chat_id] = []

                chat_memory[chat_id].append({"role": "user", "content": user_text})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]

                payload_messages = [{"role": "system", "content": assembled_prompt}] + chat_memory[chat_id]
            else:
                payload_messages = [
                    {"role": "system", "content": assembled_prompt},
                    {"role": "user", "content": user_text}
                ]

            response = groq_client.chat.completions.create(
                model=selected_model,
                messages=payload_messages,
                temperature=0.2,
                max_tokens=max_output_tokens
            )
            reply_text = response.choices[0].message.content

        # مسیر ۳: مدل Gemini + جستجوی زنده اینترنت
        else:
            web_info = fetch_web_context(user_text)
            enriched_text = f"{user_text}\n\n[اطلاعات زنده وب]:\n{web_info}" if web_info else user_text

            gemini_contents = []
            if is_memory_active:
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
                config=types.GenerateContentConfig(
                    system_instruction=assembled_prompt,
                    temperature=0.2,
                    max_output_tokens=1000
                )
            )
            reply_text = response.text

        # ارسال پاسخ و به‌روزرسانی حافظه
        if reply_text and reply_text.strip():
            raw_text = reply_text.strip()

            if is_memory_active:
                if selected_model == MODEL_GEMINI:
                    chat_memory[chat_id].append({"role": "user", "content": user_text})
                chat_memory[chat_id].append({"role": "assistant", "content": raw_text})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]

            format_and_send(chat_id, message.message_id, raw_text)
        else:
            bot.reply_to(message, "پاسخی دریافت نشد؛ لطفاً مجدداً بپرسید.")

    except Exception as e:
        print(f"Error details: {e}")
        bot.reply_to(message, "در پردازش مشکلی رخ داد؛ لطفاً کمی بعد تلاش کنید.")

print("ربات با سه موتور (Fast, Smart, Gemini Web) و Exam Mode فعال شد...")
bot.infinity_polling()
