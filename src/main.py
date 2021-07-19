import os
import re
from datetime import datetime, timedelta

from google.api_core.datetime_helpers import from_rfc3339

import api
from scheduler import Scheduler
from infi.systray import SysTrayIcon

ICON = "images/stroll.ico"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events"
]
REGEXP = r'(\d+)\?pwd=(\w+)'

SYNC_FREQUENCY = timedelta(seconds=10*60)
PREJOIN_OFFSET = timedelta(seconds=20)

scheduler = Scheduler()
scheduler.start()

def link_account(sysTrayIcon):
    global SCOPES
    api.get_creds(SCOPES, show_auth_prompt=False, reuse_creds=False)
    auto_sync()

def get_next_event():
    global next_event, PREJOIN_OFFSET

    events = []
    calendar_list = api.get_calendar_list()
    for calendar in calendar_list:
        calendar_id = calendar.get("id")
        possible_events = api.get_events_starting_from_now(calendar_id, range_offset=timedelta(days=1))  # Random offset
        # Store only zoom link containing events
        for event in possible_events:
            if bool(re.search(REGEXP, event.get("description"))):
                events.append(event)
    
    # NOTE: Timezone conversion isn't required here (constant offset)
    events.sort(key = lambda event: datetime.fromisoformat(event.get("start").get("dateTime")), reverse=True)
    return len(events) > 0 and events.pop() or None

def join_event(event):
    global REGEXP
    description = event.get("description")
    pattern = re.search(REGEXP, description)
    url = f"zoommtg://zoom.us/join?action=join&confno={pattern.group(1)}&pwd={pattern.group(2)}"
    command = f"%appdata%/Zoom/bin/zoom.exe --url=\"{url}\""
    os.popen(command)

def join_next_event(sysTrayIcon):
    event = get_next_event()
    if event:
        join_event(event)

def schedule_next_event():
    global PREJOIN_OFFSET
    event = get_next_event()
    if event:
        startTime = datetime.fromisoformat(event.get("start").get("dateTime"))
        joinTime = startTime - PREJOIN_OFFSET
        scheduler.add_task(joinTime, lambda: join_event(event))

def modify_prejoin_offset(seconds):
    global PREJOIN_OFFSET
    PREJOIN_OFFSET = timedelta(seconds=seconds)
    # Start a new sync cycle
    auto_sync()

def modify_sync_frequency(seconds):
    global SYNC_FREQUENCY
    SYNC_FREQUENCY = seconds
    # Start a new sync cycle
    auto_sync()

def on_quit(sysTrayIcon):
    global scheduler
    scheduler.terminate()

current_sync_origin = datetime.now()
def auto_sync(sync_origin=None):
    global scheduler, SYNC_FREQUENCY, current_sync_origin
    now = datetime.now().astimezone()
    # Update current sync origin if this is a new sync loop
    if sync_origin == None:
        # Must be a new sync loop if no origin was given
        current_sync_origin = sync_origin = now

    # Terminate sync if not the latest loop
    if sync_origin != current_sync_origin:
        return
    # All sync issues resolved, proceed to actual syncing
    # Don't interact with api if no credentials are present at all
    if os.path.exists("data/token.json"):
        scheduler.clear()
        schedule_next_event()
        next_call = now + SYNC_FREQUENCY
        scheduler.add_task(next_call, lambda: auto_sync(sync_origin))

DEFAULT_INDEX = 1  # Join next event when tray icon is double clicked
menu = (
    ("Link New Account", None, link_account),
    ("Join Next Event", None, join_next_event),
    ("Change Pre-join Offset", None, (
            ("Join 30 seconds before", None, lambda i: modify_prejoin_offset(30)),
            ("Join 1 minute before", None, lambda i: modify_prejoin_offset(1*60)),
            ("Join 5 minutes before", None, lambda i: modify_prejoin_offset(5*60)),
        )
    ),
    ("Change Syncing Frequency", None, (
            ("Sync once each minute", None, lambda i: modify_sync_frequency(1*60)),
            ("Sync once every 5 minutes", None, lambda i: modify_sync_frequency(5*60)),
            ("Sync once every 10 minutes", None, lambda i: modify_sync_frequency(10*60)),
        )
    ),
)


auto_sync()  # Non user-initiated syncing
os.popen("%appdata%/Zoom/bin/zoom.exe")  # Zoom start-up and login shouldn't affect prejoin period
systray = SysTrayIcon(ICON, "Stroll", menu, on_quit, DEFAULT_INDEX)
systray.start()