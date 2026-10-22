"""
Sticky Notes Module - polsoft.ITS
Kompaktowe, przenośne notatki w stylu kartek samoprzylepnych.
Zintegrowane z Text List Tool.

Author: Sebastian Januchowski / polsoft.ITS Group
"""

import json
import logging
import os
import sys
import uuid

from PyQt6.QtCore import Qt, QTimer, QPoint, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor, QPainterPath, QPixmap, QIcon, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QTextEdit, QHBoxLayout, QVBoxLayout,
    QFrame, QMenu, QColorDialog, QLabel, QSizeGrip,
)

log = logging.getLogger(__name__)

NOTE_COLORS = [
    "#fff740",
    "#ffbf69",
    "#ffadad",
    "#caffbf",
    "#9bf6ff",
    "#bdb2ff",
    "#ffc6ff",
    "#e8eddf",
]

NOTE_STRINGS = {
    "en": {
        "title": "Sticky Notes",
        "new_note": "New note",
        "delete_note": "Delete note",
        "color_note": "Change color",
        "close": "Close",
        "note_title": "Note {n}",
        "title_hint": "Click to edit title...",
        "delete_confirm": "Delete this note?",
        "save_note": "Save note",
        "ontop_on": "Always on top",
        "ontop_off": "Normal window",
    },
    "pl": {
        "title": "Notatki",
        "new_note": "Nowa notatka",
        "delete_note": "Usuń notatkę",
        "color_note": "Zmień kolor",
        "close": "Zamknij",
        "note_title": "Notatka {n}",
        "title_hint": "Kliknij aby edytować tytuł...",
        "delete_confirm": "Usunąć tę notatkę?",
        "save_note": "Zapisz notatkę",
        "ontop_on": "Zawsze na wierzchu",
        "ontop_off": "Zwykłe okno",
    },
}


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def default_notes_data_path():
    return os.path.join(get_app_dir(), "sticky_notes_data.json")


