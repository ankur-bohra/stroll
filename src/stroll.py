import os
import re
import sys
import threading
from datetime import datetime, time, timedelta

import win32com.client
from PIL import Image
from pystray import Icon, Menu, MenuItem as Item

from util import api
from util.data import TomlFile, JsonFile
from util.path import from_root
from util.scheduler import Scheduler

ICON = Image.open(from_root("images\\stroll.ico"))
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]
REGEXP = r'(\d+)\?pwd=(\w+)'

scheduler = Scheduler()
settings = TomlFile(from_root("settings.user.toml"),
                    from_root("settings.default.toml"))
data = JsonFile(from_root("data\\data.user.json"),
                from_root("data\\data.default.json"))

# UTILITY FUNCTIONS

def convert_time_to_timedelta(time):
    if time is None:
        return None
    # associate time with a date to allow operations
    start = datetime.min
    end = datetime.combine(datetime.min, time)
    td = end - start
    return td


def join_event(event):
    global REGEXP, settings
    description = event.get("description")
    pattern = re.search(REGEXP, description)
    url = f"zoommtg://zoom.us/join?action=join&confno={pattern.group(1)}&pwd={pattern.group(2)}"
    zoom_path = settings.get("General.zoom-path")
    # NOTE: This blocks the containing directory from deletion as a side effect
    command = f"{zoom_path} --url=\"{url}\""
    os.popen(command)


# API INTERACTION
def attempt_auth_BLOCKING(sysTrayIcon):  # Unsafe due to reasons below
    try:
        creds = api.get_creds(SCOPES, show_auth_prompt=False, reuse_creds=False)
        user_info = api.get_user_info(creds)
        if user_info:
            data.set("email", user_info.get("email"))
            sysTrayIcon.notify(f"Successfully linked to {user_info.get('email')}")
            sysTrayIcon.update_menu()
        auto_sync()
    except:
        sysTrayIcon.notify("Failed to link to account")

# This function is blocking (due to run_local_server). This wouldn't be an issue if it was a
# guarantee that the function would always terminate by timeout, but since it's not, we need
# to use a separate thread for this function. This thread is left to hang around until the 
# program is terminated (to avoid side effects), where it's killed forcefully.

def attempt_auth(sysTrayIcon):  # non-blocking
    thread = threading.Thread(target=attempt_auth_BLOCKING, args=(sysTrayIcon,))
    thread.daemon = True  # If the program terminates, this thread will be terminated
    thread.start()

def get_zoom_events(time_from, time_to, filters=None):
    events = []
    calendar_list = api.get_calendar_list()
    calendars_filter = settings.get("Syncing.calendars")
    for calendar in calendar_list:
        # Apply calendar filter from settings
        if (calendar not in calendars_filter) and ("*" not in calendars_filter):
            # calendar not specifically mentioned and the wildcard hasn't been applied
            # skip this calendar
            continue

        calendar_id = calendar.get("id")
        range_to_sync = convert_time_to_timedelta(
            settings.get("Syncing.range-to-sync"))
        possible_events = api.get_events_in_time_span(
            calendar_id, time_from, time_to, 
            allow_incomplete_overlaps=True, filters=filters or ["+Inside", "+OverStart", "+OverEnd", "+Across"]
        )
        # Store only zoom link containing events
        for event in possible_events:
            if event.get("description") and bool(re.search(REGEXP, event.get("description"))):
                events.append(event)
    # NOTE: Timezone conversion isn't required here (constant offset)
    events.sort(key=lambda event: datetime.fromisoformat(
        event.get("start").get("dateTime")))

    # Since this and link_account are the only functions that interact with the API, this is the ideal
    # place to update the email id from the crendetials
    if data.get("email") is None:
        # This will reuse the credits that should exist after the calls above
        creds = api.get_creds(SCOPES)
        user_info = api.get_user_info(creds)
        if user_info:
            data.set("email", user_info.get("email"))
            tray_icon.update_menu()

    return events

def get_next_event():
    range_to_sync = convert_time_to_timedelta(
            settings.get("Syncing.range-to-sync"))
    now = datetime.now().astimezone()
    events = get_zoom_events(now, now+range_to_sync, filters=["+Inside", "+OverEnd"])
    return len(events) > 0 and events.pop(0) or None


def join_next_event():
    event = get_next_event()
    if event:
        join_event(event)


def join_previous_event():
    now = datetime.now().astimezone()
    events = get_zoom_events(now-timedelta(days=1), now, filters=["+OverStart", "+Inside"])
    if len(events) > 0:
        join_event(events.pop())  # Use the last event (most recent)


def join_current_event():
    now = datetime.now().astimezone()
    events = get_zoom_events(now, now+timedelta(seconds=1))
    if len(events) > 0:
        join_event(events.pop(0))


def schedule_next_event():
    global settings, tray_icon, scheduler
    if not scheduler.active:
        return
    event = get_next_event()
    if event:
        if not scheduler.head or event.get("id") != scheduler.head.value.get("id"):
            # This is a new event, remove the old event
            scheduler.clear()
            # Schedule the new event
            startTime = datetime.fromisoformat(
                event.get("start").get("dateTime"))
            joinTime = startTime - \
                convert_time_to_timedelta(settings.get("Joining.offset"))
            scheduler.add_task(joinTime, lambda: join_event(event))
            # Tell the user a new event has been scheduled
            name = event.get("summary")
            tray_icon.notify(
                f"Event \"[{name}]\" has been scheduled for {joinTime.strftime('%r')}", "New Event Scheduled")
    elif scheduler.head:
        # The event must have been removed or completed
        scheduler.clear()


