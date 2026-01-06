from curl_cffi.requests import AsyncSession
import random
import string
from typing import Tuple, Optional
import asyncio
import logging
from database import Database

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, domain="tdjdnsd.vip"):
        self.domain = domain
        self.base_url = f"https://api.{domain}"
        self.origin = f"https://{domain}"
        self.referer = f"https://{domain}/"
        self.db = Database()
        # Use a consistent, modern User-Agent
        self.user_agent = "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

    def _get_proxy(self) -> Optional[str]:
        """Get proxy string if enabled"""
        try:
            enabled = self.db.get_setting("proxy_enabled")
            if enabled == "1":
                proxy_url = self.db.get_setting("proxy_url")
                if proxy_url:
                    return proxy_url.strip()
        except Exception as e:
            logger.error(f"Error reading proxy from DB: {e}")
            return None
        return None
        
    def _generate_random_string(self, length=8):
        """Generate random string for email"""
        letters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(letters) for i in range(length))
    
    def _generate_uuid(self):
        """Generate UUID for WhatsApp linking"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=17))
    
    def _get_common_headers(self, token: str = ""):
        """Return a dictionary of common headers used across requests"""
        return {
            "authority": f"api.{self.domain}",
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9,bn;q=0.8",
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": self.user_agent,
            "x-token": token
        }

    async def register_account(self, referral_code: str) -> Tuple[bool, str, str, str, Optional[AsyncSession]]:
        """
        Register a new account
        Returns: (success, email, password, message, session)
        """
        proxy = self._get_proxy()
        if proxy:
            # Mask sensitive parts of the proxy for logging
            masked_proxy = proxy.split('@')[-1] if '@' in proxy else proxy
            logger.info(f"Using proxy: ...@{masked_proxy}")
        
        # Adding verify=False to ignore SSL issues with some proxies
        session = AsyncSession(impersonate="chrome120", proxy=proxy if proxy else None, verify=False)
        
        username = self._generate_random_string(8)
        email = f"{username}@mailto.plus"
        password = f"{username}@"
        
        url = f"{self.base_url}/h5/taskBase/biz3/register"
        headers = self._get_common_headers()
        
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
                logger.info(f"Account registered: {email} on {self.domain}")
                return True, email, password, "Account created successfully", session
            else:
                logger.warning(f"Registration failed on {self.domain}: {data.get('msg')}")
                await session.close()
                return False, email, password, data.get("msg", "Unknown error"), None
        except Exception as e:
            logger.error(f"Registration exception on {self.domain}: {e}")
            await session.close()
            return False, email, password, str(e), None
    
    async def login_account(self, session: AsyncSession, email: str, password: str) -> Tuple[bool, Optional[str], str]:
        """
        Login to account using existing session
        Returns: (success, token, message)
        """
        url = f"{self.base_url}/h5/taskBase/login"
        headers = self._get_common_headers()
        
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
        headers = self._get_common_headers(token)
        
        payload = {
            "uuid": device_uuid,
            "phone": phone,
            "type": 2
        }
        
        try:
            response = await session.post(url, headers=headers, json=payload, timeout=120)
            data = response.json()
            if data.get("code") == 0:
                otp = data.get("data", {}).get("phone_code")
                # If OTP is empty, try a small delay and check if it's really missing
                if not otp:
                     logger.warning(f"OTP missing in initial response for {phone} on {self.domain}. Retrying log check...")
                     # In some cases, success but empty data means blocked or delayed.
                     return True, device_uuid, None, "Link requested but OTP is empty. Please check again."
                
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
        headers = self._get_common_headers(token)
        
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
