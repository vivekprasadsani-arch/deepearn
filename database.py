import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, List, Tuple
import pytz
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.conn_params = {
            "host": os.getenv("SUPABASE_DB_HOST"),
            "database": os.getenv("SUPABASE_DB_NAME"),
            "user": os.getenv("SUPABASE_DB_USER"),
            "password": os.getenv("SUPABASE_DB_PASSWORD"),
            "port": os.getenv("SUPABASE_DB_PORT", "5432")
        }
    
    def get_connection(self):
        """Create a database connection"""
        return psycopg2.connect(**self.conn_params)
    
    def set_setting(self, key: str, value: str):
        """Set a global setting"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO settings (key, value) VALUES (%s, %s) '
                    'ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value',
                    (key, value)
                )
                conn.commit()

    def get_setting(self, key: str) -> Optional[str]:
        """Get a global setting"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT value FROM settings WHERE key = %s', (key,))
                result = cursor.fetchone()
                return result[0] if result else None
    
    def add_user(self, user_id: int):
        """Add a new user"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO users (user_id, created_at) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING',
                    (user_id, datetime.utcnow())
                )
                conn.commit()

    def remove_user(self, user_id: int):
        """Remove a user and their related data"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
                conn.commit()

    def get_user_details(self, user_id: int) -> Optional[dict]:
        """Get user details"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def get_all_users_detailed(self) -> List[dict]:
        """Get all users with approval status"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
                return [dict(row) for row in cursor.fetchall()]
    
    def approve_user(self, user_id: int) -> bool:
        """Approve a user"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('UPDATE users SET approved = 1 WHERE user_id = %s', (user_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    def is_user_approved(self, user_id: int) -> bool:
        """Check if user is approved"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT approved FROM users WHERE user_id = %s', (user_id,))
                result = cursor.fetchone()
                return result and result[0] == 1
    
    def set_referral_code(self, user_id: int, code: str):
        """Set or update referral code for user"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO referral_codes (user_id, code, updated_at) VALUES (%s, %s, %s) '
                    'ON CONFLICT (user_id) DO UPDATE SET code = EXCLUDED.code, updated_at = EXCLUDED.updated_at',
                    (user_id, code, datetime.utcnow())
                )
                conn.commit()
    
    def get_referral_code(self, user_id: int) -> Optional[str]:
        """Get last used referral code for user"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT code FROM referral_codes WHERE user_id = %s', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else None
    
    def add_account(self, user_id: int, email: str, password: str, 
                   phone_number: str, referral_code: str, domain: str) -> int:
        """Add a new account"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    '''INSERT INTO accounts 
                       (user_id, email, password, phone_number, referral_code, domain, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id''',
                    (user_id, email, password, phone_number, referral_code, domain, datetime.utcnow())
                )
                account_id = cursor.fetchone()[0]
                conn.commit()
                return account_id
    
    def update_login_status(self, account_id: int, status: str):
        """Update account login status"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'UPDATE accounts SET login_status = %s WHERE id = %s',
                    (status, account_id)
                )
                conn.commit()

    def is_phone_used(self, phone_number: str, domain: str = None) -> bool:
        """Check if phone number already used for specific domain"""
        if not domain: 
             return False
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 FROM site_phone_numbers WHERE phone_number = %s AND domain = %s', (phone_number, domain))
                return cursor.fetchone() is not None
    
    def add_phone_number(self, phone_number: str, user_id: int, domain: str = None):
        """Add phone number to used list for specific domain"""
        if not domain:
            return
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO site_phone_numbers (phone_number, domain, user_id, created_at) VALUES (%s, %s, %s, %s) '
                    'ON CONFLICT (phone_number, domain) DO NOTHING',
                    (phone_number, domain, user_id, datetime.utcnow())
                )
                conn.commit()
    
    def get_today_stats(self, user_id: int, domain: str = None) -> int:
        """Get count of successfully logged in accounts today (Bangladesh time)"""
        bd_tz = pytz.timezone('Asia/Dhaka')
        now_bd = datetime.now(bd_tz)
        today_start = now_bd.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                if domain:
                    cursor.execute(
                        '''SELECT COUNT(*) FROM accounts 
                           WHERE user_id = %s 
                           AND login_status = 'success'
                           AND domain = %s
                           AND created_at >= %s''',
                        (user_id, domain, today_start)
                    )
                else:
                    cursor.execute(
                        '''SELECT COUNT(*) FROM accounts 
                           WHERE user_id = %s 
                           AND login_status = 'success'
                           AND created_at >= %s''',
                        (user_id, today_start)
                    )
                result = cursor.fetchone()
                return result[0] if result else 0
    
    def get_all_users(self) -> List[int]:
        """Get all user IDs"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT user_id FROM users')
                return [row[0] for row in cursor.fetchall()]

    def add_site(self, domain: str, user_display_name: str):
        """Add a new site"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO sites (domain, user_display_name, created_at) VALUES (%s, %s, %s) '
                    'ON CONFLICT (domain) DO UPDATE SET user_display_name = EXCLUDED.user_display_name',
                    (domain, user_display_name, datetime.utcnow())
                )
                conn.commit()

    def get_sites(self) -> List[dict]:
        """Get all sites"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM sites ORDER BY created_at ASC')
                return [dict(row) for row in cursor.fetchall()]

    def delete_site(self, domain: str):
        """Delete a site"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('DELETE FROM sites WHERE domain = %s', (domain,))
                conn.commit()
