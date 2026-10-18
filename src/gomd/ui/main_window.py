from __future__ import annotations
import json, logging, os, re, shutil, subprocess, sys, tempfile, traceback, wave
from pathlib import Path
from threading import Event
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..audio.analyzer import load_audio, spectrum, spectrogram, export_waveform_csv
from ..audio.processor import PauseSettings, synthesize_with_pauses
from ..audio.wav_tools import inspect_wav
from ..core.paths import config_dir, data_dir, default_model_dir, log_dir
from ..core.project import Project, Scene
from ..core.settings import AppSettings
from ..scenes.pipeline import synthesize_project_scenes, assemble_project_audio
from ..graphs.render import GraphRenderer
from ..help.diagnostics import collect_diagnostics, open_log_directory
from ..i18n.translations import SUPPORTED_LANGUAGES, detect_windows_language, translate as tr
from ..mathtext.engine import MathTextEngine
from ..media.library import MediaLibrary
from ..models.catalog import ModelCatalogClient, VoiceModel
from ..pronunciation.dictionary import PronunciationDictionary, PronunciationRule
from ..tts.piper import PiperCLIAdapter
from ..tts.registry import TTSRegistry
from ..tts.base import TTSRequest
from ..vocal.music import Note, VocalProject, render_preview_wav

log=logging.getLogger(__name__)

class WorkerSignals(QObject):
    succeeded=Signal(object)
    failed=Signal(str,str)
    progress=Signal(str)
    finished=Signal()

