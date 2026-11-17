import os
import re
import hashlib
import requests
from urllib.parse import unquote
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

def get_direct_laylo_seated_signups():
    """Scrapes real direct laylo.com and signup.seated.com RSVP pages from web search."""
    results = []
    seen_urls = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    search_queries = [
        ("site:laylo.com presale OR tour OR rsvp", "LAYLO RSVP"),
        ("site:signup.seated.com presale OR tour", "SEATED SIGNUP"),
        ("site:laylo.com/m/ 2026 OR 2027", "LAYLO RSVP"),
        ("site:signup.seated.com/events/", "SEATED SIGNUP"),
    ]

    for q, platform_tag in search_queries:
        try:
            resp = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": q, "df": "w"},  # df=w means past week only!
                headers=headers,
                timeout=15
            )
            if resp.status_code != 200:
                print(f"⚠️ DDG status {resp.status_code} for {q}")
                continue

            html = resp.text
            # Extract result links & titles from DuckDuckGo HTML
            blocks = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
            for raw_href, raw_title in blocks:
                # Decode DuckDuckGo redirect URL if wrapped in uddg=
                if "uddg=" in raw_href:
                    m = re.search(r'uddg=([^&]+)', raw_href)
                    clean_url = unquote(m.group(1)) if m else raw_href
                else:
                    clean_url = raw_href

                if "laylo.com" not in clean_url and "seated.com" not in clean_url:
                    continue

                clean_url = clean_url.split("?")[0].rstrip("/")
                if clean_url in seen_urls or clean_url in ("https://laylo.com", "https://signup.seated.com"):
                    continue
                seen_urls.add(clean_url)

                title = re.sub(r"<[^>]+>", "", raw_title).strip()
                if not title:
                    title = clean_url.split("/")[-1]

                uid = hashlib.sha256(clean_url.encode()).hexdigest()[:16]
                results.append({
                    "id": f"rsvp_{uid}",
                    "artist": title[:90],
                    "city": platform_tag,
                    "when": f"🎟️ Direct {platform_tag} Page",
                    "link": clean_url,
                    "is_presale": True,
                    "score": 120
                })
        except Exception as e:
            print(f"⚠️ Search error for {q}: {e}")

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

def filter_new_ids(items):
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
            f"   🔗 [Open Signup / Ticket Link]({it['link']})"
        )
    payload = {
        "embeds": [{
            "title": title,
            "description": "\n\n".join(lines),
            "color": color,
            "footer": {"text": f"24/7 Presale Radar • {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=12)

def run():
    print("🚀 Running Direct Laylo/Seated + Ticketmaster Radar...")
    signups = get_direct_laylo_seated_signups()
    tm_sales = get_ticketmaster_sales()

    new_signups = filter_new_ids(signups)
    if new_signups:
        post_to_discord("🎟️ NEW LAYLO & SEATED PRESALE SIGNUPS!", new_signups[:10], color=10181046)
    elif signups:
        post_to_discord("🎟️ ACTIVE LAYLO & SEATED SIGNUP LINKS", signups[:10], color=10181046)

    unique_tm = {}
    for it in tm_sales:
        key = f"{it['artist'].lower()}|{it['city'].lower()}"
        if key not in unique_tm or it["score"] > unique_tm[key]["score"]:
            unique_tm[key] = it

    ranked_tm = sorted(unique_tm.values(), key=lambda x: x["score"], reverse=True)
    new_tm = filter_new_ids(ranked_tm)

    if new_tm:
        post_to_discord("🆕 NEW TICKETMASTER PRESALES & ONSALES DETECTED!", new_tm[:10], color=3066993)

    if ranked_tm:
        post_to_discord("⚡ HOURLY HIGH-DEMAND SALE & PRESALE RADAR", ranked_tm[:10], color=15105570)

if __name__ == "__main__":
    run()
