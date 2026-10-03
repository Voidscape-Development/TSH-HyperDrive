from qtpy.QtGui import *
from qtpy.QtWidgets import *
from qtpy.QtCore import *
from loguru import logger

from .TSHGameAssetManager import TSHGameAssetManager
from .TSHTheme import TSHTheme, Blend
from .TournamentDataProvider.TournamentEventLookup import (
    FetchTournamentEvents, TournamentLookupError,
    ERROR_NOT_FOUND, ERROR_NO_EVENTS, ERROR_PARRY_KEY,
    STATE_ACTIVE, STATE_COMPLETED
)
from .Workers import Worker

ICON_SIZE = 52
LOCATION_ICON_SIZE = 22
DETAIL_ICON_SIZE = 14
STRIPE_WIDTH = 4
LOCATION_ICONS = {
    "online": ["./assets/icons/online.svg"],
    "offline": ["./assets/icons/offline.svg"],
    "hybrid": ["./assets/icons/offline.svg", "./assets/icons/online.svg"],
}


def LocationNames():
    return {
        "online": QApplication.translate("app", "Online"),
        "offline": QApplication.translate("app", "Offline"),
        "hybrid": QApplication.translate("app", "Hybrid (online and offline)"),
    }


def GameLogoPath(provider, gameId):
    # Same ids the providers switch the game with (see SetGameFromProvider),
    # so an event shows an icon when TSH has that game installed
    if gameId is None:
        return None
    key = "smashgg_game_id" if provider == "startgg" else "igdb_game_id"
    for game in TSHGameAssetManager.instance.games.values():
        if str(game.get(key, "")) == str(gameId):
            return game.get("logo_path")
    return None


def ThemeColors():
    theme = TSHTheme.Colors()
    return {
        "text": theme["text"],
        "window": theme["window"],
        "card": theme["surface"],
        "tile": theme["raised"],
        "border": theme["border"],
        "muted": theme["muted"],
        "highlight": theme["accent"],
        "hover": Blend(theme["surface"], theme["accent"], 0.7),
        "selected": theme["accentSoft"],
    }


def TintedIcon(path, color, size):
    pixmap = QIcon(path).pixmap(size, size)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def StatusStyle(state):
    # Label and color of each event state. Dark enough for white text.
    if state == STATE_ACTIVE:
        return QApplication.translate("app", "In progress"), QColor("#1e8449")
    if state == STATE_COMPLETED:
        return QApplication.translate("app", "Completed"), QColor("#6b7280")
    return QApplication.translate("app", "Upcoming"), QColor("#2563eb")


