import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from database import Database
from api_client import APIClient
import time

# Configuration
BOT_TOKEN = "8464284525:AAGFw7y3_au-xCIKxRWEM-64TaIffk1EmqY"
ADMIN_ID = 5742928021

# Initialize
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database("bot_data_darino.db")
api = APIClient("darino.vip")

# Store user states
user_states = {}

def clean_phone_number(phone: str) -> str:
    """Remove +, spaces, parentheses from phone number"""
    import re
    return re.sub(r'[+\s()\-]', '', phone)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    first_name = update.effective_user.first_name or "Unknown"
    
    # Check if this is a new user
    is_new_user = not db.is_user_approved(user_id)
    db.add_user(user_id)
    
    if db.is_user_approved(user_id):
        await update.message.reply_text(
            "✅ আপনি অনুমোদিত ইউজার!\n\n"
            "রেফার কোড পাঠান অথবা ফোন নাম্বার পাঠান।\n\n"
            "কমান্ড:\n"
            "/mystats - আজকের পরিসংখ্যান দেখুন"
        )
    else:
        await update.message.reply_text(
            "⏳ আপনার অ্যাকাউন্ট এখনো অনুমোদিত নয়।\n"
            "এডমিনের অনুমোদনের জন্য অপেক্ষা করুন।"
        )
        
        # Notify admin about new user
        if is_new_user:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🆕 নতুন ইউজার!\n\n"
                         f"👤 নাম: {first_name}\n"
                         f"🆔 Username: @{username}\n"
                         f"🔢 User ID: {user_id}\n\n"
                         f"অনুমোদন করতে: /approve {user_id}"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /approve command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ শুধুমাত্র এডমিন এই কমান্ড ব্যবহার করতে পারবেন।")
        return
    
    if not context.args:
        await update.message.reply_text("ব্যবহার: /approve <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        db.add_user(target_user_id)
        db.approve_user(target_user_id)
        await update.message.reply_text(f"✅ ইউজার {target_user_id} অনুমোদিত হয়েছে।")
    except ValueError:
        await update.message.reply_text("❌ সঠিক ইউজার আইডি দিন।")

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mystats command"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text("❌ আপনি অনুমোদিত নন।")
        return
    
    count = db.get_today_stats(user_id)
    await update.message.reply_text(f"📊 আজকে যুক্ত হয়েছে: {count}টি নাম্বার")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ শুধুমাত্র এডমিন এই কমান্ড ব্যবহার করতে পারবেন।")
        return
    
    if not context.args:
        await update.message.reply_text("ব্যবহার: /broadcast <message>")
        return
    
    message = ' '.join(context.args)
    users = db.get_all_users()
    
    success = 0
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=f"📢 {message}")
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
    
    await update.message.reply_text(f"✅ {success}/{len(users)} জন ইউজারকে মেসেজ পাঠানো হয়েছে।")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text("❌ আপনি অনুমোদিত নন। এডমিনের অনুমোদনের জন্য অপেক্ষা করুন।")
        return
    
    # Check if it's a referral code (alphanumeric, typically 8 chars)
    if len(text) >= 6 and text.isalnum() and text.isupper():
        db.set_referral_code(user_id, text)
        await update.message.reply_text(
            f"✅ রেফার কোড সংরক্ষিত হয়েছে: {text}\n\n"
            "এখন ফোন নাম্বার পাঠান (যেমন: 8801712345678)"
        )
        return
    
    # Check if it's a phone number (clean and validate)
    cleaned_phone = clean_phone_number(text)
    if cleaned_phone.isdigit() and len(cleaned_phone) >= 10:
        # Run in background to allow concurrent processing
        asyncio.create_task(process_phone_number(update, context, cleaned_phone))
        return
    
    await update.message.reply_text(
        "❓ রেফার কোড অথবা ফোন নাম্বার পাঠান।\n\n"
        "রেফার কোড: বড় হাতের অক্ষর এবং সংখ্যা (যেমন: A884A34A)\n"
        "ফোন নাম্বার: শুধু সংখ্যা (যেমন: 8801712345678)"
    )