class DraggableTitleBar(QFrame):
    def __init__(
        self,
        parent_widget: "StickyNote",
        bg_color: str,
        text_color: str,
        lang: str = "en",
    ):
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._drag_pos = None
        self._bg_color = bg_color
        self._text_color = text_color
        self.lang = lang

        self.setFixedHeight(28)
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        self.title_label = QLabel()
        self.title_label.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        self.title_label.mouseDoubleClickEvent = self._edit_title
        self._title_text = ""
        self._update_title_display()
        layout.addWidget(self.title_label, 1)

        self.new_btn = self._add_toolbar_button(layout, "+", "new_note")
        self.save_btn = self._add_toolbar_button(layout, "💾", "save_note")
        self.color_btn = self._add_toolbar_button(layout, "🎨", "color_note")
        self.ontop_btn = self._add_toolbar_button(
            layout, "📌", "ontop_on", checkable=True
        )
        self.ontop_btn.setChecked(True)   # notes are on top by default
        self.delete_btn = self._add_toolbar_button(layout, "🗑", "delete_note")
        self.close_btn = self._add_toolbar_button(layout, "✕", "close")

    def _add_toolbar_button(
        self,
        layout: QHBoxLayout,
        glyph: str,
        tooltip_key: str,
        checkable: bool = False,
    ) -> QPushButton:
        """Create a fixed-size title-bar button and append it to *layout*.

        Centralises the shared styling (size, cursor, tooltip) so each button
        is declared in a single line and the layout stays consistent.
        """
        button = QPushButton(glyph)
        button.setFixedSize(22, 22)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.setToolTip(NOTE_STRINGS[self.lang][tooltip_key])
        button.setCheckable(checkable)
        layout.addWidget(button)
        return button

    def _update_style(self):
        # a corrupt/hand-edited data file may hold a non-color string; fall back
        # to the default note color instead of emitting an invalid style sheet
        bg = QColor(self._bg_color)
        if not bg.isValid():
            bg = QColor("#fff740")
        darken = bg.darker(110).name()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {darken};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QLabel {{
                color: {self._text_color};
                font-weight: bold;
                font-size: 11px;
                background: transparent;
            }}
            QPushButton {{
                background-color: transparent;
                color: {self._text_color};
                border: none;
                border-radius: 3px;
                padding: 0px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 0, 0, 20);
            }}
        """)

    def update_colors(self, bg_color, text_color):
        self._bg_color = bg_color
        self._text_color = text_color
        self._update_style()

    def set_ontop_state(self, on_top):
        """Reflect the window's always-on-top flag in the pin button."""
        self.ontop_btn.setChecked(bool(on_top))
        self.ontop_btn.setToolTip(
            NOTE_STRINGS[self.lang]["ontop_on"] if on_top
            else NOTE_STRINGS[self.lang]["ontop_off"]
        )

    def update_language(self, lang):
        self.lang = lang
        self.new_btn.setToolTip(NOTE_STRINGS[self.lang]["new_note"])
        self.save_btn.setToolTip(NOTE_STRINGS[self.lang]["save_note"])
        self.color_btn.setToolTip(NOTE_STRINGS[self.lang]["color_note"])
        self.delete_btn.setToolTip(NOTE_STRINGS[self.lang]["delete_note"])
        self.close_btn.setToolTip(NOTE_STRINGS[self.lang]["close"])
        self.set_ontop_state(self.ontop_btn.isChecked())

    def set_title(self, text):
        self._title_text = text
        self._update_title_display()

    def get_title(self):
        return self._title_text

    def _update_title_display(self):
        if self._title_text:
            self.title_label.setText(self._title_text)
        else:
            palette = self.title_label.palette()
            self.title_label.setText(NOTE_STRINGS[self.lang]["title_hint"])

    def _edit_title(self, event: QMouseEvent):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self,
            NOTE_STRINGS[self.lang]["note_title"].format(n=""),
            "",
            text=self._title_text,
        )
        if ok:
            self.set_title(text.strip())
            self._parent._on_title_changed()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            self._parent._on_position_changed()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class StickyNote(QWidget):
    note_changed = pyqtSignal()
    note_deleted = pyqtSignal(str)
    new_note_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, note_id=None, data=None, lang="en"):
        super().__init__()
        self.note_id = note_id or str(uuid.uuid4())
        self.lang = lang

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._bg_color = "#fff740"
        self._text_color = "#1e1e1e"
        self._position = None
        self._size = QSize(260, 220)
        self._always_on_top = True

        if data:
            color = data.get("color", self._bg_color)
            self._bg_color = color if QColor(color).isValid() else self._bg_color
            width = int(data.get("width") or 260)
            height = int(data.get("height") or 220)
            self._size = QSize(width, height)
            self._position = QPoint(data.get("x", 100), data.get("y", 100))
            self._always_on_top = bool(data.get("on_top", True))

        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        self.resize(self._size)
        if self._position:
            self.move(self._position)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._emit_changed)

        self._build_ui(data)
        # the note can be resized by its grip; make sure the restored size sticks
        # (the layout is free to shrink the window right after it is built)
        self.resize(self._size)
        self.setMinimumSize(50, 50)

    def _build_ui(self, data):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title_bar = DraggableTitleBar(self, self._bg_color, self._text_color, self.lang)
        if data:
            self.title_bar.set_title(data.get("title", ""))
        outer.addWidget(self.title_bar)

        content_frame = QFrame()
        content_frame.setObjectName("contentFrame")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(10, 6, 10, 6)
        content_layout.setSpacing(0)

        self.text_edit = QTextEdit()
        self.text_edit.setFrameStyle(0)
        self.text_edit.textChanged.connect(self._schedule_save)
        if data:
            self.text_edit.setPlainText(data.get("content", ""))
        content_layout.addWidget(self.text_edit, 1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("""
            background: transparent;
            width: 20px;
            height: 20px;
        """)
        self.size_grip.setFixedSize(20, 20)
        bottom_row.addWidget(self.size_grip)
        content_layout.addLayout(bottom_row)

        outer.addWidget(content_frame, 1)

        self.title_bar.new_btn.clicked.connect(self.new_note_requested.emit)
        self.title_bar.save_btn.clicked.connect(self._emit_changed)
        self.title_bar.delete_btn.clicked.connect(self._delete_me)
        self.title_bar.color_btn.clicked.connect(self._change_color)
        self.title_bar.ontop_btn.toggled.connect(self._set_always_on_top)
        self.title_bar.close_btn.clicked.connect(self.close_requested.emit)

        self.title_bar.set_ontop_state(self._always_on_top)
        self._apply_colors()

    def _apply_colors(self):
        self.title_bar.update_colors(self._bg_color, self._text_color)
        self.setStyleSheet(f"""
            QFrame#contentFrame {{
                background-color: {self._bg_color};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QTextEdit {{
                background-color: {self._bg_color};
                color: {self._text_color};
                border: none;
                font-size: 12px;
                padding: 0px;
                selection-background-color: rgba(0, 0, 0, 30);
                selection-color: {self._text_color};
            }}
        """)

    def update_language(self, lang):
        self.lang = lang
        self.title_bar.update_language(lang)

    def _schedule_save(self):
        self._save_timer.start(400)

    def _emit_changed(self):
        self.note_changed.emit()

    def _on_title_changed(self):
        self._emit_changed()

    def _on_position_changed(self):
        self._schedule_save()

    def _set_always_on_top(self, on_top):
        """Pin/unpin a single note; the flag is stored per note."""
        self._always_on_top = bool(on_top)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        self.title_bar.set_ontop_state(self._always_on_top)
        # re-showing after a flag change is required for it to take effect
        if self.isVisible():
            self.show()
        self._emit_changed()

    def resizeEvent(self, event):
        self._size = self.size()
        self._schedule_save()
        super().resizeEvent(event)

    def _change_color(self):
        # NOTE: menu must not be garbage-collected while it is open, so keep
        # a reference on self for the duration of the call.
        menu = QMenu(self)
        for i, color in enumerate(NOTE_COLORS):
            action = menu.addAction(f"Kolor {i + 1}")
            action.setData(color)
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(color))
            action.setIcon(QIcon(pixmap))
            action.triggered.connect(lambda checked, c=color: self._set_color(c))
        menu.addAction(NOTE_STRINGS[self.lang]["color_note"] + "...").triggered.connect(self._pick_custom_color)
        self._color_menu = menu
        try:
            menu.exec(QCursor.pos())
        finally:
            self._color_menu = None
            menu.deleteLater()

    def _set_color(self, color):
        if not QColor(color).isValid():
            return
        self._bg_color = color
        self._apply_colors()
        self._emit_changed()

    def _pick_custom_color(self):
        color = QColorDialog.getColor(QColor(self._bg_color), self, "")
        if color.isValid():
            self._set_color(color.name())

    def _delete_me(self):
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            NOTE_STRINGS[self.lang]["delete_note"],
            NOTE_STRINGS[self.lang]["delete_confirm"],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.note_deleted.emit(self.note_id)
            self.close()

    def to_dict(self):
        return {
            "id": self.note_id,
            "title": self.title_bar.get_title(),
            "content": self.text_edit.toPlainText(),
            "color": self._bg_color,
            "x": self.x(),
            "y": self.y(),
            "width": self.size().width(),
            "height": self.size().height(),
            "on_top": self._always_on_top,
        }


