"""Windows: the big-text toast, your shortcuts and the shortcut editor, the plugin
change history, the on-screen list of shortcuts, and the setup assistant.

Everything is large, high contrast, works from the keyboard and has names for
VoiceOver."""

import json
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .daws import ALL_SCOPE, DAWS, DAWS_SCOPE, find_daw, scope_name
from .keys import MAC_BY_CODE, Combo, format_combo, parse_combo, parse_sequence, speak_combo
from .profiles import APP_ACTIONS, PLUGIN_ACTIONS, check_action, describe

OVERLAY_FLAGS = (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                 | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)

STYLE = """
    QWidget { background:#111; color:#fff; font-size:18px; }
    QLabel#h1 { font-size:30px; font-weight:800; }
    QLabel#h2 { font-size:22px; font-weight:700; margin-top:8px; }
    QLabel#muted { color:#bbb; }
    QLabel#warn { color:#ffcc00; }
    QLabel#bad { color:#ff8a80; }
    QFrame#card { background:#1c1c1c; border-radius:16px; }
    QFrame#card QLabel { background:transparent; }
    QPushButton { background:#2a2a2a; border:3px solid #555; border-radius:12px;
                  min-height:46px; padding:4px 16px; font-weight:600; }
    QPushButton:hover, QPushButton:focus { border-color:#4fc3f7; }
    QPushButton:disabled { color:#666; border-color:#333; }
    QPushButton#primary { background:#ffcc00; color:#000; border-color:#ffcc00;
                          min-height:60px; font-size:21px; }
    QPushButton#shortcut { font-size:26px; min-height:70px; }
    QLineEdit, QComboBox, QPlainTextEdit { min-height:42px; background:#2a2a2a; border:2px solid #555;
                border-radius:10px; padding:0 10px; }
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color:#4fc3f7; }
    QListWidget, QTableWidget { background:#1a1a1a; border:2px solid #333; border-radius:10px;
                                alternate-background-color:#202020; }
    QListWidget::item { min-height:44px; padding:4px 10px; }
    QListWidget::item:selected, QTableWidget::item:selected { background:#4fc3f7; color:#000; }
    QHeaderView::section { background:#222; color:#bbb; border:none; padding:8px; font-size:16px; }
    QCheckBox { spacing:12px; } QCheckBox::indicator { width:26px; height:26px; }
"""


def h(text, name="h2"):
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def muted(text):
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText)
    return label


def card(lay):
    frame = QFrame()
    frame.setObjectName("card")
    inner = QVBoxLayout(frame)
    inner.setContentsMargins(18, 14, 18, 14)
    inner.setSpacing(10)
    lay.addWidget(frame)
    return inner


def qt_event_to_combo(e):
    """A key typed into one of our windows, as a Combo (for when system-wide
    shortcuts aren't allowed yet)."""
    key = None
    if sys.platform == "darwin":
        key = MAC_BY_CODE.get(e.nativeVirtualKey())
    if key is None:
        k = e.key()
        if Qt.Key_A <= k <= Qt.Key_Z:
            key = chr(ord("a") + k - Qt.Key_A)
        elif Qt.Key_0 <= k <= Qt.Key_9:
            key = chr(ord("0") + k - Qt.Key_0)
        elif Qt.Key_F1 <= k <= Qt.Key_F20:
            key = f"f{k - Qt.Key_F1 + 1}"
        else:
            key = {Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
                   Qt.Key_Space: "space", Qt.Key_Return: "enter", Qt.Key_Enter: "enter",
                   Qt.Key_Tab: "tab", Qt.Key_Backspace: "backspace", Qt.Key_Delete: "delete",
                   Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "pageup",
                   Qt.Key_PageDown: "pagedown", Qt.Key_Minus: "-", Qt.Key_Equal: "=",
                   Qt.Key_BracketLeft: "[", Qt.Key_BracketRight: "]", Qt.Key_Semicolon: ";",
                   Qt.Key_Apostrophe: "'", Qt.Key_Comma: ",", Qt.Key_Period: ".", Qt.Key_Slash: "/",
                   Qt.Key_Backslash: "\\", Qt.Key_QuoteLeft: "`"}.get(k)
    if key is None:
        return None
    m = e.modifiers()
    mods = set()
    # Qt on a Mac calls Command "Control" and Control "Meta".
    cmd_bit, ctrl_bit = ((Qt.ControlModifier, Qt.MetaModifier) if sys.platform == "darwin"
                         else (Qt.MetaModifier, Qt.ControlModifier))
    if m & cmd_bit:
        mods.add("cmd")
    if m & ctrl_bit:
        mods.add("ctrl")
    if m & Qt.AltModifier:
        mods.add("alt")
    if m & Qt.ShiftModifier:
        mods.add("shift")
    return Combo(frozenset(mods), key)


