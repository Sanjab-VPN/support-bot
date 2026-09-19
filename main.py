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

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# ۱. وب‌سرور سبک برای زنده نگه‌داشتن سرویس روی رندر
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ۳. مدل‌ها و ساختار نگهداری وضعیت کاربران
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

دستورات فعال در بات:
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
۲. اگر اطلاعات وب در اختیارت قرار گرفت، مستقیماً به آن استناد کن و آخرین اخبار را دقیق بگو؛ حدس نزن و از توهم پرهیز کن.
۳. فرمت LaTeX و علامت دلار ($) اکیداً ممنوع است؛ تمام فرمول‌ها و عبارات را به صورت متن ساده بنویس.
۴. زبان پیش‌فرض فارسی سلیس است.
"""

EXAM_SYSTEM_PROMPT = """
دستورالعمل آزمون زبان انگلیسی (Autonomous English Exam Protocol):
کاربر در جلسه آزمون تستی است و نیاز به یک پاسخ قطعی، بدون معطلی و بدون سردرگمی برای پر کردن پاسخ‌نامه دارد.

قوانین عملیاتی:
۱. تعهد قطعی به انتخاب یک گزینه: تحت هیچ شرایطی خروجی را بدون جواب رها نکن. در هر شرایطی باید دقیقاً یکی از حروف گزینه‌ها (A یا B یا C یا D) انتخاب شود.
۲. سوالات معیوب یا چندجوابی: طبق عرف کنکور و نظر محتمل طراح، استانداردترین گزینه را انتخاب کن.
۳. تله‌های ساختاری پیشرفته: Dangling Modifier، افعال حسی/سببی مجهول و شرطی ترکیبی را با دقت بررسی کن.
۴. نهایت ایجاز: کل تحلیل حداکثر در ۲ سطر کوتاه باشد.
۵. قالب سطر آخر (اجباری):
   RESULT: [Correct Phrase/Word] -> [Option Letter]
"""

HELP_TEXT = """
🤖 <b>راهنمای دستورات دستیار شخصی:</b>

<b>موتورهای هوش مصنوعی:</b>
• /fast : مدل فوق‌سریع Qwen (کارهای روزمره و کدنویسی)
• /smart : مدل فوق‌هوشمند 120B (استدلال سنگین و تحلیلی)
• /gemini : مدل Gemini 3.5 متصل به وب (اخبار روز، شناخت اشخاص و بدون توهم)

<b>جستجوی فوری در وب:</b>
• <code>/web متن</code> یا <code>/search متن</code> : استعلام زنده از وب بدون تغییر مدل جاری
• <code>/testweb نام</code> : مشاهده خروجی خام موتورهای جستجو برای عیب‌یابی

<b>حالت تخصصی آزمون:</b>
• /exam_on : فعال‌سازی حل تست زبان (خروجی تک‌گزینه‌ای و قطعی)
• /exam_off : بازگشت به حالت عمومی

