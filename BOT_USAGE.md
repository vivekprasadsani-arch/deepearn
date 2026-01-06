# Telegram Bot Usage Guide

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the bot:
```bash
python telegram_bot.py
```

## Bot Configuration

- **Bot Token**: `8464284525:AAGFw7y3_au-xCIKxRWEM-64TaIffk1EmqY`
- **Admin ID**: `5742928021`

## Admin Commands

### `/approve <user_id>`
Approve a user to use the bot.

**Example**: `/approve 123456789`

### `/broadcast <message>`
Send a message to all users.

**Example**: `/broadcast সিস্টেম আপডেট হচ্ছে`

## User Commands

### `/start`
Start the bot and check approval status.

### `/mystats`
View today's statistics (Bangladesh timezone).

## User Workflow

1. **Send Referral Code**
   - Send the referral code (e.g., `A884A34A`)
   - Bot will save it for future use

2. **Send Phone Number**
   - Send phone number (digits only, e.g., `8801712345678`)
   - Bot will automatically:
     - Create account with random email/password
     - Login to get token
     - Request WhatsApp link
     - Send 8-digit OTP (default: `77777777`)
     - Monitor login status
     - Confirm when successful

3. **Subsequent Numbers**
   - Just send phone numbers
   - Bot uses the last referral code automatically

## Features

✅ Admin approval system
✅ Referral code management
✅ Background account creation
✅ WhatsApp linking with OTP
✅ Duplicate phone detection
✅ Bangladesh timezone stats
✅ Broadcast messaging

## Database

All data stored in `bot_data.db` (SQLite):
- Users and approval status
- Referral codes
- Accounts (email, password, phone)
- Phone numbers (for duplicate check)

## Notes

- Accounts are created in the background (user doesn't see credentials)
- OTP code is always `77777777` by default
- Login status is checked every 5 seconds for up to 5 minutes
- Phone numbers can only be linked once
