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
        print("SERPER_API_KEY is missing!")
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
                print("Serper error:", resp.status_code, resp.text[:120])
                continue

            for item in resp.json().get("organic", []):
                link = (item.get("link") or "").split("?")[0].rstrip("/")
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()

                if not link or link in seen_urls:
                    continue
                if link in ("https://laylo.com", "https://signup.seated.com", "https://www.laylo.com", "https://www.seated.com"):
                    continue

                combined_text = (link + " " + title + " " + snippet).lower()
                if "laylo" not in combined_text and "seated" not in combined_text:
                    continue

                seen_urls.add(link)
                uid = hashlib.sha256(link.encode()).hexdigest()[:16]

                results.append({
                    "id": "rsvp_" + uid,
                    "artist": title[:90] if title else link.split("/")[-1],
                    "city": platform_tag,
                    "when": "RSVP: " + snippet[:95] if snippet else "Direct " + platform_tag + " Page",
                    "link": link,
                    "is_presale": True,
                    "score": 120
                })
        except Exception as e:
            print("Serper exception:", e)

    print("Direct Laylo & Seated URLs found:", len(results))
    return results

def get_ticketmaster_sales():
    if not TICKETMASTER_API_KEY:
        print("Missing TICKETMASTER_API_KEY")
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
                    if (ps and ps > now_utc) or (ps and pe and ps <= now_utc <= pe):
                        active_presales.append((ps or now_utc, p.get("name", "Presale"), p.get("url") or ev.get("url")))

                if not active_presales and not (pub_start and pub_start > now_utc):
                    continue

                seen.add(ev_id)
                attractions = ev.get("_embedded", {}).get("attractions", [])
                artist = attractions[0].get("name") if attractions else ev.get("name", "Unknown")

                venues = ev.get("_embedded", {}).get("venues", [])
                v = venues[0] if venues else {}
                city = (v.get("city", {}).get("name", "") + ", " + country).strip(", ")

                active_presales.sort(key=lambda x: x[0])
                if active_presales:
                    p_dt, p_name, p_url = active_presales[0]
                    when_str = "Presale (" + p_name + "): " + p_dt.strftime("%b %d, %H:%M UTC")
                    link = p_url or ev.get("url", "")
                    is_presale = True
                else:
                    when_str = "Public Sale: " + pub_start.strftime("%b %d, %H:%M UTC")
                    link = ev.get("url", "")
                    is_presale = False

                score = 70 + (25 if is_presale else 0) + (30 if any(a in artist.lower() for a in PREFERRED_ARTISTS) else 0)
                results.append({
                    "id": "tm_" + artist.lower() + "_" + city.lower(),
                    "artist": artist,
                    "city": city,
                    "when": when_str,
                    "link": link,
                    "is_presale": is_presale,
                    "score": score
                })
        except Exception as e:
            print("TM error:", country, e)

    print("Ticketmaster collected:", len(results))
    return results

def filter_new_ids(items):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return items[:10]

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates"
    }
    new_items = []
    for item in items:
        ev_id = item["id"]
        try:
            check = requests.get(
                SUPABASE_URL + "/rest/v1/seen_events?event_id=eq." + requests.utils.quote(ev_id) + "&select=event_id",
                headers=headers,
                timeout=8
            )
            if check.status_code == 200 and len(check.json()) > 0:
                continue

            ins = requests.post(
                SUPABASE_URL + "/rest/v1/seen_events",
                headers=headers,
                json={"event_id": ev_id, "artist": item["artist"][:150], "url": item["link"][:400]},
                timeout=8
            )
            if ins.status_code in (200, 201, 204):
                new_items.append(item)
            else:
                print("Supabase insert status:", ins.status_code, ins.text[:100])
                new_items.append(item)
        except Exception as e:
            print("Supabase error:", e)
            new_items.append(item)

    return new_items

def post_to_discord(title, items, color=3066993):
    if not DISCORD_WEBHOOK_URL or not items:
        return
    lines = []
    for i, it in enumerate(items[:10], 1):
        line1 = "**" + str(i) + ". " + it["artist"] + "** — `" + it["city"] + "`"
        line2 = "   " + it["when"]
        line3 = "   [Open Signup / Ticket Link](" + it["link"] + ")"
        lines.append(line1 + chr(10) + line2 + chr(10) + line3)

    payload = {
        "embeds": [{
            "title": title,
            "description": (chr(10) + chr(10)).join(lines),
            "color": color,
            "footer": {"text": "24/7 Presale Radar - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        }]
    }
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=12)
    print("Discord status:", title, r.status_code)

def run():
    print("Running Zero-Repeat Laylo/Seated + Ticketmaster Radar...")

    signups = get_direct_laylo_seated_signups()
    new_signups = filter_new_ids(signups)
    print("Brand-new Laylo/Seated signups:", len(new_signups))
    if new_signups:
        post_to_discord("NEW LAYLO & SEATED PRESALE SIGNUPS!", new_signups[:10], color=10181046)

    tm_sales = get_ticketmaster_sales()
    unique_tm = {}
    for it in tm_sales:
        key = it["id"]
        if key not in unique_tm or it["score"] > unique_tm[key]["score"]:
            unique_tm[key] = it

    ranked_tm = sorted(unique_tm.values(), key=lambda x: x["score"], reverse=True)
    new_tm = filter_new_ids(ranked_tm)
    print("Brand-new Ticketmaster presales/sales:", len(new_tm))
    if new_tm:
        post_to_discord("NEW TICKETMASTER PRESALES & ONSALES!", new_tm[:10], color=3066993)

    if not new_signups and not new_tm:
        print("No brand-new events this hour - staying quiet to prevent repeats!")

if __name__ == "__main__":
    run()