class StickyNotesManager(QObject):
    save_failed = pyqtSignal(str)

    def __init__(self, lang="en", data_path=None):
        super().__init__()
        self.lang = lang
        self.notes = {}
        self.set_data_path(data_path)
        self.load_notes()

    def set_data_path(self, data_path):
        if data_path:
            self._ensure_dir(data_path)
            self._data_path = data_path
        else:
            self._data_path = default_notes_data_path()

    def get_data_path(self):
        return self._data_path

    def _close_all_notes(self):
        """Close every note on screen and forget them (used when the JSON store
        is switched to a different file)."""
        for note in list(self.notes.values()):
            try:
                note.close()
            except Exception:
                pass
        self.notes.clear()

    def _ensure_dir(self, path):
        """Create the folder that holds *path* if it is missing.

        Returns True when the folder exists (or was created), False when it
        could not be created.
        """
        folder = os.path.dirname(path)
        if folder and not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as exc:
                log.error("Could not create %s: %s", folder, exc)
                return False
        return True

    def _read_json(self, path):
        """Read a JSON object from *path*.

        Returns the parsed dict, or an empty dict when the file is missing,
        unreadable or does not hold a JSON object (corrupt/partial data).
        """
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            log.error("Could not read %s: %s", path, exc)
            return {}
        # a valid JSON file may still hold a non-object (list/null/string)
        if not isinstance(data, dict):
            return {}
        return data

    def _write_json(self, path, data):
        """Write *data* to *path* as UTF-8 JSON.

        Returns True on success, False when the folder or the file could not be
        written (so the caller can keep the current store instead of switching
        to a path that does not hold the user's notes).  The cause is logged and
        kept in ``self._last_write_error`` for the caller to report.
        """
        self._last_write_error = ""
        if not self._ensure_dir(path):
            self._last_write_error = "Could not create folder for %s" % path
            return False
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.error("Could not write %s: %s", path, exc)
            self._last_write_error = str(exc)
            return False
        return True

    def _write_old_data(self, path, old_data):
        """Copy the previously loaded data to *path*.

        Returns True on success, False when the copy could not be written (so
        the caller can keep the current store instead of switching to a path
        that does not hold the user's notes).
        """
        return self._write_json(path, old_data)

    def migrate_and_reload(self, new_path):
        self.save_notes()
        old_path = self._data_path
        old_data = self._read_json(old_path)
        # copy the notes to the new location first: if that fails, the current
        # _data_path must stay untouched so the user's notes remain reachable
        if old_data and not os.path.exists(new_path):
            if not self._write_old_data(new_path, old_data):
                return False
        self._reload_from_path(new_path)
        return True

    def _reload_from_path(self, new_path):
        """Close the on-screen notes and reload them from *new_path*.

        Shared by the migration and table-switch paths so the close/switch/load
        sequence is defined in exactly one place.
        """
        self._close_all_notes()
        self.set_data_path(new_path)
        self.load_notes()

    def set_language(self, lang):
        self.lang = lang
        for note in self.notes.values():
            note.update_language(lang)

    def load_notes(self):
        data = self._read_json(self._data_path)
        for nid, ndata in data.items():
            self._create_note(nid, ndata)

    def save_notes(self):
        """Write the notes to the JSON store.

        Returns True when the file was written, False when the save failed
        (read-only folder, locked file, disk full).  The error is logged and
        reported once through the ``save_failed`` signal so callers and the
        user learn that the notes were not persisted.
        """
        data = {nid: note.to_dict() for nid, note in self.notes.items()}
        if not self._write_json(self._data_path, data):
            # _write_json already logged the cause; report it to the user too
            self.save_failed.emit(
                self._last_write_error or "Could not save notes"
            )
            return False
        return True

    def _create_note(
        self,
        note_id: str,
        data: dict | None = None,
    ) -> "StickyNote":
        """Build a note, wire its signals and register it.

        Kept to three positional parameters so the note's ``show`` behaviour is
        not tied to the caller's argument list; every call site passes at most
        ``(note_id, data)``.
        """
        note: "StickyNote" = StickyNote(
            note_id=note_id, data=data, lang=self.lang
        )
        note.note_changed.connect(self.save_notes)
        note.note_deleted.connect(self._on_note_deleted)
        note.new_note_requested.connect(self.create_new_note)
        note.close_requested.connect(lambda: self._on_note_closed(note.note_id))
        self.notes[note.note_id] = note
        return note

    def switch_table_path(self, new_path=None):
        """Switch the JSON store used by the notes (called when the Text List
        Tool user picks a different table save location).  Notes currently on
        screen are closed and reloaded from the new file; nothing is written to
        the old or new file unless the notes are changed afterwards."""
        self._reload_from_path(new_path)

    def create_new_note(self):
        from PyQt6.QtWidgets import QApplication
        width, height = 260, 220
        offset = 30 * len(self.notes)
        # cascade the notes, then clamp so a new note always lands fully on the
        # available screen area (instead of partly/fully off-screen)
        x = 150 + offset % 400
        y = 150 + offset % 300
        # a headless/screen-less session (or a compositor that has not reported
        # its geometry yet) leaves primaryScreen() as None; fall back to the
        # cascaded defaults instead of raising AttributeError
        primary_screen = QApplication.primaryScreen()
        if primary_screen is not None:
            screen = primary_screen.availableGeometry()
            x = max(screen.left(), min(x, screen.right() - width))
            y = max(screen.top(), min(y, screen.bottom() - height))
        data = {
            "color": NOTE_COLORS[len(self.notes) % len(NOTE_COLORS)],
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
        # generate the id here: StickyNote would otherwise make its own, and the
        # note would be stored under a key that the empty file did not have yet
        note = self._create_note(str(uuid.uuid4()), data)
        note.show()
        self.save_notes()
        return note

    def show_all_notes(self):
        for note in self.notes.values():
            note.show()
            note.raise_()
            note.activateWindow()
        if not self.notes:
            self.create_new_note()

    def hide_all_notes(self):
        for note in self.notes.values():
            note.hide()

    def toggle_visibility(self):
        any_visible = any(n.isVisible() for n in self.notes.values())
        if any_visible:
            self.hide_all_notes()
        else:
            self.show_all_notes()

    def _on_note_deleted(self, note_id):
        if note_id in self.notes:
            del self.notes[note_id]
            self.save_notes()

    def _on_note_closed(self, note_id):
        if note_id in self.notes:
            self.notes[note_id].hide()
            self.save_notes()


def main():
    import sys
    app = QApplication(sys.argv)
    manager = StickyNotesManager(lang="pl")
    manager.show_all_notes()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()