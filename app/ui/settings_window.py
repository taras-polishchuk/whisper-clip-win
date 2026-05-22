from __future__ import annotations

import ctypes
import os
from dataclasses import replace

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPen, QRadialGradient, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig
from app.runtime_preferences import (
    cuda_runtime_available,
    describe_graphics_adapters,
    detect_graphics_adapters,
    directml_runtime_available,
    resolve_runtime_preference,
)
from app.services.audio_capture_service import list_input_device_names


class GlassSwitch(QCheckBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")
        self.setFixedSize(52, 30)

    def sizeHint(self) -> QSize:
        return QSize(52, 30)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        track_rect = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        knob_size = track_rect.height() - 8.0
        knob_x = track_rect.right() - knob_size - 4.0 if self.isChecked() else track_rect.left() + 4.0
        knob_rect = QRectF(knob_x, track_rect.top() + 4.0, knob_size, knob_size)

        track_gradient = QLinearGradient(track_rect.topLeft(), track_rect.topRight())
        if self.isEnabled() and self.isChecked():
            track_gradient.setColorAt(0.0, QColor(103, 182, 255, 234))
            track_gradient.setColorAt(1.0, QColor(70, 128, 255, 226))
            border_color = QColor(211, 232, 255, 144)
            knob_color = QColor(247, 251, 255, 252)
            shadow_color = QColor(54, 108, 220, 44)
        elif self.isEnabled():
            track_gradient.setColorAt(0.0, QColor(86, 98, 122, 160))
            track_gradient.setColorAt(1.0, QColor(61, 71, 92, 148))
            border_color = QColor(195, 208, 228, 70)
            knob_color = QColor(245, 248, 255, 232)
            shadow_color = QColor(5, 12, 26, 28)
        else:
            track_gradient.setColorAt(0.0, QColor(72, 83, 104, 96))
            track_gradient.setColorAt(1.0, QColor(52, 61, 79, 84))
            border_color = QColor(195, 208, 228, 34)
            knob_color = QColor(240, 244, 250, 110)
            shadow_color = QColor(5, 12, 26, 14)

        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(track_gradient)
        painter.drawRoundedRect(track_rect, track_rect.height() / 2.0, track_rect.height() / 2.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow_color)
        painter.drawEllipse(knob_rect.adjusted(0.0, 1.2, 0.0, 1.2))
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)


