import os
import logging
from supabase import create_client, Client
from datetime import datetime
from typing import Optional, List
import pytz
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        if not url or not key:
            logger.error("SUPABASE_URL or SUPABASE_KEY missing from environment variables")
            raise ValueError("Supabase configuration missing")
        self.client: Client = create_client(url, key)
    
    def set_setting(self, key: str, value: str):
        """Set a global setting"""
        try:
            self.client.table("settings").upsert({"key": key, "value": value}).execute()
        except Exception as e:
            logger.error(f"Error setting setting {key}: {e}")

    def get_setting(self, key: str) -> Optional[str]:
        """Get a global setting"""
        try:
            response = self.client.table("settings").select("value").eq("key", key).execute()
            return response.data[0]["value"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None
    
    def add_user(self, user_id: int):
        """Add a new user"""
        try:
            self.client.table("users").upsert({
                "user_id": int(user_id), 
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")

    def remove_user(self, user_id: int):
        """Remove a user and their related data"""
        try:
            self.client.table("users").delete().eq("user_id", int(user_id)).execute()
            self.client.table("referral_codes").delete().eq("user_id", int(user_id)).execute()
        except Exception as e:
            logger.error(f"Error removing user {user_id}: {e}")

    def get_user_details(self, user_id: int) -> Optional[dict]:
        """Get user details"""
        try:
            response = self.client.table("users").select("*").eq("user_id", int(user_id)).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user details {user_id}: {e}")
            return None

    def get_all_users_detailed(self) -> List[dict]:
        """Get all users with approval status"""
        try:
            response = self.client.table("users").select("*").order("created_at", desc=True).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting all users detailed: {e}")
            return []
    
    def approve_user(self, user_id: int) -> bool:
        """Approve a user"""
        try:
            response = self.client.table("users").update({"approved": 1}).eq("user_id", int(user_id)).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error approving user {user_id}: {e}")
            return False
    
    def is_user_approved(self, user_id: int) -> bool:
        """Check if user is approved"""
        try:
            response = self.client.table("users").select("approved").eq("user_id", int(user_id)).execute()
            return response.data and response.data[0]["approved"] == 1
        except Exception as e:
            logger.error(f"Error checking approval {user_id}: {e}")
            return False
    
    def set_referral_code(self, user_id: int, code: str):
        """Set or update referral code for user"""
        try:
            self.client.table("referral_codes").upsert({
                "user_id": int(user_id), 
                "code": code, 
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error setting referral code {user_id}: {e}")
    
    def get_referral_code(self, user_id: int) -> Optional[str]:
        """Get last used referral code for user"""
        try:
            response = self.client.table("referral_codes").select("code").eq("user_id", int(user_id)).execute()
            return response.data[0]["code"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting referral code {user_id}: {e}")
            return None
    
    def add_account(self, user_id: int, email: str, password: str, 
                   phone_number: str, referral_code: str, domain: str) -> int:
        """Add a new account"""
        try:
            response = self.client.table("accounts").insert({
                "user_id": int(user_id),
                "email": email,
                "password": password,
                "phone_number": phone_number,
                "referral_code": referral_code,
                "domain": domain,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            return response.data[0]["id"] if response.data else 0
        except Exception as e:
            logger.error(f"Error adding account for user {user_id}: {e}")
            return 0
    
    def update_login_status(self, account_id: int, status: str):
        """Update account login status"""
        try:
            self.client.table("accounts").update({"login_status": status}).eq("id", account_id).execute()
        except Exception as e:
            logger.error(f"Error updating login status for account {account_id}: {e}")

    def is_phone_used(self, phone_number: str, domain: str = None) -> bool:
        """Check if phone number already used for specific domain"""
        if not domain: 
             return False
        try:
            response = self.client.table("site_phone_numbers")\
                .select("phone_number")\
                .eq("phone_number", phone_number)\
                .eq("domain", domain)\
                .execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking phone use {phone_number}: {e}")
            return False
    
    def add_phone_number(self, phone_number: str, user_id: int, domain: str = None):
        """Add phone number to used list for specific domain"""
        if not domain:
            return
        try:
            self.client.table("site_phone_numbers").upsert({
                "phone_number": phone_number,
                "domain": domain,
                "user_id": int(user_id),
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error adding phone number {phone_number}: {e}")
    
    def get_today_stats(self, user_id: int, domain: str = None) -> int:
        """Get count of successfully logged in accounts today (Bangladesh time)"""
        try:
            bd_tz = pytz.timezone('Asia/Dhaka')
            now_bd = datetime.now(bd_tz)
            today_start = now_bd.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).isoformat()
            
            query = self.client.table("accounts")\
                .select("id", count="exact")\
                .eq("user_id", int(user_id))\
                .eq("login_status", "success")\
                .gte("created_at", today_start)
            
            if domain:
                query = query.eq("domain", domain)
                
            response = query.execute()
            return response.count if response.count is not None else 0
        except Exception as e:
            logger.error(f"Error getting stats for user {user_id}: {e}")
            return 0
    
    def get_all_users(self) -> List[int]:
        """Get all user IDs"""
        try:
            response = self.client.table("users").select("user_id").execute()
            return [row["user_id"] for row in response.data]
        except Exception as e:
            logger.error(f"Error getting all user IDs: {e}")
            return []

    def add_site(self, domain: str, user_display_name: str):
        """Add a new site"""
        try:
            self.client.table("sites").upsert({
                "domain": domain,
                "user_display_name": user_display_name,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as e:
            logger.error(f"Error adding site {domain}: {e}")

    def get_sites(self) -> List[dict]:
        """Get all sites"""
        try:
            response = self.client.table("sites").select("*").order("created_at", asc=True).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting sites: {e}")
            return []

    def delete_site(self, domain: str):
        """Delete a site"""
        try:
            self.client.table("sites").delete().eq("domain", domain).execute()
        except Exception as e:
            logger.error(f"Error deleting site {domain}: {e}")
