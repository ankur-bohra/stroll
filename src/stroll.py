import os
import re
from datetime import datetime, timedelta
from PIL import Image
from pystray import Icon, Menu, MenuItem as Item

import api
from data import TomlFile, JsonFile
from scheduler import Scheduler

ICON = Image.open("images\\stroll.ico")
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]
REGEXP = r'(\d+)\?pwd=(\w+)'

scheduler = Scheduler()
settings = TomlFile("settings.user.toml", "settings.default.toml")
data = JsonFile("data\\data.user.json", "data\\data.default.json")

def link_account(sysTrayIcon):
    creds = api.get_creds(SCOPES, show_auth_prompt=False, reuse_creds=False)
    user_info = api.get_user_info(creds)
    if user_info:
        data.set("email", user_info.get("email"))
        sysTrayIcon.update_menu()
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
            if event.get("description") and bool(re.search(REGEXP, event.get("description"))):
                events.append(event)
    # NOTE: Timezone conversion isn't required here (constant offset)
    events.sort(key = lambda event: datetime.fromisoformat(event.get("start").get("dateTime")), reverse=True)

    # Since this and link_account are the only functions that interact with the API, this is the ideal
    # place to update the email id from the crendetials
    if data.get("email") is None:
        creds = api.get_creds(SCOPES)  # This will reuse the credits that should exist after the calls above
        user_info = api.get_user_info(creds)
        if user_info:
            data.set("email", user_info.get("email"))
            tray_icon.update_menu()
    return len(events) > 0 and events.pop() or None

def join_event(event):
    global REGEXP, settings
    description = event.get("description")
    pattern = re.search(REGEXP, description)
    url = f"zoommtg://zoom.us/join?action=join&confno={pattern.group(1)}&pwd={pattern.group(2)}"
    command = f"{settings.get('Joining.zoom-path')} --url=\"{url}\""
    os.popen(command)

def join_next_event():
    event = get_next_event()
    if event:
        join_event(event)

def schedule_next_event():
    global settings, tray_icon
    event = get_next_event()
    if event:
        if not scheduler.head or event.get("id") != scheduler.head.value.get("id"):
            # This is a new event, remove the old event
            scheduler.clear()
            # Schedule the new event
            startTime = datetime.fromisoformat(event.get("start").get("dateTime"))
            joinTime = startTime - timedelta(seconds=settings.get("Joining.offset"))
            scheduler.add_task(joinTime, lambda: join_event(event))
            # Tell the user a new event has been scheduled
            name = event.get("summary")
            tray_icon.notify(f"Event \"[{name}]\" has been scheduled for {joinTime.strftime('%r')}", "New Event Scheduled")
    elif scheduler.head:
        # The event must have been removed or completed
        scheduler.clear()

current_sync_origin = datetime.now()
def auto_sync(sync_origin=None):
    global scheduler, current_sync_origin, settings
    # Terminate if auto-join is disabled or the scheduler is terminated
    if not settings.get("Joining.auto-join") or not scheduler.active:
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
        schedule_next_event()
        next_call = now + timedelta(seconds=settings.get("Syncing.period"))
        scheduler.add_task(next_call, lambda: auto_sync(sync_origin))

menu_items = []
def get_menu_items():
    global menu_items, settings, data
    menu_items = []

    # First comes the current account if present
    email = data.get("email")
    if email:
        menu_items.append(Item(
            email, lambda tray_icon: tray_icon, enabled=False
        ))
    
    menu_items.append(Item("Link New Account", link_account))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item("Join Next Event", lambda tray_icon: join_next_event()))
    menu_items.append(Item("Sync Next Event", lambda tray_icon: auto_sync()))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item("Open Settings File", lambda tray_icon: os.popen(
        "notepad settings.user.toml" if settings.get("Settings.open-in-notepad") else "settings.user.toml")
    ))
    menu_items.append(Item("Load Settings", lambda tray_icon: settings.load()))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item(
        "Auto-Join",
        lambda tray_icon, item: settings.set("Joining.auto-join", not item.checked),
        checked=lambda item: settings.get("Joining.auto-join")
    ))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item("Quit", stop))
    return menu_items


def stop_joining():
    global current_sync_origin, scheduler
    # Terminate current sync loop
    current_sync_origin = datetime.now().astimezone()  # Fakes a new sync loop
    scheduler.clear()  # Clear scheduled events

def init(tray_icon):
    global scheduler, data, settings, data
    # Indicate startup
    tray_icon.visible = True
    tray_icon.notify("Stroll has started")

    # Handle data files
    settings.load()
    data.load()

    # Initialize first sync loop
    scheduler.start()
    auto_sync()

def stop(tray_icon):
    global scheduler, data, settings, data
    data.dump()
    settings.dump()
    if scheduler.active:
        scheduler.terminate()
    tray_icon.stop()
    
os.popen(settings.get("Joining.zoom-path"))  # Zoom start-up and login shouldn't affect prejoin period
tray_menu = Menu(*get_menu_items())
tray_icon = Icon("Stroll", ICON, menu=tray_menu)
tray_icon.run(init)