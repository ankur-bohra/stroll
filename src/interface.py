import ctypes
import glob
import os
import re
import sys
import toml
from datetime import datetime
from threading import Timer

from PyQt5.QtCore import QRegExp, QSize, Qt
from PyQt5.QtGui import QColor, QFontDatabase, QIcon, QPixmap, QRegExpValidator
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                             QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QMenu, QPushButton, QScrollArea,
                             QSizePolicy, QTimeEdit, QVBoxLayout, QWidget,
                             QWidgetAction)

from scheduler import Scheduler


CURRENT_THEME = None


def mnemonicTextToPascal(text):
    name = text.replace("&", "")  # Strip the ampersand used for mnemonic
    name = name.title()  # Capitalize first character of all words
    name = name[0].lower() + name[1:]  # Decapitalize first character of string
    name = name.replace(" ", "")  # Remove all spaces
    return name


def solveThemeReference(path):
    '''Returns the value referred to by the given path in the current global theme.

    Example:
        solveThemeReference({'foo': {'bar': 'baz'}}, "$Theme.foo.bar") -> 'baz'

    Args:
        path(str): The path to the required value, optionally prepended by a $ sign

    Returns:
        The value referred by the path.
    '''
    global CURRENT_THEME
    keys = path.split(".")
    cursor = CURRENT_THEME
    path_traversed = ""
    for key in keys:
        # Strip $ from first key if given
        if path_traversed == "" and key[0] == "$":
            key = key[1:]

        if type(cursor) == dict:
            cursor = cursor.get(key)
            path_traversed += "." + key
        else:
            raise BaseException(
                f"Invalid path, partial path {path_traversed} does not lead to a dictionary.")
    return cursor


def fillStylesheet(theme):
    '''Fills the core stylesheet with the theme colours.

    Args:
        theme(str): The theme name, as seen in themes/theme_name.toml

    Returns:
        stylesheet(str): The filled stylesheet.
        theme(dict): The read theme dictionary.
    '''
    global CURRENT_THEME
    with open(f"themes/{theme}.toml", "r") as file:
        CURRENT_THEME = toml.load(file)

    with open(f"themes/base.qss") as file:
        style = file.read()

    regex = r"\$(?:\w+\.?)+"
    # \$: Raw match
    # (?:\w+\.?): Non capturing group
    #   \w+: Match word
    #   \.?: Optional period
    # +: Allow deep indexing e.g. $a.b.c
    style = re.sub(
        regex, lambda match: solveThemeReference(match.group(0)), style)
    return style


def createMenu(parent, text, statusTip=None, children=[], container=None):
    '''Create a QMenu object with common properties.

    Args:
        parent(QWidget): The parent for the menu.
        text(str): The mnemonic-containing text for the menu. Used to construct the menu objectName in pascal case.
        statusTip(optional, str): The status tip shown on hovering over the menu.
        children(optional, List[QAction | QMenu | str]): A list of actions, menus and "|" (for separators), to add to the menu in the given order.
        container(optional, QWidget): The container for the menu. Must have an addMenu() method.
    '''
    name = mnemonicTextToPascal(text)

    menu = QMenu(text, parent, objectName=name)
    if statusTip:
        menu.setStatusTip(statusTip)

    for child in children:
        if child == "|":
            menu.addSeparator()
        elif type(child) == QMenu:
            menu.addMenu(child)
        else:
            menu.addAction(child)

    if container:
        container.addMenu(menu)
    return menu


def createAction(parent, text, trigger=None, checkable=False, checked=False, icon=None):
    '''Create an action with common properties.

    Args:
        parent(QWidget): The parent for the action.
        text(string): The mnemonic-containing action text.
        checkable(optional, bool): Control whether the action is checkable. Defaults to False.
        checked(optional, bool): Conrol whether the action is checked if it is checkable. Defaults to False.
    '''
    action = QAction(text, parent, objectName=mnemonicTextToPascal(text))
    action.setCheckable(checkable)
    if checkable:
        action.setChecked(checked)
    if icon:
        action.setIcon(icon)
    if trigger:
        action.triggered.connect(trigger)
    return action