class Toast(QWidget):
    """Large, high-contrast text that never takes focus or blocks clicks."""

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(1100)
        f = QFont()
        f.setPointSize(26)
        f.setBold(True)
        self.label.setFont(f)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_text(self, text, ok=True, ms=1600):
        bg, fg = ("#ffcc00", "#000") if ok else ("#ff8a80", "#000")
        self.label.setStyleSheet(f"color:{fg}; background:{bg}; border-radius:18px; padding:14px 28px;")
        self.label.setText(text)
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.bottom() - self.height() - 120)
        self.show()
        self.raise_()
        self.timer.start(ms if ok else ms + 1400)


# Editing one shortcut -----------------------------------------------------------------

KINDS = [
    ("plugin", "Plugin undo"),
    ("keys", "Press other keys"),
    ("menu", "Choose a menu item"),
    ("button", "Press a button in the window"),
    ("suite", "Run a Limitless Sound action"),
    ("type", "Type some text"),
    ("say", "Say something"),
    ("app", "Limitless Keys"),
    ("pass", "Let the app have this shortcut"),
    ("steps", "Several things, one after another"),
]


class BindingDialog(QDialog):
    """Pick a shortcut and what it does."""

    capture = Signal()        # ask the app to catch the next shortcut pressed anywhere

    def __init__(self, profiles, scope, binding=None, suite_actions=(), parent=None):
        super().__init__(parent)
        self.profiles, self.scope = profiles, scope
        self.original = dict(binding) if binding else None
        self.combo = None
        self._recording = None      # "trigger" or "keys" while waiting for a shortcut
        self.setWindowTitle(f"Shortcut for {profiles.name(scope)}")
        self.setAccessibleName(self.windowTitle())
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(10)

        lay.addWidget(h(f"Works in {profiles.name(scope)}"))
        self.shortcut_btn = QPushButton()
        self.shortcut_btn.setObjectName("shortcut")
        self.shortcut_btn.clicked.connect(lambda: self.start_recording("trigger"))
        lay.addWidget(self.shortcut_btn)
        self.notes = QLabel()
        self.notes.setObjectName("warn")
        self.notes.setWordWrap(True)
        lay.addWidget(self.notes)

        lay.addWidget(h("Does"))
        self.kind = QComboBox()
        self.kind.setAccessibleName("What the shortcut does")
        for k, label in KINDS:
            self.kind.addItem(label, k)
        lay.addWidget(self.kind)

        self.stack = QStackedWidget()
        self.editors = {}
        self.plugin_pick = QComboBox()
        for k, label in PLUGIN_ACTIONS.items():
            self.plugin_pick.addItem(label, k)
        self._page("plugin", self.plugin_pick, "Plugin undo works across every plugin, newest change first.")

        keys_row = QWidget()
        kr = QHBoxLayout(keys_row)
        kr.setContentsMargins(0, 0, 0, 0)
        self.keys_edit = QLineEdit()
        self.keys_edit.setPlaceholderText("cmd+s   or several: cmd+a, cmd+c")
        self.keys_edit.setAccessibleName("Keys to press")
        rec = QPushButton("Record…")
        rec.setAccessibleName("Record keys to press")
        rec.clicked.connect(lambda: self.start_recording("keys"))
        kr.addWidget(self.keys_edit, 1)
        kr.addWidget(rec)
        self._page("keys", keys_row, "Write keys like cmd+shift+s, or press Record and press them.",
                   self.keys_edit)

        self.menu_edit = QLineEdit()
        self.menu_edit.setPlaceholderText("Edit > Undo History…")
        self._page("menu", self.menu_edit, "The menu, then the item, as they're written in the app. "
                                           "Works in any language and however the app's keys are set.")
        self.button_edit = QLineEdit()
        self.button_edit.setPlaceholderText("Bounce")
        self._page("button", self.button_edit, "The button's name, as VoiceOver reads it.")
        self.suite_pick = QComboBox()
        self.suite_pick.setEditable(True)
        for a in suite_actions:
            self.suite_pick.addItem(f"{a.get('label', a['id'])}  ({a['id']})", a["id"])
        self._page("suite", self.suite_pick, "Any action from Limitless Zoom, Voice, Color and the rest. "
                                             "Needs the Limitless Sound hub.")
        self.type_edit = QLineEdit()
        self._page("type", self.type_edit, "Typed into the app in front.")
        self.say_edit = QLineEdit()
        self._page("say", self.say_edit, "Said out loud.")
        self.app_pick = QComboBox()
        for k, label in APP_ACTIONS.items():
            self.app_pick.addItem(label, k)
        self._page("app", self.app_pick, "")
        self._page("pass", QLabel(""), "Use this to switch off a shortcut from Every DAW or Every app "
                                       "in just this app.")
        self.steps_edit = QPlainTextEdit()
        self.steps_edit.setPlaceholderText('[{"keys": "cmd+a"}, {"wait": 0.2}, {"menu": "Edit > Copy"}]')
        self.steps_edit.setMinimumHeight(140)
        self._page("steps", self.steps_edit, 'A list of things to do, in JSON: keys, menu, button, plugin, '
                                             'suite, type, say, wait.')
        lay.addWidget(self.stack)
        self.kind.currentIndexChanged.connect(lambda i: self.stack.setCurrentIndex(i))

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Name it (optional)")
        self.label_edit.setAccessibleName("Name")
        lay.addWidget(self.label_edit)
        self.repeat = QCheckBox("Keep doing it while I hold the shortcut down")
        lay.addWidget(self.repeat)

        self.error = QLabel()
        self.error.setObjectName("bad")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save, 1)
        lay.addLayout(row)
        self.resize(640, 640)
        self._load(binding)

    def _page(self, kind, widget, help_text, focus=None):
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(widget)
        if help_text:
            pl.addWidget(muted(help_text))
        pl.addStretch(1)
        self.stack.addWidget(page)
        self.editors[kind] = focus or widget

    def _load(self, binding):
        if binding:
            try:
                self.set_combo(parse_combo(binding["keys"]))
            except ValueError:
                self.set_combo(None)
            action = binding.get("do", {})
            self.label_edit.setText(binding.get("label", ""))
            self.repeat.setChecked(bool(binding.get("repeat")))
        else:
            self.set_combo(None)
            action = {"plugin": "undo"}
        kind = next((k for k, _ in KINDS if k in action), "plugin")
        self.kind.setCurrentIndex([k for k, _ in KINDS].index(kind))
        v = action.get(kind)
        if kind == "plugin":
            self.plugin_pick.setCurrentIndex(max(0, self.plugin_pick.findData(v)))
        elif kind == "keys":
            self.keys_edit.setText(", ".join(str(c) for c in parse_sequence(v)) if v else "")
        elif kind == "menu":
            self.menu_edit.setText(" > ".join(v) if isinstance(v, list) else str(v))
        elif kind == "button":
            self.button_edit.setText(v)
        elif kind == "suite":
            i = self.suite_pick.findData(v)
            if i >= 0:
                self.suite_pick.setCurrentIndex(i)
            else:
                self.suite_pick.setEditText(v)
        elif kind == "type":
            self.type_edit.setText(v)
        elif kind == "say":
            self.say_edit.setText(v)
        elif kind == "app":
            self.app_pick.setCurrentIndex(max(0, self.app_pick.findData(v)))
        elif kind == "steps":
            self.steps_edit.setPlainText(json.dumps(v, indent=2, ensure_ascii=False))

    # Recording -------------------------------------------------------------------

    def start_recording(self, what):
        self._recording = what
        if what == "trigger":
            self.shortcut_btn.setText("Press your shortcut now…")
        else:
            self.keys_edit.setPlaceholderText("Press the keys now…")
        self.capture.emit()

    def got_combo(self, combo):
        what, self._recording = self._recording, None
        if what == "trigger":
            self.set_combo(combo)
        elif what == "keys":
            current = self.keys_edit.text().strip()
            self.keys_edit.setText(f"{current}, {combo}" if current else str(combo))
            self.keys_edit.setPlaceholderText("cmd+s   or several: cmd+a, cmd+c")

    def keyPressEvent(self, e):
        if self._recording:
            combo = qt_event_to_combo(e)
            if combo is not None:
                self.got_combo(combo)
                return
        super().keyPressEvent(e)

    def set_combo(self, combo):
        self.combo = combo
        if combo is None:
            self.shortcut_btn.setText("Click, then press your shortcut")
            self.shortcut_btn.setAccessibleName("Shortcut: not set. Press to record one.")
            self.notes.setText("")
            return
        self.shortcut_btn.setText(f"{format_combo(combo)}    {speak_combo(combo)}")
        self.shortcut_btn.setAccessibleName(f"Shortcut: {speak_combo(combo)}. Press to change it.")
        notes = self.profiles.notes_for(self.scope, str(combo))
        other = self.profiles.find_in_scope(self.scope, combo)
        if other is not None and (self.original is None or parse_combo(self.original["keys"]) != combo):
            notes.insert(0, f"Already does: {other.label}. Saving replaces it.")
        self.notes.setText("\n".join(notes))

    # Saving -----------------------------------------------------------------------

    def action(self):
        kind = self.kind.currentData()
        if kind == "plugin":
            return {"plugin": self.plugin_pick.currentData()}
        if kind == "keys":
            return {"keys": self.keys_edit.text().strip()}
        if kind == "menu":
            return {"menu": self.menu_edit.text().strip()}
        if kind == "button":
            return {"button": self.button_edit.text().strip()}
        if kind == "suite":
            i = self.suite_pick.currentIndex()
            text = self.suite_pick.currentText().strip()
            data = self.suite_pick.itemData(i) if i >= 0 and self.suite_pick.itemText(i) == text else None
            return {"suite": data or text}
        if kind == "type":
            return {"type": self.type_edit.text()}
        if kind == "say":
            return {"say": self.say_edit.text().strip()}
        if kind == "app":
            return {"app": self.app_pick.currentData()}
        if kind == "pass":
            return {"pass": True}
        try:
            return {"steps": json.loads(self.steps_edit.toPlainText() or "[]")}
        except ValueError as e:
            return {"steps": None, "_error": f"That isn't valid JSON: {e}"}

    def result_binding(self):
        if self.combo is None:
            raise ValueError("Press a shortcut first.")
        action = self.action()
        if "_error" in action:
            raise ValueError(action["_error"])
        problem = check_action(action)
        if problem:
            raise ValueError(problem[0].upper() + problem[1:] + ".")
        b = {"keys": str(self.combo), "do": action}
        if self.label_edit.text().strip():
            b["label"] = self.label_edit.text().strip()
        if self.repeat.isChecked():
            b["repeat"] = True
        return b

    def _save(self):
        try:
            b = self.result_binding()
            self.profiles.set_binding(self.scope, b,
                                      replacing=self.original["keys"] if self.original else None)
        except ValueError as e:
            self.error.setText(str(e))
            return
        self.accept()


