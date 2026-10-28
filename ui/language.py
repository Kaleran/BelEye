"""Language / localization manager.

Wraps QTranslator so the whole app can switch between Russian (the source
language, hard-coded in tr() calls) and English (loaded from a .qm file).

Safe to import before QApplication exists — the translator is only created
and installed in ``install()``, which is called from main() after
QApplication is constructed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QSettings,
    QTranslator,
    Signal,
)

log = logging.getLogger(__name__)

RU = "ru"
EN = "en"

SETTINGS_KEY = "ui/language"
_TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "resources" / "translations"


class LanguageManager(QObject):
    """Owns the active language, installs the QTranslator, and notifies listeners.

    English is the source language (hard-coded in tr() calls). Russian is
    loaded from a .qm file. When English is active, no translator is
    installed and tr() returns the source string.
    """

    #: Emitted after the language actually changed (code, "ru" | "en").
    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang: str = EN
        self._translator: QTranslator | None = None

    # -------- state --------

    def language(self) -> str:
        return self._lang

    def is_english(self) -> bool:
        return self._lang == EN

    # -------- standalone translate helper --------

    @staticmethod
    def tr(source: str, disambiguation: str | None = None) -> str:
        """Translate ``source`` using the installed QTranslator.

        Falls back to ``source`` itself when no translator is installed or no
        translation exists. Safe to call from non-QObject code (e.g. main.py).

        Uses the ``__main__`` context, under which all standalone (non-QObject)
        strings are collected in the translation files.
        """
        app = QCoreApplication.instance()
        if app is None:
            return source
        if disambiguation is not None:
            return app.translate("__main__", source, disambiguation)
        return app.translate("__main__", source)

    # -------- load / install --------

    def _qm_path(self, lang: str) -> Path:
        return _TRANSLATIONS_DIR / f"beleye_{lang}.qm"

    def _load_translator(self, lang: str) -> QTranslator | None:
        """Load the .qm for ``lang``. Returns None if the file is missing."""
        qm = self._qm_path(lang)
        if not qm.exists():
            log.warning("[language] no translation file at %s", qm)
            return None
        translator = QTranslator()
        if not translator.load(str(qm)):
            log.warning("[language] failed to load %s", qm)
            return None
        return translator

    def install(self, app, lang: str | None = None) -> None:
        """Install the translator for ``lang`` on ``app``.

        When ``lang`` is the source language (``en``), any previously installed
        translator is removed so tr() returns source strings.
        """
        lang = lang if lang in (RU, EN) else EN

        # Remove old translator
        if self._translator is not None:
            app.removeTranslator(self._translator)
            self._translator = None

        if lang == EN:
            # Source language: nothing to translate.
            self._lang = EN
            log.info("[language] language = en (source, no translator)")
            self.language_changed.emit(EN)
            return

        translator = self._load_translator(RU)
        if translator is None:
            self._lang = EN
            log.warning("[language] falling back to en (ru translation missing)")
            self.language_changed.emit(EN)
            return

        app.installTranslator(translator)
        self._translator = translator
        self._lang = RU
        log.info("[language] language = ru (translator installed)")
        self.language_changed.emit(RU)

    def set_language(self, lang: str, *, persist: bool = True) -> None:
        if lang not in (RU, EN):
            log.warning("[language] refusing unknown language %r", lang)
            return
        if persist:
            QSettings("BelEye", "BelEye").setValue(SETTINGS_KEY, lang)
        app = QCoreApplication.instance()
        if app is None:
            self._lang = lang
            return
        self.install(app, lang)

    def initial_language(self) -> str:
        """Persisted choice, or en on first run."""
        stored = QSettings("BelEye", "BelEye").value(SETTINGS_KEY)
        if stored in (RU, EN):
            return str(stored)
        return EN


#: Application-wide singleton. Safe to import before QApplication exists.
language = LanguageManager()