async def process_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    """Process phone number and link to WhatsApp"""
    user_id = update.effective_user.id
    
    # Check if phone already used
    if db.is_phone_used(phone):
        await update.message.reply_text("⚠️ এই নাম্বারটি আগেই যুক্ত করা হয়েছে।")
        return
    
    # Get referral code
    referral_code = db.get_referral_code(user_id)
    if not referral_code:
        await update.message.reply_text("❌ প্রথমে রেফার কোড পাঠান।")
        return
    
    status_msg = await update.message.reply_text("⏳ অ্যাকাউন্ট তৈরি হচ্ছে...")
    
    # Step 1: Register account (gets a new session)
    success, email, password, msg, session = await api.register_account(referral_code)
    
    if not success:
        await status_msg.edit_text(f"❌ অ্যাকাউন্ট তৈরি ব্যর্থ: {msg}")
        return
    
    try:
        # Step 2: Login to get token
        await status_msg.edit_text("⏳ লগইন হচ্ছে...")
        success, token, msg = await api.login_account(session, email, password)
        if not success:
            await status_msg.edit_text(f"❌ লগইন ব্যর্থ: {msg}")
            return
        
        # Step 3: Request WhatsApp link
        await status_msg.edit_text("⏳ হোয়াটসঅ্যাপ লিংক রিকোয়েস্ট করা হচ্ছে...")
        success, device_uuid, otp, msg = await api.request_whatsapp_link(session, token, phone)
        if not success:
            await status_msg.edit_text(f"❌ লিংক রিকোয়েস্ট ব্যর্থ: {msg}")
            return
        
        # Save account to database
        account_id = db.add_account(user_id, email, password, phone, referral_code)
        
        # Send OTP to user
        await status_msg.edit_text(
            f"✅ হোয়াটসঅ্যাপ লিংক রিকোয়েস্ট সফল!\n\n"
            f"📱 নাম্বার: {phone}\n"
            f"🔐 OTP কোড: {otp}\n\n"
            f"হোয়াটসঅ্যাপে এই কোড প্রবেশ করান।\n"
            f"লগইন স্ট্যাটাস চেক করা হচ্ছে..."
        )
        
        # Step 4: Poll for login status (in background)
        # We need to keep session alive for monitoring or create new one?
        # Actually check_login_status needs session. 
        # We should pass the session to the background task, and the background task should close it when done.
        
        async def monitor_login(mon_session, mon_token, mon_uuid):
            try:
                max_attempts = 24  # 120 seconds (5 second intervals)
                for attempt in range(max_attempts):
                    await asyncio.sleep(5)
                    
                    is_logged_in, status_msg_text = await api.check_login_status(mon_session, mon_token, mon_uuid)
                    
                    if is_logged_in:
                        db.update_login_status(account_id, "success")
                        db.add_phone_number(phone, user_id)
                        await update.message.reply_text(
                            f"🎉 লগইন সফল হয়েছে!\n\n"
                            f"📱 নাম্বার: {phone}\n"
                            f"✅ অ্যাকাউন্ট সফলভাবে যুক্ত হয়েছে।"
                        )
                        return
                
                # Timeout
                await update.message.reply_text(
                    f"⏱️ টাইমআউট: {phone}\n\n"
                    f"লগইন কনফার্ম হয়নি। পরে আবার চেষ্টা করুন।"
                )
            finally:
                # Close session when done monitoring
                await api.close_session(mon_session)
        
        # Start monitoring in background
        # Pass session ownership to the background task
        asyncio.create_task(monitor_login(session, token, device_uuid))
        
    except Exception as e:
        # If any error falls through before passing to monitor, close session
        await api.close_session(session)
        logger.error(f"Error processing number: {e}")
        await status_msg.edit_text(f"❌ এরর: {str(e)}")

def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