# All shortcuts -------------------------------------------------------------------------

class ShortcutsWindow(QWidget):
    """Every profile and its shortcuts. Changes are saved straight away."""

    changed = Signal()
    capture = Signal(object)          # a BindingDialog wants the next shortcut
    add_app_requested = Signal()

    def __init__(self, profiles, suite_actions=lambda: [], parent=None):
        super().__init__(parent, Qt.Window)
        self.profiles = profiles
        self.suite_actions = suite_actions
        self.setWindowTitle("My shortcuts — Limitless Keys")
        self.setAccessibleName("My shortcuts")
        self.setStyleSheet(STYLE)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(18)

        left = QVBoxLayout()
        left.addWidget(h("Where", "h2"))
        self.scope_list = QListWidget()
        self.scope_list.setAccessibleName("Apps")
        self.scope_list.setMinimumWidth(240)
        self.scope_list.currentRowChanged.connect(lambda _: self.show_scope())
        left.addWidget(self.scope_list, 1)
        add_app = QPushButton("Add an app…")
        add_app.clicked.connect(self.add_app_requested)
        self.remove_app = QPushButton("Remove this app")
        self.remove_app.clicked.connect(self._remove_scope)
        left.addWidget(add_app)
        left.addWidget(self.remove_app)
        outer.addLayout(left)

        right = QVBoxLayout()
        self.title = h("", "h1")
        self.subtitle = muted("")
        right.addWidget(self.title)
        right.addWidget(self.subtitle)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Shortcut", "Does", "Held down"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setAccessibleName("Shortcuts")
        self.table.cellDoubleClicked.connect(lambda r, c: self.edit())
        right.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, fn in (("Add a shortcut…", self.add), ("Change…", self.edit), ("Remove", self.remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        right.addLayout(row)
        self.problems = QLabel()
        self.problems.setObjectName("bad")
        self.problems.setWordWrap(True)
        right.addWidget(self.problems)
        row2 = QHBoxLayout()
        for text, fn in (("Import…", self._import), ("Export…", self._export),
                         ("Restore the defaults", self._defaults)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row2.addWidget(b)
        right.addLayout(row2)
        outer.addLayout(right, 1)
        self.resize(1080, 700)
        self.refresh()

    def scopes(self):
        known = [DAWS_SCOPE, ALL_SCOPE] + list(DAWS)
        return known + [s for s in self.profiles.scopes() if s not in known]

    def refresh(self, keep=None):
        keep = keep or self.current_scope()
        self.scope_list.blockSignals(True)
        self.scope_list.clear()
        for s in self.scopes():
            n = len(self.profiles.bindings(s)) if s in self.profiles.data.get("apps", {}) else 0
            item = QListWidgetItem(f"{self.profiles.name(s)}" + (f"  ({n})" if n else ""))
            item.setData(Qt.UserRole, s)
            self.scope_list.addItem(item)
        self.scope_list.blockSignals(False)
        scopes = self.scopes()
        self.scope_list.setCurrentRow(scopes.index(keep) if keep in scopes else 0)
        self.show_scope()

    def current_scope(self):
        item = self.scope_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def show_scope(self):
        scope = self.current_scope()
        if scope is None:
            return
        name = self.profiles.name(scope)
        self.title.setText(name)
        if scope == DAWS_SCOPE:
            self.subtitle.setText("These work in every DAW. A shortcut set for one DAW wins over these.")
        elif scope == ALL_SCOPE:
            self.subtitle.setText("These work in every app, unless the app in front has its own.")
        else:
            self.subtitle.setText(f"These work while {name} is in front, and win over Every DAW "
                                  "and Every app.")
        self.remove_app.setEnabled(scope not in (DAWS_SCOPE, ALL_SCOPE) and scope not in DAWS)
        apps = self.profiles.data.get("apps", {})
        bindings = apps.get(scope, {}).get("bindings", [])
        self.table.setRowCount(0)
        for b in bindings:
            r = self.table.rowCount()
            self.table.insertRow(r)
            try:
                keys = format_combo(b["keys"])
                spoken = speak_combo(b["keys"])
            except (ValueError, KeyError):
                keys = spoken = str(b.get("keys"))
            k = QTableWidgetItem(keys)
            k.setData(Qt.UserRole, b)
            k.setData(Qt.AccessibleTextRole, spoken)
            f = k.font()
            f.setPointSize(f.pointSize() + 4)
            f.setBold(True)
            k.setFont(f)
            off = b.get("on", True) is False
            does = b.get("label") or describe(b.get("do"))
            self.table.setItem(r, 0, k)
            self.table.setItem(r, 1, QTableWidgetItem(does + (" (off)" if off else "")))
            self.table.setItem(r, 2, QTableWidgetItem("repeats" if b.get("repeat") else ""))
        self.table.resizeColumnToContents(0)
        self.problems.setText("\n".join(self.profiles.problems))

    def selected(self):
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _dialog(self, binding=None):
        dlg = BindingDialog(self.profiles, self.current_scope(), binding, self.suite_actions(), self)
        dlg.capture.connect(lambda: self.capture.emit(dlg))
        if dlg.exec():
            self.profiles.save()
            self.refresh()
            self.changed.emit()

    def add(self):
        self._dialog()

    def edit(self):
        b = self.selected()
        if b is not None:
            self._dialog(b)

    def remove(self):
        b = self.selected()
        if b is not None:
            self.profiles.remove_binding(self.current_scope(), b["keys"])
            self.profiles.save()
            self.refresh()
            self.changed.emit()

    def add_scope(self, app_id, name):
        self.profiles.add_scope(find_daw(app_id) or app_id, name)
        self.profiles.save()
        self.refresh(keep=find_daw(app_id) or app_id)

    def _remove_scope(self):
        scope = self.current_scope()
        if scope in (DAWS_SCOPE, ALL_SCOPE) or scope in DAWS:
            return
        self.profiles.remove_scope(scope)
        self.profiles.save()
        self.refresh(keep=DAWS_SCOPE)
        self.changed.emit()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import shortcuts", "", "Shortcuts (*.json)")
        if not path:
            return
        try:
            self.profiles.import_from(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Import shortcuts", str(e))
            return
        self.profiles.save()
        self.refresh()
        self.changed.emit()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export shortcuts", "My shortcuts.json",
                                              "Shortcuts (*.json)")
        if path:
            self.profiles.export_to(path)

    def _defaults(self):
        if QMessageBox.question(self, "Restore the defaults",
                                "Put every shortcut back the way it came? Your own shortcuts are removed."
                                ) == QMessageBox.Yes:
            self.profiles.restore_defaults()
            self.profiles.save()
            self.refresh()
            self.changed.emit()


class AddAppDialog(QDialog):
    def __init__(self, apps, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add an app")
        self.setStyleSheet(STYLE)
        self.choice = None
        lay = QVBoxLayout(self)
        lay.addWidget(h("Which app?"))
        lay.addWidget(muted("Apps that are open now. Open the app first if it isn't here."))
        self.list = QListWidget()
        self.list.setAccessibleName("Open apps")
        for name, app_id in apps:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, (app_id, name))
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(lambda _: self._ok())
        lay.addWidget(self.list, 1)
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("…or its bundle id, like com.example.app")
        lay.addWidget(self.manual)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Add")
        ok.setObjectName("primary")
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok, 1)
        lay.addLayout(row)
        self.resize(520, 600)

    def _ok(self):
        text = self.manual.text().strip()
        if text:
            self.choice = (text, text)
        elif self.list.currentItem():
            self.choice = self.list.currentItem().data(Qt.UserRole)
        if self.choice:
            self.accept()


# Plugin change history -----------------------------------------------------------------

def ago(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} h ago"


class HistoryWindow(QWidget):
    """Every plugin change, newest first, with plugin undo and redo."""

    undo = Signal()
    redo = Signal()

    def __init__(self, plugins, status=lambda: "", parent=None):
        super().__init__(parent, Qt.Window)
        self.plugins = plugins
        self.status_text = status
        self.setWindowTitle("Plugin changes — Limitless Keys")
        self.setAccessibleName("Plugin changes")
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.addWidget(h("Plugin changes", "h1"))
        self.status = muted("")
        lay.addWidget(self.status)
        self.list = QListWidget()
        self.list.setAccessibleName("Plugin changes, newest first")
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        u = QPushButton("Undo plugin change   ⌥⌘Z")
        u.setObjectName("primary")
        u.clicked.connect(self.undo)
        r = QPushButton("Redo   ⌥⇧⌘Z")
        r.clicked.connect(self.redo)
        row.addWidget(u, 2)
        row.addWidget(r, 1)
        lay.addLayout(row)
        self._version = -1
        self.timer = QTimer(self, interval=300, timeout=self.refresh)
        self.resize(760, 620)

    def showEvent(self, e):
        self._version = -1
        self.refresh()
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def refresh(self):
        self.status.setText(self.status_text())
        tl = self.plugins.timeline
        if tl.version == self._version:
            return
        self._version = tl.version
        with self.plugins.lock:
            rows = tl.recent(300)
        self.list.clear()
        now = tl.clock()
        if not rows:
            self.list.addItem("No plugin changes yet. Move a knob in a plugin and it shows here.")
        for src, step, undone in rows:
            text = f"{src.title} — {step.describe()}   ·   {ago(now - step.time)}"
            item = QListWidgetItem(("↶ undone   " if undone else "") + text)
            if undone:
                item.setForeground(Qt.gray)
            self.list.addItem(item)


# Your shortcuts on screen ---------------------------------------------------------------

class CheatSheet(QWidget):
    """Big list of the shortcuts that work in the app in front. Never takes focus."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setAccessibleName("My shortcuts")
        self.setStyleSheet("QWidget{background:#111;color:#fff;} QLabel#h1{font-size:30px;font-weight:800;}"
                           "QLabel#keys{font-size:28px;font-weight:800;color:#ffcc00;}"
                           "QLabel#does{font-size:22px;} QLabel#muted{color:#bbb;font-size:17px;}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(30, 24, 30, 24)
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_for(self, app_name, bindings, ms=12000):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.lay.addWidget(h(f"Your shortcuts in {app_name}", "h1"))
        if not bindings:
            self.lay.addWidget(muted("None yet. Add some from the Limitless Keys menu: My shortcuts."))
        for b in bindings[:24]:
            row = QWidget()
            r = QHBoxLayout(row)
            r.setContentsMargins(0, 2, 0, 2)
            k = QLabel(format_combo(b.combo))
            k.setObjectName("keys")
            k.setMinimumWidth(170)
            d = QLabel(b.label)
            d.setObjectName("does")
            d.setWordWrap(True)
            r.addWidget(k)
            r.addWidget(d, 1)
            self.lay.addWidget(row)
        self.lay.addWidget(muted("Press the same shortcut again to hide this."))
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.show()
        self.raise_()
        self.timer.start(ms)

    def mousePressEvent(self, e):
        self.hide()


# Setup ------------------------------------------------------------------------------------

STATE_MARK = {"ok": ("✓", "#3ddc84"), "missing": ("!", "#ff9f43"), "unknown": ("?", "#9e9e9e")}


class Setup(QWidget):
    """The setup assistant: shown on first launch and from the menu."""

    request_permission = Signal(str)
    open_logic_undo = Signal()
    install_plugin = Signal()
    login_changed = Signal(bool)
    finished = Signal()

    def __init__(self, login=None, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Set up Limitless Keys")
        self.setAccessibleName("Limitless Keys setup")
        self.setStyleSheet(STYLE)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        lay.addWidget(h("Two undos, and your own shortcuts", "h1"))
        lay.addWidget(muted(
            "<b>⌘Z</b> stays your DAW's undo, for edits, regions, notes and mixing. "
            "<b>⌥⌘Z</b> undoes only plugin changes, newest first, across every plugin. "
            "<b>⌥⇧⌘Z</b> redoes them, and holding <b>⌃⌥⌘Z</b> lets you hear the sound before "
            "your last plugin change. You can change any of these, and add your own shortcuts "
            "for any app."))

        self.perm_header = h("1. Allow access")
        lay.addWidget(self.perm_header)
        self.perm_box = QVBoxLayout()
        lay.addLayout(self.perm_box)
        self.perm_rows = {}

        lay.addWidget(h("2. Try it"))
        c = card(lay)
        c.addWidget(QLabel("In Logic Pro or Pro Tools, move a plugin knob, then press ⌥⌘Z."))
        self.heard = QLabel("Waiting for a shortcut…")
        self.heard.setObjectName("warn")
        self.heard.setWordWrap(True)
        c.addWidget(self.heard)

        lay.addWidget(h("3. Logic Pro: keep plugin changes out of ⌘Z"))
        c = card(lay)
        c.addWidget(muted(
            "Logic can put plugin changes into its main undo, where ⌘Z would undo them too. "
            "To leave them out: open <b>Edit › Undo History</b>, and next to <b>Include Parameter "
            "Changes From</b> turn <b>Plug-in</b> off (in older Logic versions: a plugin window's "
            "settings menu › <b>Include Plug-In Undo Steps in Project Undo History</b>). "
            "Leave <b>Mixer</b> as you like it. Plugin undo needs no plugin in Logic: it presses the "
            "Undo button of the plugin window you changed last, so keep plugin windows open while "
            "you tweak."))
        b = QPushButton("Open Logic's Undo History")
        b.clicked.connect(self.open_logic_undo)
        c.addWidget(b, alignment=Qt.AlignLeft)

        lay.addWidget(h("4. Pro Tools and other DAWs: the Limitless Undo plugin"))
        c = card(lay)
        c.addWidget(muted(
            "Pro Tools keeps no undo for plugin changes, so put a plugin inside <b>Limitless Undo</b>: "
            "insert Limitless Undo on the track, then choose your plugin in it. Every change you make "
            "is remembered, even with the window closed and after you reopen the session. It works in "
            "Logic, Ableton Live and other DAWs too."))
        self.install_btn = QPushButton("Install the Limitless Undo plugin")
        self.install_btn.clicked.connect(self.install_plugin)
        c.addWidget(self.install_btn, alignment=Qt.AlignLeft)
        self.plugin_status = muted("")
        c.addWidget(self.plugin_status)

        self.login = None
        if login is not None:
            self.login = QCheckBox("Open Limitless Keys when I log in")
            self.login.setChecked(login)
            self.login.toggled.connect(self.login_changed)
            lay.addWidget(self.login)
        self.done = QPushButton("Done")
        self.done.setObjectName("primary")
        self.done.clicked.connect(self._finish)
        lay.addWidget(self.done)
        lay.addWidget(muted("Open this again any time from the keyboard icon in the menu bar."))

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.resize(820, 900)

    def set_permissions(self, perms):
        self.perm_header.setVisible(bool(perms))
        for p in perms:
            row = self.perm_rows.get(p["key"])
            if row is None:
                frame = QFrame()
                frame.setObjectName("card")
                hl = QHBoxLayout(frame)
                hl.setContentsMargins(16, 12, 16, 12)
                mark = QLabel()
                mark.setFixedWidth(44)
                mark.setAlignment(Qt.AlignCenter)
                text = QLabel()
                text.setWordWrap(True)
                btn = QPushButton("Allow…")
                btn.clicked.connect(lambda _=False, k=p["key"]: self.request_permission.emit(k))
                hl.addWidget(mark)
                hl.addWidget(text, 1)
                hl.addWidget(btn)
                self.perm_box.addWidget(frame)
                row = self.perm_rows[p["key"]] = (mark, text, btn)
            mark, text, btn = row
            symbol, color = STATE_MARK.get(p["state"], STATE_MARK["unknown"])
            mark.setText(symbol)
            mark.setStyleSheet(f"font-size:30px; font-weight:800; color:{color};")
            text.setText(f"<b>{p['title']}</b><br><span style='color:#bbb'>{p['why']}</span>")
            btn.setVisible(p["state"] != "ok")
            btn.setAccessibleName(f"Allow {p['title']}")

    def set_heard(self, text):
        self.heard.setText(text)

    def set_plugin_status(self, text):
        self.plugin_status.setText(text)

    def _finish(self):
        self.finished.emit()
        self.close()


__all__ = ["Toast", "BindingDialog", "ShortcutsWindow", "AddAppDialog", "HistoryWindow", "CheatSheet",
           "Setup", "qt_event_to_combo", "scope_name"]
