import os
import json
import requests
import time
from requests.auth import HTTPBasicAuth

# --- الإعدادات: بتتقرا من GitHub Secrets / Environment Variables ---
H1_USERNAME = os.environ["H1_USERNAME"]
H1_PASSWORD = os.environ["H1_PASSWORD"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

# مسار نسبي جوه الريبو نفسه عشان نقدر نعمله commit تاني بعد كل run
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h1_scopes_db.json")


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


def send_discord_alert(title, description, url):
    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "url": url,
            "color": 15105570,  # لون برتقالي مميز للـ Scopes الجديدة
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    except Exception as e:
        print(f"[-] Discord alert failed: {e}")


def get_program_scopes(handle):
    """يدخل جوه كل برنامج ويقشر الـ Wildcards, Domains, URLs (سواء Bounty أو VDP)"""
    url = f"https://api.hackerone.com/v1/hackers/programs/{handle}"
    scopes = []
    TARGET_TYPES = ["URL", "WILDCARD", "Domain"]

    try:
        response = requests.get(url, auth=HTTPBasicAuth(H1_USERNAME, H1_PASSWORD), timeout=20)
        if response.status_code == 200:
            structured_scopes = response.json().get("relationships", {}).get("structured_scopes", {}).get("data", [])
            for scope in structured_scopes:
                attributes = scope.get("attributes", {})
                asset_id = attributes.get("asset_identifier")
                asset_type = attributes.get("asset_type")

                if asset_id and (asset_type in TARGET_TYPES):
                    scopes.append(asset_id)
        time.sleep(0.1)  # تأخير خفيف عشان الـ Rate Limit للـ API
    except Exception:
        pass
    return scopes


def monitor_h1_advanced():
    db = load_db()
    is_first_run = (len(db) == 0)
    all_programs = []
    page = 1
    per_page = 100

    print("[*] Syncing ALL HackerOne Programs (Bounty + VDP)...")

    while True:
        url = "https://api.hackerone.com/v1/hackers/programs"
        params = {
            "page[size]": per_page,
            "page[number]": page
        }
        try:
            response = requests.get(url, auth=HTTPBasicAuth(H1_USERNAME, H1_PASSWORD), params=params, timeout=20)
            if response.status_code != 200:
                break
            data = response.json().get("data", [])
            if not data:
                break
            all_programs.extend(data)
            page += 1
            time.sleep(0.1)
        except Exception:
            break

    print(f"[+] Total programs fetched: {len(all_programs)}. Processing target diffs...")

    for program in all_programs:
        handle = program['attributes']['handle']
        name = program['attributes']['name']
        program_url = f"https://hackerone.com/{handle}"

        if handle not in db or (not db[handle].get("scopes") and handle in db):
            current_scopes = get_program_scopes(handle)

            if handle not in db:
                db[handle] = {"name": name, "scopes": current_scopes}
            else:
                db[handle]["scopes"] = current_scopes

            if not is_first_run and current_scopes:
                scopes_text = "\n".join([f"• `{s}`" for s in current_scopes])
                send_discord_alert(
                    title=f"🚨 New Scope Fetched: {name}",
                    description=f"**Assets Detected (Bounty/VDP):**\n{scopes_text}",
                    url=program_url
                )

        else:
            old_scopes = db[handle].get("scopes", [])
            current_scopes = get_program_scopes(handle)
            new_scopes_detected = [s for s in current_scopes if s not in old_scopes]

            if new_scopes_detected:
                db[handle]["scopes"] = current_scopes
                if not is_first_run:
                    scopes_text = "\n".join([f"• `{s}`" for s in new_scopes_detected])
                    send_discord_alert(
                        title=f"🔥 New Web Scope Added to {name}!",
                        description=f"**Assets:**\n{scopes_text}",
                        url=program_url
                    )

    save_db(db)
    print("[+] Database Sync Complete successfully.")


if __name__ == "__main__":
    monitor_h1_advanced()
