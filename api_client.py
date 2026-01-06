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
        """Get proxy string if enabled and ensure protocol is present"""
        try:
            enabled = self.db.get_setting("proxy_enabled")
            if enabled == "1":
                proxy_url = self.db.get_setting("proxy_url")
                if proxy_url:
                    proxy_url = proxy_url.strip()
                    # If no protocol specified, default to http://
                    if "://" not in proxy_url:
                        # For abcproxy and similar, often they are socks5, but we'll default to http
                        # and let the user know if it fails.
                        proxy_url = f"http://{proxy_url}"
                    return proxy_url
        except Exception as e:
            logger.error(f"Error reading proxy from DB: {e}")
            return None
        return None
        
    def _generate_random_string(self, length=8):
        """Generate random string for email"""
        letters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(letters) for i in range(length))
    
    def _generate_uuid(self):
        """Generate UUID for WhatsApp linking (16 chars is standard)"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    
    def _get_common_headers(self, token: str = ""):
        """Return a dictionary of common headers used across requests"""
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9,bn;q=0.8",
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "user-agent": self.user_agent
        }
        if token:
            headers["x-token"] = token
        return headers

    async def register_account(self, referral_code: str) -> Tuple[bool, str, str, str, Optional[AsyncSession]]:
        """
        Register a new account
        Returns: (success, email, password, message, session)
        """
        proxy = self._get_proxy()
        proxies = {"http": proxy, "https": proxy} if proxy else None
        
        if proxy:
            import re
            masked_proxy = re.sub(r':([^@/:]+)@', ':***@', proxy)
            logger.info(f"Initializing session with proxy: {masked_proxy}")
        
        # Using proxies dict and verify=False for proxy compatibility
        session = AsyncSession(
            impersonate="chrome120", 
            proxies=proxies, 
            verify=False,
            timeout=120
        )
        
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
                logger.warning(f"Login failed on {self.domain} for {email}: {data.get('msg')} (Response: {response.text})")
                return False, None, data.get("msg", "Login failed")
        except Exception as e:
            logger.error(f"Login exception on {self.domain}: {e}")
            return False, None, str(e)
    
    
    def _get_country_code(self, phone: str) -> str:
        """Extract country code from phone number"""
        cleaned = phone.replace('+', '').strip()
        # Common country codes mapping
        # Sorted by length desc to match longer codes first (e.g. 1 vs 1242)
        codes = sorted(['1', '880', '91', '44', '60', '62', '84', '92', '55', '7'], key=len, reverse=True)
        for code in codes:
            if cleaned.startswith(code):
                return code
        return "1" # Default to US/Canada if unknown

    async def request_whatsapp_link(self, session: AsyncSession, token: str, phone: str) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Request WhatsApp linking using existing session
        Returns: (success, uuid, otp_code, message)
        """
        device_uuid = self._generate_uuid()
        url = f"{self.base_url}/h5/taskUser/phoneCode"
        headers = self._get_common_headers(token)
        
        # Ensure phone has + if it's missing
        formatted_phone = phone if phone.startswith("+") else f"+{phone}"
        country_code = self._get_country_code(formatted_phone)
        
        payload = {
            "uuid": device_uuid,
            "phone": formatted_phone,
            "type": 2,
            "country_code": country_code,
            "lang": "en"
        }
        
        try:
            response = await session.post(url, headers=headers, json=payload, timeout=120)
            data = response.json()
            if data.get("code") == 0:
                otp = data.get("data", {}).get("phone_code")
                # If OTP is empty, try a small delay and check if it's really missing
                if not otp:
                     logger.warning(f"OTP missing in initial response for {phone} on {self.domain}. Response: {response.text}")
                     # In some cases, success but empty data means blocked or delayed.
                     return True, device_uuid, None, "Link requested but OTP is empty. Please check again."
                
                return True, device_uuid, otp, "OTP generated"
            else:
                logger.warning(f"Link request failed on {self.domain} for {phone}: {data.get('msg')} (Response: {response.text})")
                return False, None, None, data.get("msg", "Failed to get OTP")
        except Exception as e:
            logger.error(f"Link request exception on {self.domain}: {e}")
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
