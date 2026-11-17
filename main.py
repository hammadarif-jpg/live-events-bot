import os
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def get_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"⚠️ Supabase connection warning: {e}")
    return None

def verify_and_rank_events(raw_events, preferred_artists=None):
    if not raw_events:
        return []

    preferred_lower = [a.lower() for a in (preferred_artists or [])]
    seen_keys = set()
    verified = []

    for ev in raw_events:
        artist = str(ev.get("artist") or ev.get("event_name") or "").strip()
        reg_link = str(ev.get("reg_link") or ev.get("url") or "").strip()
        if not artist or not reg_link:
            continue

        dedup_key = f"{artist.lower()}|{str(ev.get('city', '')).lower()}|{str(ev.get('date', '')).lower()}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        score = 60
        if ev.get("has_presale"):
            score += 25
        if any(pref in artist.lower() for pref in preferred_lower):
            score += 30
        source = str(ev.get("source", ""))
        if "Laylo" in source or "Seated" in source or "Presale" in source:
            score += 15

        ev["artist"] = artist
        ev["reg_link"] = reg_link
        ev["city"] = ev.get("city") or "Global"
        ev["date"] = ev.get("date") or "Upcoming Presale / Sale"
        ev["rank_score"] = score
        verified.append(ev)

    verified.sort(key=lambda x: x["rank_score"], reverse=True)
    return verified

def filter_new_and_save_to_db(ranked_events):
    if not ranked_events:
        return []

    sb = get_supabase()
    if not sb:
        print("⚠️ Supabase not configured; returning top new events directly.")
        return ranked_events[:10]

    new_events = []
    for ev in ranked_events:
        ev_id = str(ev.get("id") or ev.get("reg_link"))
        try:
            existing = sb.table("seen_events").select("event_id").eq("event_id", ev_id).execute()
            if existing.data:
                continue

            sb.table("seen_events").insert({
                "event_id": ev_id,
                "artist": ev.get("artist", "")[:200],
                "url": ev.get("reg_link", "")[:500],
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
            new_events.append(ev)
        except Exception:
            try:
                sb.table("seen_events").insert({"event_id": ev_id}).execute()
                new_events.append(ev)
            except Exception as e2:
                print(f"⚠️ DB insert warning: {e2}")

    return new_events
