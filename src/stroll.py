import os
import re
import toml
from datetime import datetime, timedelta

from infi.systray import SysTrayIcon

import api
from scheduler import Scheduler

ICON = "images/stroll.ico"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events"
]
REGEXP = r'(\d+)\?pwd=(\w+)'

settings = {}

scheduler = Scheduler()

def link_account(sysTrayIcon):
    global SCOPES
    api.get_creds(SCOPES, show_auth_prompt=False, reuse_creds=False)
    auto_sync()

def get_next_event():
    global next_event

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
    global REGEXP, settings
    description = event.get("description")
    pattern = re.search(REGEXP, description)
    url = f"zoommtg://zoom.us/join?action=join&confno={pattern.group(1)}&pwd={pattern.group(2)}"
    command = f"{settings.get('Joining').get('zoom-path')} --url=\"{url}\""
    os.popen(command)

def join_next_event(sysTrayIcon):
    event = get_next_event()
    if event:
        join_event(event)

def schedule_next_event():
    global settings
    event = get_next_event()
    if event:
        startTime = datetime.fromisoformat(event.get("start").get("dateTime"))
        joinTime = startTime - timedelta(seconds=settings.get("Joining").get("offset"))
        scheduler.add_task(joinTime, lambda: join_event(event))

def load_settings():
    global settings
    settings = toml.load("settings.toml")
    auto_sync()  # Just in case some joining/syncing settings have been changed

def modify_settings(field, value):
    global settings
    keys = field.split(".")[::-1]
    cursor = settings
    while len(keys) > 1:  # The last part is the actual key, the one before that is the last dictionary
        key = keys.pop()
        cursor = cursor.get(key)
    cursor[keys.pop()] = value
    with open("settings.toml", "w") as settings_file:
        toml.dump(settings, settings_file)
    load_settings()  # Handle all updates

def on_quit(sysTrayIcon):
    global scheduler
    scheduler.terminate()

current_sync_origin = datetime.now()
def auto_sync(sync_origin=None):
    global scheduler, current_sync_origin, settings

    if settings.get("Joining").get("auto-join") == False:
        return

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
        next_call = now + timedelta(seconds=settings.get("Syncing").get("period"))
        scheduler.add_task(next_call, lambda: auto_sync(sync_origin))

def stop_joining():
    global current_sync_origin, scheduler
    current_sync_origin = datetime.now().astimezone()
    scheduler.clear()  # Clear previously scheduled events

DEFAULT_INDEX = 1  # Join next event when tray icon is double clicked
menu = (
    ("Link New Account", None, link_account),
    ("<SEPARATOR>", None, lambda i: None),
    ("Sync Next Event", None, auto_sync),
    ("Join Next Event", None, join_next_event),
    ("<SEPARATOR>", None,  lambda i: None),
    ("Auto-Joining", None, (
        ("Enable Joining", None, lambda i: modify_settings("Joining.auto-join", True)),
        ("Disable Joining", None, lambda i: modify_settings("Joining.auto-join", False))
    )),
    ("Settings", None, (
        ("Open Settings File", None, lambda i: os.popen(os.path.join(os.getcwd(), "settings.toml"))),
        ("Reload Settings", None, load_settings)
    ))
)


scheduler.start()
load_settings()  # Also starts the initial sync loop
os.popen(settings.get("Joining").get("zoom-path"))  # Zoom start-up and login shouldn't affect prejoin period
systray = SysTrayIcon(ICON, "Stroll", menu, on_quit, DEFAULT_INDEX)
systray.start()
