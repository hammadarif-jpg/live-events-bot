import os
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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

def get_ticketmaster_sales():
    if not TICKETMASTER_API_KEY:
        print("❌ Missing TICKETMASTER_API_KEY")
        return []

    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []
    seen = set()

    markets = ["US", "GB", "CA", "AU", "DE"]
    for country in markets:
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
                print(f"⚠️ TM {country} status {r.status_code}: {r.text[:100]}")
                continue

            events = r.json().get("_embedded", {}).get("events", [])
            for ev in events:
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
                    if (ps and ps > now_utc) or (ps and pe and ps <= now_utc <= pe):
                        active_presales.append((ps or now_utc, p.get("name", "Presale"), p.get("url") or ev.get("url")))

                if not active_presales and not (pub_start and pub_start > now_utc):
                    continue

                seen.add(ev_id)
                attractions = ev.get("_embedded", {}).get("attractions", [])
                artist = attractions[0].get("name") if attractions else ev.get("name", "Unknown")

                venues = ev.get("_embedded", {}).get("venues", [])
                v = venues[0] if venues else {}
                city = f"{v.get('city', {}).get('name', '')}, {country}".strip(", ")

                active_presales.sort(key=lambda x: x[0])
                if active_presales:
                    p_dt, p_name, p_url = active_presales[0]
                    when_str = f"🎟️ Presale ({p_name}): {p_dt.strftime('%b %d, %H:%M UTC')}"
                    link = p_url or ev.get("url", "")
                    is_presale = True
                else:
                    when_str = f"🔥 Public Sale: {pub_start.strftime('%b %d, %H:%M UTC')}"
                    link = ev.get("url", "")
                    is_presale = False

                score = 70 + (25 if is_presale else 0) + (30 if any(a in artist.lower() for a in PREFERRED_ARTISTS) else 0)
                results.append({
                    "id": ev_id,
                    "artist": artist,
                    "city": city,
                    "when": when_str,
                    "link": link,
                    "is_presale": is_presale,
                    "score": score
                })
        except Exception as e:
            print(f"⚠️ TM {country} error: {e}")

    print(f"✅ Ticketmaster collected: {len(results)}")
    return results

def get_presale_signup_news():
    feeds = [
        "https://news.google.com/rss/search?q=%22presale%22+%22sign+up%22+tour+when:2d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22artist+presale%22+OR+%22laylo%22+OR+%22seated%22+tour+when:3d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22presale+registration%22+OR+%22tickets+on+sale%22+tour+when:2d&hl=en-GB&gl=GB&ceid=GB:en",
    ]
    results = []
    seen = set()
    for url in feeds:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:15]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "")[:16]
                if not title or not link:
                    continue
                clean_title = title.split(" - ")[0].strip()
                uid = hashlib.sha256(clean_title.lower().encode()).hexdigest()[:16]
                if uid in seen:
                    continue
                seen.add(uid)
                results.append({
                    "id": f"signup_{uid}",
                    "artist": clean_title[:85],
                    "city": "Global / Tour Signup",
                    "when": f"🆕 Signup Alert ({pub})",
                    "link": link,
                    "is_presale": True,
                    "score": 95
                })
        except Exception as e:
            print(f"⚠️ RSS error: {e}")

    print(f"✅ Presale Signups collected: {len(results)}")
    return results

def filter_new_ids(items):
    """Checks Supabase for already sent IDs; never drops items if DB fails."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return items[:10]

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    new_items = []
    for item in items:
        ev_id = item["id"]
        try:
            check = requests.get(
                f"{SUPABASE_URL}/rest/v1/seen_events?event_id=eq.{ev_id}&select=event_id",
                headers=headers,
                timeout=8
            )
            if check.status_code == 200 and len(check.json()) > 0:
                continue

            requests.post(
                f"{SUPABASE_URL}/rest/v1/seen_events",
                headers=headers,
                json={"event_id": ev_id, "artist": item["artist"][:150], "url": item["link"][:400]},
                timeout=8
            )
            new_items.append(item)
        except Exception:
            new_items.append(item)
    return new_items

def post_to_discord(title, items, color=3066993):
    if not DISCORD_WEBHOOK_URL or not items:
        return
    lines = []
    for i, it in enumerate(items[:10], 1):
        lines.append(
            f"**{i}. {it['artist']}** — `{it['city']}`\n"
            f"   {it['when']}\n"
            f"   🔗 [Open Signup / Ticket Page]({it['link']})"
        )
    payload = {
        "embeds": [{
            "title": title,
            "description": "\n\n".join(lines),
            "color": color,
            "footer": {"text": f"24/7 Presale Radar • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}
        }]
    }
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=12)
    print(f"📨 Discord '{title}' status: {r.status_code}")

def run():
    print("🚀 Running Self-Contained Presale & High-Sale Radar...")
    all_items = get_presale_signup_news() + get_ticketmaster_sales()

    # Deduplicate by artist + city
    unique = {}
    for it in all_items:
        key = f"{it['artist'].lower()}|{it['city'].lower()}"
        if key not in unique or it["score"] > unique[key]["score"]:
            unique[key] = it

    ranked = sorted(unique.values(), key=lambda x: x["score"], reverse=True)
    print(f"🛡️ Total unique verified sales/signups: {len(ranked)}")

    new_items = filter_new_ids(ranked)
    print(f"🆕 Brand-new alerts: {len(new_items)}")

    if new_items:
        post_to_discord("🆕 NEW PRESALE SIGNUPS & TOUR ANNOUNCEMENTS!", new_items[:10], color=3066993)

    if ranked:
        post_to_discord("⚡ HOURLY HIGH-DEMAND SALE & PRESALE RADAR", ranked[:10], color=15105570)
    else:
        post_to_discord("⚡ HOURLY RADAR STATUS", [{"artist": "No events returned from API", "city": "Check Logs", "when": "Verify API Key", "link": "https://developer.ticketmaster.com"}], color=15158332)

if __name__ == "__main__":
    run()
