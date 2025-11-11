from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv, find_dotenv
import requests
import logging
from collections import defaultdict
from datetime import datetime

# Load environment variables from .env file
load_dotenv(find_dotenv())

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
app = Flask(__name__)


def hex_to_decimal(hex_color):
    """Convert hex color code to decimal for Discord embed."""
    if hex_color and hex_color.startswith('#'):
        return int(hex_color[1:], 16)
    return 0  # Default to black if invalid

def get_attendance_status(hex_color):
    """Determine attendance status from background color. Green = present, Red = absent."""
    if not hex_color or not hex_color.startswith('#'):
        return "Unknown"
    
    # Extract RGB values
    hex_clean = hex_color[1:]
    if len(hex_clean) == 6:
        r = int(hex_clean[0:2], 16)
        g = int(hex_clean[2:4], 16)
        b = int(hex_clean[4:6], 16)
        
        # Green colors have higher G component, red colors have higher R component
        # Check if it's more green (present) or red (absent)
        if g > r and g > b:
            return "Present"
        elif r > g and r > b:
            return "Absent"
        else:
            # If it's not clearly green or red, check if it's closer to green or red
            green_score = g - max(r, b)
            red_score = r - max(g, b)
            if green_score > red_score:
                return "Present"
            else:
                return "Absent"
    
    return "Unknown"

def format_date(date_str):
    """Format ISO date string to readable format."""
    try:
        if date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M')
    except:
        pass
    return date_str or "N/A"

def format_discord_message(person, events):
    """Create a Discord embed message for a person's events."""
    if not events:
        return None
    
    # Get color from first event's bg field
    color = hex_to_decimal(events[0].get('bg', '#000000'))
    
    # Format fields for each event
    fields = []
    for event in events:
        practice_date = format_date(event.get('practice_date', ''))
        event_type = event.get('type', 'N/A').replace('\n', ' - ')
        change_type = event.get('type_change', 'N/A')
        cell = event.get('cell', 'N/A')
        sheet_name = event.get('sheetName', 'N/A')
        bg_color = event.get('bg', '')
        attendance_status = get_attendance_status(bg_color)
        
        # Use emoji to make status more visible
        status_emoji = "✅" if attendance_status == "Present" else "❌"
        
        field_value = f"**Status:** {status_emoji} {attendance_status}\n"
        field_value += f"**Date:** {practice_date}\n"
        field_value += f"**Type:** {event_type}\n"
        field_value += f"**Change:** {change_type}\n"
        field_value += f"**Cell:** {cell}\n"
        field_value += f"**Sheet:** {sheet_name}"
        
        if event.get('newValue'):
            field_value += f"\n**New Value:** {event.get('newValue')}"
        
        fields.append({
            "name": f"Event {len(fields) + 1}",
            "value": field_value,
            "inline": False
        })
    
    # Get timestamp from date_changed if available
    timestamp = None
    if events and events[0].get('date_changed'):
        try:
            # Parse date_changed format "09-27T09:23Z" or similar
            date_changed = events[0].get('date_changed', '')
            # Try to parse it - this is a simplified parser
            # You may need to adjust based on actual format
            if 'T' in date_changed:
                parts = date_changed.split('T')
                if len(parts) == 2:
                    # Assume current year and parse
                    year = datetime.now().year
                    month_day = parts[0]
                    time_part = parts[1].replace('Z', '')
                    try:
                        month, day = month_day.split('-')
                        hour, minute = time_part.split(':') if ':' in time_part else (time_part[:2], time_part[2:])
                        timestamp = datetime(int(year), int(month), int(day), int(hour), int(minute)).isoformat()
                    except:
                        pass
        except:
            pass
    
    # Count attendance statuses for summary
    present_count = sum(1 for e in events if get_attendance_status(e.get('bg', '')) == "Present")
    absent_count = sum(1 for e in events if get_attendance_status(e.get('bg', '')) == "Absent")
    
    description = f"{len(events)} change(s) recorded"
    if present_count > 0 or absent_count > 0:
        status_summary = []
        if present_count > 0:
            status_summary.append(f"✅ {present_count} Present")
        if absent_count > 0:
            status_summary.append(f"❌ {absent_count} Absent")
        if status_summary:
            description += f" | {', '.join(status_summary)}"
    
    embed = {
        "title": f"Attendance Updates for {person}",
        "description": description,
        "color": color,
        "fields": fields,
        "timestamp": timestamp or datetime.utcnow().isoformat(),
        "footer": {
            "text": "Attendance System"
        }
    }
    
    return {"embeds": [embed]}

def send_msg(payload):
    """Send message to Discord webhook. Payload can be embed format or plain content."""
    res = requests.post(WEBHOOK_URL, json=payload)
    return res.text, res.status_code
    
@app.route('/', methods=['GET'])
def health_check():
    return "Hello", 200

@app.route('/event', methods=['POST'])
def handle_event():
    print(request.json)
    data = request.json
    print(data)
    
    if not data:
        return "No data provided", 400
    
    # Group events by person
    events_by_person = defaultdict(list)
    for event in data:
        person = event.get('person', 'Unknown')
        events_by_person[person].append(event)
    
    # Send one formatted message per person
    for person, events in events_by_person.items():
        embed_payload = format_discord_message(person, events)
        if embed_payload:
            t, c = send_msg(embed_payload)
            print(f"Sent message for {person}: {c}")
    
    return "Success", 204


if __name__ == '__main__':
    # loop = asyncio.new_event_loop()
    # loop.create_task(run_bot())
    # asyncio.set_event_loop(loop)
    app.run(host="0.0.0.0")
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