class SettingsWindow(QDialog):
    config_saved = Signal(object)

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._backdrop_applied = False
        self._drag_offset: QPoint | None = None
        self._section_buttons: dict[str, QPushButton] = {}
        self._section_targets: dict[str, QWidget] = {}
        self._scroll_area: QScrollArea | None = None

        self.setObjectName("settingsWindow")
        self.setWindowTitle("WhisperClip Settings")
        self.setModal(False)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(1120, 820)
        self.setMinimumSize(980, 760)

        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText("Ctrl+Alt+Space")
        self._model_combo = QComboBox()
        self._model_combo.addItems(["small", "medium", "distil-large-v3", "large-v3"])
        self._device_combo = QComboBox()
        self._device_combo.addItems(["auto", "cpu", "gpu"])
        self._compute_type_combo = QComboBox()
        self._compute_type_combo.addItems(["auto", "int8", "int8_float16", "float16", "float32"])
        self._microphone_combo = QComboBox()
        self._graphics_label = QLabel()
        self._graphics_label.setWordWrap(True)
        self._graphics_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._runtime_label = QLabel()
        self._runtime_label.setWordWrap(True)
        self._runtime_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._overlay_checkbox = GlassSwitch()
        self._autopaste_checkbox = GlassSwitch()
        self._start_on_login_checkbox = GlassSwitch()
        self._beam_size_spin = QSpinBox()
        self._beam_size_spin.setRange(1, 10)
        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 1.0)
        self._temperature_spin.setSingleStep(0.1)
        self._temperature_spin.setDecimals(2)
        self._condition_checkbox = GlassSwitch()
        self._vad_checkbox = GlassSwitch()
        self._vad_min_silence_spin = QSpinBox()
        self._vad_min_silence_spin.setRange(100, 3000)
        self._vad_min_silence_spin.setSingleStep(100)
        self._vad_min_silence_spin.setSuffix(" ms")
        self._initial_prompt_edit = QPlainTextEdit()
        self._initial_prompt_edit.setPlaceholderText("Base prompt passed to the active transcription backend.")
        self._custom_terms_edit = QPlainTextEdit()
        self._custom_terms_edit.setPlaceholderText("One custom term per line, for example:\nWhisperClip\nTypeScript\nPostgreSQL")
        self._replacement_rules_edit = QPlainTextEdit()
        self._replacement_rules_edit.setPlaceholderText("One rule per line, for example:\nвізпер => Whisper\nреакт => React")

        self._hero_title = QLabel()
        self._hero_title.setObjectName("heroTitle")
        self._hero_subtitle = QLabel()
        self._hero_subtitle.setObjectName("heroSubtitle")
        self._hero_subtitle.setWordWrap(True)
        self._runtime_chip = QLabel("CPU")
        self._runtime_chip.setObjectName("runtimeChip")
        self._model_chip = QLabel()
        self._model_chip.setObjectName("metaChip")
        self._device_chip = QLabel()
        self._device_chip.setObjectName("metaChip")
        self._sidebar_summary_title = QLabel()
        self._sidebar_summary_title.setObjectName("sidebarSummaryTitle")
        self._sidebar_summary_title.setWordWrap(True)
        self._sidebar_summary_body = QLabel()
        self._sidebar_summary_body.setObjectName("sidebarSummaryBody")
        self._sidebar_summary_body.setWordWrap(True)
        self._close_button = QPushButton("Close")
        self._close_button.setObjectName("ghostButton")
        self._save_button = QPushButton("Save changes")
        self._save_button.setObjectName("primaryButton")
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setObjectName("secondaryButton")
        self._footer_note = QLabel(
            "Decode and text rules apply immediately. Model or device changes apply after restart."
        )
        self._footer_note.setObjectName("footerNote")
        self._footer_note.setWordWrap(True)

        for button in (self._close_button, self._save_button, self._cancel_button):
            button.setCursor(Qt.PointingHandCursor)

        self._build_ui()
        self._apply_styles()

        self._device_combo.currentTextChanged.connect(self._reload_runtime_preview_from_form)
        self._compute_type_combo.currentTextChanged.connect(self._reload_runtime_preview_from_form)
        self._model_combo.currentTextChanged.connect(self._refresh_header_preview)
        self._device_combo.currentTextChanged.connect(self._refresh_header_preview)
        self._close_button.clicked.connect(self.hide)
        self._cancel_button.clicked.connect(self.hide)
        self._save_button.clicked.connect(self._save)
        if self._scroll_area is not None:
            self._scroll_area.verticalScrollBar().valueChanged.connect(self._sync_active_section)

        self.reload(config)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        for center_x, center_y, radius, color in (
            (self.width() * 0.11, self.height() * 0.08, self.width() * 0.24, QColor(108, 158, 245, 30)),
            (self.width() * 0.50, self.height() * 0.06, self.width() * 0.22, QColor(120, 138, 255, 18)),
            (self.width() * 0.87, self.height() * 0.82, self.width() * 0.22, QColor(90, 182, 255, 16)),
        ):
            gradient = QRadialGradient(center_x, center_y, radius)
            gradient.setColorAt(0.0, color)
            gradient.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setBrush(gradient)
            painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2.0, radius * 2.0))

        haze_rect = QRectF(20.0, 18.0, self.width() - 40.0, self.height() - 36.0)
        haze = QLinearGradient(haze_rect.topLeft(), haze_rect.bottomRight())
        haze.setColorAt(0.0, QColor(158, 201, 255, 10))
        haze.setColorAt(0.32, QColor(116, 170, 255, 6))
        haze.setColorAt(0.7, QColor(255, 255, 255, 2))
        haze.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(haze)
        painter.drawRoundedRect(haze_rect, 36.0, 36.0)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._backdrop_applied:
            self._apply_windows_backdrop()
            self._backdrop_applied = True

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and event.position().y() <= 92:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def reload(self, config: AppConfig) -> None:
        self._config = config
        self._hotkey_edit.setText(config.hotkey)
        self._model_combo.setCurrentText(config.model_name)
        self._device_combo.setCurrentText(config.device)
        self._compute_type_combo.setCurrentText(config.compute_type)
        self._overlay_checkbox.setChecked(config.overlay_enabled)
        self._autopaste_checkbox.setChecked(config.autopaste_enabled)
        self._start_on_login_checkbox.setChecked(config.start_on_login)
        self._beam_size_spin.setValue(config.beam_size)
        self._temperature_spin.setValue(config.temperature)
        self._condition_checkbox.setChecked(config.condition_on_previous_text)
        self._vad_checkbox.setChecked(config.vad_filter)
        self._vad_min_silence_spin.setValue(config.vad_min_silence_duration_ms)
        self._initial_prompt_edit.setPlainText(config.initial_prompt)
        self._custom_terms_edit.setPlainText("\n".join(config.custom_terms))
        self._replacement_rules_edit.setPlainText(self._format_replacement_rules(config.replacement_rules))
        self._reload_devices(config.microphone_device)
        self._refresh_header_preview()
        self._reload_runtime_preview(config)

    def _reload_devices(self, selected: str | None) -> None:
        self._microphone_combo.clear()
        self._microphone_combo.addItems(list_input_device_names())
        target = selected or "Default"
        index = self._microphone_combo.findText(target)
        if index >= 0:
            self._microphone_combo.setCurrentIndex(index)

    def _reload_runtime_preview(self, config: AppConfig) -> None:
        adapters = detect_graphics_adapters()
        self._graphics_label.setText(describe_graphics_adapters(adapters))
        try:
            resolution = resolve_runtime_preference(
                config.device,
                config.compute_type,
                adapters,
                cuda_runtime_available(),
                directml_runtime_available(),
            )
            self._runtime_label.setText(resolution.summary)
            self._sidebar_summary_title.setText(
                f"{resolution.actual_backend.upper()} on {resolution.actual_device.upper()}"
            )
            self._sidebar_summary_body.setText(resolution.summary)
            self._set_chip(
                self._runtime_chip,
                f"{resolution.actual_backend.upper()} / {resolution.actual_device.upper()}",
                "accent" if resolution.actual_device != "cpu" else "muted",
            )
        except RuntimeError as exc:
            self._runtime_label.setText(str(exc))
            self._sidebar_summary_title.setText("Runtime issue")
            self._sidebar_summary_body.setText(str(exc))
            self._set_chip(self._runtime_chip, "RUNTIME ISSUE", "warning")

    def _reload_runtime_preview_from_form(self) -> None:
        preview_config = replace(
            self._config,
            device=self._device_combo.currentText(),
            compute_type=self._compute_type_combo.currentText(),
        )
        self._reload_runtime_preview(preview_config)

    def _refresh_header_preview(self) -> None:
        model_name = self._model_combo.currentText() or self._config.model_name
        preferred_device = self._device_combo.currentText() or self._config.device
        profile_label = model_name.replace("-", " ").title()
        self._hero_title.setText(f"{profile_label} transcription profile")
        self._hero_subtitle.setText(
            "A lighter acrylic control surface for dictation, routing, and transcript shaping, "
            f"with a current preference for {preferred_device.upper()}."
        )
        self._set_chip(self._model_chip, profile_label, "soft")
        self._set_chip(
            self._device_chip,
            f"Prefers {preferred_device.upper()}",
            "accent" if preferred_device != "cpu" else "muted",
        )

    def _save(self) -> None:
        microphone = self._microphone_combo.currentText()
        updated = replace(
            self._config,
            hotkey=self._hotkey_edit.text().strip() or self._config.hotkey,
            model_name=self._model_combo.currentText(),
            device=self._device_combo.currentText(),
            compute_type=self._compute_type_combo.currentText(),
            beam_size=self._beam_size_spin.value(),
            temperature=self._temperature_spin.value(),
            condition_on_previous_text=self._condition_checkbox.isChecked(),
            vad_filter=self._vad_checkbox.isChecked(),
            vad_min_silence_duration_ms=self._vad_min_silence_spin.value(),
            overlay_enabled=self._overlay_checkbox.isChecked(),
            autopaste_enabled=self._autopaste_checkbox.isChecked(),
            start_on_login=self._start_on_login_checkbox.isChecked(),
            initial_prompt=self._initial_prompt_edit.toPlainText().strip(),
            custom_terms=self._parse_terms(self._custom_terms_edit.toPlainText()),
            replacement_rules=self._parse_replacement_rules(self._replacement_rules_edit.toPlainText()),
            microphone_device=None if microphone == "Default" else microphone,
        )
        updated.save()
        self.config_saved.emit(updated)
        self.hide()

    def _parse_terms(self, raw_text: str) -> list[str]:
        return [line.strip() for line in raw_text.splitlines() if line.strip()]

    def _parse_replacement_rules(self, raw_text: str) -> dict[str, str]:
        rules: dict[str, str] = {}
        for line in raw_text.splitlines():
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                continue
            if "=>" in stripped_line:
                source, target = stripped_line.split("=>", 1)
            elif "=" in stripped_line:
                source, target = stripped_line.split("=", 1)
            else:
                continue
            source = source.strip()
            target = target.strip()
            if source and target:
                rules[source] = target
        return rules

    def _format_replacement_rules(self, rules: dict[str, str]) -> str:
        return "\n".join(f"{source} => {target}" for source, target in rules.items())

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(0)

        self._surface = QFrame()
        self._surface.setObjectName("surface")
        self._apply_shadow(self._surface)
        root_layout.addWidget(self._surface)

        surface_layout = QVBoxLayout(self._surface)
        surface_layout.setContentsMargins(24, 24, 24, 24)
        surface_layout.setSpacing(18)

        title_bar = QFrame()
        title_bar.setObjectName("windowChrome")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(22, 18, 22, 18)
        title_layout.setSpacing(16)

        title_text_layout = QVBoxLayout()
        title_text_layout.setSpacing(4)
        eyebrow = QLabel("WhisperClip Studio")
        eyebrow.setObjectName("eyebrow")
        caption = QLabel("Settings")
        caption.setObjectName("windowTitle")
        subtitle = QLabel("WinUI-inspired tuning surface for runtime, capture, and transcript shaping.")
        subtitle.setObjectName("windowSubtitle")
        subtitle.setWordWrap(True)
        title_text_layout.addWidget(eyebrow)
        title_text_layout.addWidget(caption)
        title_text_layout.addWidget(subtitle)
        title_layout.addLayout(title_text_layout, 1)
        title_layout.addWidget(self._runtime_chip, 0, Qt.AlignTop)
        title_layout.addWidget(self._close_button, 0, Qt.AlignTop)
        surface_layout.addWidget(title_bar)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(18)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 20, 18, 18)
        sidebar_layout.setSpacing(12)

        sidebar_label = QLabel("Control center")
        sidebar_label.setObjectName("sidebarLabel")
        sidebar_caption = QLabel(
            "Acrylic-first navigation for runtime, capture, quality, and vocabulary shaping."
        )
        sidebar_caption.setObjectName("sidebarCaption")
        sidebar_caption.setWordWrap(True)
        sidebar_layout.addWidget(sidebar_label)
        sidebar_layout.addWidget(sidebar_caption)

        nav_label = QLabel("Sections")
        nav_label.setObjectName("sidebarSectionLabel")
        sidebar_layout.addWidget(nav_label)
        sidebar_layout.addWidget(self._create_nav_button("overview", "Overview"))
        sidebar_layout.addWidget(self._create_nav_button("runtime", "Runtime"))
        sidebar_layout.addWidget(self._create_nav_button("capture", "Capture"))
        sidebar_layout.addWidget(self._create_nav_button("quality", "Quality"))
        sidebar_layout.addWidget(self._create_nav_button("language", "Vocabulary"))
        sidebar_layout.addStretch(1)

        sidebar_summary = QFrame()
        sidebar_summary.setObjectName("sidebarSummary")
        sidebar_summary_layout = QVBoxLayout(sidebar_summary)
        sidebar_summary_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_summary_layout.setSpacing(8)
        summary_kicker = QLabel("Live route")
        summary_kicker.setObjectName("sidebarSummaryKicker")
        sidebar_summary_layout.addWidget(summary_kicker)
        sidebar_summary_layout.addWidget(self._sidebar_summary_title)
        sidebar_summary_layout.addWidget(self._sidebar_summary_body)
        sidebar_layout.addWidget(sidebar_summary)

        body_layout.addWidget(sidebar)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("contentScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area = scroll_area

        content = QWidget()
        content.setObjectName("scrollContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        hero_card, hero_layout = self._create_card(
            "Current profile",
            "Fluid overview for the active transcription stack, hardware route, and current preference.",
            object_name="heroCard",
        )
        hero_layout.addWidget(self._hero_title)
        hero_layout.addWidget(self._hero_subtitle)
        hero_chip_row = QHBoxLayout()
        hero_chip_row.setSpacing(10)
        hero_chip_row.addWidget(self._model_chip, 0)
        hero_chip_row.addWidget(self._device_chip, 0)
        hero_chip_row.addStretch(1)
        hero_layout.addLayout(hero_chip_row)
        hero_panels = QHBoxLayout()
        hero_panels.setSpacing(14)
        hero_panels.addWidget(self._create_value_panel("Detected graphics", self._graphics_label), 1)
        hero_panels.addWidget(self._create_value_panel("Runtime preview", self._runtime_label), 1)
        hero_layout.addLayout(hero_panels)
        self._register_section("overview", hero_card)
        content_layout.addWidget(hero_card)

        runtime_card, runtime_layout = self._create_card(
            "Runtime and shortcuts",
            "Choose model size, compute target, and the shortcut that opens a new dictation pass.",
        )
        runtime_grid = QGridLayout()
        runtime_grid.setHorizontalSpacing(14)
        runtime_grid.setVerticalSpacing(14)
        runtime_grid.addWidget(
            self._create_field_block(
                "Hotkey",
                "Global shortcut used to start and stop recording.",
                self._hotkey_edit,
            ),
            0,
            0,
        )
        runtime_grid.addWidget(
            self._create_field_block(
                "Model",
                "Larger models improve accuracy but increase first-load and inference cost.",
                self._model_combo,
            ),
            0,
            1,
        )
        runtime_grid.addWidget(
            self._create_field_block(
                "Device",
                "Auto prefers GPU acceleration when the active backend supports it.",
                self._device_combo,
            ),
            1,
            0,
        )
        runtime_grid.addWidget(
            self._create_field_block(
                "Compute type",
                "Used mainly on the faster-whisper path. DirectML manages precision internally.",
                self._compute_type_combo,
            ),
            1,
            1,
        )
        runtime_layout.addLayout(runtime_grid)
        self._register_section("runtime", runtime_card)
        content_layout.addWidget(runtime_card)

        capture_card, capture_layout = self._create_card(
            "Capture flow",
            "Shape how the assistant records, pastes, and stays visible on the desktop.",
        )
        capture_grid = QGridLayout()
        capture_grid.setHorizontalSpacing(14)
        capture_grid.setVerticalSpacing(14)
        capture_grid.addWidget(
            self._create_field_block(
                "Microphone",
                "Select the capture source or keep the Windows default input device.",
                self._microphone_combo,
            ),
            0,
            0,
            1,
            2,
        )
        capture_grid.addWidget(
            self._create_toggle_block(
                "Overlay indicator",
                self._overlay_checkbox,
                "Shows the floating top-right status indicator while the app is active.",
            ),
            1,
            0,
        )
        capture_grid.addWidget(
            self._create_toggle_block(
                "Autopaste",
                self._autopaste_checkbox,
                "Paste directly into the focused app when possible, otherwise keep the result in the clipboard.",
            ),
            1,
            1,
        )
        capture_grid.addWidget(
            self._create_toggle_block(
                "Start on login",
                self._start_on_login_checkbox,
                "Launch WhisperClip automatically after Windows sign-in.",
            ),
            2,
            0,
        )
        capture_layout.addLayout(capture_grid)
        self._register_section("capture", capture_card)
        content_layout.addWidget(capture_card)

        quality_card, quality_layout = self._create_card(
            "Recognition quality",
            "Control decoding behavior, silence handling, and how much each clip depends on previous context.",
        )
        quality_grid = QGridLayout()
        quality_grid.setHorizontalSpacing(14)
        quality_grid.setVerticalSpacing(14)
        quality_grid.addWidget(
            self._create_field_block(
                "Beam size",
                "Higher values may improve stability at the cost of extra latency.",
                self._beam_size_spin,
            ),
            0,
            0,
        )
        quality_grid.addWidget(
            self._create_field_block(
                "Temperature",
                "Keeps decoding conservative at low values and more flexible at higher values.",
                self._temperature_spin,
            ),
            0,
            1,
        )
        quality_grid.addWidget(
            self._create_field_block(
                "VAD minimum silence",
                "How long silence must last before the VAD path treats it as a segment boundary.",
                self._vad_min_silence_spin,
            ),
            1,
            0,
            1,
            2,
        )
        quality_grid.addWidget(
            self._create_toggle_block(
                "Condition on previous text",
                self._condition_checkbox,
                "Pass previous text within the same clip to stabilize continuing dictation.",
            ),
            2,
            0,
        )
        quality_grid.addWidget(
            self._create_toggle_block(
                "Filter silence with VAD",
                self._vad_checkbox,
                "Filter silence before decoding when the active backend supports the VAD path.",
            ),
            2,
            1,
        )
        quality_layout.addLayout(quality_grid)
        self._register_section("quality", quality_card)
        content_layout.addWidget(quality_card)

        language_card, language_layout = self._create_card(
            "Language shaping",
            "Bias the transcript toward your vocabulary and clean up common replacements after decoding.",
        )
        prompt_grid = QGridLayout()
        prompt_grid.setHorizontalSpacing(14)
        prompt_grid.setVerticalSpacing(14)
        prompt_grid.addWidget(
            self._create_field_block(
                "Initial prompt",
                "Used as the runtime context prompt for the active backend.",
                self._initial_prompt_edit,
            ),
            0,
            0,
            1,
            2,
        )
        prompt_grid.addWidget(
            self._create_field_block(
                "Custom terms",
                "One term per line. Good for product names, code symbols, and brand vocabulary.",
                self._custom_terms_edit,
            ),
            1,
            0,
        )
        prompt_grid.addWidget(
            self._create_field_block(
                "Replacement rules",
                "Use '=>' or '=' to normalize recurring mistakes after transcription.",
                self._replacement_rules_edit,
            ),
            1,
            1,
        )
        language_layout.addLayout(prompt_grid)
        self._register_section("language", language_card)
        content_layout.addWidget(language_card)

        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        body_layout.addWidget(scroll_area, 1)
        surface_layout.addLayout(body_layout, 1)

        footer = QFrame()
        footer.setObjectName("footerBar")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 16, 18, 16)
        footer_layout.setSpacing(12)
        footer_layout.addWidget(self._footer_note, 1)
        footer_layout.addWidget(self._cancel_button)
        footer_layout.addWidget(self._save_button)
        surface_layout.addWidget(footer)

        self._set_active_section("overview")

    def _create_card(self, title: str, description: str, object_name: str = "card") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        description_label = QLabel(description)
        description_label.setObjectName("cardDescription")
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        return card, layout

    def _create_field_block(self, title: str, description: str, widget: QWidget) -> QFrame:
        block = QFrame()
        block.setObjectName("fieldBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("fieldTitle")
        description_label = QLabel(description)
        description_label.setObjectName("fieldDescription")
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addWidget(widget)
        return block

    def _create_toggle_block(self, title: str, checkbox: QCheckBox, description: str) -> QFrame:
        block = QFrame()
        block.setObjectName("toggleBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("fieldTitle")
        checkbox.setAccessibleName(title)
        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(checkbox, 0, Qt.AlignRight)

        description_label = QLabel(description)
        description_label.setObjectName("fieldDescription")
        description_label.setWordWrap(True)
        layout.addLayout(header_layout)
        layout.addWidget(description_label)
        layout.addStretch(1)
        return block

    def _create_value_panel(self, title: str, value_label: QLabel) -> QFrame:
        panel = QFrame()
        panel.setObjectName("valuePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("valuePanelTitle")
        value_label.setObjectName("valuePanelBody")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return panel

    def _create_nav_button(self, key: str, title: str) -> QPushButton:
        button = QPushButton(title)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, section=key: self._scroll_to_section(section))
        self._section_buttons[key] = button
        return button

    def _register_section(self, key: str, widget: QWidget) -> None:
        self._section_targets[key] = widget

    def _scroll_to_section(self, key: str) -> None:
        target = self._section_targets.get(key)
        if target is None or self._scroll_area is None:
            return
        self._scroll_area.verticalScrollBar().setValue(max(0, target.y() - 8))
        self._set_active_section(key)

    def _sync_active_section(self, value: int) -> None:
        if not self._section_targets:
            return
        current_key = "overview"
        for key in ("overview", "runtime", "capture", "quality", "language"):
            target = self._section_targets.get(key)
            if target is not None and value >= target.y() - 60:
                current_key = key
        self._set_active_section(current_key)

    def _set_active_section(self, active_key: str) -> None:
        for key, button in self._section_buttons.items():
            button.setChecked(key == active_key)

    def _apply_shadow(self, widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(4, 10, 20, 92))
        widget.setGraphicsEffect(shadow)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            #settingsWindow {
                background: transparent;
                color: #e9f1ff;
                font-family: "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI";
            }
            #surface {
                background: qlineargradient(
                    x1: 0,
                    y1: 0,
                    x2: 1,
                    y2: 1,
                    stop: 0 rgba(29, 35, 48, 228),
                    stop: 0.5 rgba(22, 29, 42, 220),
                    stop: 1 rgba(19, 25, 38, 226)
                );
                border: 1px solid rgba(226, 236, 255, 28);
                border-radius: 30px;
            }
            #windowChrome {
                background: qlineargradient(
                    x1: 0,
                    y1: 0,
                    x2: 1,
                    y2: 1,
                    stop: 0 rgba(255, 255, 255, 18),
                    stop: 0.52 rgba(255, 255, 255, 12),
                    stop: 1 rgba(255, 255, 255, 8)
                );
                border: 1px solid rgba(233, 241, 255, 24);
                border-radius: 22px;
            }
            #sidebar,
            #card,
            #footerBar,
            #sidebarSummary,
            #valuePanel,
            #fieldBlock,
            #toggleBlock {
                background: qlineargradient(
                    x1: 0,
                    y1: 0,
                    x2: 0,
                    y2: 1,
                    stop: 0 rgba(255, 255, 255, 10),
                    stop: 1 rgba(255, 255, 255, 4)
                );
                border: 1px solid rgba(233, 241, 255, 18);
            }
            #sidebar {
                border-radius: 22px;
            }
            #heroCard {
                background: qlineargradient(
                    x1: 0,
                    y1: 0,
                    x2: 1,
                    y2: 1,
                    stop: 0 rgba(96, 151, 255, 22),
                    stop: 0.48 rgba(90, 114, 214, 14),
                    stop: 1 rgba(255, 255, 255, 6)
                );
                border: 1px solid rgba(233, 241, 255, 22);
                border-radius: 24px;
            }
            #card {
                border-radius: 22px;
            }
            #fieldBlock,
            #toggleBlock,
            #valuePanel,
            #sidebarSummary,
            #footerBar {
                border-radius: 18px;
            }
            #eyebrow {
                color: rgba(143, 193, 255, 214);
                font-size: 11px;
                font-weight: 700;
            }
            #windowTitle {
                color: #f4f8ff;
                font-size: 32px;
                font-weight: 700;
            }
            #windowSubtitle {
                color: rgba(216, 226, 240, 158);
                font-size: 13px;
            }
            #heroTitle {
                color: #f5f9ff;
                font-size: 28px;
                font-weight: 700;
            }
            #heroSubtitle {
                color: rgba(216, 226, 240, 170);
                font-size: 14px;
            }
            #runtimeChip,
            #metaChip {
                padding: 8px 14px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 700;
            }
            #runtimeChip {
                min-height: 18px;
            }
            QLabel#runtimeChip[tone="accent"],
            QLabel#metaChip[tone="accent"] {
                background: rgba(85, 160, 255, 28);
                border: 1px solid rgba(111, 183, 255, 82);
                color: #eef6ff;
            }
            QLabel#runtimeChip[tone="muted"],
            QLabel#metaChip[tone="muted"] {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(233, 241, 255, 22);
                color: #eef4ff;
            }
            QLabel#runtimeChip[tone="soft"],
            QLabel#metaChip[tone="soft"] {
                background: rgba(123, 125, 255, 18);
                border: 1px solid rgba(152, 165, 255, 54);
                color: #edf1ff;
            }
            QLabel#runtimeChip[tone="warning"],
            QLabel#metaChip[tone="warning"] {
                background: rgba(255, 182, 72, 18);
                border: 1px solid rgba(255, 196, 98, 62);
                color: #fff2d8;
            }
            #cardTitle {
                color: #f3f8ff;
                font-size: 18px;
                font-weight: 700;
            }
            #cardDescription {
                color: rgba(213, 222, 236, 144);
                font-size: 12px;
            }
            #fieldTitle, #valuePanelTitle {
                color: #f3f8ff;
                font-size: 13px;
                font-weight: 600;
            }
            #fieldDescription {
                color: rgba(204, 214, 230, 140);
                font-size: 12px;
            }
            #valuePanelBody {
                color: #dff1ff;
                font-size: 13px;
                font-weight: 600;
            }
            #sidebarLabel {
                color: #f4f8ff;
                font-size: 17px;
                font-weight: 700;
            }
            #sidebarCaption {
                color: rgba(204, 214, 230, 136);
                font-size: 12px;
            }
            #sidebarSectionLabel,
            #sidebarSummaryKicker {
                color: rgba(143, 193, 255, 198);
                font-size: 11px;
                font-weight: 700;
            }
            #sidebarSummaryTitle {
                color: #f3f8ff;
                font-size: 16px;
                font-weight: 700;
            }
            #sidebarSummaryBody {
                color: rgba(213, 222, 236, 146);
                font-size: 12px;
            }
            #footerNote {
                color: rgba(208, 218, 232, 146);
                font-size: 12px;
            }
            QLineEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox,
            QPlainTextEdit {
                background: rgba(11, 16, 28, 134);
                border: 1px solid rgba(233, 241, 255, 22);
                border-radius: 14px;
                color: #f2f7ff;
                padding: 12px 14px;
                selection-background-color: rgba(90, 160, 255, 86);
            }
            QLineEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox {
                min-height: 46px;
            }
            QPlainTextEdit {
                min-height: 154px;
            }
            QLineEdit:hover,
            QComboBox:hover,
            QSpinBox:hover,
            QDoubleSpinBox:hover,
            QPlainTextEdit:hover {
                background: rgba(14, 20, 34, 150);
                border: 1px solid rgba(233, 241, 255, 32);
            }
            QLineEdit:focus,
            QComboBox:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus,
            QPlainTextEdit:focus {
                background: rgba(16, 24, 38, 164);
                border: 1px solid rgba(109, 178, 255, 116);
            }
            QComboBox::drop-down,
            QSpinBox::up-button,
            QSpinBox::down-button,
            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: rgba(26, 31, 43, 244);
                border: 1px solid rgba(233, 241, 255, 26);
                padding: 8px;
                selection-background-color: rgba(96, 151, 255, 52);
                selection-color: #f4f8ff;
            }
            QPushButton {
                min-height: 44px;
                padding: 0 18px;
                border-radius: 14px;
                font-size: 13px;
                font-weight: 600;
            }
            #navButton {
                min-height: 42px;
                padding: 0 14px;
                border-radius: 12px;
                text-align: left;
                color: rgba(207, 217, 232, 146);
                background: transparent;
                border: 1px solid transparent;
            }
            #navButton:hover {
                color: #f4f8ff;
                background: rgba(255, 255, 255, 8);
                border: 1px solid rgba(233, 241, 255, 18);
            }
            #navButton:checked {
                color: #f4f8ff;
                background: rgba(96, 151, 255, 18);
                border: 1px solid rgba(111, 183, 255, 40);
            }
            #primaryButton {
                color: #ffffff;
                background: qlineargradient(
                    x1: 0,
                    y1: 0,
                    x2: 1,
                    y2: 1,
                    stop: 0 #77d8ff,
                    stop: 1 #3d7dff
                );
                border: none;
            }
            #primaryButton:hover {
                background: qlineargradient(
                    x1: 0,
                    y1: 0,
                    x2: 1,
                    y2: 1,
                    stop: 0 #93e3ff,
                    stop: 1 #5793ff
                );
            }
            #secondaryButton,
            #ghostButton {
                color: #eef5ff;
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(233, 241, 255, 18);
            }
            #secondaryButton:hover,
            #ghostButton:hover {
                background: rgba(255, 255, 255, 14);
                border: 1px solid rgba(233, 241, 255, 26);
            }
            QScrollArea {
                background: transparent;
            }
            QScrollBar:vertical {
                width: 12px;
                margin: 6px 0 6px 0;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                min-height: 34px;
                border-radius: 6px;
                background: rgba(255, 255, 255, 22);
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(111, 183, 255, 68);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
                height: 0px;
            }
            """
        )

    def _set_chip(self, label: QLabel, text: str, tone: str) -> None:
        label.setText(text)
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _apply_windows_backdrop(self) -> None:
        if os.name != "nt":
            return

        class Margins(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        hwnd = int(self.winId())
        dark_mode = ctypes.c_int(1)
        corner_preference = ctypes.c_int(2)
        backdrop_type = ctypes.c_int(4)
        margins = Margins(-1, -1, -1, -1)

        try:
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
            dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_preference), ctypes.sizeof(corner_preference))
            dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type))
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            return