class Worker(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__(); self.fn=fn; self.signals=WorkerSignals(); self.cancel_event=Event()
    def run(self):
        try: self.signals.succeeded.emit(self.fn(self.cancel_event, self.signals.progress.emit))
        except BaseException as exc: self.signals.failed.emit(str(exc),traceback.format_exc())
        finally: self.signals.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings):
        super().__init__(); self.settings=settings
        self.language=settings.language if settings.language in SUPPORTED_LANGUAGES else detect_windows_language()
        self.project: Project|None=None; self.current_scene: Scene|None=None
        self.last_error_description=""
        self.model_catalog=[]; self.media_items=[]; self.dictionary=PronunciationDictionary()
        self.dictionary_path=data_dir()/"pronunciation.json"
        if self.dictionary_path.exists():
            try: self.dictionary=PronunciationDictionary.load_json(self.dictionary_path)
            except Exception: log.exception("Could not load pronunciation dictionary")
        self.pool=QThreadPool.globalInstance(); self._workers=set(); self._active_worker=None
        self.tts_registry=TTSRegistry.discover()
        self.setWindowTitle(f"{APP_NAME} · {__version__}"); self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1]/"resources"/"app_icon.svg"))); self.resize(1420,900); self.setMinimumSize(920,620)
        self._build_ui(); self._apply_style(); self.refresh_installed_models(); self._populate_dictionary()
        self.cancel_button=QPushButton("Отменить" if self.language=="ru" else "Cancel")
        self.cancel_button.clicked.connect(self.cancel_active_task); self.statusBar().addPermanentWidget(self.cancel_button); self.cancel_button.hide()
        self._autosave_timer=QTimer(self); self._autosave_timer.setInterval(max(15,int(self.settings.autosave_seconds))*1000); self._autosave_timer.timeout.connect(self._autosave); self._autosave_timer.start()
        self.statusBar().showMessage(tr("common.ready",self.language))

    def t(self,key,**kwargs): return tr(key,self.language,**kwargs)
    def _label(self,key): return QLabel(self.t(key))
    def _button(self,key,slot):
        b=QPushButton(self.t(key)); b.clicked.connect(slot); return b
    def _confirm_overwrite(self,path):
        target=Path(path)
        if not target.exists(): return True
        return QMessageBox.question(self,self.t("common.warning"),f"Replace this existing file?\n{target}") == QMessageBox.StandardButton.Yes
    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow, QWidget { background: #fffafd; color: #302b39; font-size: 10pt; }
        QListWidget { background: #f8eff8; border: 0; padding: 9px; border-radius: 12px; }
        QListWidget::item { padding: 12px 10px; border-radius: 8px; }
        QListWidget::item:selected { background: #ebd8f3; color: #3c2352; font-weight: 600; }
        QPushButton { background: #ead7f1; border: 1px solid #ddc5e8; border-radius: 8px; padding: 8px 12px; }
        QPushButton:hover { background: #ddc4ea; }
        QPushButton:disabled { color: #9a94a1; background: #f1edf3; }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget { background: white; border: 1px solid #dcd2e2; border-radius: 6px; padding: 5px; selection-background-color: #d8bbe8; }
        QProgressBar { border: 1px solid #dcd2e2; border-radius: 6px; text-align: center; }
        QProgressBar::chunk { background: #bd8ad3; border-radius: 5px; }
        QGroupBox { border: 1px solid #e5d8e9; border-radius: 10px; margin-top: 12px; padding: 10px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
        """)

    def _build_ui(self):
        shell=QWidget(); root=QHBoxLayout(shell); root.setContentsMargins(12,12,12,12); root.setSpacing(12)
        self.nav=QListWidget(); self.nav.setFixedWidth(205)
        self.pages=QStackedWidget(); root.addWidget(self.nav); root.addWidget(self.pages,1); self.setCentralWidget(shell)
        self._add_page("nav.studio",self._build_studio())
        self._add_page("nav.projects",self._build_projects())
        self._add_page("nav.models",self._build_models())
        self._add_page("nav.media",self._build_media())
        self._add_page("nav.graphs",self._build_graphs())
        self._add_page("nav.analyzer",self._build_analyzer())
        self._add_page("nav.vocal",self._build_vocal())
        self._add_page("nav.pronunciation",self._build_pronunciation())
        self._add_page("nav.settings",self._build_settings())
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex); self.nav.setCurrentRow(0)
        menu=self.menuBar().addMenu("GoMD")
        quit_action=QAction("Exit" if self.language!="ru" else "Выход",self); quit_action.triggered.connect(self.close); menu.addAction(quit_action)

    def _add_page(self,key,widget):
        item=QListWidgetItem(self.t(key)); self.nav.addItem(item); self.pages.addWidget(widget)

    def _build_studio(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setSpacing(10)
        heading=QLabel(self.t("app.title")); heading.setFont(QFont("Segoe UI",18,QFont.Weight.Bold)); layout.addWidget(heading)
        sub=QLabel("Карина × ChatGPT  ·  local-first mathematics voice studio"); sub.setStyleSheet("color:#76657f"); layout.addWidget(sub)
        bar=QHBoxLayout(); self.project_label=QLabel(self.t("studio.no_project")); bar.addWidget(self.project_label,1)
        bar.addWidget(self._button("project.open",self.open_project)); bar.addWidget(self._button("project.new",self.new_project)); layout.addLayout(bar)
        choices=QHBoxLayout(); choices.addWidget(self._label("studio.engine"))
        self.engine_combo=QComboBox()
        for adapter in self.tts_registry.adapters(): self.engine_combo.addItem(adapter.name,adapter.id)
        engine_index=self.engine_combo.findData(self.settings.tts_engine)
        if engine_index>=0: self.engine_combo.setCurrentIndex(engine_index)
        elif self.engine_combo.findData("piper-cli")>=0: self.engine_combo.setCurrentIndex(self.engine_combo.findData("piper-cli"))
        choices.addWidget(self.engine_combo)
        choices.addWidget(self._label("studio.model")); self.model_combo=QComboBox(); choices.addWidget(self.model_combo,1)
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        choices.addWidget(self._button("common.browse",self.choose_model_file)); layout.addLayout(choices)
        split=QSplitter(Qt.Orientation.Horizontal)
        source_box=QGroupBox(self.t("studio.source")); sb=QVBoxLayout(source_box); self.source_edit=QPlainTextEdit(); self.source_edit.setPlaceholderText("2x^2=9 => x=1,5"); sb.addWidget(self.source_edit)
        norm_box=QGroupBox(self.t("studio.normalized")); nb=QVBoxLayout(norm_box); self.normalized_edit=QPlainTextEdit(); self.normalized_edit.setPlaceholderText("Два икс в квадрате равно девяти…"); nb.addWidget(self.normalized_edit)
        split.addWidget(source_box); split.addWidget(norm_box); split.setSizes([1,1]); layout.addWidget(split,1)
        knobs=QHBoxLayout(); knobs.addWidget(self._label("studio.text_language"))
        self.text_language_combo=QComboBox(); self.text_language_combo.addItem("Русский (ru-RU)" if self.language=="ru" else "Russian (ru-RU)","ru"); self.text_language_combo.addItem("Английский (UK, en-GB)" if self.language=="ru" else "English (UK, en-GB)","en-GB"); knobs.addWidget(self.text_language_combo)
        self.text_language_combo.setCurrentIndex(max(0,self.text_language_combo.findData(self.settings.tts_text_language)))
        knobs.addWidget(self._label("Speed" if self.language!="ru" else "Скорость"))
        self.speed_spin=QDoubleSpinBox(); self.speed_spin.setRange(.5,2); self.speed_spin.setSingleStep(.05); self.speed_spin.setValue(self.settings.speech_rate); self.speed_spin.setSuffix("×"); knobs.addWidget(self.speed_spin)
        knobs.addWidget(self._label("Pitch (post-processing)" if self.language!="ru" else "Pitch после синтеза"))
        self.pitch_spin=QDoubleSpinBox(); self.pitch_spin.setRange(-8,8); self.pitch_spin.setSingleStep(.5); self.pitch_spin.setValue(self.settings.pitch_semitones); self.pitch_spin.setSuffix(" st"); knobs.addWidget(self.pitch_spin); knobs.addStretch(1)
        layout.addLayout(knobs)
        buttons=QHBoxLayout(); buttons.addWidget(self._button("studio.normalize",self.normalize_text)); buttons.addWidget(self._button("studio.save",self.save_current_scene)); buttons.addWidget(self._button("studio.synthesize",self.synthesize_current)); buttons.addWidget(self._button("studio.preview",self.preview_current)); layout.addLayout(buttons)
        self.studio_progress=QProgressBar(); self.studio_progress.setRange(0,0); self.studio_progress.hide(); layout.addWidget(self.studio_progress)
        self.studio_hint=QLabel("Local processing: text and audio stay on this computer unless you explicitly use the online voice catalogue."); self.studio_hint.setWordWrap(True); self.studio_hint.setStyleSheet("color:#76657f"); layout.addWidget(self.studio_hint)
        return page

    def _build_projects(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("project.scenes")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        row=QHBoxLayout(); row.addWidget(self._button("project.new",self.new_project)); row.addWidget(self._button("project.open",self.open_project)); row.addWidget(self._button("project.save",self.save_project)); l.addLayout(row)
        self.scene_list=QListWidget(); self.scene_list.currentRowChanged.connect(self._on_scene_selected); self.scene_list.itemDoubleClicked.connect(self._rename_scene); l.addWidget(self.scene_list,1)
        row=QHBoxLayout(); row.addWidget(self._button("project.add",self.add_scene)); row.addWidget(self._button("project.duplicate",self.duplicate_scene)); row.addWidget(self._button("project.delete",self.delete_scene)); row.addWidget(self._button("project.up",lambda:self.move_scene(-1))); row.addWidget(self._button("project.down",lambda:self.move_scene(1))); l.addLayout(row)
        row=QHBoxLayout(); row.addWidget(self._button("project.batch",self.batch_synthesize)); row.addWidget(self._button("project.assemble",self.assemble_project)); l.addLayout(row)
        self.project_info=QLabel(self.t("project.empty")); self.project_info.setWordWrap(True); l.addWidget(self.project_info)
        return p

    def _build_models(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("nav.models")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        note=QLabel(self.t("models.note")); note.setWordWrap(True); l.addWidget(note)
        row=QHBoxLayout(); self.catalog_language=QComboBox(); self.catalog_language.addItem("Все языки" if self.language=="ru" else "All languages",""); self.catalog_language.addItem("Русский (ru_RU)","ru"); self.catalog_language.addItem("Английский (UK)" if self.language=="ru" else "English (UK)","en-GB"); row.addWidget(self._label("models.language")); row.addWidget(self.catalog_language)
        self.catalog_query=QLineEdit(); self.catalog_query.setPlaceholderText(self.t("models.query")); row.addWidget(self.catalog_query,1); row.addWidget(self._button("models.search",self.search_models)); l.addLayout(row)
        self.catalog_table=QTableWidget(0,5); self.catalog_table.setHorizontalHeaderLabels(["Модель","Язык","Качество","Размер","Лицензия"] if self.language=="ru" else ["Model","Language","Quality","Size","Licence"]); self.catalog_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.catalog_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.catalog_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.catalog_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch); self.catalog_table.cellDoubleClicked.connect(self.open_selected_model_source); l.addWidget(self.catalog_table,1)
        row=QHBoxLayout(); row.addWidget(self._button("models.refresh",self.search_models)); self.model_download_button=self._button("models.download",self.download_selected_model); self.model_download_button.setEnabled(False); row.addWidget(self.model_download_button); self.catalog_progress=QProgressBar(); self.catalog_progress.setRange(0,0); self.catalog_progress.hide(); row.addWidget(self.catalog_progress,1); l.addLayout(row)
        self.catalog_table.itemSelectionChanged.connect(self.update_selected_model_action)
        return p

    def _build_media(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("nav.media")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        row=QHBoxLayout(); self.media_root=QLineEdit(); self.media_root.setPlaceholderText(str(Path.home()/"Music")); row.addWidget(self.media_root,1); row.addWidget(self._button("media.choose",self.choose_media_folder)); row.addWidget(self._button("media.scan",self.scan_media)); l.addLayout(row)
        row=QHBoxLayout(); self.media_query=QLineEdit(); self.media_query.setPlaceholderText(self.t("media.query")); self.media_query.textChanged.connect(self.filter_media); row.addWidget(self.media_query,1); row.addWidget(self._button("media.play",self.play_media)); row.addWidget(self._button("media.rename",self.rename_media)); row.addWidget(self._button("media.move",self.move_media)); row.addWidget(self._button("media.delete",self.delete_media)); row.addWidget(self._button("media.add_project",self.add_media_to_project)); l.addLayout(row)
        self.media_table=QTableWidget(0,5); self.media_table.setHorizontalHeaderLabels(["Имя","Длительность","Частота","Каналы","Размер"] if self.language=="ru" else ["Name","Duration","Sample rate","Channels","Size"]); self.media_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.media_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.media_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.media_table.cellDoubleClicked.connect(lambda *_:self.play_media()); l.addWidget(self.media_table,1)
        return p

    def _build_graphs(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("nav.graphs")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        form=QFormLayout(); self.graph_functions=QPlainTextEdit("y=x^2\ny=sin(x)"); self.graph_functions.setMaximumHeight(100); form.addRow(self._label("graphs.expression"),self.graph_functions)
        axes=QHBoxLayout(); self.axis_spins={}
        for key,val in (("graphs.xmin",-10),("graphs.xmax",10),("graphs.ymin",-10),("graphs.ymax",10)):
            box=QDoubleSpinBox(); box.setRange(-1e6,1e6); box.setDecimals(2); box.setValue(val); self.axis_spins[key]=box; axes.addWidget(self._label(key)); axes.addWidget(box)
        l.addLayout(form); l.addLayout(axes)
        row=QHBoxLayout(); row.addWidget(self._button("graphs.render",self.render_graph)); row.addWidget(self._button("graphs.csv",self.export_graph_csv)); l.addLayout(row)
        self.graph_result=QLabel("PNG / SVG / PDF export · safe mathematical parser (no eval)"); self.graph_result.setWordWrap(True); l.addWidget(self.graph_result); l.addStretch(1)
        return p

    def _build_analyzer(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("nav.analyzer")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        row=QHBoxLayout(); self.analyzer_path=QLineEdit(); row.addWidget(self.analyzer_path,1); row.addWidget(self._button("audio.open",self.open_audio_file)); row.addWidget(self._button("audio.export",self.export_audio_csv)); row.addWidget(self._button("audio.save_image",self.save_analysis_image)); l.addLayout(row)
        self.analyzer_info=QLabel("Откройте PCM WAV, чтобы посмотреть осциллограмму, спектр, длительность, пик и RMS." if self.language=="ru" else "Open a PCM WAV file to view its waveform, spectrum, duration, peak and RMS."); self.analyzer_info.setWordWrap(True); l.addWidget(self.analyzer_info)
        self.analyzer_view=QLabel(); self.analyzer_view.setAlignment(Qt.AlignmentFlag.AlignCenter); self.analyzer_view.setMinimumHeight(360); self.analyzer_view.setStyleSheet("background:white; border:1px solid #e5d8e9; border-radius:10px"); l.addWidget(self.analyzer_view,1)
        row=QHBoxLayout(); self.analyzer_mode=QComboBox(); self.analyzer_mode.addItem(self.t("audio.waveform"),"waveform"); self.analyzer_mode.addItem(self.t("audio.spectrum"),"spectrum"); self.analyzer_mode.addItem(self.t("audio.spectrogram"),"spectrogram"); self.analyzer_mode.currentIndexChanged.connect(self.refresh_audio_chart); row.addWidget(self.analyzer_mode); row.addStretch(1); l.addLayout(row)
        return p

    def _build_vocal(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel("Vocal α · 0.0.0.1"); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        notice=QLabel(self.t("vocal.notice")); notice.setStyleSheet("font-weight:600; color:#814f8e"); l.addWidget(notice)
        warning=QLabel(self.t("vocal.warning")); warning.setWordWrap(True); l.addWidget(warning)
        row=QHBoxLayout(); row.addWidget(self._label("vocal.bpm")); self.vocal_bpm=QSpinBox(); self.vocal_bpm.setRange(30,240); self.vocal_bpm.setValue(100); row.addWidget(self.vocal_bpm); row.addWidget(self._label("vocal.syllable")); self.vocal_syllable=QLineEdit("la"); self.vocal_syllable.setMaxLength(30); row.addWidget(self.vocal_syllable,1); l.addLayout(row)
        self.piano=QTableWidget(36,16); self.piano.setVerticalHeaderLabels([self._midi_label(n) for n in range(83,47,-1)]); self.piano.setHorizontalHeaderLabels([str(n+1) for n in range(16)]); self.piano.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.piano.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents); self.piano.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.piano.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems); self.piano.cellClicked.connect(self._piano_cell_clicked); l.addWidget(self.piano,1)
        row=QHBoxLayout(); row.addWidget(self._button("vocal.add",self.add_vocal_note)); row.addWidget(self._button("vocal.remove",self.remove_vocal_note)); row.addWidget(self._button("vocal.play",self.render_vocal)); row.addWidget(self._button("vocal.save",self.save_vocal)); row.addWidget(self._button("vocal.open",self.open_vocal)); l.addLayout(row)
        self.vocal_project=VocalProject(); self._refresh_piano(); return p

    def _build_pronunciation(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("nav.pronunciation")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        self.dict_table=QTableWidget(0,6); self.dict_table.setHorizontalHeaderLabels(["Исходный текст","Произношение","Язык","Контекст","Приоритет","Включено"] if self.language=="ru" else ["Source","Replacement","Language","Context","Priority","Enabled"]); self.dict_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.dict_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch); self.dict_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); l.addWidget(self.dict_table,1)
        row=QHBoxLayout(); row.addWidget(self._button("dict.add",self.add_dictionary_rule)); row.addWidget(self._button("dict.edit",self.edit_dictionary_rule)); row.addWidget(self._button("dict.remove",self.remove_dictionary_rule)); row.addWidget(self._button("dict.import",self.import_dictionary)); row.addWidget(self._button("dict.export",self.export_dictionary)); row.addWidget(self._button("dict.apply",self.save_dictionary)); l.addLayout(row)
        return p

    def _build_settings(self):
        p=QWidget(); l=QVBoxLayout(p); title=QLabel(self.t("settings.help")); title.setFont(QFont("Segoe UI",16,QFont.Weight.Bold)); l.addWidget(title)
        form=QFormLayout(); self.language_combo=QComboBox()
        for code,label in SUPPORTED_LANGUAGES.items(): self.language_combo.addItem(label,code)
        self.language_combo.setCurrentIndex(max(0,self.language_combo.findData(self.language))); form.addRow(self._label("settings.language"),self.language_combo)
        self.piper_path=QLineEdit(self.settings.piper_executable); piper_row=QHBoxLayout(); piper_row.addWidget(self.piper_path,1); piper_row.addWidget(self._button("common.browse",self.choose_piper)); form.addRow(self._label("settings.piper"),piper_row)
        self.model_dir_edit=QLineEdit(self.settings.model_directory or str(default_model_dir())); model_row=QHBoxLayout(); model_row.addWidget(self.model_dir_edit,1); model_row.addWidget(self._button("common.browse",self.choose_model_directory)); form.addRow(self._label("settings.model_dir"),model_row)
        self.output_dir_edit=QLineEdit(self.settings.output_directory); output_row=QHBoxLayout(); output_row.addWidget(self.output_dir_edit,1); output_row.addWidget(self._button("common.browse",self.choose_output_directory)); form.addRow(self._label("settings.output_dir"),output_row)
        l.addLayout(form); row=QHBoxLayout(); row.addWidget(self._button("settings.save",self.save_settings)); row.addWidget(self._button("settings.pauses",self.configure_pauses)); l.addLayout(row)
        box=QGroupBox(self.t("help.title")); bl=QVBoxLayout(box)
        if self.language=="ru":
            help_copy="• MathText преобразует распространённую школьную запись и показывает неоднозначности.\n• Piper — внешний локальный движок; нужны исполняемый файл, модель .onnx и её .onnx.json.\n• Сцены хранятся как UTF-8-текст, JSON-метаданные и аудиофайлы.\n• Парсер графиков использует список разрешённых математических операций и не исполняет Python-код.\n• Vocal α создаёт тональные превью, а не реалистический вокал."
        else:
            help_copy="• MathText converts common school notation and surfaces ambiguities.\n• Piper is an external local engine; an executable, .onnx model and matching .onnx.json are required.\n• Scenes are stored as UTF-8 text, JSON metadata and audio files.\n• The graph parser uses an allow-list of mathematical operations and does not execute Python code.\n• Vocal α renders tone previews, not realistic singing."
        help_text=QLabel(help_copy); help_text.setWordWrap(True); bl.addWidget(help_text)
        row=QHBoxLayout(); row.addWidget(self._button("help.copy_error",self.copy_error_description)); row.addWidget(self._button("help.copy_info",self.copy_diagnostics)); row.addWidget(self._button("help.open_log",self.open_logs)); bl.addLayout(row); l.addWidget(box)
        l.addStretch(1); return p

    # General task lifecycle
    def cancel_active_task(self):
        if self._active_worker is None:
            return
        self._active_worker.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Отмена…" if self.language=="ru" else "Cancelling…")
        self.statusBar().showMessage("Cancellation requested; a running external process may take a moment to stop.",5000)

    def _autosave(self):
        if self._active_worker is not None: return
        try:
            if self.project:
                self._save_editor_to_scene(); self.project.save()
            self.settings.selected_model=self.model_combo.currentData() or ""
            self.settings.tts_text_language=self.text_language_combo.currentData() or "ru"
            self.settings.speech_rate=self.speed_spin.value(); self.settings.pitch_semitones=self.pitch_spin.value()
            self.settings.tts_engine=self.engine_combo.currentData() or "piper-cli"
            if hasattr(self,"piper_path"): self.settings.piper_executable=self.piper_path.text().strip() or "piper"
            if hasattr(self,"model_dir_edit"): self.settings.model_directory=self.model_dir_edit.text().strip()
            if hasattr(self,"output_dir_edit"): self.settings.output_directory=self.output_dir_edit.text().strip()
            self.settings.save()
        except Exception:
            log.exception("Autosave failed")

    def _run_async(self,fn,on_success:Callable,progress_widget:QProgressBar|None=None):
        if self._active_worker is not None:
            self.statusBar().showMessage("An operation is already running; cancel or wait for it to finish.",5000); return None
        worker=Worker(fn); self._workers.add(worker); self._active_worker=worker
        self.pages.setEnabled(False); self.nav.setEnabled(False)
        if hasattr(self,"cancel_button"):
            self.cancel_button.setEnabled(True); self.cancel_button.setText("Отменить" if self.language=="ru" else "Cancel"); self.cancel_button.show()
        if progress_widget:
            progress_widget.setRange(0,0); progress_widget.show()
        def update_progress(msg):
            match=re.match(r"__GOMD_DOWNLOAD__:(\d+):(\d+):(.*)",msg)
            if progress_widget and match:
                done,total=int(match.group(1)),int(match.group(2))
                if total>0:
                    progress_widget.setRange(0,100); progress_widget.setValue(min(100,int(done*100/total)))
                else: progress_widget.setRange(0,0)
                msg=f"{match.group(3)}: {done} / {total if total else '?'} bytes"
            self.statusBar().showMessage(msg,8000)
        worker.signals.progress.connect(update_progress)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(self._show_worker_error)
        def finished():
            self._workers.discard(worker)
            if self._active_worker is worker: self._active_worker=None
            if hasattr(self,"cancel_button"):
                self.cancel_button.hide(); self.cancel_button.setEnabled(True); self.cancel_button.setText("Отменить" if self.language=="ru" else "Cancel")
            if progress_widget: progress_widget.hide()
            self.pages.setEnabled(True); self.nav.setEnabled(True)
            self.statusBar().showMessage(self.t("common.ready"),4000)
        worker.signals.finished.connect(finished); self.pool.start(worker); return worker
    def _show_worker_error(self,message,details):
        self.last_error_description=message
        log.error("Background task failed: %s\n%s",message,details)
        box=QMessageBox(self); box.setIcon(QMessageBox.Icon.Warning); box.setWindowTitle(self.t("common.error")); box.setText(self.t("common.failed",error=message)); box.setDetailedText(details); box.exec()

    # Studio and project integration
    def _current_adapter(self):
        engine_id=self.engine_combo.currentData() if hasattr(self,"engine_combo") else "piper-cli"
        adapter=self.tts_registry.get(engine_id or "piper-cli")
        if isinstance(adapter,PiperCLIAdapter) and hasattr(self,"piper_path"):
            adapter.executable=self.piper_path.text().strip() or self.settings.piper_executable or "piper"
        return adapter
    def on_engine_changed(self,*args):
        self.refresh_installed_models()
    def refresh_installed_models(self):
        previous=self.model_combo.currentData() or self.settings.selected_model
        self.model_combo.clear()
        configured_dir=self.model_dir_edit.text().strip() if hasattr(self,"model_dir_edit") else self.settings.model_directory
        model_dir=Path(configured_dir).expanduser() if configured_dir else default_model_dir()
        try: adapter=self._current_adapter(); models=adapter.discover_models(model_dir)
        except Exception: log.exception("Could not list models for selected engine"); models=[]
        for model in models: self.model_combo.addItem(Path(model).stem,str(Path(model).resolve()))
        # A previously selected external model remains selectable even outside the default model folder.
        if previous and Path(previous).is_file() and self.model_combo.findData(str(Path(previous).resolve()))<0:
            valid,reason=adapter.validate_model(Path(previous))
            if valid: self.model_combo.addItem(Path(previous).stem,str(Path(previous).resolve()))
        if previous:
            idx=self.model_combo.findData(str(Path(previous).resolve())) if Path(previous).exists() else self.model_combo.findData(previous)
            if idx>=0: self.model_combo.setCurrentIndex(idx)
        if not self.model_combo.count(): self.model_combo.addItem(self.t("common.no_model"),"")
    def choose_model_file(self):
        adapter=self._current_adapter()
        if isinstance(adapter,PiperCLIAdapter):
            path,_=QFileDialog.getOpenFileName(self,self.t("studio.model"),str(default_model_dir()),"Piper ONNX models (*.onnx)")
        else:
            path,_=QFileDialog.getOpenFileName(self,self.t("studio.model"),str(Path.home()),"Model files (*.*)")
        if not path: return
        valid,reason=adapter.validate_model(Path(path))
        if not valid: QMessageBox.warning(self,self.t("common.warning"),reason); return
        idx=self.model_combo.findData(str(Path(path).resolve()))
        if idx<0: self.model_combo.addItem(Path(path).stem,str(Path(path).resolve())); idx=self.model_combo.count()-1
        self.model_combo.setCurrentIndex(idx)
    def normalize_text(self):
        result=MathTextEngine().normalize(self.source_edit.toPlainText())
        transformed=self.dictionary.apply(result.text,language=self.text_language_combo.currentData() or "ru",engine_id=self.engine_combo.currentData())
        self.normalized_edit.setPlainText(transformed)
        if result.warnings:
            QMessageBox.information(self,self.t("common.warning"),"\n".join(result.warnings[:10]))
        self.statusBar().showMessage("Normalized" if self.language!="ru" else "Нормализация завершена",4000)
    def _save_editor_to_scene(self):
        if self.current_scene and self.project:
            self.current_scene.text=self.source_edit.toPlainText(); self.current_scene.normalized_text=self.normalized_edit.toPlainText()
            self.current_scene.engine_id=self.engine_combo.currentData() or "piper-cli"
            self.current_scene.model_path=self.model_combo.currentData() or ""
            self.current_scene.settings={"speed":self.speed_spin.value(),"pitch":self.pitch_spin.value(),"text_language":self.text_language_combo.currentData() or "ru"}
            self.project.save_scene(self.current_scene); self.project.save()
    def save_current_scene(self):
        if not self.project or not self.current_scene:
            QMessageBox.information(self,self.t("common.success"),self.t("studio.no_project")); return
        self._save_editor_to_scene(); self.statusBar().showMessage(self.t("common.saved"),3000)
    def synthesize_current(self):
        text=self.normalized_edit.toPlainText().strip()
        if not text: QMessageBox.warning(self,self.t("common.warning"),"Normalize or enter the speech-ready text first."); return
        model_value=self.model_combo.currentData()
        if not model_value:
            self.choose_model_file(); model_value=self.model_combo.currentData()
        if not model_value: return
        model=Path(model_value)
        adapter=self._current_adapter()
        valid,reason=adapter.validate_model(model)
        if not valid: QMessageBox.warning(self,self.t("common.warning"),reason); return
        if not adapter.is_available(): QMessageBox.warning(self,self.t("common.warning"),f"{adapter.name} is not available. Check its installation/settings."); return
        self._save_editor_to_scene()
        if self.project and self.current_scene:
            output=self.project.scene_dir(self.current_scene)/"audio.wav"
            if output.exists() and QMessageBox.question(self,self.t("common.warning"),"Replace the current scene audio?")!=QMessageBox.StandardButton.Yes: return
        else:
            default=Path(self.settings.output_directory).expanduser() if self.settings.output_directory else Path.home()/"Music"
            output_str,_=QFileDialog.getSaveFileName(self,"Export synthesized WAV",str(default/"speech.wav"),"WAV audio (*.wav)")
            if not output_str: return
            output=Path(output_str)
            if output.suffix.lower()!=".wav": output=output.with_suffix(".wav")
            if output.exists() and QMessageBox.question(self,self.t("common.warning"),"Replace the selected output file?")!=QMessageBox.StandardButton.Yes: return
        overwrite_allowed=output.exists()
        request=TTSRequest(text=text,output_path=output,model_path=model,speed=self.speed_spin.value())
        pitch_semitones=self.pitch_spin.value()
        pause_settings=PauseSettings(self.settings.comma_pause_ms,self.settings.period_pause_ms,self.settings.semicolon_pause_ms,
                                     self.settings.colon_pause_ms,self.settings.ellipsis_pause_ms,self.settings.question_pause_ms,
                                     self.settings.exclamation_pause_ms,self.settings.paragraph_pause_ms)
        self._set_busy(True); self.pages.setEnabled(False); self.nav.setEnabled(False)
        def task(cancel,progress):
            # Preserve an existing scene audio file until the new result validates.
            temp=output.with_name(output.stem+".gomd_tmp.wav")
            if temp.exists(): temp.unlink()
            local_request=TTSRequest(text=request.text,output_path=temp,model_path=request.model_path,speed=request.speed)
            try:
                synthesize_with_pauses(adapter,local_request,pause_settings,cancel_event=cancel,progress=progress)
                if abs(pitch_semitones)>0.001:
                    from ..audio.processor import AudioProcessor
                    pitched_path=temp.with_name(temp.stem+"_pitched.wav")
                    pitched_path.unlink(missing_ok=True)
                    AudioProcessor().change_pitch(temp,pitched_path,pitch_semitones)
                    pitched_path.replace(temp)
                inspect_wav(temp,False)
                if output.exists() and not overwrite_allowed:
                    raise FileExistsError(f"Output appeared while synthesis was running; refusing to overwrite: {output}")
                temp.replace(output)
                return str(output)
            finally: temp.unlink(missing_ok=True); temp.with_name(temp.stem+"_pitched.wav").unlink(missing_ok=True)
        def done(path):
            self._set_busy(False); self.studio_hint.setText(f"WAV created: {path}")
            if self.project and self.current_scene:
                self.current_scene.audio_path=str(Path(path).resolve()); self.current_scene.status="synthesized"; self.current_scene.model_path=str(model.resolve())
                self.project.save_scene(self.current_scene); self.project.save(); self._refresh_scenes()
            self.preview_path=Path(path); QMessageBox.information(self,self.t("common.success"),f"WAV created and verified:\n{path}")
        def error(message,details): self._set_busy(False); self._show_worker_error(message,details)
        worker=Worker(task); self._workers.add(worker); self._active_worker=worker; self.studio_progress.show(); self.cancel_button.setEnabled(True); self.cancel_button.show()
        worker.signals.progress.connect(lambda m:self.statusBar().showMessage(m,7000)); worker.signals.succeeded.connect(done); worker.signals.failed.connect(error)
        worker.signals.finished.connect(lambda:(self._workers.discard(worker),setattr(self,"_active_worker",None),self.studio_progress.hide(),self.cancel_button.hide(),self.cancel_button.setEnabled(True),self.cancel_button.setText("Отменить" if self.language=="ru" else "Cancel"),self.pages.setEnabled(True),self.nav.setEnabled(True)))
        self.pool.start(worker)
    def _set_busy(self,value):
        for widget in (self.source_edit,self.normalized_edit): widget.setReadOnly(bool(value))
    def preview_current(self):
        path=None
        if self.current_scene and self.current_scene.audio_path and Path(self.current_scene.audio_path).is_file(): path=Path(self.current_scene.audio_path)
        elif hasattr(self,"preview_path") and self.preview_path.is_file(): path=self.preview_path
        if not path:
            QMessageBox.information(self,self.t("common.warning"),"No generated or selected WAV file is available yet."); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def new_project(self):
        name,ok=QInputDialog.getText(self,self.t("project.new"),self.t("project.name"),text=("Урок математики" if self.language=="ru" else "Math lesson"))
        if not ok or not name.strip(): return
        root=QFileDialog.getExistingDirectory(self,"Choose parent folder for the project",str(Path.home()/"Documents"))
        if not root: return
        import re
        safe_name=re.sub(r'[<>:"/\\|?*\x00-\x1f]+',"_",name.strip()).strip(" .")[:80]
        if not safe_name or safe_name in {".",".."}:
            QMessageBox.warning(self,self.t("common.warning"),"Enter a valid project name without path separators."); return
        root_path=Path(root).expanduser().resolve(); target=(root_path/safe_name).resolve()
        if target.parent!=root_path:
            QMessageBox.warning(self,self.t("common.warning"),"The project path must remain inside the selected parent folder."); return
        try:
            self.project=Project.create(target,safe_name); self.current_scene=None; self._refresh_scenes()
            if self.project.scenes: self._load_scene(self.project.scenes[0])
            self.project_label.setText(f"{self.project.name} · {self.project.root}"); self.nav.setCurrentRow(1)
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def open_project(self):
        root=QFileDialog.getExistingDirectory(self,self.t("project.open"),str(Path.home()/"Documents"))
        if not root: return
        try:
            candidate=Project.open(Path(root))
            self.project=candidate; self.current_scene=None; self._refresh_scenes()
            if candidate.scenes: self._load_scene(candidate.scenes[0])
            self.project_label.setText(f"{candidate.name} · {candidate.root}"); self.nav.setCurrentRow(1)
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),f"Could not open project: {exc}")
    def _refresh_scenes(self):
        self.scene_list.blockSignals(True); self.scene_list.clear()
        if self.project:
            for scene in self.project.scenes:
                suffix=" ✓" if scene.status=="synthesized" and scene.audio_path and Path(scene.audio_path).is_file() else ""
                self.scene_list.addItem(scene.name+suffix)
            if self.current_scene:
                idx=next((i for i,s in enumerate(self.project.scenes) if s.id==self.current_scene.id),-1)
                if idx>=0: self.scene_list.setCurrentRow(idx)
            self.project_info.setText(f"{self.project.name}\n{self.project.root}\n{len(self.project.scenes)} scene(s)")
        else: self.project_info.setText(self.t("project.empty"))
        self.scene_list.blockSignals(False)
    def _on_scene_selected(self,index):
        if not self.project or index<0 or index>=len(self.project.scenes): return
        scene=self.project.scenes[index]
        if self.current_scene and self.current_scene.id!=scene.id: self._save_editor_to_scene()
        self._load_scene(scene)
    def _load_scene(self,scene):
        self.current_scene=scene; self.source_edit.setPlainText(scene.text); self.normalized_edit.setPlainText(scene.normalized_text)
        idx=self.model_combo.findData(scene.model_path)
        if idx>=0: self.model_combo.setCurrentIndex(idx)
        text_language=scene.settings.get("text_language", "ru") if scene.settings else "ru"
        lang_index=self.text_language_combo.findData(text_language)
        if lang_index>=0: self.text_language_combo.setCurrentIndex(lang_index)
        speed=scene.settings.get("speed") if scene.settings else None
        pitch=scene.settings.get("pitch") if scene.settings else None
        if speed is not None: self.speed_spin.setValue(float(speed))
        if pitch is not None: self.pitch_spin.setValue(float(pitch))
        self.project_label.setText(f"{self.project.name} · {scene.name}" if self.project else self.t("studio.no_project"))
    def save_project(self):
        if not self.project: return
        self._save_editor_to_scene(); self.project.save(); self.statusBar().showMessage(self.t("common.saved"),3000)
    def add_scene(self):
        if not self.project: QMessageBox.information(self,self.t("common.warning"),self.t("project.empty")); return
        self._save_editor_to_scene(); scene=self.project.add_scene(); self.current_scene=scene; self._refresh_scenes(); self._load_scene(scene); self.scene_list.setCurrentRow(len(self.project.scenes)-1)
    def duplicate_scene(self):
        if not self.project or not self.current_scene: return
        self._save_editor_to_scene(); scene=self.project.add_scene(self.current_scene.name+" copy",self.current_scene); self._refresh_scenes(); self._load_scene(scene); self.scene_list.setCurrentRow(len(self.project.scenes)-1)
    def delete_scene(self):
        if not self.project or not self.current_scene: return
        if len(self.project.scenes)<=1: QMessageBox.warning(self,self.t("common.warning"),"A project must keep at least one scene."); return
        if QMessageBox.question(self,self.t("common.confirm_delete"),f"Delete scene {self.current_scene.name}?")!=QMessageBox.StandardButton.Yes: return
        old_index=self.project.scenes.index(self.current_scene)
        try: self.project.delete_scene(self.current_scene.id); self.current_scene=self.project.scenes[min(old_index,len(self.project.scenes)-1)]; self._refresh_scenes(); self._load_scene(self.current_scene)
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def move_scene(self,delta):
        if not self.project or not self.current_scene: return
        self._save_editor_to_scene(); self.project.move_scene(self.current_scene.id,delta); self._refresh_scenes()
    def _rename_scene(self,item):
        if not self.project: return
        row=self.scene_list.row(item); scene=self.project.scenes[row]
        name,ok=QInputDialog.getText(self,"Rename scene","Scene name",text=scene.name)
        if ok and name.strip(): scene.name=name.strip(); self.project.save(); self._refresh_scenes()

    def batch_synthesize(self):
        if not self.project:
            QMessageBox.information(self,self.t("common.warning"),self.t("project.empty")); return
        model_value=self.model_combo.currentData()
        if not model_value:
            self.choose_model_file(); model_value=self.model_combo.currentData()
        if not model_value: return
        existing=[str((self.project.scene_dir(s)/"audio.wav")) for s in self.project.scenes if (self.project.scene_dir(s)/"audio.wav").exists()]
        overwrite=False
        if existing:
            if QMessageBox.question(self,self.t("common.warning"),f"{len(existing)} scene audio file(s) already exist. Replace them after each new WAV is validated?")!=QMessageBox.StandardButton.Yes: return
            overwrite=True
        self._save_editor_to_scene()
        for scene in self.project.scenes:
            scene.settings.setdefault("text_language",self.text_language_combo.currentData() or "ru")
        model=Path(model_value); adapter=self._current_adapter()
        valid,reason=adapter.validate_model(model)
        if not valid: QMessageBox.warning(self,self.t("common.warning"),reason); return
        if not adapter.is_available(): QMessageBox.warning(self,self.t("common.warning"),f"{adapter.name} is not available."); return
        pauses=PauseSettings(self.settings.comma_pause_ms,self.settings.period_pause_ms,self.settings.semicolon_pause_ms,
            self.settings.colon_pause_ms,self.settings.ellipsis_pause_ms,self.settings.question_pause_ms,
            self.settings.exclamation_pause_ms,self.settings.paragraph_pause_ms)
        if self._active_worker is not None:
            QMessageBox.information(self,self.t("common.warning"),"Another background task is already running."); return
        self._set_busy(True); self.pages.setEnabled(False); self.nav.setEnabled(False)
        project=self.project; speed=self.speed_spin.value(); pitch_semitones=self.pitch_spin.value()
        text_language=self.text_language_combo.currentData() or "ru"; dictionary=self.dictionary
        def task(cancel,progress):
            return [str(x) for x in synthesize_project_scenes(project,adapter,model,speed,pauses,
                dictionary=dictionary,text_language=text_language,overwrite=overwrite,
                cancel_event=cancel,progress=progress,pitch_semitones=pitch_semitones)]
        worker=Worker(task); self._active_worker=worker; self._workers.add(worker); self.cancel_button.setEnabled(True); self.cancel_button.show(); self.studio_progress.show()
        worker.signals.progress.connect(lambda m:self.statusBar().showMessage(m,7000))
        worker.signals.succeeded.connect(lambda paths:(self._set_busy(False),self._refresh_scenes(),QMessageBox.information(self,self.t("common.success"),f"Synthesized {len(paths)} scene(s).")))
        worker.signals.failed.connect(lambda m,d:(self._set_busy(False),self._show_worker_error(m,d)))
        def finished():
            self._workers.discard(worker)
            if self._active_worker is worker: self._active_worker=None
            self.cancel_button.hide(); self.cancel_button.setEnabled(True); self.studio_progress.hide(); self.pages.setEnabled(True); self.nav.setEnabled(True)
        worker.signals.finished.connect(finished); self.pool.start(worker)

    def assemble_project(self):
        if not self.project:
            QMessageBox.information(self,self.t("common.warning"),self.t("project.empty")); return
        pause,ok=QInputDialog.getInt(self,self.t("project.assemble"),"Pause between scenes (ms)",self.settings.scene_pause_ms,0,10000,50)
        if not ok: return
        output=self.project.root/"exports"/"final.wav"
        overwrite=False
        if output.exists():
            if QMessageBox.question(self,self.t("common.warning"),f"Replace the existing final WAV?\n{output}")!=QMessageBox.StandardButton.Yes: return
            overwrite=True
        self._run_async(lambda cancel,progress:str(assemble_project_audio(self.project,output,pause_ms=pause,overwrite=overwrite)),
            lambda path:(setattr(self,"preview_path",Path(path)),QMessageBox.information(self,self.t("common.success"),f"Final WAV created:\n{path}"),QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path))))))

    # Online voice catalogue; requests happen only after the user explicitly clicks Search.
    def search_models(self):
        language=self.catalog_language.currentData() or ""; query=self.catalog_query.text()
        self._run_async(lambda cancel,progress: ModelCatalogClient().search(language,query,progress),self._show_catalog_models,self.catalog_progress)
    def _show_catalog_models(self,models):
        configured_dir=self.model_dir_edit.text().strip() or str(default_model_dir())
        directory=Path(configured_dir).expanduser()
        self.model_catalog=models; self.catalog_table.setRowCount(0)
        for model in models:
            safe_name="".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in model.name)
            candidate=(directory/(safe_name+".onnx")).resolve()
            cfg=candidate.with_name(candidate.name+".json")
            model.installed=candidate.is_file() and cfg.is_file()
            model.installed_path=str(candidate) if model.installed else ""
            row=self.catalog_table.rowCount(); self.catalog_table.insertRow(row)
            license_status=(self.t("models.installed")+" · "+("review licence" if self.language!="ru" else "проверьте лицензию")) if model.installed else ("Review model card" if model.license_url else "Unknown")
            vals=(model.name,model.language_code,model.quality,model.size_label,license_status)
            for col,val in enumerate(vals):
                item=QTableWidgetItem(str(val)); item.setData(Qt.ItemDataRole.UserRole,model.model_id); self.catalog_table.setItem(row,col,item)
        self.update_selected_model_action()
        self.statusBar().showMessage(f"{len(models)} models found" if self.language!="ru" else f"Найдено моделей: {len(models)}",6000)
    def update_selected_model_action(self):
        model=self._selected_catalog_model() if hasattr(self,"catalog_table") else None
        self.model_download_button.setEnabled(model is not None)
        if model and model.installed:
            self.model_download_button.setText("Выбрать установленную" if self.language=="ru" else "Select installed")
        else:
            self.model_download_button.setText(self.t("models.download"))
    def _selected_catalog_model(self):
        row=self.catalog_table.currentRow()
        return self.model_catalog[row] if 0<=row<len(self.model_catalog) else None
    def open_selected_model_source(self,*args):
        model=self._selected_catalog_model()
        if model: QDesktopServices.openUrl(QUrl(model.license_url or model.source_url))
    def download_selected_model(self):
        model=self._selected_catalog_model()
        if not model: QMessageBox.information(self,self.t("common.warning"),"Select a model row first."); return
        if model.installed and model.installed_path:
            piper_index=self.engine_combo.findData("piper-cli")
            if piper_index>=0: self.engine_combo.setCurrentIndex(piper_index)
            self.refresh_installed_models()
            idx=self.model_combo.findData(str(Path(model.installed_path).resolve()))
            if idx>=0: self.model_combo.setCurrentIndex(idx)
            QMessageBox.information(self,self.t("common.success"),("Голос уже установлен. Он выбран в студии; повторная загрузка не нужна." if self.language=="ru" else "This voice is already installed and selected in the studio; no download is needed."))
            return
        answer=QMessageBox.question(self,self.t("common.warning"),
            f"Download {model.name} ({model.size_label}) from Hugging Face?\n\nThe voice model is a separate third-party asset. Review its model card and licence before commercial use.\n\nSource: {model.source_url}")
        if answer!=QMessageBox.StandardButton.Yes: return
        directory=Path(self.model_dir_edit.text().strip() or str(default_model_dir()))
        client=ModelCatalogClient()
        self._run_async(lambda cancel,progress: str(client.download(model,directory,cancel_event=cancel,progress=lambda done,total,name:progress(f"__GOMD_DOWNLOAD__:{done}:{total or 0}:{name}"))),self._model_downloaded,self.catalog_progress)
    def _model_downloaded(self,path):
        piper_index=self.engine_combo.findData("piper-cli")
        if piper_index>=0: self.engine_combo.setCurrentIndex(piper_index)
        self.refresh_installed_models(); idx=self.model_combo.findData(str(Path(path).resolve()))
        if idx>=0: self.model_combo.setCurrentIndex(idx)
        QMessageBox.information(self,self.t("common.success"),f"Voice installed and configuration checked:\n{path}")

    # Media library and safe file operations.
    def choose_media_folder(self):
        folder=QFileDialog.getExistingDirectory(self,self.t("media.choose"),self.media_root.text() or str(Path.home()))
        if folder: self.media_root.setText(folder); self.scan_media()
    def scan_media(self):
        if not self.media_root.text().strip(): self.choose_media_folder(); return
        try: self.media_items=MediaLibrary().scan(Path(self.media_root.text()),recursive=True); self.filter_media()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def filter_media(self):
        q=self.media_query.text().casefold().strip() if hasattr(self,"media_query") else ""
        results=[item for item in self.media_items if not q or q in item.name.casefold() or q in str(item.path).casefold()]
        self.media_table.setRowCount(0)
        for media in results:
            row=self.media_table.rowCount(); self.media_table.insertRow(row)
            vals=(media.name,f"{media.duration_seconds:.2f} s" if media.duration_seconds is not None else media.status,
                  f"{media.sample_rate} Hz" if media.sample_rate else "—",str(media.channels or "—"),f"{media.size_bytes/1024:.1f} KiB")
            for col,val in enumerate(vals):
                cell=QTableWidgetItem(val); cell.setData(Qt.ItemDataRole.UserRole,str(media.path)); self.media_table.setItem(row,col,cell)
    def _selected_media_path(self):
        row=self.media_table.currentRow()
        return Path(self.media_table.item(row,0).data(Qt.ItemDataRole.UserRole)) if row>=0 and self.media_table.item(row,0) else None
    def play_media(self):
        path=self._selected_media_path()
        if path and path.is_file(): QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else: QMessageBox.information(self,self.t("common.warning"),"Select an existing WAV file.")
    def rename_media(self):
        path=self._selected_media_path()
        if not path: return
        name,ok=QInputDialog.getText(self,self.t("media.rename"),"Filename",text=path.name)
        if not ok: return
        try: MediaLibrary().rename(path,name); self.scan_media()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def move_media(self):
        path=self._selected_media_path()
        if not path: return
        folder=QFileDialog.getExistingDirectory(self,self.t("media.move"),str(path.parent))
        if not folder: return
        try: MediaLibrary().move(path,Path(folder)); self.scan_media()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def delete_media(self):
        path=self._selected_media_path()
        if not path: return
        if QMessageBox.question(self,self.t("common.confirm_delete"),f"Permanently delete this file?\n{path}")!=QMessageBox.StandardButton.Yes: return
        try: MediaLibrary().delete(path,confirmed=True); self.scan_media()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def add_media_to_project(self):
        path=self._selected_media_path()
        if not self.project: QMessageBox.information(self,self.t("common.warning"),self.t("project.empty")); return
        if not path: return
        try: self.project.add_media(path); QMessageBox.information(self,self.t("common.success"),"Copied into project media folder.")
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))

    # Mathematical graphing with a safe AST evaluator.
    def _graph_values(self):
        return [self.axis_spins[k].value() for k in ("graphs.xmin","graphs.xmax","graphs.ymin","graphs.ymax")]
    def render_graph(self):
        funcs=[line.strip() for line in self.graph_functions.toPlainText().splitlines() if line.strip()]
        if not funcs: QMessageBox.information(self,self.t("common.warning"),"Enter at least one function."); return
        path,_=QFileDialog.getSaveFileName(self,self.t("graphs.render"),str(Path.home()/"graph.png"),"PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path: return
        if Path(path).suffix.lower() not in (".png",".svg",".pdf"): path+=".png"
        if not self._confirm_overwrite(path): return
        try:
            renderer=GraphRenderer(); renderer.render(funcs,Path(path),*self._graph_values())
            self.graph_result.setText(f"Saved graph: {path}"); QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))
        except Exception as exc: QMessageBox.warning(self,self.t("graphs.error"),str(exc))
    def export_graph_csv(self):
        funcs=[line.strip() for line in self.graph_functions.toPlainText().splitlines() if line.strip()]
        if not funcs: return
        path,_=QFileDialog.getSaveFileName(self,self.t("graphs.csv"),str(Path.home()/"graph.csv"),"CSV (*.csv)")
        if not path: return
        xmin,xmax,_,_=self._graph_values()
        try: GraphRenderer().export_csv(funcs,Path(path),xmin,xmax); self.graph_result.setText(f"CSV saved: {path}")
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))

    # WAV diagnostics and signal visualization.
    def open_audio_file(self):
        path,_=QFileDialog.getOpenFileName(self,self.t("audio.open"),str(Path.home()),"WAV audio (*.wav)")
        if not path: return
        self.analyzer_path.setText(path); self.refresh_audio_chart()
    def refresh_audio_chart(self):
        source=Path(self.analyzer_path.text().strip()) if self.analyzer_path.text().strip() else None
        if not source or not source.is_file(): return
        try:
            info=inspect_wav(source,True)
            self.analyzer_info.setText(f"{source.name}\n{self.t('audio.duration')}: {info.duration_seconds:.2f} s · {self.t('audio.rate')}: {info.sample_rate} Hz · {self.t('audio.channels')}: {info.channels}\n{self.t('audio.peak')}: {info.peak:.4f} · {self.t('audio.rms')}: {info.rms:.4f}")
            import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
            fig,ax=plt.subplots(figsize=(10,4),dpi=110)
            mode=self.analyzer_mode.currentData()
            if mode=="spectrum":
                _,freqs,db=spectrum(source); ax.plot(freqs,db); ax.set_xlabel("Frequency (Hz)"); ax.set_ylabel("Relative magnitude (dB)"); ax.set_ylim(-100,3)
            elif mode=="spectrogram":
                _,frame_times,freqs,db=spectrogram(source); mesh=ax.pcolormesh(frame_times,freqs,db,shading="auto",vmin=-80,vmax=0,cmap="magma"); ax.set_xlabel("Time (s)"); ax.set_ylabel("Frequency (Hz)"); fig.colorbar(mesh,ax=ax,label="Relative magnitude (dB)")
            else:
                _,times,samples=load_audio(source); stride=max(1,len(samples)//100000); ax.plot(times[::stride],samples[::stride],linewidth=.45); ax.set_xlabel("Time (s)"); ax.set_ylabel("Amplitude"); ax.set_ylim(-1.05,1.05)
            ax.grid(True,alpha=.25); fig.tight_layout(); image_path=data_dir()/"cache"/"audio_analysis_preview.png"; image_path.parent.mkdir(parents=True,exist_ok=True); fig.savefig(image_path); plt.close(fig)
            from PySide6.QtGui import QPixmap
            pix=QPixmap(str(image_path)); self.analyzer_view.setPixmap(pix.scaled(self.analyzer_view.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        except Exception as exc: self.analyzer_info.setText(f"Could not analyze WAV: {exc}")
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"analyzer_path") and self.analyzer_path.text(): self.refresh_audio_chart()
    def save_analysis_image(self):
        source=Path(self.analyzer_path.text().strip()) if self.analyzer_path.text().strip() else None
        if not source or not source.is_file():
            QMessageBox.information(self,self.t("common.warning"),"Open a WAV file and render its analysis first."); return
        rendered=data_dir()/"cache"/"audio_analysis_preview.png"
        self.refresh_audio_chart()
        if not rendered.is_file(): return
        target,_=QFileDialog.getSaveFileName(self,self.t("audio.save_image"),str(Path.home()/"audio_analysis.png"),"PNG image (*.png)")
        if not target: return
        output=Path(target)
        if output.suffix.lower()!=".png": output=output.with_suffix(".png")
        if not self._confirm_overwrite(output): return
        try:
            output.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(rendered,output)
            QMessageBox.information(self,self.t("common.success"),f"Analysis image exported:\n{output}")
        except OSError as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def export_audio_csv(self):
        path=Path(self.analyzer_path.text().strip()) if self.analyzer_path.text().strip() else None
        if not path or not path.is_file(): self.open_audio_file(); path=Path(self.analyzer_path.text().strip()) if self.analyzer_path.text().strip() else None
        if not path or not path.is_file(): return
        output,_=QFileDialog.getSaveFileName(self,self.t("audio.export"),str(path.with_name(path.stem+"_waveform.csv")),"CSV (*.csv)")
        if not output or not self._confirm_overwrite(output): return
        try: export_waveform_csv(path,Path(output),stride=max(1,int(inspect_wav(path,False).frames/100000))); QMessageBox.information(self,self.t("common.success"),f"CSV exported:\n{output}")
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))

    # Vocal α: editable, saved note grid with an explicitly non-vocal tone preview.
    def _midi_label(self,midi):
        names=["C","C♯","D","D♯","E","F","F♯","G","G♯","A","A♯","B"]
        return f"{names[midi%12]}{midi//12-1}"
    def _refresh_piano(self):
        if not hasattr(self,"piano"): return
        self.piano.clearContents()
        self.piano.setVerticalHeaderLabels([self._midi_label(n) for n in range(83,47,-1)])
        for note in self.vocal_project.notes:
            col=int(note.start_beats); row=83-note.midi_note
            if 0<=row<36 and 0<=col<16:
                cell=QTableWidgetItem(note.syllable); cell.setBackground(Qt.GlobalColor.lightGray); cell.setToolTip(f"MIDI {note.midi_note}, {note.duration_beats:g} beat(s)"); self.piano.setItem(row,col,cell)
    def _piano_cell_clicked(self,row,col):
        self._selected_piano=(row,col)
    def add_vocal_note(self):
        cell=self.piano.currentIndex()
        if not cell.isValid(): QMessageBox.information(self,self.t("common.warning"),"Select a cell in the piano roll first."); return
        row,col=cell.row(),cell.column(); midi=83-row; syllable=self.vocal_syllable.text().strip() or "la"
        self.vocal_project.bpm=self.vocal_bpm.value()
        self.vocal_project.notes=[n for n in self.vocal_project.notes if not (int(n.start_beats)==col and n.midi_note==midi)]
        self.vocal_project.notes.append(Note(float(col),1.0,midi,syllable)); self._refresh_piano()
    def remove_vocal_note(self):
        cell=self.piano.currentIndex()
        if not cell.isValid(): return
        col,row=cell.column(),cell.row(); midi=83-row
        self.vocal_project.notes=[n for n in self.vocal_project.notes if not (int(n.start_beats)==col and n.midi_note==midi)]; self._refresh_piano()
    def render_vocal(self):
        self.vocal_project.bpm=self.vocal_bpm.value()
        path,_=QFileDialog.getSaveFileName(self,self.t("vocal.play"),str(Path.home()/"vocal_preview.wav"),"WAV audio (*.wav)")
        if not path or not self._confirm_overwrite(path): return
        try:
            result=render_preview_wav(self.vocal_project,Path(path)); self.preview_path=result; QDesktopServices.openUrl(QUrl.fromLocalFile(str(result)))
            QMessageBox.information(self,self.t("common.success"),"Tone preview created. This is not a singing voice.")
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def save_vocal(self):
        path,_=QFileDialog.getSaveFileName(self,self.t("vocal.save"),str(Path.home()/"vocal_project.json"),"GoMD Vocal project (*.json)")
        if not path or not self._confirm_overwrite(path): return
        try: self.vocal_project.bpm=self.vocal_bpm.value(); self.vocal_project.save(Path(path)); self.statusBar().showMessage(self.t("common.saved"),3000)
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def open_vocal(self):
        path,_=QFileDialog.getOpenFileName(self,self.t("vocal.open"),str(Path.home()),"GoMD Vocal project (*.json)")
        if not path: return
        try: self.vocal_project=VocalProject.load(Path(path)); self.vocal_bpm.setValue(self.vocal_project.bpm); self._refresh_piano()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))

    # Pronunciation dictionary management.
    def _populate_dictionary(self):
        if not hasattr(self,"dict_table"): return
        self.dict_table.setRowCount(0)
        for rule in self.dictionary.rules:
            row=self.dict_table.rowCount(); self.dict_table.insertRow(row)
            vals=(rule.source,rule.replacement,rule.language,rule.context,str(rule.priority),"yes" if rule.enabled else "no")
            for col,value in enumerate(vals): self.dict_table.setItem(row,col,QTableWidgetItem(value))
    def add_dictionary_rule(self):
        self._dictionary_rule_dialog(None)
    def edit_dictionary_rule(self):
        index=self.dict_table.currentRow()
        if not 0<=index<len(self.dictionary.rules):
            QMessageBox.information(self,self.t("common.warning"),"Select a pronunciation rule first."); return
        self._dictionary_rule_dialog(index)
    def remove_dictionary_rule(self):
        index=self.dict_table.currentRow()
        if not 0<=index<len(self.dictionary.rules):
            QMessageBox.information(self,self.t("common.warning"),"Select a pronunciation rule first."); return
        rule=self.dictionary.rules[index]
        if QMessageBox.question(self,self.t("common.confirm_delete"),f"Remove rule {rule.source!r}?")!=QMessageBox.StandardButton.Yes: return
        self.dictionary.rules.pop(index); self.save_dictionary()
    def _dictionary_rule_dialog(self,index):
        from PySide6.QtWidgets import QDialog
        existing=self.dictionary.rules[index] if index is not None else None
        dlg=QDialog(self); dlg.setWindowTitle(self.t("dict.edit") if existing else self.t("dict.add")); form=QFormLayout(dlg)
        source=QLineEdit(existing.source if existing else ""); replacement=QLineEdit(existing.replacement if existing else "")
        language=QComboBox(); language.addItem("*", "*"); language.addItem("ru", "ru"); language.addItem("en-GB", "en-GB")
        engine=QComboBox(); engine.addItem("* (all engines)" if self.language!="ru" else "* (все движки)","*")
        for adapter in self.tts_registry.adapters(): engine.addItem(adapter.name,adapter.id)
        if existing:
            language.setCurrentIndex(max(0,language.findData(existing.language))); engine.setCurrentIndex(max(0,engine.findData(existing.engine_id)))
        context=QLineEdit(existing.context if existing else ""); priority=QSpinBox(); priority.setRange(-10000,10000); priority.setValue(existing.priority if existing else 100)
        case_sensitive=QCheckBox(); case_sensitive.setChecked(existing.case_sensitive if existing else False)
        enabled=QCheckBox(); enabled.setChecked(existing.enabled if existing else True); note=QLineEdit(existing.note if existing else "")
        labels=("dict.source","dict.replacement","dict.language")
        form.addRow(self.t(labels[0]),source); form.addRow(self.t(labels[1]),replacement); form.addRow(self.t(labels[2]),language)
        form.addRow("TTS engine" if self.language!="ru" else "TTS-движок",engine)
        form.addRow("Context regex" if self.language!="ru" else "Регулярное выражение контекста",context)
        form.addRow(self.t("dict.priority"),priority); form.addRow("Case sensitive" if self.language!="ru" else "Учитывать регистр",case_sensitive)
        form.addRow("Enabled" if self.language!="ru" else "Правило включено",enabled); form.addRow("Note" if self.language!="ru" else "Примечание",note)
        buttons=QHBoxLayout(); save=QPushButton(self.t("common.ok")); cancel=QPushButton(self.t("common.cancel")); save.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject); buttons.addWidget(save); buttons.addWidget(cancel); form.addRow(buttons)
        if not dlg.exec(): return
        if not source.text().strip(): QMessageBox.warning(self,self.t("common.warning"),"Rule source cannot be empty."); return
        rule=PronunciationRule(source=source.text().strip(),replacement=replacement.text(),language=language.currentData(),
            context=context.text().strip(),case_sensitive=case_sensitive.isChecked(),priority=priority.value(),enabled=enabled.isChecked(),
            engine_id=engine.currentData(),note=note.text())
        try:
            if existing: self.dictionary.rules[index]=rule
            else: self.dictionary.add(rule)
            self.save_dictionary()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def import_dictionary(self):
        path,_=QFileDialog.getOpenFileName(self,self.t("dict.import"),str(Path.home()),"Dictionary files (*.json *.csv)")
        if not path: return
        try:
            imported=PronunciationDictionary.load_json(Path(path)) if path.lower().endswith(".json") else PronunciationDictionary.import_csv(Path(path))
            self.dictionary.rules.extend(imported.rules); self.save_dictionary()
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def export_dictionary(self):
        path,_=QFileDialog.getSaveFileName(self,self.t("dict.export"),str(Path.home()/"pronunciation.json"),"JSON (*.json);;CSV (*.csv)")
        if not path or not self._confirm_overwrite(path): return
        try:
            if Path(path).suffix.lower()==".csv": self.dictionary.export_csv(Path(path))
            else: self.dictionary.save_json(Path(path))
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def save_dictionary(self):
        try: self.dictionary.save_json(self.dictionary_path); self._populate_dictionary(); self.statusBar().showMessage(self.t("common.saved"),3000)
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))

    # Settings, diagnostics and lifecycle.
    def choose_piper(self):
        path,_=QFileDialog.getOpenFileName(self,self.t("settings.piper"),str(Path.home()),"Executables (*.exe);;All files (*.*)")
        if path: self.piper_path.setText(path)
    def choose_model_directory(self):
        path=QFileDialog.getExistingDirectory(self,self.t("settings.model_dir"),self.model_dir_edit.text())
        if path: self.model_dir_edit.setText(path)
    def choose_output_directory(self):
        path=QFileDialog.getExistingDirectory(self,self.t("settings.output_dir"),self.output_dir_edit.text() or str(Path.home()))
        if path: self.output_dir_edit.setText(path)
    def configure_pauses(self):
        from PySide6.QtWidgets import QDialog
        dlg=QDialog(self); dlg.setWindowTitle(self.t("settings.pauses")); form=QFormLayout(dlg); controls={}
        names=[("comma_pause_ms","Comma" if self.language!="ru" else "Запятая"),("period_pause_ms","Full stop" if self.language!="ru" else "Точка"),("semicolon_pause_ms","Semicolon" if self.language!="ru" else "Точка с запятой"),("colon_pause_ms","Colon" if self.language!="ru" else "Двоеточие"),("ellipsis_pause_ms","Ellipsis" if self.language!="ru" else "Многоточие"),("question_pause_ms","Question mark" if self.language!="ru" else "Вопросительный знак"),("exclamation_pause_ms","Exclamation mark" if self.language!="ru" else "Восклицательный знак"),("paragraph_pause_ms","Paragraph" if self.language!="ru" else "Абзац")]
        for name,label in names:
            spin=QSpinBox(); spin.setRange(0,5000); spin.setSingleStep(25); spin.setSuffix(" ms"); spin.setValue(int(getattr(self.settings,name))); controls[name]=spin; form.addRow(label,spin)
        buttons=QHBoxLayout(); ok=QPushButton(self.t("common.ok")); cancel=QPushButton(self.t("common.cancel")); ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject); buttons.addWidget(ok); buttons.addWidget(cancel); form.addRow(buttons)
        if dlg.exec():
            for name,spin in controls.items(): setattr(self.settings,name,spin.value())
            try:
                self.settings.save(); self.statusBar().showMessage(self.t("common.saved"),3000)
            except OSError as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def save_settings(self):
        new_lang=self.language_combo.currentData()
        self.settings.language=new_lang; self.settings.tts_text_language=self.text_language_combo.currentData() or "ru"; self.settings.tts_engine=self.engine_combo.currentData() or "piper-cli"; self.settings.piper_executable=self.piper_path.text().strip() or "piper"
        self.settings.model_directory=self.model_dir_edit.text().strip(); self.settings.output_directory=self.output_dir_edit.text().strip()
        self.settings.selected_model=self.model_combo.currentData() or ""; self.settings.speech_rate=self.speed_spin.value(); self.settings.pitch_semitones=self.pitch_spin.value()
        try:
            self.settings.save(); self.language=new_lang; self.refresh_installed_models()
            QMessageBox.information(self,self.t("common.success"),"Settings saved. Restart the app to relabel the entire interface after changing language.")
        except Exception as exc: QMessageBox.warning(self,self.t("common.error"),str(exc))
    def copy_error_description(self):
        text=self.last_error_description or ("Ошибок фоновых задач пока не зарегистрировано." if self.language=="ru" else "No background-task error has been recorded yet.")
        QApplication.clipboard().setText(text); self.statusBar().showMessage(self.t("common.copy"),2500)
    def copy_diagnostics(self):
        text=collect_diagnostics(self.piper_path.text(),self.model_combo.currentData() or "")
        QApplication.clipboard().setText(text); self.statusBar().showMessage(self.t("common.copy"),2500)
    def open_logs(self):
        folder=open_log_directory(); QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    def closeEvent(self,event):
        try:
            if hasattr(self,"_autosave_timer"): self._autosave_timer.stop()
            self._save_editor_to_scene()
            if self.project: self.project.save()
            self.settings.tts_engine=self.engine_combo.currentData() or "piper-cli"; self.settings.selected_model=self.model_combo.currentData() or ""; self.settings.tts_text_language=self.text_language_combo.currentData() or "ru"; self.settings.speech_rate=self.speed_spin.value(); self.settings.pitch_semitones=self.pitch_spin.value()
            self.settings.piper_executable=self.piper_path.text().strip() or "piper"; self.settings.model_directory=self.model_dir_edit.text().strip(); self.settings.output_directory=self.output_dir_edit.text().strip(); self.settings.save()
            if self._active_worker: self._active_worker.cancel_event.set()
        except Exception: log.exception("Error while closing application")
        event.accept()
