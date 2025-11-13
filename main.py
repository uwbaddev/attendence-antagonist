from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv, find_dotenv
import requests
import logging
from collections import defaultdict
from datetime import datetime, timedelta
import pytz
import threading

# Load environment variables from .env file
EST = pytz.timezone("America/Toronto")
load_dotenv(find_dotenv())

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Batching configuration - messages within this time window (in seconds) will be batched together
BATCH_WINDOW_SECONDS = int(os.getenv("DEV_BATCH_WINDOW_SECONDS")) if os.getenv("ENV") == "development" else 20 

app = Flask(__name__)

# Thread-safe storage for pending events
pending_events_lock = threading.Lock()
pending_events = []  # List of tuples: (event, timestamp, person)

def batch_processor_thread():
    """Background thread that periodically processes and sends batched events."""
    import time
    while True:
        try:
            time.sleep(BATCH_WINDOW_SECONDS)  # Check every 30 seconds
            process_and_send_batched_events()
        except Exception as e:
            print(f"Error in batch processor thread: {e}")


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

def parse_date_changed(date_changed_str):
    """Parse date_changed format "09-27T09:23Z" to datetime object for comparison."""
    try:
        if not date_changed_str or 'T' not in date_changed_str:
            return None
        
        parts = date_changed_str.split('T')
        if len(parts) == 2:
            year = datetime.now(EST).year
            month_day = parts[0]
            time_part = parts[1].replace('Z', '')
            month, day = month_day.split('-')
            hour, minute = time_part.split(':') if ':' in time_part else (time_part[:2], time_part[2:])
            # Create naive datetime, assume UTC (since it had 'Z')
            dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
            dt_utc = pytz.UTC.localize(dt)
            return dt_utc
    except:
        pass
    return None

def format_date(date_str):
    """Format ISO date string to readable format in EST timezone."""
    try:
        if date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # If datetime is naive, assume UTC
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
            # Convert to EST
            dt_est = dt.astimezone(EST)
            return dt_est.strftime('%Y-%m-%d %H:%M')
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
                    # Assume current year and parse (use EST timezone)
                    year = datetime.now(EST).year
                    month_day = parts[0]
                    time_part = parts[1].replace('Z', '')
                    try:
                        month, day = month_day.split('-')
                        hour, minute = time_part.split(':') if ':' in time_part else (time_part[:2], time_part[2:])
                        # Create naive datetime, assume UTC (since it had 'Z')
                        dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
                        dt_utc = pytz.UTC.localize(dt)
                        # Convert to EST
                        dt_est = dt_utc.astimezone(EST)
                        timestamp = dt_est.isoformat()
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
        "timestamp": datetime.now(EST).isoformat() or timestamp,
        "footer": {
            "text": f"Attendance System"
        }
    }   
    
    return {"embeds": [embed]}

def is_quiet_period():
    """Check if current time is in quiet period: Saturday 12:00am to Sunday 7:30pm EST."""
    now_est = datetime.now(EST)
    weekday = now_est.weekday()  # 0=Monday, 5=Saturday, 6=Sunday
    hour = now_est.hour
    minute = now_est.minute
    
    # Saturday (5) from 00:00 onwards
    if weekday == 5:
        return True
    
    # Sunday (6) until 19:30 (7:30pm)
    if weekday == 6:
        if hour < 19 or (hour == 19 and minute < 30):
            return True
    
    return False

def send_msg(payload):
    """Send message to Discord webhook. Payload can be embed format or plain content."""
    res = requests.post(WEBHOOK_URL, json=payload)
    return res.text, res.status_code

