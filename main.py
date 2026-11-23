import os
import hashlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)

DISCORD_WEBHOOK_URL = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
TICKETMASTER_API_KEY = (os.getenv("TICKETMASTER_API_KEY") or "").strip()
SERPER_API_KEY = (os.getenv("SERPER_API_KEY") or "").strip()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip()

PREFERRED_ARTISTS = [
    "taylor swift", "drake", "coldplay", "oasis", "stray kids", "gracie abrams",
    "bruno mars", "the weeknd", "sabrina carpenter", "bad bunny", "morgan wallen",
    "olivia rodrigo", "billie eilish", "kendrick lamar", "lady gaga", "post malone",
    "ed sheeran", "beyonce", "ariana grande", "travis scott", "dua lipa",
    "tame impala", "p!nk", "pink", "billy strings", "deftones", "phoebe bridgers"
]

def parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def get_direct_laylo_seated_signups():
    if not SERPER_API_KEY:
        print("❌ SERPER_API_KEY is missing!")
        return []

    results = []
    seen_urls = set()

    queries = [
        ("laylo.com presale tour", "LAYLO RSVP"),
        ("signup.seated.com presale tour", "SEATED SIGNUP"),
        ("presale rsvp laylo", "LAYLO RSVP"),
        ("presale signup seated", "SEATED SIGNUP"),
    ]

    for q, platform_tag in queries:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 20},
                timeout=15
            )
            if resp.status_code != 200:
                print(f"⚠️ Serper error ({resp.status_code}): {resp.text[:120]}")
                continue

            for item in resp.json().get("organic", []):
                link = (item.get("link") or "").split("?")[0].rstrip("/")
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()

                if not link or link in seen_urls:
                    continue
                if link in ("https://laylo.com", "https://signup.seated.com", "https://www.laylo.com", "https://www.seated.com"):
                    continue

                combined_text = f"{link} {title} {snippet}".lower()
                if "laylo" not in combined_text and "seated" not in combined_text:
                    continue

                seen_urls.add(link)
                uid = hashlib.sha256(link.encode()).hexdigest()[:16]

                results.append({
                    "id": f"rsvp_{uid}",
                    "artist": title[:90] if title else link.split("/")[-1],
                    "city": platform_tag,
                    "when": f"🎟️ {snippet[:95]}" if snippet else f"🎟️ Direct {platform_tag} Page",
                    "link": link,
                    "is_presale": True,
                    "score": 120
                })
        except Exception as e:
            print(f"⚠️ Serper exception: {e}")

    print(f"✅ Direct Laylo & Seated URLs found: {len(results)}")
    return results

def get_ticketmaster_sales():
    if not TICKETMASTER_API_KEY:
        print("❌ Missing TICKETMASTER_API_KEY")
        return []

    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    seen = set()

    for country in ["US", "GB", "CA", "AU", "DE"]:
        params = {
            "apikey": TICKETMASTER_API_KEY,
            "countryCode": country,
            "classificationName": "Music",
            "onsaleStartDateTime": now_str,
            "size": 150
        }
        try:
            r = requests.get("https://app.ticketmaster.com/discovery/v2/events.json", params=params, timeout=15)
            if r.status_code != 200:
                continue

            for ev in r.json().get("_embedded", {}).get("events", []):
                ev_id = ev.get("id")
                if not ev_id or ev_id in seen:
                    continue

                sales = ev.get("sales", {})
                pub_start = parse_iso(sales.get("public", {}).get("startDateTime"))
                presales = sales.get("presales", [])

                active_presales = []
                for p in presales:
                    ps = parse_iso(p.get("startDateTime"))
                    pe = parse_iso(p.get("endDateTime"))
                    if (ps and ps >
