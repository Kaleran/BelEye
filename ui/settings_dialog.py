from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import config as cfg
from app import nvr_config as nvrcfg
from app import secrets as keystore
from app.config import CameraConfig
from app.nvr_config import NvrConfig, nvr_keyring_user
from .camera_form import CameraForm
from .language import EN, RU, language
from .nvr_form import NvrForm
from .theme import theme

log = logging.getLogger(__name__)

ROLE_KIND = Qt.UserRole       # "camera" | "nvr"
ROLE_ID = Qt.UserRole + 1     # source id


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Source settings"))
        self.resize(560, 460)

        self._cameras: list[CameraConfig] = cfg.load_cameras()
        self._nvrs: list[NvrConfig] = nvrcfg.load_nvrs()
        self._changed = False

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._edit())

        self._title = QLabel(self.tr("Sources"))
        self._subtitle = QLabel("")
        self._apply_theme()
        theme.changed.connect(lambda _m: self._apply_theme())
        self._refresh_list()

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        header.addWidget(self._title)
        header.addWidget(self._subtitle)

        # ---- Language selector ----
        self._lang_combo = QComboBox()
        self._lang_combo.addItem(self.tr("Russian"), RU)
        self._lang_combo.addItem(self.tr("English"), EN)
        self._lang_combo.setCurrentIndex(0 if language.language() == RU else 1)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self._lang_label = QLabel(self.tr("Language:"))

        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_row.setSpacing(8)
        lang_row.addWidget(self._lang_label)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch(1)

        add_cam_btn = QPushButton(self.tr("Add camera"))
        add_cam_btn.setProperty("primary", True)
        add_cam_btn.setCursor(Qt.PointingHandCursor)
        add_cam_btn.clicked.connect(self._add_camera)

        add_nvr_btn = QPushButton(self.tr("Add NVR"))
        add_nvr_btn.setProperty("primary", True)
        add_nvr_btn.setCursor(Qt.PointingHandCursor)
        add_nvr_btn.clicked.connect(self._add_nvr)

        edit_btn = QPushButton(self.tr("Edit"))
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(self._edit)

        del_btn = QPushButton(self.tr("Delete"))
        del_btn.setProperty("danger", True)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(self._delete)

        side = QVBoxLayout()
        side.setSpacing(6)
        side.addLayout(lang_row)
        side.addSpacing(8)
        side.addWidget(add_cam_btn)
        side.addWidget(add_nvr_btn)
        side.addSpacing(8)
        side.addWidget(edit_btn)
        side.addWidget(del_btn)
        side.addStretch(1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.list, 1)
        body.addLayout(side)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_btn = buttons.button(QDialogButtonBox.Close)
        close_btn.setText(self.tr("Done"))
        close_btn.setCursor(Qt.PointingHandCursor)
        buttons.rejected.connect(self.accept)
        close_btn.clicked.connect(self.accept)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)
        root.addLayout(header)
        root.addLayout(body, 1)
        root.addWidget(buttons)

        # Restart prompt shown after a language change.
        self._restart_prompt: QLabel | None = None
        self._build_restart_prompt(root)

    def _build_restart_prompt(self, root: QVBoxLayout) -> None:
        self._restart_prompt = QLabel(
            self.tr("Restart the application to apply the new language.")
        )
        self._restart_prompt.setWordWrap(True)
        self._restart_prompt.setStyleSheet(
            f"color: {theme.token('warning')}; font-size: 12px;"
        )
        self._restart_prompt.hide()
        root.addWidget(self._restart_prompt)

    def _on_language_changed(self, _idx: int) -> None:
        data = self._lang_combo.currentData()
        if data not in (RU, EN):
            return
        language.set_language(data)
        self._restart_prompt.show()

    def _apply_theme(self) -> None:
        self._title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {theme.token('text_primary')};"
        )
        self._subtitle.setStyleSheet(
            f"font-size: 12px; color: {theme.token('text_muted')};"
        )

    # ---------------- list ----------------

    def _refresh_list(self) -> None:
        self.list.clear()
        for cam in self._cameras:
            path = "" if (cam.path or "").strip() in ("", "/") else cam.path
            item = QListWidgetItem(
                f"[CAM]  {cam.name}   ·   {cam.host}:{cam.port}{path}"
            )
            item.setData(ROLE_KIND, "camera")
            item.setData(ROLE_ID, cam.id)
            self.list.addItem(item)
        for nvr in self._nvrs:
            ch_n = len(nvr.channels)
            item = QListWidgetItem(
                f"[NVR]  {nvr.name}   ·   {nvr.host}:{nvr.port}   ·   "
                f"{self.tr('channels', 'NVR channels count')}: {ch_n}"
            )
            item.setData(ROLE_KIND, "nvr")
            item.setData(ROLE_ID, nvr.id)
            self.list.addItem(item)
        self._update_subtitle()

    def _update_subtitle(self) -> None:
        parts = []
        if self._cameras:
            parts.append(f"{self.tr('cameras', 'subtitle camera count')}: {len(self._cameras)}")
        if self._nvrs:
            parts.append(f"NVR: {len(self._nvrs)}")
        self._subtitle.setText(", ".join(parts) if parts else self.tr("empty"))

    def _selected(self) -> tuple[str, str] | None:
        item = self.list.currentItem()
        if not item:
            return None
        return str(item.data(ROLE_KIND)), str(item.data(ROLE_ID))

    # ---------------- camera ops ----------------

    def _add_camera(self) -> None:
        form = CameraForm(parent=self)
        if form.exec() == QDialog.Accepted:
            cam, pwd = form.result_data()
            self._cameras = cfg.add_camera(self._cameras, cam)
            try:
                keystore.set_password(cam.id, pwd)
            except Exception as exc:
                QMessageBox.warning(self, self.tr("Keyring"), self.tr("Failed to save password: {exc}").format(exc=exc))
            self._changed = True
            self._refresh_list()

    def _edit_camera(self, cam_id: str) -> None:
        cam = next((c for c in self._cameras if c.id == cam_id), None)
        if not cam:
            return
        pwd = keystore.get_password(cam.id)
        form = CameraForm(camera=cam, password=pwd, parent=self)
        if form.exec() == QDialog.Accepted:
            updated, new_pwd = form.result_data()
            self._cameras = cfg.update_camera(self._cameras, updated)
            try:
                keystore.set_password(updated.id, new_pwd)
            except Exception as exc:
                QMessageBox.warning(self, self.tr("Keyring"), self.tr("Failed to save password: {exc}").format(exc=exc))
            self._changed = True
            self._refresh_list()

    def _delete_camera(self, cam_id: str) -> None:
        cam = next((c for c in self._cameras if c.id == cam_id), None)
        if not cam:
            return
        if QMessageBox.question(
            self, self.tr("Delete"),
            self.tr("Delete camera «{name}»?").format(name=cam.name),
        ) != QMessageBox.Yes:
            return
        self._cameras = cfg.delete_camera(self._cameras, cam.id)
        keystore.delete_password(cam.id)
        self._changed = True
        self._refresh_list()

    # ---------------- nvr ops ----------------

    def _add_nvr(self) -> None:
        form = NvrForm(parent=self)
        if form.exec() == QDialog.Accepted:
            nvr, pwd = form.result_data()
            self._nvrs = nvrcfg.add_nvr(self._nvrs, nvr)
            try:
                keystore.set_password(nvr_keyring_user(nvr.id), pwd)
            except Exception as exc:
                QMessageBox.warning(self, self.tr("Keyring"), self.tr("Failed to save password: {exc}").format(exc=exc))
            self._changed = True
            self._refresh_list()

    def _edit_nvr(self, nvr_id: str) -> None:
        nvr = next((n for n in self._nvrs if n.id == nvr_id), None)
        if not nvr:
            return
        pwd = keystore.get_password(nvr_keyring_user(nvr.id))
        form = NvrForm(nvr=nvr, password=pwd, parent=self)
        if form.exec() == QDialog.Accepted:
            updated, new_pwd = form.result_data()
            self._nvrs = nvrcfg.update_nvr(self._nvrs, updated)
            try:
                keystore.set_password(nvr_keyring_user(updated.id), new_pwd)
            except Exception as exc:
                QMessageBox.warning(self, self.tr("Keyring"), self.tr("Failed to save password: {exc}").format(exc=exc))
            self._changed = True
            self._refresh_list()

    def _delete_nvr(self, nvr_id: str) -> None:
        nvr = next((n for n in self._nvrs if n.id == nvr_id), None)
        if not nvr:
            return
        if QMessageBox.question(
            self, self.tr("Delete"),
            self.tr("Delete recorder «{name}»?").format(name=nvr.name),
        ) != QMessageBox.Yes:
            return
        self._nvrs = nvrcfg.delete_nvr(self._nvrs, nvr.id)
        keystore.delete_password(nvr_keyring_user(nvr.id))
        self._changed = True
        self._refresh_list()

    # ---------------- dispatch ----------------

    def _edit(self) -> None:
        sel = self._selected()
        if not sel:
            return
        kind, sid = sel
        if kind == "camera":
            self._edit_camera(sid)
        elif kind == "nvr":
            self._edit_nvr(sid)

    def _delete(self) -> None:
        sel = self._selected()
        if not sel:
            return
        kind, sid = sel
        if kind == "camera":
            self._delete_camera(sid)
        elif kind == "nvr":
            self._delete_nvr(sid)

    # ---------------- external ----------------

    def changed(self) -> bool:
        return self._changed

    def cameras(self) -> list[CameraConfig]:
        return self._cameras

    def nvrs(self) -> list[NvrConfig]:
        return self._nvrs