def createChoiceActionGroup(parent, groupName, choices, default):
    '''Create an action group with checkable actions.

    Args:
        parent(QWidget): The parent for the actions in the action group.
        groupName(str): Name of the action group.
        choices(Dict[str: lambda | function]): Dictionary of choice-onChosen pairs, optionally with an acceptor.
        default(str): The default choice.

    Returns:
        A tuple of all actions in the action group.

    To add a choice that accepts a float, a single pair of the following
    format may be added:
        "ACCEPTOR": {
            "Hint": "Acceptor Hint"         
                    (str): The hint showed above the input field.
            "Range": (minValue, maxValue)   
                    (tuple): The range of the input field.
            "Default": defaultValue,        
                    (optional, float): The default value of the field. Defaults to minValue 
            "Suffix": suffix,               
                    (optional, str): The suffix added to the field.
            "Triggered":  onChosen          
                    (function | lambda): The callback for when the field is chosen.
        }
    The field-accepting choice is always at the end and separated from
    other choices by a separator.
    '''
    actionGroup = QActionGroup(parent, objectName=groupName)
    actionGroup.setExclusive(True)

    actions = ()
    for actionText in choices:
        if actionText != "ACCEPTOR":
            isDefault = actionText.replace("&", "") == default.replace(
                "&", "")  # Mnemonic can be omitted while calling
            action = createAction(
                parent, actionText, choices[actionText], checkable=True, checked=isDefault)
            actionGroup.addAction(action)
            actions += (action,)

    # Always add acceptor at end
    if "ACCEPTOR" in choices:
        info = choices["ACCEPTOR"]
        hint, suffix, onChosen = info["Hint"], info["Suffix"], info["Triggered"],
        minValue, maxValue, defaultValue = info["Range"][0], info["Range"][1], info["Default"]
        # Acceptor choice comes before field
        # While WidgetActions do provide a checkable property right out of the box,
        # it looks congested. Hence a separate action using the hint is made.
        action = createAction(parent, hint, onChosen,
                              checkable=True, checked=default == "ACCEPTOR")
        actionGroup.addAction(action)

        # Create input field
        # Append to given hint e.g. setCustomDurationAcceptor
        field = QDoubleSpinBox(parent, objectName=action.objectName()+"Field")
        field.setRange(minValue, maxValue)
        field.setSuffix(" "+suffix)  # Suffix looks better with a space before
        field.setValue(defaultValue)
        # Widgets can only be added using WidgetActions
        fieldWidget = QWidgetAction(parent)
        fieldWidget.setDefaultWidget(field)

        actions += ("|", action, fieldWidget)  # Separator goes before acceptor

    return actions


def forceAspectRatio(widget, ratio):
    '''Forces a widget to resize with an aspect ratio.

    Args:
        widget(QWidget): The widget that will be resized.
        ratio(float): The ratio of the widget's height to its width.
    '''
    sidebar = widget.parent().findChild(QFrame, "sidebar")
    scale = QSize(100, ratio*100)

    def resizeEvent(event):
        size = QSize(scale)
        size.scale(event.size(), Qt.AspectRatioMode.KeepAspectRatio)
        widget.resize(size)
    # widget.sizeHint = sizeHint
    widget.resizeEvent = resizeEvent


def makeButtonIconDynamic(pushButton, size, ratio):
    '''Allows a QPushButton to resize its icon with the button itself.

    Args:
        pushButton(QPushButton): The button that will resize its icon.
        size(QSize): The size of the icon at any scale. Used to maintain aspect ratio.
        ratio(float): The ratio of the icon size to the button size. This allows "padding" around the icon.
    '''
    oldEvent = pushButton.resizeEvent

    def wrapped(event):
        oldEvent(event)
        iconSize = QSize(size)  # Use original pixmap size for scaling.
        # Icon must be scaled to provide padding
        iconSize.scale(pushButton.size() * ratio, Qt.KeepAspectRatio)
        pushButton.setIconSize(iconSize)
    pushButton.resizeEvent = wrapped


def alphaAwareFill(pixmap, color):
    '''Fills a pixmap with the specified color alpha adjusted.

    Args:
        pixmap(QPixmap): The pixmap to fill with color.
        color(QColor): The color to fill the object with.

    Returns:
        The filled pixmap.
    '''
    # Pixmaps are meant for displaying and don't support modification
    # to pixels, while images do.
    image = pixmap.toImage()

    for y in range(image.height()):
        for x in range(image.width()):
            color.setAlpha(image.pixelColor(x, y).alpha())
            image.setPixelColor(x, y, color)

    pixmap = QPixmap.fromImage(image)
    return pixmap


