import os
import re
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

def get_direct_laylo_seated_signups():
    """Fetches direct Laylo, Seated, and Artist Presale RSVP signup links."""
    results = []
    seen = set()

    # Targeted RSS + web discovery specifically for Laylo, Seated & Artist Presale signups
    queries = [
        "https://news.google.com/rss/search?q=%22signup.seated.com%22+OR+%22seated.com%22+presale+when:7d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22laylo.com%22+presale+OR+tour+when:7d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22sign+up+for+presale%22+OR+%22register+for+presale%22+tour+when:3d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22artist+presale%22+%22sign+up%22+2026+OR+2027+when:3d&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=%22presale+sign-up%22+OR+%22presale+signup%22+tickets+when:3d&hl=en-GB&gl=GB&ceid=GB:en",
    ]

    for url in queries:
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

                low = title.lower()
                if "seated" in low:
                    tag = "SEATED SIGNUP"
                elif "laylo" in low:
                    tag = "LAYLO RSVP"
                else:
                    tag = "PRESALE SIGNUP"

                results.append({
                    "id": f"rsvp_{uid}",
                    "artist": clean_title[:90],
                    "city": tag,
                    "when": f"🎟️ {tag} • {pub}",
                    "link": link,
                    "is_presale": True,
                    "is_signup": True,
                    "score": 110
                })
        except Exception as e:
            print(f"⚠️ Signup RSS warning: {e}")

    print(f"✅ Direct Laylo/Seated/Presale Signups found: {len(results)}")
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
                    "is_signup": False,
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
    print("🚀 Running Presale Signups & Ticketmaster Radar...")
    signups = get_direct_laylo_seated_signups()
    tm_sales = get_ticketmaster_sales()

    # Separate alert specifically for Laylo / Seated / Presale Signups
    new_signups = filter_new_ids(signups)
    if new_signups:
        post_to_discord("🎟️ NEW PRESALE SIGNUPS (LAYLO / SEATED / ARTIST RSVP)", new_signups[:10], color=10181046)
    elif signups:
        post_to_discord("🎟️ ACTIVE PRESALE SIGNUP RADAR (LAYLO / SEATED / RSVP)", signups[:8], color=10181046)

    # Ticketmaster upcoming presales & high-demand sales
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
