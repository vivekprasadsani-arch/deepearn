import os
import asyncio
import logging
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from database import Database
from api_client import APIClient
import time

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Initialize
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()

# Cache for API clients
api_clients = {}

def get_api_client(domain: str) -> APIClient:
    """Get or create API client for a domain"""
    if domain not in api_clients:
        api_clients[domain] = APIClient(domain)
    return api_clients[domain]

# Migrate initial sites if empty
def migrate_sites():
    sites = db.get_sites()
    if not sites:
        initial_sites = [
            ("tdjdnsd.vip", "Site 1"),
            ("darino.vip", "Site 2"),
            ("valeno.vip", "Site 3")
        ]
        for domain, name in initial_sites:
            db.add_site(domain, name)

migrate_sites()

# Store user states and selected modes
# user_states: user_id -> {"domain": "...", "display_name": "..."}
user_states = {}

# Keyboard Markups
def get_main_menu():
    keyboard = [
        [KeyboardButton("➕ Add WhatsApp")],
        [KeyboardButton("📊 My Stats")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_site_keyboard(is_admin=False):
    sites = db.get_sites()
    keyboard = []
    for site in sites:
        # User sees "Site 1", Admin sees "tdjdnsd.vip"
        label = site['domain'] if is_admin else site['user_display_name']
        keyboard.append([InlineKeyboardButton(label, callback_data=f"site_{site['domain']}")])
    return InlineKeyboardMarkup(keyboard)

def clean_phone_number(phone: str) -> str:
    """Remove +, spaces, parentheses from phone number"""
    import re
    return re.sub(r'[+\s()\-]', '', phone)

def get_registration_hint(message: str) -> str:
    """Return actionable hint for known registration failures."""
    text = (message or "").lower()
    if "record not found" in text:
        return "\n\n💡 রেফার কোডটি এই সাইটের জন্য বৈধ নয়। নতুন/সঠিক রেফার কোড দিন।"
    if "registration is restricted" in text:
        return "\n\n💡 সাইট রেজিস্ট্রেশন রিকোয়েস্ট সীমাবদ্ধ করছে (IP/region/rate limit)। প্রক্সি অন করে আবার চেষ্টা করুন।"
    if "retrieve verification code again" in text:
        return "\n\n💡 সার্ভার ভেরিফিকেশন-চেক চাইছে। কিছুক্ষণ পর পুনরায় চেষ্টা করুন বা প্রক্সি ব্যবহার করুন।"
    return ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    first_name = update.effective_user.first_name or "Unknown"
    
    # Check if this is a new user
    is_new_user = not db.is_user_approved(user_id)
    db.add_user(user_id)
    
    # Set default mode if not set
    if user_id not in user_states:
        user_states[user_id] = {"domain": "tdjdnsd.vip", "display_name": "Site 1"}
    
    if db.is_user_approved(user_id):
        current = user_states.get(user_id)
        mode_text = f"বর্তমান মোড: **{current['display_name']}**" if current else "কোন সাইট সিলেক্ট করা নেই।"
        
        await update.message.reply_text(
            f"✅ আপনি অনুমোদিত ইউজার!\n"
            f"{mode_text}\n\n"
            "নিচের মেনু থেকে কাজ শুরু করুন।",
            reply_markup=get_main_menu(),
            parse_mode='Markdown'
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
    """Handle /approve or /adduser command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("ব্যবহার: /approve <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        db.add_user(target_user_id)
        db.approve_user(target_user_id)
        await update.message.reply_text(f"✅ ইউজার {target_user_id} অনুমোদিত হয়েছে।")
        try:
            await context.bot.send_message(chat_id=target_user_id, text="✅ আপনার অ্যাকাউন্ট অনুমোদিত হয়েছে! এখন বট ব্যবহার শুরু করতে পারেন। /start দিন।")
        except: pass
    except ValueError:
        await update.message.reply_text("❌ সঠিক ইউজার আইডি দিন।")

async def remove_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removeuser command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("ব্যবহার: /removeuser <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        db.remove_user(target_user_id)
        await update.message.reply_text(f"✅ ইউজার {target_user_id} রিমুভ করা হয়েছে।")
    except ValueError:
        await update.message.reply_text("❌ সঠিক ইউজার আইডি দিন।")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /users command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    users = db.get_all_users_detailed()
    if not users:
        await update.message.reply_text("কোন ইউজার পাওয়া যায়নি।")
        return
    
    msg = "👤 **ইউজার লিস্ট:**\n\n"
    for u in users:
        status = "✅ Approved" if u['approved'] else "⏳ Pending"
        msg += f"• `{u['user_id']}` | {status} | {u['created_at'][:10]}\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def add_site_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addsite domain DisplayName"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("ব্যবহার: /addsite <domain> <display_name>\nউদাহরণ: `/addsite test.vip Site 4`", parse_mode='Markdown')
        return
    
    domain = context.args[0]
    display_name = ' '.join(context.args[1:])
    db.add_site(domain, display_name)
    await update.message.reply_text(f"✅ সাইট যুক্ত করা হয়েছে:\nDomain: `{domain}`\nDisplay Name: `{display_name}`", parse_mode='Markdown')

async def del_site_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delsite domain"""
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("ব্যবহার: /delsite <domain>")
        return
    
    domain = context.args[0]
    db.delete_site(domain)
    await update.message.reply_text(f"✅ সাইট `{domain}` ডিলিট করা হয়েছে।", parse_mode='Markdown')

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stats command"""
    user_id = update.effective_user.id
    
    if not db.is_user_approved(user_id):
        return
    
    sites = db.get_sites()
    stats_msg = "📊 **আজকের পরিসংখ্যান:**\n\n"
    total_today = 0
    
    for site in sites:
        domain = site['domain']
        user_label = site['user_display_name']
        admin_label = domain
        
        # Determine labels
        label = admin_label if user_id == ADMIN_ID else user_label
        
        count = db.get_today_stats(user_id, domain)
        stats_msg += f"🔹 {label}: {count}টি\n"
        total_today += count
        
    stats_msg += f"\n📝 মোট: {total_today}টি"
    
    await update.message.reply_text(stats_msg, parse_mode='Markdown')

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

async def proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /proxy command (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ শুধুমাত্র এডমিন এই কমান্ড ব্যবহার করতে পারবেন।")
        return
    
    if not context.args:
        # Show status
        enabled = db.get_setting("proxy_enabled") == "1"
        url = db.get_setting("proxy_url") or "Not set"
        status = "✅ চালু" if enabled else "❌ বন্ধ"
        
        await update.message.reply_text(
            f"🌐 **প্রক্সি সেটিংস**\n\n"
            f"স্ট্যাটাস: {status}\n"
            f"URL: `{url}`\n\n"
            "কমান্ড:\n"
            "`/proxy on` - প্রক্সি চালু করুন\n"
            "`/proxy off` - প্রক্সি বন্ধ করুন\n"
            "`/setproxy <url>` - প্রক্সি সেট করুন\n"
            "Format: `http://user:pass@host:port`",
            parse_mode='Markdown'
        )
        return

    action = context.args[0].lower()
    
    if action == "on":
        if not db.get_setting("proxy_url"):
            await update.message.reply_text("❌ আগে প্রক্সি URL সেট করুন।")
            return
        db.set_setting("proxy_enabled", "1")
        await update.message.reply_text("✅ প্রক্সি চালু করা হয়েছে।")
        
    elif action == "off":
        db.set_setting("proxy_enabled", "0")
        await update.message.reply_text("✅ প্রক্সি বন্ধ করা হয়েছে।")
        
    else:
        await update.message.reply_text("❌ ভুল কমান্ড। ব্যবহার করুন: on / off")

async def set_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setproxy command"""
    if update.effective_user.id != ADMIN_ID:
        return
        
    if not context.args:
        await update.message.reply_text(
            "ব্যবহার: `/setproxy <url>`\n\n"
            "Format Examples:\n"
            "1. `http://1.2.3.4:8080`\n"
            "2. `socks5://user:pass@1.2.3.4:1080`",
            parse_mode='Markdown'
        )
        return
        
    proxy_url = context.args[0].strip()
    db.set_setting("proxy_url", proxy_url)
    await update.message.reply_text(f"✅ প্রক্সি URL সেট করা হয়েছে:\n`{proxy_url}`", parse_mode='Markdown')

async def site_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle site selection from inline keyboard"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    domain = query.data.replace("site_", "")
    
    sites = db.get_sites()
    site = next((s for s in sites if s['domain'] == domain), None)
    
    if not site:
        await query.edit_message_text("❌ সাইটটি খুঁজে পাওয়া যায়নি।")
        return
    
    user_states[user_id] = {"domain": domain, "display_name": site['user_display_name']}
    
    label = site['domain'] if user_id == ADMIN_ID else site['user_display_name']
    
    await query.edit_message_text(
        f"✅ মোড পরিবর্তন করা হয়েছে: **{label}**\n\n"
        f"এখন `{label}` এর জন্য রেফার কোড অথবা ফোন নাম্বার পাঠান।",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages and menu buttons"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not db.is_user_approved(user_id):
        await update.message.reply_text("❌ আপনি অনুমোদিত নন। এডমিনের অনুমোদনের জন্য অপেক্ষা করুন।")
        return

    # Handle Menu Buttons
    if text == "➕ Add WhatsApp":
        is_admin = (user_id == ADMIN_ID)
        await update.message.reply_text(
            "🌐 একটি সাইট সিলেক্ট করুন:",
            reply_markup=get_site_keyboard(is_admin)
        )
        return
        
    if text == "📊 My Stats":
        await mystats(update, context)
        return
    
    # Get current mode
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("❌ আগে \"➕ Add WhatsApp\" বাটনে ক্লিক করে একটি সাইট সিলেক্ট করুন।")
        return
        
    current_mode = state['display_name']
    domain = state['domain']
    label = domain if user_id == ADMIN_ID else current_mode
    
    # Check if it's a referral code (alphanumeric, typically 6+ chars)
    if len(text) >= 6 and text.isalnum() and text.isupper():
        db.set_referral_code(user_id, text)
        await update.message.reply_text(
            f"✅ **{label}** এর জন্য রেফার কোড সংরক্ষিত: `{text}`\n\n"
            "এখন ফোন নাম্বার পাঠান (যেমন: 8801712345678)",
            parse_mode='Markdown'
        )
        return
    
    # Check if it's a phone number (clean and validate)
    cleaned_phone = clean_phone_number(text)
    if cleaned_phone.isdigit() and len(cleaned_phone) >= 10:
        # Run in background via async task
        asyncio.create_task(process_phone_number(update, context, cleaned_phone, state))
        return
    
    await update.message.reply_text(
        f"❓ বর্তমান মোড: **{label}**\n\n"
        "রেফার কোড অথবা ফোন নাম্বার পাঠান।\n"
        "অথবা সাইট পরিবর্তন করুন।",
        parse_mode='Markdown'
    )

async def process_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str, state: dict):
    """Process phone number and link to WhatsApp for specific site"""
    user_id = update.effective_user.id
    domain = state['domain']
    mode_label = domain if user_id == ADMIN_ID else state['display_name']
    
    api = get_api_client(domain)
    
    # Check if phone already used per site
    if db.is_phone_used(phone, domain):
        await update.message.reply_text(f"⚠️ এই নাম্বারটি আগেই **{mode_label}** এ ব্যবহার করা হয়েছে।")
        return
    
    # Get referral code
    referral_code = db.get_referral_code(user_id)
    if not referral_code:
        await update.message.reply_text(f"❌ প্রথমে **{mode_label}** এর জন্য রেফার কোড পাঠান।", parse_mode='Markdown')
        return
    
    status_msg = await update.message.reply_text(f"⏳ [{mode_label}] অ্যাকাউন্ট তৈরি হচ্ছে...")
    
    try:
        # Step 1: Register account
        success, email, password, msg, session = await api.register_account(referral_code)
        
        if not success:
            hint = get_registration_hint(msg)
            await status_msg.edit_text(f"❌ [{mode_label}] অ্যাকাউন্ট তৈরি ব্যর্থ: {msg}{hint}")
            return
        
        try:
            # Step 2: Login
            await status_msg.edit_text(f"⏳ [{mode_label}] লগইন হচ্ছে...")
            success, token, msg = await api.login_account(session, email, password)
            if not success:
                await status_msg.edit_text(f"❌ [{mode_label}] লগইন ব্যর্থ: {msg}")
                return
            
            # Step 3: Request link
            await status_msg.edit_text(f"⏳ [{mode_label}] লিংক রিকোয়েস্ট করা হচ্ছে...")
            success, device_uuid, otp, msg = await api.request_whatsapp_link(session, token, phone)
            if not success:
                await status_msg.edit_text(f"❌ [{mode_label}] লিংক রিকোয়েস্ট ব্যর্থ: {msg}")
                return
            
            # Save pending account
            account_id = db.add_account(user_id, email, password, phone, referral_code, domain)
            
            if not otp:
                await status_msg.edit_text(
                    f"⚠️ [{mode_label}] লিংক রিকোয়েস্ট হয়েছে কিন্তু ওটিপি (OTP) পাওয়া যায়নি।\n\n"
                    f"📱 নাম্বার: {phone}\n"
                    "সম্ভবত আপনার আইপি ব্লক করা হয়েছে অথবা সাইট থেকে ডাটা দিতে দেরি করছে। প্রক্সি ব্যবহার করে পুনরায় চেষ্টা করুন।"
                )
                await api.close_session(session)
                return

            await status_msg.edit_text(
                f"✅ [{mode_label}] লিংক রিকোয়েস্ট সফল!\n\n"
                f"📱 নাম্বার: {phone}\n"
                f"🔐 OTP কোড: {otp}\n\n"
                f"হোয়াটসঅ্যাপে কোডটি দিন। লগইন চেক করা হচ্ছে..."
            )
            
            # Step 4: Monitor
            async def monitor_login(mon_session, mon_token, mon_uuid):
                try:
                    for _ in range(24): # 120s
                        await asyncio.sleep(5)
                        is_logged_in, _ = await api.check_login_status(mon_session, mon_token, mon_uuid)
                        if is_logged_in:
                            db.update_login_status(account_id, "success")
                            db.add_phone_number(phone, user_id, domain)
                            await update.message.reply_text(
                                f"🎉 [{mode_label}] লগইন সফল হয়েছে!\n"
                                f"📱 নাম্বার: {phone}"
                            )
                            return
                    await update.message.reply_text(f"⏱️ [{mode_label}] টাইমআউট: {phone}")
                finally:
                    await api.close_session(mon_session)
            
            asyncio.create_task(monitor_login(session, token, device_uuid))
            
        except Exception as e:
            await api.close_session(session)
            raise e
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ এরর: {str(e)}")

def main():
    """Start the bot"""
    # Start Flask app in a separate thread for Render port binding
    port = int(os.getenv("PORT", 10000))
    flask_app = Flask(__name__)
    
    @flask_app.route("/")
    def health_check():
        return "Bot is running", 200
    
    def run_flask():
        # Disable logging for Flask to keep terminal clean
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask server started on port {port} for Render health checks")

    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("adduser", approve))
    application.add_handler(CommandHandler("removeuser", remove_user_cmd))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("addsite", add_site_cmd))
    application.add_handler(CommandHandler("delsite", del_site_cmd))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("proxy", proxy_command))
    application.add_handler(CommandHandler("setproxy", set_proxy))
    
    # Callback Query Handler
    application.add_handler(CallbackQueryHandler(site_selection_callback, pattern="^site_"))
    
    # Message Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