def createMultiInputDialog(title, parent, standardButtons=None):
    '''Creates a QInputDialog-like dialog that allows multiple entries.

    The entries are handled using a QFormLayout accessible as the form
    attribute. Entries are to be added to dialog.form as they would in
    any QFormLayout.

    Args:
        title(string): The title for the dialog window.
        parent(QWidget): The parent for the dialog.
        standardButtons(optional, StandardButtons | StandardButton): The buttons at the bottom of the dialog.

    Returns: The dialog.
    '''
    dialog = QDialog(parent)
    dialog.setWindowTitle(" " + title)  # Too close by default

    grid = QGridLayout(dialog)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSizeConstraint(QGridLayout.SizeConstraint.SetNoConstraint)

    formContainer = QWidget(dialog, objectName="formContainer")
    # Window resizes to this size due to grid layout
    formContainer.setFixedSize(600, 270)
    formContainer.setContentsMargins(16, 16, 16, 16)
    form = QFormLayout(formContainer)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    dialog.form = form

    feedback = QLabel(formContainer, objectName="feedback")
    dialog.feedback = feedback

    buttonBox = QDialogButtonBox()
    buttonBox.setContentsMargins(16, 8, 16, 8)
    # Can't be styled by default
    buttonBox.setAttribute(Qt.WA_StyledBackground, True)
    dialog.buttonBox = buttonBox
    if standardButtons:
        buttonBox.setStandardButtons(standardButtons)

    grid.addWidget(formContainer, 0, 0)
    grid.addWidget(feedback, 1, 0, Qt.AlignmentFlag.AlignHCenter)
    grid.addWidget(buttonBox, 2, 0)

    return dialog


def createBoardButtonLabelPair(parent, text, iconPath, statusTip=None):
    '''Creates and shows a button-label pair styled for the board area.

    Args:
        parent(QWidget): The parent for the pair. Normally the board itself.
        text(string): The text the label should hold.
        iconPath(string): The relative-from-root path for the icon the button will use.
        statusTip(optional, string): The status tip for the button.

    Returns:
        The button and the label.
    '''
    button = QPushButton(parent)
    button.setProperty("type", "boardButton")
    fillColor = solveThemeReference("Board.LabelledButton.foreground")
    filledPixmap = alphaAwareFill(QPixmap(iconPath), QColor(fillColor))
    button.setIcon(QIcon(filledPixmap))
    button.setFixedSize(25, 25)
    button.setIconSize(QSize(25, 25))
    if statusTip:
        button.setStatusTip("Create a new meeting.")

    label = QLabel(text, parent)
    label.setProperty("type", "boardButtonLabel")
    label.setFixedSize(len(text)*14, 35)

    # For whatever reason show() needs to be explicitly called after the first pair is created.
    button.show()
    label.show()
    return button, label


def createMeetingCard(title, info, time):
    '''Creates a meeting card.

    Args:
        title(str): The title assigned to the meeting.
        link(str): The user given link for the meeting. Reformatted for uniformity.
        time(datetime): The time to join the meeting at.

    Returns:
        A QFrame representing the meeting.
    '''
    card = QFrame(objectName="meetingCard")
    card.setFixedSize(758, 115)

    name = QLabel(title, card, objectName="name")
    name.setFixedSize(300, 40)
    name.move(23, 23)

    # RED: #902039; YELLOW: #e3dd89; GREEN: #708f6f; GREY: #939393; LINK: #365CF2; TEXT: 11
    clockPixmap = alphaAwareFill(
        QPixmap("icons/home/clock.png").scaled(17, 17), QColor("#902039"))
    clock = QLabel(card)
    clock.setPixmap(clockPixmap)
    clock.setFixedSize(17, 17)
    clock.move(23, 75)
    # There's no character for non zero-padded hour
    joinTime = QLabel(time.strftime(
        f"{time.hour}:%M %p"), card, objectName="joinTime")
    joinTime.setFixedSize(82, 17)
    joinTime.move(48, 74)

    linkPixmap = alphaAwareFill(
        QPixmap("icons/home/link.png").scaled(17, 17), QColor(solveThemeReference("MeetingCard.Link.Icon.background")))
    linkIcon = QLabel(card)
    linkIcon.setPixmap(linkPixmap)
    linkIcon.setFixedSize(17, 17)
    linkIcon.move(147, 75)
    # Links are "rebuilt" for uniformity
    linkFormat = "https://www.zoom.us/j/{0}?pwd={1}"
    # Only the link contains the password, it's useless and space-consuming on the card itself.
    # Verification of the link can be done through meeting ID.
    link = linkFormat.format(info['id'], info['pwd'])
    # Meeting IDs are bold for easier comparison.
    text = linkFormat.format(f"<b>{info['id']}</b>", ' . . .')
    richText = f"<a href='{link}'> {text} </a>"
    meetingLink = QLabel(richText, card, objectName="link")
    meetingLink.setOpenExternalLinks(True)
    meetingLink.setFixedSize(378, 27)
    meetingLink.move(172, 68)
    meetingLink.setTextInteractionFlags(
        Qt.TextInteractionFlag.LinksAccessibleByMouse)
    return card


