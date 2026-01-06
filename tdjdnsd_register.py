import requests
import random
import string
import pandas as pd
import os
import time

def generate_random_string(length=8):
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def register_account(invite_code, session):
    username = generate_random_string(8)
    email = f"{username}@mailto.plus"
    password = f"{username}@"
    
    url = "https://api.tdjdnsd.vip/h5/taskBase/biz3/register"
    
    headers = {
        "authority": "api.tdjdnsd.vip",
        "accept": "*/*",
        "accept-language": "en-GB,en;q=0.9,es-US;q=0.8,es;q=0.7",
        "content-type": "application/json",
        "h5-platform": "tdjdnsd.vip",
        "origin": "https://tdjdnsd.vip",
        "referer": "https://tdjdnsd.vip/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36",
        "x-token": ""
    }
    
    payload = {
        "email": email,
        "password": password,
        "confirmPassword": password,
        "promo_code": invite_code,
        "source": None
    }
    
    try:
        response = session.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        if data.get("code") == 0:
            return True, email, password, "Success"
        else:
            return False, email, password, data.get("msg", "Unknown error")
    except Exception as e:
        return False, email, password, str(e)

def main():
    print("=== tdjdnsd.vip Auto Register Tool ===")
    invite_code = input("Enter Invitation Code: ").strip()
    try:
        count_input = input("How many accounts to create?: ").strip()
        count = int(count_input)
    except ValueError:
        print("Invalid number.")
        return

    accounts = []
    session = requests.Session()
    
    success_count = 0
    for i in range(count):
        print(f"[{i+1}/{count}] Registering...", end="\r")
        success, email, password, msg = register_account(invite_code, session)
        if success:
            accounts.append({"Email": email, "Password": password, "Status": "Success"})
            success_count += 1
            print(f"[{i+1}/{count}] Success: {email}")
        else:
            accounts.append({"Email": email, "Password": password, "Status": f"Failed: {msg}"})
            print(f"[{i+1}/{count}] Failed: {email} ({msg})")
        
        # Add a small delay to avoid being flagged
        time.sleep(1)

    if accounts:
        file_path = "tdjdnsd_Accounts.xlsx"
        existing_data = pd.DataFrame()
        
        if os.path.exists(file_path):
            try:
                existing_data = pd.read_excel(file_path)
            except:
                pass
        
        new_df = pd.DataFrame(accounts)
        final_df = pd.concat([existing_data, new_df], ignore_index=True)
            
        final_df.to_excel(file_path, index=False)
        print(f"\nSaved {success_count} successful accounts to {file_path}")
    else:
        print("\nNo accounts created.")

if __name__ == "__main__":
    main()
