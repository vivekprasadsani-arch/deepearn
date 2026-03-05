from curl_cffi.requests import AsyncSession
import os
import random
import string
from typing import Tuple, Optional, Dict, Any, List
import logging
from database import Database

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, domain="tdjdnsd.vip"):
        self.domain = domain
        self.base_url = f"https://api.{domain}"
        self.origin = f"https://{domain}"
        self.referer = f"https://{domain}/"
        self.request_timeout = int(os.getenv("API_TIMEOUT", "120"))
        register_paths_env = os.getenv("ACCOUNT_REGISTER_PATHS", "/h5/taskBase/biz3/register,/h5/taskBase/register")
        self.register_paths = [p.strip() for p in register_paths_env.split(",") if p.strip()]
        if not self.register_paths:
            self.register_paths = ["/h5/taskBase/biz3/register"]
        self.login_paths = [
            "/h5/taskBase/login",
        ]

        domains_from_env = os.getenv("ACCOUNT_EMAIL_DOMAINS", "mailto.plus,gmail.com")
        self.email_domains = [d.strip() for d in domains_from_env.split(",") if d.strip()]
        if not self.email_domains:
            self.email_domains = ["mailto.plus"]

        self.db = None
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
            try:
                self.db = Database()
            except Exception as e:
                logger.warning(
                    "Database unavailable; running without DB-backed settings (proxy disabled): %s",
                    e
                )
        # Match current browser pattern seen in HAR to reduce anti-bot variance.
        self.user_agent = os.getenv(
            "API_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        )

    def create_session(self) -> AsyncSession:
        """Create an AsyncSession configured with optional proxy."""
        proxy = self._get_proxy()
        proxies = {"http": proxy, "https": proxy} if proxy else None

        if proxy:
            import re
            masked_proxy = re.sub(r':([^@/:]+)@', ':***@', proxy)
            logger.info(f"Initializing session with proxy: {masked_proxy}")

        return AsyncSession(
            impersonate="chrome120",
            proxies=proxies,
            verify=False,
            timeout=self.request_timeout
        )

    def _get_proxy(self) -> Optional[str]:
        """Get proxy string if enabled and ensure protocol is present"""
        if not self.db:
            return None
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

    def _generate_password(self, length=8) -> str:
        """Generate numeric password to maximize backend compatibility."""
        return ''.join(random.choice(string.digits) for _ in range(length))

    def _generate_email(self) -> str:
        """Generate random email using configured domains."""
        username = self._generate_random_string(10)
        domain = random.choice(self.email_domains)
        return f"{username}@{domain}"

    def _generate_uuid(self):
        """Generate UUID for WhatsApp linking (16 chars is standard)"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))

    def _get_common_headers(self, token: Optional[str] = None):
        """Return a dictionary of common headers used across requests"""
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,bn;q=0.8",
            "content-type": "application/json",
            "h5-platform": self.domain,
            "origin": self.origin,
            "referer": self.referer,
            "user-agent": self.user_agent,
            "x-token": token or ""
        }
        return headers

    async def _post_json(
        self,
        session: AsyncSession,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Tuple[Optional[int], Dict[str, Any], str]:
        """Send POST and return (status_code, parsed_json, raw_text)."""
        response = await session.post(url, headers=headers, json=payload, timeout=self.request_timeout)
        raw = response.text or ""
        try:
            data = response.json()
        except Exception:
            data = {}
        return response.status_code, data, raw

    async def register_account(self, referral_code: str) -> Tuple[bool, str, str, str, Optional[AsyncSession]]:
        """
        Register a new account
        Returns: (success, email, password, message, session)
        """
        session = self.create_session()

        email = self._generate_email()
        password = self._generate_password(8)

        headers = self._get_common_headers()
        errors: List[str] = []

        try:
            for index, path in enumerate(self.register_paths):
                url = f"{self.base_url}{path}"
                for _ in range(2):
                    payload = {
                        "email": email,
                        "password": password,
                        "confirmPassword": password,
                        "promo_code": referral_code,
                        "source": None
                    }
                    status_code, data, raw = await self._post_json(session, url, headers, payload)
                    msg = data.get("msg", "").strip() if isinstance(data, dict) else ""
                    code = data.get("code") if isinstance(data, dict) else None

                    if status_code == 200 and code == 0:
                        logger.info(f"Account registered: {email} on {self.domain} via {path}")
                        return True, email, password, "Account created successfully", session

                    detail = msg or (raw[:160] if raw else f"http {status_code}")
                    errors.append(f"{path}: {detail}")
                    logger.warning(
                        "Registration failed on %s via %s (status=%s code=%s): %s",
                        self.domain,
                        path,
                        status_code,
                        code,
                        detail
                    )

                    lower_msg = msg.lower()
                    if "exist" in lower_msg or "already" in lower_msg or "registered" in lower_msg:
                        email = self._generate_email()
                        password = self._generate_password(8)
                        continue
                    # If request reached business logic (e.g., code=7), don't switch endpoint.
                    # Next endpoint is only for true path mismatch situations.
                    if status_code == 200 and isinstance(code, int):
                        await session.close()
                        return False, email, password, f"{path}: {detail}", None
                    break

                if index < len(self.register_paths) - 1 and self._should_try_next_register_path(status_code, msg):
                    continue
                if errors:
                    await session.close()
                    return False, email, password, errors[-1], None

            await session.close()
            fallback_msg = " | ".join(errors[-3:]) if errors else "Unknown error"
            return False, email, password, fallback_msg, None
        except Exception as e:
            logger.error(f"Registration exception on {self.domain}: {e}")
            await session.close()
            return False, email, password, str(e), None

    def _should_try_next_register_path(self, status_code: Optional[int], msg: str) -> bool:
        """Move to next register path only when current path looks unavailable."""
        if status_code in {404, 405, 410, 500, 502, 503, 504}:
            return True
        lower_msg = (msg or "").lower()
        return "not found" in lower_msg and "record not found" not in lower_msg
    
    async def login_account(self, session: AsyncSession, email: str, password: str) -> Tuple[bool, Optional[str], str]:
        """
        Login to account using existing session
        Returns: (success, token, message)
        """
        headers = self._get_common_headers()

        payload = {
            "email": email,
            "password": password
        }

        try:
            errors: List[str] = []
            for path in self.login_paths:
                url = f"{self.base_url}{path}"
                status_code, data, raw = await self._post_json(session, url, headers, payload)
                code = data.get("code") if isinstance(data, dict) else None
                if status_code == 200 and code == 0:
                    token = data.get("data", {}).get("token", "")
                    return True, token, "Login successful"

                msg = data.get("msg", "").strip() if isinstance(data, dict) else ""
                detail = msg or (raw[:160] if raw else f"http {status_code}")
                errors.append(f"{path}: {detail}")
                logger.warning(
                    "Login failed on %s for %s via %s (status=%s code=%s): %s",
                    self.domain,
                    email,
                    path,
                    status_code,
                    code,
                    detail
                )

            return False, None, " | ".join(errors[-3:]) if errors else "Login failed"
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