def Initials(name):
    words = [w for w in (name or "").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


class TSHEventCard(QWidget):
    def __init__(self, provider, event, parent=None):
        super().__init__(parent)
        colors = ThemeColors()
        muted = colors["muted"]
        statusText, self.statusColor = StatusStyle(event.get("state"))

        layout = QHBoxLayout(self)
        # Room on the left for the status stripe
        layout.setContentsMargins(STRIPE_WIDTH + 10, 8, 12, 8)
        layout.setSpacing(12)

        # Game logo in a tile, or the game's initials when TSH doesn't have it
        tile = QLabel()
        tile.setFixedSize(ICON_SIZE, ICON_SIZE)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setStyleSheet(
            f"background: {colors['tile'].name()}; border-radius: 8px;"
            f"color: {muted.name()}; font-weight: bold;")
        logoPath = GameLogoPath(provider, event.get("gameId"))
        pixmap = QPixmap(logoPath) if logoPath else QPixmap()
        if not pixmap.isNull():
            tile.setPixmap(pixmap.scaled(
                ICON_SIZE - 8, ICON_SIZE - 8,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            tile.setText(Initials(event.get("game")))
        tile.setToolTip(event.get("game", ""))
        layout.addWidget(tile)

        column = QVBoxLayout()
        column.setSpacing(4)
        layout.addLayout(column, 1)

        nameRow = QHBoxLayout()
        nameRow.setSpacing(6)
        column.addLayout(nameRow)

        name = QLabel(event.get("name", ""))
        name.setStyleSheet(f"color: {colors['text'].name()};")
        font = name.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.15)
        name.setFont(font)
        nameRow.addWidget(name, 1)

        pill = QLabel(statusText.upper())
        pillFont = pill.font()
        pillFont.setBold(True)
        pillFont.setPointSizeF(pillFont.pointSizeF() * 0.8)
        pillFont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        pill.setFont(pillFont)
        pill.setStyleSheet(
            f"background: {self.statusColor.name()}; color: white;"
            "border-radius: 9px; padding: 2px 8px;")
        nameRow.addWidget(pill)

        # Online/offline as icons, so it reads at a glance
        location = event.get("location")
        tooltip = LocationNames().get(location)
        for icon in LOCATION_ICONS.get(location, []):
            label = QLabel()
            label.setPixmap(QIcon(icon).pixmap(LOCATION_ICON_SIZE, LOCATION_ICON_SIZE))
            label.setToolTip(tooltip)
            nameRow.addWidget(label)

        details = QHBoxLayout()
        details.setSpacing(4)
        column.addLayout(details)

        def addDetail(iconPath, value):
            if details.count() > 0:
                details.addSpacing(10)
            if iconPath:
                icon = QLabel()
                icon.setPixmap(TintedIcon(iconPath, muted, DETAIL_ICON_SIZE))
                details.addWidget(icon)
            label = QLabel(value)
            label.setStyleSheet(f"color: {muted.name()};")
            details.addWidget(label)

        if event.get("game"):
            addDetail(None, event.get("game"))
        addDetail("./assets/icons/people.svg", QApplication.translate(
            "app", "{0} entrants").format(event.get("numEntrants", 0)))
        if event.get("startAt"):
            date = QDateTime.fromSecsSinceEpoch(int(event.get("startAt")))
            addDetail("./assets/icons/calendar.svg",
                      QLocale().toString(date, QLocale.FormatType.ShortFormat))
        details.addStretch()

    def paintEvent(self, event):
        # Status stripe down the card's left edge
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.statusColor)
        painter.drawRoundedRect(
            QRectF(4, 8, STRIPE_WIDTH, self.height() - 16), STRIPE_WIDTH / 2, STRIPE_WIDTH / 2)
        painter.end()


class TSHSelectEventWindow(QDialog):
    def __init__(self, parent, threadPool, onEventSelected):
        super().__init__(parent)
        self.threadPool = threadPool
        self.onEventSelected = onEventSelected
        self.provider = None

        self.setWindowTitle(QApplication.translate("app", "Select an event"))
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout()
        self.setLayout(layout)

        colors = ThemeColors()

        self.header = QLabel(QApplication.translate("app", "Loading events..."))
        self.header.setWordWrap(True)
        font = self.header.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.4)
        self.header.setFont(font)
        layout.addWidget(self.header)

        self.subheader = QLabel()
        self.subheader.setStyleSheet(f"color: {colors['muted'].name()};")
        self.subheader.hide()
        layout.addWidget(self.subheader)

        self.searchBar = QLineEdit()
        self.searchBar.setPlaceholderText(QApplication.translate("app", "Filter..."))
        self.searchBar.textEdited.connect(self.FilterList)
        layout.addWidget(self.searchBar)

        self.eventList = QListWidget()
        self.eventList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.eventList.itemDoubleClicked.connect(lambda item: self.LoadSelectedEvent())
        self.eventList.installEventFilter(self)
        # Each event is a rounded box on the window's background
        self.eventList.setSpacing(4)
        self.eventList.setFrameShape(QFrame.Shape.NoFrame)
        self.eventList.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.eventList.setStyleSheet(f"""
            QListWidget {{ background: {colors['window'].name()}; outline: none; }}
            QListWidget::item {{
                background: {colors['card'].name()};
                border: 1px solid {colors['border'].name()};
                border-radius: 10px;
            }}
            QListWidget::item:hover {{
                border: 1px solid {colors['hover'].name()};
            }}
            QListWidget::item:selected {{
                background: {colors['selected'].name()};
                border: 2px solid {colors['highlight'].name()};
            }}
        """)
        layout.addWidget(self.eventList)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.okButton = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.okButton.setDisabled(True)
        buttons.accepted.connect(self.LoadSelectedEvent)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(600, 500)

    def eventFilter(self, obj, event):
        if obj is self.eventList and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.LoadSelectedEvent()
                return True
        return super().eventFilter(obj, event)

    def Load(self, parsed, parryApiKey=None):
        worker = Worker(lambda progress_callback=None, cancel_event=None:
                        FetchTournamentEvents(parsed, parryApiKey))
        worker.signals.result.connect(self.SetEvents)
        worker.signals.error.connect(self.ShowError)
        self.threadPool.start(worker)
        self.show()

    def SetEvents(self, result):
        self.provider = result.get("provider")
        self.header.setText(result.get("tournamentName", ""))
        self.subheader.setText(QApplication.translate(
            "app", "{0} events").format(len(result.get("events", []))))
        self.subheader.show()
        self.eventList.clear()

        for event in result.get("events", []):
            card = TSHEventCard(self.provider, event)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, event)
            # What the filter matches against
            item.setData(Qt.ItemDataRole.UserRole + 1,
                         f"{event.get('name', '')} {event.get('game', '')}".lower())
            item.setSizeHint(card.sizeHint())
            self.eventList.addItem(item)
            self.eventList.setItemWidget(item, card)

        if self.eventList.count() > 0:
            self.eventList.setCurrentRow(0)
            self.okButton.setDisabled(False)
        self.eventList.setFocus()

    def ShowError(self, error):
        value = error[1]
        code = value.code if isinstance(value, TournamentLookupError) else None
        message = {
            ERROR_NOT_FOUND: QApplication.translate(
                "app", "The tournament could not be found. Check the link or slug and try again."),
            ERROR_NO_EVENTS: QApplication.translate(
                "app", "This tournament has no events."),
            ERROR_PARRY_KEY: QApplication.translate(
                "app", "A valid parry.gg API key is needed to load parry.gg tournaments."),
        }.get(code, QApplication.translate("app", "The tournament's events could not be loaded."))
        self.header.setText(message)
        logger.error(f"Could not load tournament events: {value}")

    def FilterList(self, text):
        text = text.lower()
        for i in range(self.eventList.count()):
            item = self.eventList.item(i)
            item.setHidden(text not in item.data(Qt.ItemDataRole.UserRole + 1))
        # Keep an event selected, so OK and Enter load what's on screen
        current = self.eventList.currentItem()
        if current is None or current.isHidden():
            visible = [self.eventList.item(i) for i in range(self.eventList.count())
                       if not self.eventList.item(i).isHidden()]
            if visible:
                self.eventList.setCurrentItem(visible[0])

    def LoadSelectedEvent(self):
        item = self.eventList.currentItem()
        if item is None or item.isHidden():
            return
        event = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        self.onEventSelected(event.get("url"))