def createHomeScrollableArea(parent, cards=[]):
    '''Creates the scrollable meetings area in the home board.

    Args:
        parent(QWidget): The parent for the scrollable area.
        cards(List[QWidget]): The cards to put in the scrollable area.
    '''
    scrollArea = QScrollArea(parent)
    scrollArea.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    scrollArea.setContentsMargins(0, 0, 0, 0)

    scrollArea.setFixedSize(789, 300)
    scrollArea.move(17, 68)

    holder = QWidget(scrollArea, objectName="scrollHolder")
    # (Height + Padding) per card * No. of cards
    holder.setMinimumSize(758, (115+15) * len(cards))
    scrollArea.setWidget(holder)

    vL = QVBoxLayout(holder)
    vL.setContentsMargins(0, 0, 0, 0)
    for card in cards:
        vL.addWidget(card)

    scrollArea.show()


def createSettingsField(parent, type, text, trigger, options=None):
    '''Creates a container that holds all parts of a settings field.

    Args:
        parent(QWidget): The widget to parent the card to.
        type(str): The type of the field. "Checkbox" or "Combobox",
        text(str): The text the field starts with. Always prepended with 
                    a bullet point. Always followed by the corresponding
                    interactive widget.
        trigger(function | lambda): The function to call when the field 
                                    value changes.
        options(tuple[str]): The options to be used in the "Combobox". 
                            The first  option must be the default option.
                            Ignored if the type is not "Combobox".

    Returns
        The field-container QWidget created.
    '''
    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setSpacing(10)

    textLabel = QLabel(f"•  {text}", container, objectName="fieldText")
    layout.addWidget(textLabel)

    if type == "Checkbox":
        field = QCheckBox(container)
        field.stateChanged.connect(trigger)
    elif type == "Combobox":
        trigger, options = options, trigger  # This is a lazy overload solution
        field = QComboBox(container)
        field.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        for index in range(len(options)):
            # Initial space is for padding, trailing is to avoid clipping
            field.insertItem(index, " "+options[index]+" ")
    layout.addWidget(field)
        

    return container


def createSettingsCard(parent, title, settings):
    '''Creates a card that groups the given settings.

    Cards do not truncate for any number of settings.

    Args:
        parent(QWidget): The widget to parent the card to.
        title(str): The title for the card.
        settings(List[dict]): The settings the card will group.
            There is a specific format for accepting various types of settings.
            The general format for the parameter is {field1, field2, ...}, where
            each field is a tuple with the following format:
                (type, text, trigger, options)

                type: "Checkbox" | "Combobox",
                    (str): The type of the field.
                text: fieldText,
                    (str): The text the field starts with. Always prepended with 
                            a bullet point. Always followed by the corresponding
                            interactive widget.
                trigger: onFieldChange
                    (function | lambda): The function to call when the field value changes.
                options: (defaultOption, option2, option3, ...),
                    (tuple[str]): The options to be used in the "Combobox". The first
                                    option must be the default option.
                                    Ignored if the type is not "Combobox".
            Fields must be present in the order they are to be added.

    Returns
        The settings card created.
    '''
    card = QFrame(parent)
    card.setFixedSize(743, 150)
    card.setObjectName("settingsCard")

    titleLabel = QLabel("Auto Sync", card, objectName="title")
    titleLabel.setFixedSize(700, 32)
    titleLabel.move(21, 18)

    i = 0
    for field in settings:
        fieldContainer = createSettingsField(card, *field)
        fieldContainer.move(21, 45 + 33*i)
        i+=1

    card.show()
    return card


