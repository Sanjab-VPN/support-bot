import os
import threading
from flask import Flask
import telebot
from groq import Groq

# ۱. وب‌سرور سبک برای فعال نگه داشتن سرویس در رندر
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active and running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ۲. فراخوانی امن متغیرها از رندر
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# پرامپت فشرده برای کاهش مصرف توکن ورودی و خروجی
SYSTEM_PROMPT = """
تو دستیار پشتیبانی رسمی هستی.
قوانین:
۱. فقط به فارسی سلیس و روان بنویس.
۲. بسیار کوتاه، مفید و حداکثر در ۲ الی ۳ جمله پاسخ بده تا سریع باشی.
۳. از مقدمه‌چینی پرهیز کن و مستقیماً به سراغ اصل پاسخ برو.
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "سلام! پشتیبان هوشمند در خدمت شماست. سوال خود را بفرمایید.")

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ],
            temperature=0.3,
            max_tokens=350
        )
        
        reply_text = response.choices[0].message.content
        
        # محافظت در برابر پیام خالی برای جلوگیری از خطای ۴۰۰ تلگرام
        if reply_text and reply_text.strip():
            bot.reply_to(message, reply_text.strip())
        else:
            bot.reply_to(message, "متاسفانه متنی برای پاسخ تولید نشد، لطفاً سوالتان را طور دیگری بپرسید.")

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "سیستم موقتاً پاسخگو نیست؛ لطفاً لحظاتی دیگر تلاش کنید.")

print("ربات در حال اجراست...")
bot.infinity_polling()
