import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_event_report(events_list, report_title="🔥 TOP EVENTS — DAILY DISCOVERY REPORT"):
    """Sends ranked, verified events to Discord in clean batches of 5 embeds per message."""
    if not DISCORD_WEBHOOK_URL:
        print("❌ Error: DISCORD_WEBHOOK_URL missing in .env")
        return False

    if not events_list:
        print("ℹ️ No new events to notify on Discord.")
        return True

    # Divide into chunks of 5 embeds to respect Discord's 6000-character embed limit
    chunk_size = 5
    for i in range(0, len(events_list), chunk_size):
        chunk = events_list[i:i + chunk_size]
        embeds = []

        for idx, ev in enumerate(chunk, start=i + 1):
            is_presale = ev.get("has_presale", False)
            color = 0x00FF7F if is_presale else 0xFF4500  # Green for Presale/Signup, Orange-Red for General
            badge = "🎟️ PRESALE / SIGNUP" if is_presale else "🔥 HOT EVENT"

            embeds.append({
                "title": f"#{idx} {ev.get('name', 'Unknown Event')} [{badge}]",
                "url": ev.get("ticket_link", "https://ticketmaster.com"),
                "color": color,
                "fields": [
                    {"name": "🎤 Artist / Tour", "value": ev.get("artist", "N/A"), "inline": True},
                    {"name": "📍 Location & Venue", "value": f"{ev.get('venue', 'TBD')}, {ev.get('city', 'USA')}", "inline": True},
                    {"name": "🎟️ Artist / Presale Schedule", "value": ev.get("presale", "Check Signup Link"), "inline": False},
                    {"name": "🌍 Public Sale & Show Date", "value": f"{ev.get('date', 'TBD')}", "inline": False},
                    {"name": "🔗 Direct Action Links", "value": f"👉 **[PRESALE SIGNUP / REGISTRATION]({ev.get('reg_link', '#')})**  |  🎫 **[TICKET PAGE]({ev.get('ticket_link', '#')})**", "inline": False}
                ],
                "footer": {"text": f"Rank Score: {ev.get('rank_score', 50)}/100 • Source: {ev.get('source', 'Official')}"}
            })

        header = f"📢 **{report_title}** (Part {i // chunk_size + 1})" if i > 0 else f"📢 **{report_title}**"
        payload = {"content": header, "embeds": embeds}

        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
        if res.status_code in [200, 204]:
            print(f"✅ Discord batch {i // chunk_size + 1} delivered ({len(chunk)} events)!")
        else:
            print(f"❌ Discord Error: {res.status_code} - {res.text}")
            return False

        time.sleep(1.5)  # Rate-limit protection

    return True