def joinMeeting(id, hashed_pwd):
    '''Joins a zoom meeting using the zoom client's url protocol.

    Args:
        id(int): The meeting ID.
        hashed_pwd(str): The hashed password as it appears in the meeting link.
    '''
    url = f"zoommtg://zoom.us/join?action=join&confno={id}&pwd={hashed_pwd}"
    command = f"%appdata%/Zoom/bin/zoom.exe --url=\"{url}\""
    os.popen(command)


class StrollWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # WINDOW ATTRIBUTES
        # Used to switch from empty message after tooltips to previous message
        self._statusBarMessage = "Starting up Stroll..."
        self._activeBoard = None  # e.g. calendar, home, ...
        self._scheduler = Scheduler()

        # WINDOW CONFIGURATION
        self.setWindowTitle(" Stroll")
        appIcon = QIcon("icons/stroll.png")
        # setWindowIcon() should but doesn't apply the icon to the windows taskbar.
        # Windows needs to be told python is hosting another application and python's icon should be not be used.
        # This can be done by changing the Application User Model Id to an arbitary string.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Stroll")
        # setWindowIcon() will now affect window and taskbar icons.
        self.setWindowIcon(appIcon)
        self.setFixedSize(900, 450)

        # WINDOW FILLING
        self._createStatusBar()
        self._createMenuBar()
        self._createBody()
        self._showHome()

        self._scheduler.start()

    def _createStatusBar(self):
        '''Creates the status bar at the bottom of the window.

        The status bar is used to display the next meeting and its time if one is pending.
        '''
        statusBar = self.statusBar()
        # No use of non-functional size grip
        statusBar.setSizeGripEnabled(False)
        # Status bar is set to an empty string if any element's status tip is displayed, hiding the actual status.
        statusBar.messageChanged.connect(
            lambda text: text == "" and self._showStatusBarMessage(self._statusBarMessage))
        self._showStatusBarMessage(self._statusBarMessage)

    def _showStatusBarMessage(self, message, duration=-1):
        '''Shows a message on the status bar.

        Args:
            message(str): The message to display.
            duration(optional, float): The number of seconds to display the message for, -1 for non-disappearing. Defaults to -1.
        '''
        oldMessage = self._statusBarMessage
        self._statusBarMessage = message
        self.statusBar().showMessage(message)

        # Timer could be called with -1 duration but that would be bad for memory.
        if duration > 0:
            Timer(duration, lambda: self._showStatusBarMessage(oldMessage)).start()

    def _createMenuBar(self):
        '''Creates the menu bar at the top of the window.

        The menu bar provides a native interface for finer control of the application.
        '''
        menubar = self.menuBar()

        # MEETING MENU
        newMeeting = createAction(
            self, "&New Meeting", self._showCreationPrompt)
        joinMeeting = createAction(
            self, "&Join Next Meeting", self._joinMeeting)
        syncMeetings = createAction(self, "&Sync Meetings", self._syncMeetings)
        syncMeetings.setEnabled(False)

        children = [newMeeting, joinMeeting, "|", syncMeetings]
        meetingMenu = createMenu(
            self, "&Meeting", "Create or join meetings", children=children, container=menubar)

        # JOINING MENU
        pausedButton = createAction(
            self, "&Paused", lambda: self._changeStatus("Pause"))
        brieflyPause = createMenu(self, "&Briefly Pause", children=createChoiceActionGroup(self, "pauseValues", {
            "Pause for &1 minute": lambda: self._changeStatus("Pause", 1),
            "Pause for &5 minutes": lambda: self._changeStatus("Pause", 5),
            "Pause for &10 minutes": lambda: self._changeStatus("Pause", 10),
            "ACCEPTOR": {
                "Hint": "&Set Custom Pause",
                "Range": (0, 120),
                "Default": 30,
                "Suffix": "mins",
                "Triggered": lambda: self._changeStatus("Pause", self.findChild(QDoubleSpinBox, "setCustomPauseField").value())
            }
        }, default="Pause for 5 minutes"))

        children = [pausedButton, brieflyPause]
        createMenu(self, "&Joining", "Pause automatic joining.",
                   children=children, container=menubar)

        # EDIT MENU
        preferences = createMenu(self, "&Preferences", children=[
            createAction(self, "Change Color &Theme", self._changeTheme),
            createAction(self, "Open &Settings", self._showSettings),
        ])

        enableSyncing = createAction(
            self, "&Enable Syncing", self._toggleSyncing, checkable=True, checked=False)
        enableSyncing.setEnabled(False)
        autoSyncMenu = createMenu(self, "&Automatically Sync", children=createChoiceActionGroup(self, "syncDelay", choices={
            "Sync every 5 minutes": lambda: self._setSyncDelay(5),
            "Sync every 10 minutes": lambda: self._setSyncDelay(10),
            "Sync every 30 minutes": lambda: self._setSyncDelay(30),
            "ACCEPTOR": {
                "Hint": "Set Custom Delay",
                "Range": (1, 90),
                "Default": 45,
                "Suffix": "mins",
                "Triggered": lambda: self._setSyncDelay(self.findChild(QDoubleSpinBox, "setCustomDelayField").value())
            }
        }, default="Sync every 10 minutes"))

        linkAccount = createAction(
            self, "&Link Google Account", self._linkAccount)
        removeAccount = createAction(
            self, "&Remove Account", self._removeAccount)
        removeAccount.setEnabled(False)

        children = [enableSyncing, autoSyncMenu,
                    "|", linkAccount, removeAccount]
        syncing = createMenu(self, "&Syncing", children=children)

        children = [preferences, syncing]
        createMenu(self, "&Edit", "Edit preferences and syncing.",
                   children, container=menubar)
        # HELP MENU
        about = createAction(self, "&About")
        usage = createAction(self, "&How To Use")
        report = createAction(self, "&Report Issue")
        credit = createAction(self, "@ankur-bohra",
                              icon=QIcon("icons/GitHub.png"))
        credit.setEnabled(False)

        children = [about, usage, report, "|", credit]
        createMenu(self, "&Help", children=children, container=menubar)

    def _createBody(self):
        '''Creates the sidebar and board.
        '''
        sidebar = QFrame(self, objectName="sidebar")

        board = QFrame(self, objectName="board")
        self._board = board

        container = QFrame(self)
        self.setCentralWidget(container)
        # A ratio must be maintained between the sidebar and the board. This
        # can be done using a horizontal layout or a grid. WHile a horizontal
        # layout seems more intuitive, implementing the ratio is significantly
        # simpler using grids and columnspans.
        grid = QGridLayout(container)
        grid.setSpacing(0)  # Grid shouldn't have any gaps inside
        grid.setContentsMargins(0, 0, 0, 0)  # or outside
        grid.addWidget(sidebar, 0, 0, 1, 1)
        # Board should have a width ~10x that of the sidebar
        # So it must occupy 10 columns if the sidebar occupies one
        grid.addWidget(board, 0, 1, 1, 10)

        self._fillSidebar(sidebar)

    def _fillSidebar(self, sidebar):
        '''Fills the sidebar with functional buttons
        '''
        grid = QGridLayout(sidebar)
        buttons = glob.glob("icons/sidebar/*.png")
        for i in range(len(buttons)):
            # icons/sidebar\\Settings.png -> Settings.png -> Settings
            buttons[i] = buttons[i].split("\\")[-1][0:-4]

        # All icons are given the same target size, and each icon adjusts according
        # to its own aspect ratio.
        iconToButtonRatio = 0.7

        INACTIVE_BTN_ICON_COLOR = solveThemeReference("Sidebar.Button.Inactive.foreground")
        ACTIVE_BTN_ICON_COLOR = solveThemeReference("Sidebar.Button.Active.foreground")
        for button_no in range(len(buttons)):
            name = buttons[button_no]
            # The button holder has the rounded corners and holds the actual push
            # button. It is responsible for handling the resizing.
            button = QPushButton(self, objectName=f"sidebarButton{name}")
            button.setSizePolicy(QSizePolicy.Policy.Preferred,
                                 QSizePolicy.Policy.Preferred)
            button.setProperty("active", False)
            button.setProperty("type", "sidebarButton")
            forceAspectRatio(button, 1)

            # The button switches between premade copies of active and inactive icons.
            pixmap = QPixmap(f"icons/sidebar/{name}.png")
            
            # Make icons accessible directly from button.
            button.inactiveIcon = QIcon(alphaAwareFill(
                pixmap, QColor(INACTIVE_BTN_ICON_COLOR)))
            button.activeIcon = QIcon(alphaAwareFill(
                pixmap, QColor(ACTIVE_BTN_ICON_COLOR)))
            makeButtonIconDynamic(button, pixmap.size(), iconToButtonRatio)
            button.setIcon(button.inactiveIcon)  # Default is set separately.
            button.clicked.connect(getattr(self, f"_show{name}"))
            # Every odd row is occupied by a button.
            grid.addWidget(button, button_no*2 + 1, 0)

        # Grid is made with uniform rows everywhere to maintain even margins.
        for row_no in range(0, len(buttons)*2+1):
            grid.setRowStretch(row_no, 1)

    def _activateSidebarButton(self, name):
        '''Activates the specified button and deactivaties the active button.

        NOTE: This method must be called BEFORE changing the board.

        Args:
            name(str): The name of the button to be activated.
        '''
        if name == self._activeBoard:
            # No change required
            return

        button = self.findChild(QPushButton, f"sidebarButton{name}")
        button.setProperty("active", True)
        # Activate new button
        button.setIcon(button.activeIcon)
        # The changed icon must be scaled to fit the current size
        button.resize(button.size())
        # Deactivate old button
        if self._activeBoard and self._activeBoard != name:
            oldButton = self.findChild(
                QPushButton, f"sidebarButton{self._activeBoard}")
            oldButton.setProperty("active", False)
            if oldButton:
                oldButton.setIcon(oldButton.inactiveIcon)
                oldButton.resize(oldButton.size())

        # with open("themes/light_stroll.qss", "r") as stylesheet:
        styleSheet = self.styleSheet()
        self.setStyleSheet("")
        self.setStyleSheet(styleSheet)

    def _clearBoard(self):
        for child in self._board.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.deleteLater()

    def _showHome(self):
        self._activateSidebarButton("Home")
        self._clearBoard()
        self._activeBoard = "Home"

        newMeeting, newMeetingLabel = createBoardButtonLabelPair(
            self._board, "New Meeting", "icons/home/add.png", "Create a new meeting.")
        newMeeting.clicked.connect(self._showCreationPrompt)

        if self._scheduler.head is None:
            # Show button at center
            newMeeting.setFixedSize(50, 50)
            newMeeting.setIconSize(QSize(50, 50))
            newMeeting.move(375, 160)

            newMeetingLabel.setProperty("type", "boardButtonLabelLarge")
            newMeetingLabel.setStyleSheet(self.styleSheet())  # Needs an update to enforce style
            newMeetingLabel.setFixedSize(202, 45)
            newMeetingLabel.move(300, 220)
            return

        newMeeting.move(33, 24)
        newMeetingLabel.move(72, 16)

        pause, pauseLabel = createBoardButtonLabelPair(
            self._board, "Pause Joining", "icons/home/pause.png", "Toggle automatic joining.")
        pause.clicked.connect(self._toggleJoining)
        pause.move(569, 24)
        pauseLabel.move(608, 16)

        # Create main scrollable area
        cards = []
        node = self._scheduler.head
        while node:
            data = node.value["data"]
            cards.append(createMeetingCard(
                data["title"], data["info"], data["time"]))
            node = node.next
        scrollArea = createHomeScrollableArea(self._board, cards)

    def _showSettings(self):
        self._activateSidebarButton("Settings")
        self._clearBoard()
        self._activeBoard = "Settings"

    def _showCalendar(self):
        self._activateSidebarButton("Calendar")
        self._clearBoard()
        self._activeBoard = "Calendar"

        general = createSettingsCard(self._board, "General", {
            ("Combobox", "Sync meetings from", ("Calendar1", "Calendar2", "Calendar3"), 
                lambda: print("Edited")),
            ("Checkbox", "Use event names as meeting names", lambda: print("Edited")),
        })
        general.move(25, 50)

        autoSync = createSettingsCard(self._board, "General", {
            ("Combobox", "Sync meetings every", ("Calendar1", "Calendar2", "Calendar3"), 
                lambda: print("Edited")),
            ("Checkbox", "Use event names as meeting names", lambda: print("Edited")),
        })
        autoSync.move(25, 250)        

    def _showCreationPrompt(self):
        dialog = createMultiInputDialog(
            "New Meeting", self, QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        dialog.setFixedSize(600, 220)

        linkRegEx = QRegExp(
            r"(?:https?://)?(?:[^\s\.]+\.)?zoom\.us/j/(\d{9,11})\?pwd=(\w+)(?:.+)?")
        # (?:https?://)? : optionally allow https:// or http://
        # (?:[^\s\.]+\.)? : optionally allow subdomain e.g. subdomain.zoom.us => subdomain. Don't allow spaces or further subdomains.
        # zoom\.us/j/ : raw match
        # (\d{9,11}) : meeting id, can be 9-11 digits
        # \?pwd= : raw match
        # (\w+): match all alphanumeric characters NOTE: May be enforced to 32 characters if found to be always true.
        # (?:.+)?: optionally allow instances of #success after link e.g. ?pwd=xxxxxxxxxxxxxxxxxx#success

        title = QLineEdit(placeholderText="(Defaults to meeting id)")

        # Meeting title defaults to meeting id
        title.textChanged.connect(
            lambda text: title.setText(
                # Change to meeting id if 1) Title is empty and 2) Meeting id is found
                # itemAt is a dirty method to get the `link` QLineEdit defined later
                # NOTE: labels are stored as items before corresponding QLineEdits, hence itemAt(3)
                linkRegEx.cap(1) if (linkRegEx.exactMatch(
                    dialog.form.itemAt(3).widget().text()) and text == "") else text
            )
        )
        dialog.form.addRow("Title:", title)

        link = QLineEdit(
            placeholderText="(...)zoom.us/j/xxxxxxxxx(x(x))?pwd=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx(...)")
        linkValidator = QRegExpValidator(linkRegEx)
        link.setValidator(linkValidator)
        # Meeting title defaults to meeting id
        link.textChanged.connect(
            lambda text: title.setText(
                # Change to meeting id if 1) Title is empty and 2) Meeting id is found
                linkRegEx.cap(1) if (linkRegEx.exactMatch(text)
                                     and title.text() == "") else title.text()
            )
        )
        dialog.form.addRow("Meeting Link:", link)

        time = QTimeEdit(displayFormat="hh:mm:ss AP")
        dialog.form.addRow("Join Time:", time)

        dialog.buttonBox.accepted.connect(
            # Add meeting, destroy dialogue, show home if a valid link is found, all other data will then also be valid.
            # Chaining ors with non-returning functions allows multiple calls in a single statement.
            lambda: self._addMeeting(title.text(), link.text(), time.time()) or dialog.deleteLater() or self._showHome(
            ) if linkRegEx.exactMatch(link.text()) else dialog.feedback.setText("Invalid link. Try again or send a report!")
        )
        dialog.buttonBox.rejected.connect(dialog.destroy)
        dialog.setStyleSheet(self.styleSheet())
        dialog.show()

    def _addMeeting(self, title, link, time):
        '''Adds a meeting to the scheduler and updates internal record.

        Args:
            title(string): The title associated with the meeting. Used only internally.
            link(string): The link associated with the meeting.
            time(QTime): The time to join the meeting at.
        '''
        linkRegEx = r"(?:https?://)?(?:[^\s\.]+\.)?zoom\.us/j/(\d{9,11})\?pwd=(\w+)(?:.+)?"
        pattern = re.search(linkRegEx, link)
        meetingId = int(pattern.group(1))
        password = pattern.group(2)
        # Time is converted to datetime for operations and scheduler compatibility
        today = datetime.today()
        time = datetime(today.year, today.month, today.day,
                        time.hour(), time.minute(), time.second())
        data = {
            "title": title,
            "info": {
                "id": meetingId,
                "pwd": password
            },
            "time": time
        }

        self._scheduler.add_task(time, lambda: joinMeeting(
            meetingId, password), data=data)

    def _joinMeeting(self): pass
    def _syncMeetings(self): pass
    def _changeStatus(self, action, duration=-1): pass
    def _changeTheme(self): pass
    def _setSyncDelay(self, delay): pass
    def _toggleSyncing(self): pass
    def _toggleJoining(self): pass
    def _linkAccount(self): pass
    def _removeAccount(self): pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    stylesheet = fillStylesheet("light")
    window = StrollWindow()
    fontDb = QFontDatabase()
    for file in glob.glob("fonts/*.ttf"):
        fontDb.addApplicationFont(file)
    window.setStyleSheet(stylesheet)
    window.show()
    sys.exit(app.exec_() and window._scheduler.terminate())
