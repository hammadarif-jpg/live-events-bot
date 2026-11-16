import os
import hashlib
import re
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(override=True)

raw_url = os.getenv("SUPABASE_URL", "").strip()
parsed = urlparse(raw_url)
SUPABASE_URL = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else raw_url.rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

def generate_event_hash(event: dict) -> str:
    """Creates a unique fingerprint to detect duplicate events across different platforms."""
    clean_artist = re.sub(r'[^a-z0-9]', '', event.get('artist', '').lower())[:15]
    clean_city = re.sub(r'[^a-z0-9]', '', event.get('city', '').lower())[:10]
    date_str = event.get('date', 'TBD')[:10]
    raw_key = f"{clean_artist}_{date_str}_{clean_city}"
    return hashlib.sha256(raw_key.encode()).hexdigest()[:24]

def verify_and_rank_events(events: list, preferred_artists=None) -> list:
    """Filters out canceled/invalid events, removes duplicates in batch, and calculates priority rank."""
    if preferred_artists is None:
        preferred_artists = []

    seen_hashes = set()
    verified_list = []

    for ev in events:
        status = ev.get("status", "").upper()
        if any(bad in status for bad in ["CANCEL", "POSTPONE"]):
            continue

        link = ev.get("ticket_link", "")
        if not link.startswith("http"):
            continue

        ev_hash = generate_event_hash(ev)
        if ev_hash in seen_hashes:
            continue
        seen_hashes.add(ev_hash)
        ev["event_hash"] = ev_hash

        score = ev.get("popularity_score", 50)
        if ev.get("has_presale"):
            score += 20
        if "Ticketmaster" in ev.get("platform", "") or "Live Nation" in ev.get("platform", ""):
            score += 10
        if any(fav.lower() in ev.get("name", "").lower() for fav in preferred_artists):
            score += 30

        ev["rank_score"] = min(100, score)
        verified_list.append(ev)

    verified_list.sort(key=lambda x: x["rank_score"], reverse=True)
    return verified_list

def filter_new_and_save_to_db(events: list) -> list:
    """Checks Supabase REST API for already-notified events and saves only brand-new discoveries."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ Supabase credentials missing in .env — running without DB deduplication.")
        return events

    rest_endpoint = f"{SUPABASE_URL}/rest/v1/discovered_events"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    new_events = []
    for ev in events:
        ev_hash = ev["event_hash"]
        try:
            check_res = requests.get(
                rest_endpoint,
                headers=headers,
                params={"select": "id", "event_hash": f"eq.{ev_hash}"},
                timeout=10
            )
            if check_res.status_code == 200 and len(check_res.json()) > 0:
                continue  # Already stored & notified

            record = {
                "event_hash": ev_hash,
                "name": ev.get("name"),
                "artist": ev.get("artist"),
                "event_date": ev.get("date"),
                "venue": ev.get("venue"),
                "city": ev.get("city"),
                "platform": ev.get("platform"),
                "status": ev.get("status"),
                "presale_info": ev.get("presale"),
                "has_presale": ev.get("has_presale", False),
                "reg_link": ev.get("reg_link"),
                "ticket_link": ev.get("ticket_link"),
                "source": ev.get("source"),
                "rank_score": ev.get("rank_score", 50),
                "notified": True
            }
            ins_res = requests.post(rest_endpoint, headers=headers, json=record, timeout=10)
            if ins_res.status_code in [200, 201, 204]:
                new_events.append(ev)
            else:
                print(f"⚠️ DB Insert Warning ({ins_res.status_code}): {ins_res.text}")
        except Exception as e:
            print(f"⚠️ DB Connection Error for {ev.get('name')}: {e}")

    return new_events