# SYNCING

current_sync_origin = datetime.now()
def auto_sync(sync_origin=None):
    global scheduler, current_sync_origin, settings
    # Terminate if auto-join is disabled
    if not settings.get("Joining.auto-join"):
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
    # Don't proceed if scheduler is terminated or paused
    
    if os.path.exists(from_root("data\\token.json")):
        schedule_next_event()
        next_call = now + \
            convert_time_to_timedelta(settings.get("Syncing.period"))
        if scheduler.active:
            scheduler.add_task(next_call, lambda: auto_sync(sync_origin))


def stop_joining():
    global current_sync_origin, scheduler
    # Terminate current sync loop
    current_sync_origin = datetime.now().astimezone()  # Fakes a new sync loop
    scheduler.clear()  # Clear scheduled events


# MENU LIFECYCLE

def get_menu_items():
    global settings, data
    menu_items = []

    # First comes the current account if present
    has_creds = os.path.exists(from_root("data\\token.json"))
    if has_creds:
        # First try get the current email from the credentials
        creds = api.get_creds(SCOPES)
        user_info = api.get_user_info(creds)
        if user_info:
            data.set("email", user_info.get("email"))
        email = data.get("email")
        if email:
            menu_items.append(Item(
                email, lambda tray_icon: tray_icon, enabled=False
            ))

    menu_items.append(Item("Link New Account", attempt_auth))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item(
        "Auto-Join",
        lambda tray_icon, item: settings.set(
            "Joining.auto-join", not item.checked) or tray_icon.update_menu(),
        checked=lambda item: settings.get("Joining.auto-join")
    ))
    menu_items.append(Item("Sync Next Event", lambda tray_icon: auto_sync(), enabled=settings.get("Joining.auto-join")))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(
        Item("Join Previous Event", lambda tray_icon: join_previous_event()))
    menu_items.append(
        Item("Join Current Event", lambda tray_icon: join_current_event()))
    menu_items.append(
        Item("Join Next Event", lambda tray_icon: join_next_event()))

    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item("Open Settings File", lambda tray_icon: os.popen(
        f"notepad {from_root('settings.user.toml')}" if settings.get("Settings.open-in-notepad") else from_root('settings.user.toml'))
    ))
    menu_items.append(Item("Load Settings", lambda tray_icon: settings.load()))


    menu_items.append(Menu.SEPARATOR)
    menu_items.append(Item("Quit", stop))
    return (*menu_items,)


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

    # Join on startup if enabled
    has_creds = os.path.exists(from_root("data\\token.json"))
    if has_creds:
        join_type = settings.get("General.join-on-startup")
        if join_type == False:
            return
        join_type = join_type.lower()
        now = datetime.now().astimezone()
        time_from = time_to = None
        if join_type == "current":
            time_from = now
            time_to = now + timedelta(seconds=1)
        elif join_type == "latest":
            time_from = now - timedelta(days=1)
            time_to = now + timedelta(seconds=1)

        if time_from and time_to:
            events = get_zoom_events(time_from, time_to)
            if len(events) > 0:
                event = events.pop(0)
                join_event(event)


tray_icon = None


def start():
    global tray_icon
    # Zoom start-up and login shouldn't affect prejoin period
    os.popen(settings.get("General.zoom-path"))
    tray_menu = Menu(get_menu_items)
    tray_icon = Icon("Stroll", ICON, menu=tray_menu)
    tray_icon.run(init)


def stop(tray_icon):
    global scheduler, data, settings, auth_threads
    data.dump()
    settings.dump()
    if scheduler.active:
        scheduler.terminate()
    tray_icon.stop()


# DEVICE-STARTUP SHORTCUT
# Instead of adding/deleting the startup shortcut required, a startup shortcut is always present, and it always
# invokes the main program, which decides whether or not to start the tray icon.
# This may be a little confusing for the user since stroll.exe would show up as the startup shortcut
startup_folder = os.path.expandvars(
    "%appdata%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup")
shortcut_path = os.path.join(startup_folder, "Stroll.lnk")
if not os.path.exists(shortcut_path):
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    # The TargetPath is normally the executable itself but that causes a console to pop up when launched
    # from a shortcut. Instead we use a bat file that invokes the main program and closes itself.
    # First create the bat file
    shortcut.TargetPath = "wscript"
    shortcut.Arguments = from_root("launch.vbs")
    shortcut.WorkingDirectory = from_root("")
    shortcut.IconLocation = from_root("images\\stroll.ico")
    shortcut.WindowStyle = 7
    shortcut.save()


# STARTUP
is_device_startup = len(sys.argv) > 1 and sys.argv[1] == "--startup"
autostart = settings.get("General.auto-start")
# Device startup and normal launch are the same case
if (is_device_startup and autostart) or not is_device_startup:
    # Either it was device startup and it was wanted, or it has been explicitly ran
    start()
# But if some time is specified, then actual startup has to be scheduled for the future
elif is_device_startup and type(autostart) == time:
    time_to_start = datetime.combine(datetime.today(), autostart)
    scheduler.start()
    scheduler.add_task(time_to_start, start)