<b>مدیریت حافظه:</b>
• /memory_on : فعال‌سازی حافظه گفتگو
• /memory_off : غیرفعال‌سازی حافظه (حالت مستقل و سبک)
• /clear : پاکسازی تاریخچه مکالمه
"""

# ۵. ابزارهای واکشی و جستجوی وب
def clean_query_for_search(text):
    """حذف ضمایر و افعال عامیانه برای استخراج کلیدواژه‌های خبری دقیق"""
    cleaned = re.sub(r'[؟?!\.,]', '', text)
    slang_words = ['چیشده', 'چی شده', 'کیه', 'کیست', 'کجاست', 'چیکار کرده', 'چه خبر', 'حالش چطوره', 'درباره', 'در مورد']
    for word in slang_words:
        cleaned = cleaned.replace(word, '')
    cleaned = cleaned.strip()
    return cleaned if cleaned else text

def fetch_web_context(query):
    """جستجوی ترکیبی: اول DuckDuckGo و در صورت نیاز فید Google News"""
    search_term = clean_query_for_search(query)
    snippets = []

    # لایه اول: DuckDuckGo
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"{search_term} اخبار", max_results=3))
            if not results:
                results = list(ddgs.text(search_term, max_results=3))
            for r in results:
                snippets.append(f"• {r.get('title', '')}: {r.get('body', '')}")
    except Exception as e:
        print(f"DDGS Error: {e}")

    # لایه دوم (سوپاپ اطمینان): فید اخبار گوگل
    if not snippets:
        try:
            encoded_query = urllib.parse.quote(search_term)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fa&gl=IR&ceid=IR:fa"
            resp = requests.get(rss_url, timeout=5)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall('./channel/item')[:3]:
                    title = item.find('title').text if item.find('title') is not None else ""
                    snippets.append(f"• خبر: {title}")
        except Exception as e:
            print(f"Google News RSS Error: {e}")

    return "\n".join(snippets)

# ۶. تابع ارسال امن پیام با تبدیل تگ‌های HTML
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

# ۷. دستورات کنترلی تلگرام
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
        f"• <b>حالت آزمون:</b> {exam_text}\n\n"
        + HELP_TEXT
    )
    reply_formatted(message, welcome_text)

@bot.message_handler(commands=['help'])
def send_help(message):
    if not is_authorized(message.from_user.id):
        return
    reply_formatted(message, HELP_TEXT)

@bot.message_handler(commands=['fast'])
def switch_to_fast(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_FAST
    reply_formatted(message, "⚡️ <b>مدل فوق‌سریع فعال شد.</b>")

@bot.message_handler(commands=['smart'])
def switch_to_smart(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_SMART
    reply_formatted(message, "🧠 <b>مدل فوق‌هوشمند (120B) فعال شد.</b>")

@bot.message_handler(commands=['gemini'])
def switch_to_gemini(message):
    if not is_authorized(message.from_user.id):
        return
    user_model[message.chat.id] = MODEL_GEMINI
    reply_formatted(message, "🌐 <b>مدل Gemini متصل به وب فعال شد.</b> از این لحظه تمام سوالات از اینترنت بررسی می‌شوند.")

@bot.message_handler(commands=['exam_on'])
def enable_exam_mode(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = True
    reply_formatted(message, "🎯 <b>حالت آزمون فعال شد.</b> خروجی تک‌گزینه‌ای و قطعی.")

@bot.message_handler(commands=['exam_off'])
def disable_exam_mode(message):
    if not is_authorized(message.from_user.id):
        return
    exam_mode_status[message.chat.id] = False
    reply_formatted(message, "⚪️ <b>حالت آزمون غیرفعال شد.</b>")

@bot.message_handler(commands=['memory_on'])
def enable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = True
    reply_formatted(message, "✅ <b>حافظه فعال شد.</b>")

@bot.message_handler(commands=['memory_off'])
def disable_memory(message):
    if not is_authorized(message.from_user.id):
        return
    memory_status[message.chat.id] = False
    chat_memory[message.chat.id] = []
    reply_formatted(message, "❌ <b>حافظه غیرفعال شد.</b>")

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
    query = message.text.replace('/testweb', '').strip() or "امیر نوری"
    bot.send_chat_action(message.chat.id, 'typing')
    data = fetch_web_context(query)
    if data:
        reply_formatted(message, f"🔍 <b>نتایج خام دریافتی از وب:</b>\n\n{data[:1500]}")
    else:
        reply_formatted(message, "❌ وب سرچ پاسخی برنگرداند.")

@bot.message_handler(commands=['web', 'search'])
def handle_quick_search(message):
    if not is_authorized(message.from_user.id):
        return
    
    if not gemini_client:
        reply_formatted(message, "⚠️ متغیر GEMINI_API_KEY در تنظیمات پنل رندر تنظیم نشده است.")
        return

    query = message.text.replace('/web', '').replace('/search', '').strip()
    if not query:
        reply_formatted(message, "لطفاً عبارت مد نظر را بنویسید:\nمثال: <code>/web امیر نوری</code>")
        return

    bot.send_chat_action(message.chat.id, 'typing')
    web_data = fetch_web_context(query)
    prompt = f"بر اساس اطلاعات زنده وب، دقیق و مستند به پرسش پاسخ بده:\n\nاطلاعات وب:\n{web_data}\n\nپرسش: {query}"
    
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
        reply_formatted(message, response.text)
    except Exception as e:
        reply_formatted(message, f"خطا در جستجو: {e}")

# ۸. مدیریت پیام‌های متنی عمومی
@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    user_text = message.text

    try:
        bot.send_chat_action(chat_id, 'typing')

        is_memory_active = memory_status.get(chat_id, True)
        is_exam_active = exam_mode_status.get(chat_id, False)
        selected_model = user_model.get(chat_id, MODEL_FAST)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        assembled_prompt = BASE_SYSTEM_PROMPT
        if is_exam_active:
            assembled_prompt += f"\n\n{EXAM_SYSTEM_PROMPT}"
        assembled_prompt += f"\nاطلاعات سیستمی: زمان سرور: {current_time}"

        # مسیر مدل‌های فوق‌سریع و هوشمند Groq
        if selected_model in [MODEL_FAST, MODEL_SMART]:
            if not groq_client:
                reply_formatted(message, "⚠️ کلید GROQ_API_KEY در تنظیمات رندر تعریف نشده است.")
                return

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

        # مسیر مدل Gemini متصل به وب
        else:
            if not gemini_client:
                reply_formatted(message, "⚠️ کلید GEMINI_API_KEY در تنظیمات رندر تعریف نشده است.")
                return

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

        # ثبت سوابق در حافظه و ارسال پاسخ
        if reply_text and reply_text.strip():
            raw_text = reply_text.strip()
            if is_memory_active:
                if selected_model == MODEL_GEMINI:
                    chat_memory[chat_id].append({"role": "user", "content": user_text})
                chat_memory[chat_id].append({"role": "assistant", "content": raw_text})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]
            reply_formatted(message, raw_text)
        else:
            reply_formatted(message, "پاسخی دریافت نشد.")

    except Exception as e:
        print(f"Chat Execution Error: {e}")
        reply_formatted(message, f"خطا در پردازش: {e}")

print("ربات سه موتوره با قابلیت وب‌سرچ فعال شد...")
bot.infinity_polling()
