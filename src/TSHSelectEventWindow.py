from qtpy.QtGui import *
from qtpy.QtWidgets import *
from qtpy.QtCore import *
from loguru import logger

from .TSHGameAssetManager import TSHGameAssetManager
from .TournamentDataProvider.TournamentEventLookup import (
    FetchTournamentEvents, TournamentLookupError,
    ERROR_NOT_FOUND, ERROR_NO_EVENTS, ERROR_PARRY_KEY,
    STATE_ACTIVE, STATE_COMPLETED
)
from .Workers import Worker

ICON_SIZE = 48
LOCATION_ICON_SIZE = 22
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


class TSHEventCard(QWidget):
    def __init__(self, provider, event, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        icon = QLabel()
        icon.setFixedSize(ICON_SIZE, ICON_SIZE)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logoPath = GameLogoPath(provider, event.get("gameId"))
        if logoPath:
            pixmap = QPixmap(logoPath)
            if not pixmap.isNull():
                icon.setPixmap(pixmap.scaled(
                    ICON_SIZE, ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(icon)

        text = QVBoxLayout()
        text.setSpacing(2)
        layout.addLayout(text, 1)

        nameRow = QHBoxLayout()
        text.addLayout(nameRow)

        name = QLabel(event.get("name", ""))
        font = name.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.15)
        name.setFont(font)
        nameRow.addWidget(name, 1)

        # Online/offline as icons, so it reads at a glance
        location = event.get("location")
        tooltip = LocationNames().get(location)
        for icon in LOCATION_ICONS.get(location, []):
            label = QLabel()
            label.setPixmap(QIcon(icon).pixmap(LOCATION_ICON_SIZE, LOCATION_ICON_SIZE))
            label.setToolTip(tooltip)
            nameRow.addWidget(label)

        details = QLabel(" · ".join(self.Details(event)))
        details.setWordWrap(True)
        text.addWidget(details)

    @staticmethod
    def Details(event):
        details = []
        if event.get("game"):
            details.append(event.get("game"))
        details.append(QApplication.translate(
            "app", "{0} entrants").format(event.get("numEntrants", 0)))
        if event.get("startAt"):
            date = QDateTime.fromSecsSinceEpoch(int(event.get("startAt")))
            details.append(QLocale().toString(date, QLocale.FormatType.ShortFormat))
        if event.get("state") == STATE_ACTIVE:
            details.append(QApplication.translate("app", "In progress"))
        elif event.get("state") == STATE_COMPLETED:
            details.append(QApplication.translate("app", "Completed"))
        else:
            details.append(QApplication.translate("app", "Upcoming"))
        return details


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

        self.header = QLabel(QApplication.translate("app", "Loading events..."))
        self.header.setWordWrap(True)
        font = self.header.font()
        font.setBold(True)
        self.header.setFont(font)
        layout.addWidget(self.header)

        self.searchBar = QLineEdit()
        self.searchBar.setPlaceholderText(QApplication.translate("app", "Filter..."))
        self.searchBar.textEdited.connect(self.FilterList)
        layout.addWidget(self.searchBar)

        self.eventList = QListWidget()
        self.eventList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.eventList.itemDoubleClicked.connect(lambda item: self.LoadSelectedEvent())
        self.eventList.installEventFilter(self)
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
