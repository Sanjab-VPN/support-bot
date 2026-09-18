import os
import threading
from flask import Flask
import telebot
from groq import Groq

# ۱. وب‌سرور سبک برای فعال ماندن در سرویس رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی امن توکن‌ها از محیط رندر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
تو پشتیبان رسمی، مودب و دقیق هستی.
دستورات:
۱. فقط به فارسی سلیس و بدون لغات انگلیسی پاسخ بده.
۲. پاسخ‌ها کوتاه، کاربردی و زیر ۳ جمله باشند.
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام! پشتیبان هوشمند همیشه آنلاین در خدمت شماست.")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ],
            temperature=0.2,
            max_tokens=250
        )
        bot.reply_to(message, response.choices[0].message.content)

    except Exception as e:
        print(f"Error: {e}")
        # ارسال علت دقیق ارور در تلگرام جهت عیب‌یابی سریع
        bot.reply_to(message, f"علت خطا:\n{e}")

print("ربات در حال اجراست...")
bot.infinity_polling()
