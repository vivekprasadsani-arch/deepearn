from curl_cffi.requests import AsyncSession
import random
import string
from typing import Tuple, Optional
import asyncio
from database import Database

class APIClient:
    def __init__(self, domain="tdjdnsd.vip"):
        self.domain = domain
        self.base_url = f"https://api.{domain}"
        self.origin = f"https://{domain}"
        self.referer = f"https://{domain}/"
        self.db = Database()

    def _get_proxy(self) -> Optional[str]:
        """Get proxy string if enabled"""
        try:
            enabled = self.db.get_setting("proxy_enabled")
            if enabled == "1":
                return self.db.get_setting("proxy_url")
        except:
            return None
        return None
        
    def _generate_random_string(self, length=8):
        """Generate random string for email"""
        letters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(letters) for i in range(length))
    
    def _generate_uuid(self):
        """Generate UUID for WhatsApp linking"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=17))
    
    async def register_account(self, referral_code: str) -> Tuple[bool, str, str, str, Optional[AsyncSession]]:
        """
        Register a new account
        Returns: (success, email, password, message, session)
        """
        # Create a new session for this flow
        proxy = self._get_proxy()
        session = AsyncSession(impersonate="chrome120", proxy=proxy if proxy else None)
        
        username = self._generate_random_string(8)
        email = f"{username}@mailto.plus"
        password = f"{username}@"
        
        url = f"{self.base_url}/h5/taskBase/biz3/register"
        
        headers = {
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
            "x-token": ""
        }
        
        payload = {
            "email": email,
            "password": password,
            "confirmPassword": password,
            "promo_code": referral_code,
            "source": None
        }
        
        try:
            response = await session.post(url, headers=headers, json=payload, timeout=120)
            data = response.json()
            if data.get("code") == 0:
                return True, email, password, "Account created successfully", session
            else:
                await session.close()
                return False, email, password, data.get("msg", "Unknown error"), None
        except Exception as e:
            await session.close()
            return False, email, password, str(e), None
    
    async def login_account(self, session: AsyncSession, email: str, password: str) -> Tuple[bool, Optional[str], str]:
        """
        Login to account using existing session
        Returns: (success, token, message)
        """
        url = f"{self.base_url}/h5/taskBase/login"
        
        headers = {
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
            "x-token": ""
        }
        
        payload = {
            "email": email,
            "password": password
        }
        
        try:
            response = await session.post(url, headers=headers, json=payload, timeout=120)
            data = response.json()
            if data.get("code") == 0:
                token = data.get("data", {}).get("token", "")
                return True, token, "Login successful"
            else:
                return False, None, data.get("msg", "Login failed")
        except Exception as e:
            return False, None, str(e)
    
    async def request_whatsapp_link(self, session: AsyncSession, token: str, phone: str) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Request WhatsApp linking using existing session
        Returns: (success, uuid, otp_code, message)
        """
        device_uuid = self._generate_uuid()
        url = f"{self.base_url}/h5/taskUser/phoneCode"
        
        headers = {
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
            "x-token": token
        }
        
        payload = {
            "uuid": device_uuid,
            "phone": phone,
            "type": 2
        }
        
        try:
            response = await session.post(url, headers=headers, json=payload, timeout=120)
            data = response.json()
            if data.get("code") == 0:
                otp = data.get("data", {}).get("phone_code", "77777777")
                return True, device_uuid, otp, "OTP generated"
            else:
                return False, None, None, data.get("msg", "Failed to get OTP")
        except Exception as e:
            return False, None, None, str(e)
    
    async def check_login_status(self, session: AsyncSession, token: str, device_uuid: str) -> Tuple[bool, str]:
        """
        Check if WhatsApp login is successful using existing session
        Returns: (is_logged_in, message)
        """
        url = f"{self.base_url}/h5/taskUser/scanCodeResult"
        
        headers = {
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
            "x-token": token
        }
        
        payload = {
            "uuid": device_uuid
        }
        
        try:
            response = await session.post(url, headers=headers, json=payload, timeout=120)
            data = response.json()
            
            # code 0 means success, code 88 means "No results yet"
            if data.get("code") == 0:
                return True, "Login successful"
            elif data.get("code") == 88:
                return False, "Waiting for login..."
            else:
                return False, data.get("msg", "Unknown status")
        except Exception as e:
            return False, str(e)

    async def close_session(self, session: AsyncSession):
        """Close session"""
        if session:
            try:
                await session.close()
            except:
                pass