def process_and_send_batched_events():
    """Process events that are older than the batching window and send them."""
    global pending_events
    
    with pending_events_lock:
        now = datetime.now(EST)
        cutoff_time = now - timedelta(seconds=BATCH_WINDOW_SECONDS)
        
        # Separate events into those ready to send and those still pending
        events_to_process = []
        still_pending = []
        
        for event, timestamp, person in pending_events:
            if timestamp <= cutoff_time:
                events_to_process.append((event, person))
            else:
                still_pending.append((event, timestamp, person))
        
        # Update pending events to only include those still within the window
        pending_events = still_pending
    
    # If no events ready to send, return early
    if not events_to_process:
        return
    
    # Group events by person
    events_by_person = defaultdict(list)
    for event, person in events_to_process:
        events_by_person[person].append(event)
    
    # Process events for each person (filter by cell, merge bg/newValue, etc.)
    filtered_events_by_person = {}
    for person, events in events_by_person.items():
        # Group events by cell
        events_by_cell = defaultdict(list)
        for event in events:
            cell = event.get('cell', 'N/A')
            events_by_cell[cell].append(event)
        
        # For each cell, track latest bg change and latest newValue change separately
        latest_events = []
        for cell, cell_events in events_by_cell.items():
            # Track latest event that changed bg
            latest_bg_event = None
            latest_bg_datetime = None
            
            # Track latest event that changed newValue
            latest_newvalue_event = None
            latest_newvalue_datetime = None
            
            for event in cell_events:
                date_changed = event.get('date_changed', '')
                event_datetime = parse_date_changed(date_changed)
                
                # Check if this event has a bg change
                if event.get('bg'):
                    if event_datetime is None:
                        if latest_bg_event is None:
                            latest_bg_event = event
                    else:
                        if latest_bg_datetime is None or event_datetime > latest_bg_datetime:
                            latest_bg_datetime = event_datetime
                            latest_bg_event = event
                
                # Check if this event has a newValue change
                if 'newValue' in event and event.get('newValue') is not None:
                    if event_datetime is None:
                        if latest_newvalue_event is None:
                            latest_newvalue_event = event
                    else:
                        if latest_newvalue_datetime is None or event_datetime > latest_newvalue_datetime:
                            latest_newvalue_datetime = event_datetime
                            latest_newvalue_event = event
            
            # Merge the latest bg and newValue changes into a single event
            if latest_bg_event or latest_newvalue_event:
                # Start with the event that has the later timestamp, or use bg event as base if both exist
                if latest_bg_event and latest_newvalue_event:
                    # Use the later timestamp to determine base event
                    if latest_bg_datetime and latest_newvalue_datetime:
                        base_event = latest_bg_event if latest_bg_datetime >= latest_newvalue_datetime else latest_newvalue_event
                    else:
                        base_event = latest_bg_event
                    
                    # Create merged event with latest bg and latest newValue
                    merged_event = base_event.copy()
                    if latest_bg_event:
                        merged_event['bg'] = latest_bg_event.get('bg')
                    if latest_newvalue_event:
                        merged_event['newValue'] = latest_newvalue_event.get('newValue')
                    # Use the later date_changed timestamp
                    if latest_bg_datetime and latest_newvalue_datetime:
                        merged_event['date_changed'] = latest_bg_event.get('date_changed') if latest_bg_datetime >= latest_newvalue_datetime else latest_newvalue_event.get('date_changed')
                    elif latest_bg_datetime:
                        merged_event['date_changed'] = latest_bg_event.get('date_changed')
                    elif latest_newvalue_datetime:
                        merged_event['date_changed'] = latest_newvalue_event.get('date_changed')
                    
                    latest_events.append(merged_event)
                elif latest_bg_event:
                    latest_events.append(latest_bg_event)
                elif latest_newvalue_event:
                    latest_events.append(latest_newvalue_event)
        
        filtered_events_by_person[person] = latest_events
    
    # Send one formatted message per person
    for person, events in filtered_events_by_person.items():
        embed_payload = format_discord_message(person, events)
        if embed_payload:
            t, c = send_msg(embed_payload)
            print(f"Sent batched message for {person}: {c}")
    
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
    
    # Check if we're in quiet period (Saturday 12:00am to Sunday 7:30pm EST)
    if is_quiet_period():
        now_est = datetime.now(EST)
        print(f"Quiet period active - skipping notifications. Current EST time: {now_est.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        return "Success (quiet period - notifications disabled)", 204
    
    # Add new events to the pending queue with current timestamp
    now = datetime.now(EST)
    with pending_events_lock:
        for event in data:
            person = event.get('person', 'Unknown')
            pending_events.append((event, now, person))
        print(f"Added {len(data)} event(s) to pending queue. Total pending: {len(pending_events)}")
    
    # Process and send any events that are ready (older than BATCH_WINDOW_SECONDS)
    process_and_send_batched_events()
    
    return "Success", 204


if __name__ == '__main__':
    # Start background thread for processing batched events
    batch_thread = threading.Thread(target=batch_processor_thread, daemon=True)
    batch_thread.start()
    print(f"Started batch processor thread (window: {BATCH_WINDOW_SECONDS} seconds)")
    
    # loop = asyncio.new_event_loop()
    # loop.create_task(run_bot())
    # asyncio.set_event_loop(loop)
    app.run(host="0.0.0.0")
else:
    # Start background thread for processing batched events (for gunicorn)
    batch_thread = threading.Thread(target=batch_processor_thread, daemon=True)
    batch_thread.start()
    print(f"Started batch processor thread (window: {BATCH_WINDOW_SECONDS} seconds)")
    
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

