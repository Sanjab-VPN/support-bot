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

# ۱. وب‌سرور سبک برای زنده نگه‌داشتن در رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Hybrid Fast + Web AI Assistant is Online!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی متغیرها و کلاینت‌ها
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ALLOWED_USERS_RAW = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS_RAW.split(",") if uid.strip().isdigit()]

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ۳. متغیرهای حافظه و تنظیمات چت
chat_memory = {}
memory_status = {}
user_engine = {}  # 'groq' یا 'gemini'

def is_authorized(user_id):
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

SYSTEM_PROMPT = """
تو یک دستیار هوش مصنوعی شخصی، هوشمند، سریع و مسلط به تمامی زمینه‌ها هستی.
خروجی تو در تلگرام نمایش داده می‌شود.

قوانین نگارشی:
۱. اگر اطلاعات وب در اختیارت قرار گرفت، مستقیماً به آن استناد کن و از توهم پرهیز کن.
۲. تحت هیچ شرایطی از فرمت LaTeX و علامت دلار ($) استفاده نکن؛ تمام فرمول‌ها را به صورت متن ساده بنویس.
۳. پاسخ‌ها سریع، دقیق و با لحن طبیعی و روان باشند.
"""

HELP_TEXT = """
🤖 <b>راهنمای دستیار هوشمند دوگانه:</b>

⚡ <b>موتورهای پاسخ‌دهی:</b>
• /engine_groq : فعال‌سازی موتور پرسرعت Groq (زیر ۱ ثانیه - مناسب مکالمه و کد)
• /engine_gemini : فعال‌سازی موتور Gemini با اتصال به وب (دقیق، بدون توهم و زنده)

🔍 <b>جستجوی سریع:</b>
• با نوشتن <code>/web متن</code> یا <code>/search متن</code> می‌توانید بدون تغییر موتور، همان یک پیام را مستقیماً در وب جستجو کنید.

🧠 <b>تنظیمات حافظه:</b>
• /memory_on : فعال‌سازی حافظه
• /memory_off : غیرفعال‌سازی حافظه
• /clear : پاکسازی حافظه فعلی
"""

def fetch_web_context(query):
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
    formatted = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', raw_text)
    formatted = re.sub(r'```(.*?)```', r'<pre>\1</pre>', formatted, flags=re.DOTALL)
    formatted = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted)
    try:
        bot.reply_to(telebot.types.Message(message_id=message_id, chat=telebot.types.Chat(chat_id, 'private')), formatted, parse_mode='HTML')
    except ApiTelegramException:
        bot.send_message(chat_id, raw_text)

# دستورات تغییر وضعیت
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_authorized(message.from_user.id):
        return
    chat_id = message.chat.id
    chat_memory[chat_id] = []
    if chat_id not in memory_status:
        memory_status[chat_id] = True
    if chat_id not in user_engine:
        user_engine[chat_id] = "groq"
    
    bot.reply_to(message, f"سلام! دستیار شخصی آماده است.\nموتور فعال: <b>{user_engine[chat_id].upper()}</b>\n\n" + HELP_TEXT, parse_mode='HTML')

@bot.message_handler(commands=['help'])
def send_help(message):
    if not is_authorized(message.from_user.id):
        return
    bot.reply_to(message, HELP_TEXT, parse_mode='HTML')

@bot.message_handler(commands=['engine_groq'])
def switch_groq(message):
    if not is_authorized(message.from_user.id):
        return
    user_engine[message.chat.id] = "groq"
    bot.reply_to(message, "⚡ <b>موتور Groq فعال شد.</b> سرعت پاسخ‌دهی به حداکثر رسید.", parse_mode='HTML')

@bot.message_handler(commands=['engine_gemini'])
def switch_gemini(message):
    if not is_authorized(message.from_user.id):
        return
    user_engine[message.chat.id] = "gemini"
    bot.reply_to(message, "🌐 <b>موتور Gemini + سرچ وب فعال شد.</b> پاسخ‌ها با بررسی زنده اینترنت داده می‌شوند.", parse_mode='HTML')

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
    bot.reply_to(message, "حافظه پاک شد.")

# سرچ تکی و فوری در وب بدون نیاز به تغییر موتور
@bot.message_handler(commands=['web', 'search'])
def handle_quick_search(message):
    if not is_authorized(message.from_user.id):
        return
    
    query = message.text.replace('/web', '').replace('/search', '').strip()
    if not query:
        bot.reply_to(message, "لطفاً عبارت مورد نظر را بعد از دستور بنویسید.\nمثال: <code>/web سام صابری کیه</code>", parse_mode='HTML')
        return

    bot.send_chat_action(message.chat.id, 'typing')
    web_data = fetch_web_context(query)
    prompt = f"با توجه به اطلاعات وب به این موضوع پاسخ بده:\n\nاطلاعات وب:\n{web_data}\n\nپرسش: {query}"
    
    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=800
            )
        )
        format_and_send(message.chat.id, message.message_id, response.text.strip())
    except Exception as e:
        print(f"Search Error: {e}")
        bot.reply_to(message, "خطا در جستجوی اینترنتی.")

# هندلر پیام‌های عادی
@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if not is_authorized(message.from_user.id):
        return

    chat_id = message.chat.id
    current_engine = user_engine.get(chat_id, "groq")
    is_mem = memory_status.get(chat_id, True)
    text = message.text

    bot.send_chat_action(chat_id, 'typing')

    try:
        # ۱. مسیر موتور فوق‌سریع GROQ (پیش‌فرض)
        if current_engine == "groq":
            system_meta = f"{SYSTEM_PROMPT}\nزمان سرور: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            if is_mem:
                if chat_id not in chat_memory:
                    chat_memory[chat_id] = []
                chat_memory[chat_id].append({"role": "user", "content": text})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]
                messages = [{"role": "system", "content": system_meta}] + chat_memory[chat_id]
            else:
                messages = [{"role": "system", "content": system_meta}, {"role": "user", "content": text}]

            resp = groq_client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=messages,
                temperature=0.3,
                max_tokens=800
            )
            ans = resp.choices[0].message.content.strip()

            if is_mem:
                chat_memory[chat_id].append({"role": "assistant", "content": ans})

            format_and_send(chat_id, message.message_id, ans)

        # ۲. مسیر موتور همه‌فن‌حریف GEMINI + سرچ وب
        else:
            web_info = fetch_web_context(text)
            enriched = f"{text}\n\n[اطلاعات وب]:\n{web_info}" if web_info else text

            contents = []
            if is_mem:
                if chat_id not in chat_memory:
                    chat_memory[chat_id] = []
                for m in chat_memory[chat_id]:
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})
                contents.append({"role": "user", "parts": [{"text": enriched}]})
            else:
                contents = [{"role": "user", "parts": [{"text": enriched}]}]

            resp = gemini_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=800
                )
            )
            ans = resp.text.strip()

            if is_mem:
                chat_memory[chat_id].append({"role": "user", "content": text})
                chat_memory[chat_id].append({"role": "assistant", "content": ans})
                if len(chat_memory[chat_id]) > 10:
                    chat_memory[chat_id] = chat_memory[chat_id][-10:]

            format_and_send(chat_id, message.message_id, ans)

    except Exception as e:
        print(f"Chat Error: {e}")
        bot.reply_to(message, "در پردازش پیام خطایی رخ داد. لطفاً دوباره تلاش کنید.")

print("ربات هیبریدی (Groq + Gemini Web) آماده به کار است...")
bot.infinity_polling()
