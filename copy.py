import configparser
import json
import os
import re
import subprocess
import sys
import tempfile

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

PAT_BYTES = re.compile(
    r"Transferred:\s*([\d\.]+\s*(?:[KMGT]?iB|B))\s*/\s*([\d\.]+\s*(?:[KMGT]?iB|B))",
    re.IGNORECASE,
)
PAT_FILES = re.compile(r"Transferred:\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
RCLONE_FLAGS = ["--progress"]

DEFAULT_COPY_SETTINGS = {
    "create_empty_src_dirs": True,
    "error_on_no_transfer": False,
    "fast_list": True,
    "dry_run": False,
    "checksum": False,
    "size_only": False,
    "ignore_existing": False,
    "update": False,
    "use_json_log": False,
    "stats": "1s",
    "transfers": "4",
    "checkers": "8",
    "retries": "5",
    "low_level_retries": "10",
    "multi_thread_streams": "4",
    "buffer_size": "",
    "tpslimit": "",
    "log_level": "NOTICE",
}

COPY_SETTING_HELP = {
    "create_empty_src_dirs": "Cria no destino as pastas vazias encontradas na origem. Isso preserva a estrutura completa do diretório mesmo quando algumas pastas ainda não têm arquivos.",
    "error_on_no_transfer": "Faz a operação retornar erro quando nenhum arquivo for transferido. É útil para detectar execuções que terminaram sem copiar nada, em vez de tratá-las como sucesso silencioso.",
    "fast_list": "Pede ao rclone para fazer listagens maiores com menos chamadas à API do remote. Normalmente acelera a varredura, mas pode usar mais memória em estruturas grandes.",
    "dry_run": "Simula toda a cópia sem gravar nada no destino. Serve para validar caminho, seleção e parâmetros antes de executar a transferência real.",
    "checksum": "Compara arquivos usando hash quando o backend suportar essa informação. É mais confiável para detectar diferenças, mas pode deixar a operação mais lenta.",
    "size_only": "Compara arquivos apenas pelo tamanho. É mais rápido, porém menos rigoroso do que checksum, porque ignora alterações em arquivos com o mesmo tamanho.",
    "ignore_existing": "Ignora no destino os arquivos que já existem. Use quando quiser copiar apenas o que ainda não foi enviado ou baixado.",
    "update": "Copia somente quando a origem for mais nova do que o destino. Ajuda a evitar sobrescritas desnecessárias em sincronizações incrementais.",
    "stats": "Define a frequência de atualização das estatísticas no painel de atividade.\n\nExemplos:\n- 1s atualiza a cada segundo\n- 5s reduz a frequência de atualização\n\nImpacto:\n- valores menores deixam o progresso mais vivo no log\n- também aumentam a quantidade de mensagens exibidas",
    "transfers": "Quantidade de arquivos copiados em paralelo.\n\nExemplos:\n- 1 faz uma cópia por vez\n- 4 é um valor equilibrado para uso comum\n- 8 ou mais pode acelerar lotes grandes\n\nImpacto:\n- valores altos aumentam uso de banda, CPU e disco\n- também elevam o número de conexões simultâneas",
    "checkers": "Número de verificações paralelas para listar, consultar e validar itens antes ou durante a cópia.\n\nExemplos:\n- 4 para carga leve\n- 8 para uso normal\n- 16 para remotes grandes\n\nImpacto:\n- pode melhorar a velocidade de descoberta dos arquivos\n- também aumenta chamadas à API e consumo de recursos",
    "retries": "Quantidade de novas tentativas completas quando a operação falha por erro recuperável.\n\nExemplos:\n- 3 para falhas rápidas\n- 5 como padrão equilibrado\n- 10 para ambientes instáveis\n\nImpacto:\n- valores maiores aumentam a chance de concluir a cópia\n- também prolongam o tempo até a operação desistir",
    "low_level_retries": "Tentativas extras para erros menores de leitura, escrita, rede ou partes da transferência.\n\nExemplos:\n- 10 é um valor seguro\n- 20 pode ajudar em links ruins\n\nImpacto:\n- melhora a tolerância a instabilidade\n- pode deixar operações problemáticas demorando mais para encerrar",
    "multi_thread_streams": "Número de streams paralelos usados em arquivos grandes quando o backend suporta multithread.\n\nExemplos:\n- 1 desativa o ganho paralelo\n- 4 é um bom começo\n- 8 pode acelerar arquivos muito grandes\n\nImpacto:\n- pode melhorar uploads e downloads grandes\n- aumenta uso de banda, CPU e memória",
    "buffer_size": "Tamanho do buffer em memória por transferência.\n\nExemplos:\n- 8M para uso econômico\n- 16M ou 32M para equilíbrio\n- 64M para maior desempenho em alguns cenários\n\nImpacto:\n- buffers maiores podem estabilizar e acelerar a cópia\n- também aumentam o consumo total de RAM conforme cresce o número de transfers",
    "tpslimit": "Limita a quantidade de requisições por segundo ao remote.\n\nExemplos:\n- 2 limita mais fortemente\n- 5 é moderado\n- 10 permite maior agressividade\n\nImpacto:\n- ajuda a evitar bloqueios, rate limit e throttling\n- valores muito baixos podem reduzir a velocidade de listagem e cópia",
    "log_level": "Controla o nível de detalhe do log exibido em Atividade. DEBUG mostra muito mais informação; NOTICE é um equilíbrio para uso normal; ERROR mostra só falhas.",
    "use_json_log": "Faz o rclone emitir logs em formato JSON. É útil para análise técnica ou integração, mas fica menos legível para leitura manual no painel.",
}

LOG_LEVELS = ("DEBUG", "INFO", "NOTICE", "ERROR")

ACCENT = "#1f6fff"
ACCENT_DARK = "#0f56d9"
ACCENT_LIGHT = "#dbe9ff"
SURFACE = "#f5f8ff"
CARD = "#ffffff"
TEXT = "#17325c"
TEXT_SOFT = "#57719b"
SUCCESS = "#198754"
WARNING = "#b26a00"
ERROR = "#df3b43"
BORDER = "#d7e3f4"

ROLE_KIND = Qt.UserRole + 1
ROLE_PATH = Qt.UserRole + 2
ROLE_LOADED = Qt.UserRole + 3


def parse_size(value):
    match = re.match(r"([\d\.]+)\s*([KMGT]?iB|B)", value, re.IGNORECASE)
    if not match:
        raise ValueError(f"Unrecognized size: {value}")
    number, unit = match.groups()
    multiplier = {
        "B": 1,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }
    return int(float(number) * multiplier[unit.upper()])


class InAppToolTip(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inAppTooltip")
        self.setWindowFlags(Qt.Widget)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setObjectName("inAppTooltipLabel")
        layout.addWidget(self.label)
        self.hide()

    def show_for(self, anchor, text):
        host = anchor.window().centralWidget() or anchor.window()
        if self.parent() is not host:
            self.setParent(host)
        self.label.setText(text)
        self.adjustSize()
        pos = anchor.mapTo(host, QPoint(anchor.width() + 10, 0))
        x = min(max(8, pos.x()), max(8, host.width() - self.width() - 8))
        y = min(max(8, pos.y()), max(8, host.height() - self.height() - 8))
        self.move(x, y)
        self.raise_()
        self.show()


class InfoButton(QToolButton):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.help_text = text
        self.setText("ⓘ")
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        self.setObjectName("infoButton")
        self.setFocusPolicy(Qt.NoFocus)

    def _tooltip(self):
        window = self.window()
        tip = getattr(window, "_in_app_tooltip", None)
        if tip is None:
            tip = InAppToolTip(window.centralWidget() or window)
            window._in_app_tooltip = tip
        return tip

    def enterEvent(self, event):
        self._tooltip().show_for(self, self.help_text)
        super().enterEvent(event)

    def leaveEvent(self, event):
        tip = getattr(self.window(), "_in_app_tooltip", None)
        if tip is not None:
            tip.hide()
        super().leaveEvent(event)


class StateCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "stateCheck")
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.stateChanged.connect(self._refresh_icon)
        self._refresh_icon()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.EnabledChange, QEvent.StyleChange, QEvent.PaletteChange):
            self._refresh_icon()

    def _refresh_icon(self):
        self.setIcon(self._build_icon(self.isChecked(), self.isEnabled()))

    @staticmethod
    def _build_icon(checked, enabled):
        if enabled and checked:
            fill = QColor(ACCENT)
            border = QColor(ACCENT_DARK)
            mark = QColor("#ffffff")
        elif enabled:
            fill = QColor("#ffffff")
            border = QColor("#7d9ac7")
            mark = None
        else:
            fill = QColor("#eef3fb")
            border = QColor("#c3d2e8")
            mark = QColor("#a8b9d3") if checked else None

        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(border, 1.35))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(2.0, 2.0, 14.0, 14.0), 4, 4)

        if mark is not None:
            painter.setPen(QPen(mark, 2.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(5.2, 9.4, 7.6, 11.8)
            painter.drawLine(7.6, 11.8, 12.9, 6.3)

        painter.end()
        return QIcon(pixmap)


class RcloneCopyWorker(QThread):
    started_ok = Signal()
    line_received = Signal(str)
    failed = Signal(str)
    finished_result = Signal(int, bool)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd
        self.proc = None
        self.cancelled = False

    def run(self):
        try:
            self.proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.started_ok.emit()
        for line in iter(self.proc.stdout.readline, ""):
            self.line_received.emit(line)

        rc = self.proc.wait()
        self.finished_result.emit(rc, self.cancelled)

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass


class RcloneListWorker(QThread):
    loaded = Signal(object, list, str)

    def __init__(self, cmd, context):
        super().__init__()
        self.cmd = cmd
        self.context = context

    def run(self):
        try:
            result = subprocess.run(
                self.cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            output = result.stdout or result.stderr or "[]"
            if result.returncode != 0:
                raise RuntimeError(output.strip())

            entries = json.loads(output)
            items = sorted(
                [
                    {
                        "name": entry.get("Name", "").strip(),
                        "kind": "dir" if entry.get("IsDir") else "file",
                    }
                    for entry in entries
                    if entry.get("Name", "").strip()
                ],
                key=lambda entry: (entry["kind"] != "dir", entry["name"].lower()),
            )
            self.loaded.emit(self.context, items, "")
        except Exception as exc:
            self.loaded.emit(self.context, [], str(exc))


class ResponsiveShell(QWidget):
    def __init__(self, left_widget, right_widget, threshold=1120, left_stretch=11, right_stretch=10):
        super().__init__()
        self.threshold = threshold
        self.left_stretch = left_stretch
        self.right_stretch = right_stretch

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, left_stretch)
        self.splitter.setStretchFactor(1, right_stretch)
        layout.addWidget(self.splitter)
        self._apply_orientation()

    def resizeEvent(self, event):
        self._apply_orientation()
        super().resizeEvent(event)

    def _apply_orientation(self):
        orientation = Qt.Vertical if self.width() < self.threshold else Qt.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
            if orientation == Qt.Vertical:
                self.splitter.setSizes([max(360, self.height() // 2), max(280, self.height() // 2)])
            else:
                self.splitter.setSizes([max(500, self.width() // 2), max(420, self.width() // 2)])


class RcloneManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Backup Manager")
        self.resize(1280, 900)
        self.setMinimumSize(980, 680)

        app_icon = self._load_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
            QApplication.instance().setWindowIcon(app_icon)

        self.rclone_bin = self._resolve_rclone_bin()
        self.settings_path = self._resolve_settings_path()
        self.conf_path = os.path.join(
            os.environ.get("USERPROFILE", ""), r"AppData\Roaming\rclone\rclone.conf"
        )
        self.remotes = []
        self.active_operation = None
        self.action_buttons = []
        self.cancel_buttons = []
        self.list_workers = set()
        self.copy_settings_widgets = {}

        self.status_text = "Pronto para iniciar."
        self.details_text = "Selecione uma origem, um destino e inicie a cópia."

        QApplication.instance().setStyle("Fusion")
        self._build_ui()
        self._load_app_settings()
        self._refresh_flags_preview()
        self.load_remotes(show_errors=False)

    def closeEvent(self, event):
        try:
            self._save_app_settings(show_feedback=False)
        except Exception:
            pass
        super().closeEvent(event)

    def _resolve_rclone_bin(self):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        bundled = os.path.join(base_dir, "rclone.exe")
        if os.path.isfile(bundled):
            return bundled

        fallback = os.path.join(os.path.dirname(sys.executable), "rclone.exe")
        if os.path.isfile(fallback):
            return fallback

        return bundled

    def _resolve_asset_path(self, *parts):
        candidates = [
            getattr(sys, "_MEIPASS", None),
            os.path.dirname(os.path.abspath(__file__)),
            os.path.dirname(sys.executable),
        ]
        for base_dir in candidates:
            if not base_dir:
                continue
            candidate = os.path.join(base_dir, *parts)
            if os.path.isfile(candidate):
                return candidate
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)

    def _load_app_icon(self):
        for filename in ("app_icon.ico", "app_icon.png"):
            icon_path = self._resolve_asset_path("assets", filename)
            if os.path.isfile(icon_path):
                return QIcon(icon_path)
        return QIcon()

    def _resolve_settings_path(self):
        candidates = [
            os.path.dirname(os.path.abspath(__file__)),
            os.path.dirname(sys.executable),
            tempfile.gettempdir(),
        ]
        for base_dir in candidates:
            try:
                os.makedirs(base_dir, exist_ok=True)
                probe = os.path.join(base_dir, ".backup_manager_probe")
                with open(probe, "w", encoding="utf-8") as handle:
                    handle.write("ok")
                os.remove(probe)
                return os.path.join(base_dir, "backup_manager.settings.json")
            except Exception:
                continue
        return os.path.join(tempfile.gettempdir(), "backup_manager.settings.json")

    def _build_ui(self):
        self.setStyleSheet(self._build_stylesheet())
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setIconSize(QSize(56, 20))
        self.tabs.addTab(self._build_tab_local_to_remote(), self._tab_icon("local"), " Local para Remote")
        self.tabs.addTab(self._build_tab_remote_to_local(), self._tab_icon("download"), " Remote para Local")
        self.tabs.addTab(self._build_tab_remote_to_remote(), self._tab_icon("remote"), " Remote para Remote")
        self.tabs.addTab(self._build_tab_settings(), self._tab_icon("settings"), " Configurações")
        root.addWidget(self.tabs, 1)

        status_wrap = QFrame()
        status_layout = QVBoxLayout(status_wrap)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(2)
        self.status_label = QLabel(self.status_text)
        self.status_label.setObjectName("statusLabel")
        self.details_label = QLabel(self.details_text)
        self.details_label.setObjectName("detailsLabel")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.details_label)
        root.addWidget(status_wrap)

    def _build_stylesheet(self):
        return f"""
        QMainWindow, QWidget#appRoot {{
            background: {SURFACE};
        }}
        QWidget {{
            background: transparent;
            color: {TEXT};
            font-family: 'Segoe UI';
            font-size: 10pt;
        }}
        #heroCard {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d7bff, stop:1 #0f4ec9);
            border: 1px solid rgba(255,255,255,0.18);
            border-radius: 14px;
        }}
        #heroTitle {{
            color: white;
            font-size: 21pt;
            font-weight: 700;
        }}
        #heroSubtitle {{
            color: #dce9ff;
            font-size: 11pt;
        }}
        #heroCircle {{
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 40px;
            min-width: 80px;
            min-height: 80px;
            max-width: 80px;
            max-height: 80px;
            font-size: 30pt;
            font-weight: 700;
        }}
        #summaryCard, #card {{
            background: {CARD};
            border: 1px solid {BORDER};
            border-radius: 12px;
        }}
        #summaryRow {{
            background: transparent;
        }}
        #summaryTitle, #cardTitle {{
            color: {TEXT};
            font-size: 12pt;
            font-weight: 700;
        }}
        #summaryText, #mutedLabel {{
            color: {TEXT_SOFT};
            font-size: 10pt;
        }}
        #sectionDivider {{
            background: {BORDER};
            min-height: 1px;
            max-height: 1px;
            border: none;
        }}
        QTabWidget::pane {{
            border: none;
            margin-top: 8px;
        }}
        QTabBar::tab {{
            background: rgba(255,255,255,0.72);
            border: 1px solid {BORDER};
            border-bottom: none;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            padding: 12px 18px;
            margin-right: 6px;
            color: {TEXT};
        }}
        QTabBar::tab:selected {{
            background: {CARD};
            color: {ACCENT_DARK};
            font-weight: 700;
        }}
        QLineEdit, QComboBox {{
            background: #fbfdff;
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 8px 10px;
            min-height: 22px;
        }}
        QTextEdit, QPlainTextEdit, QTreeWidget {{
            background: #fbfdff;
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus, QTreeWidget:focus {{
            border: 1px solid {ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 28px;
        }}
        QComboBox::down-arrow {{
            image: none;
        }}
        QComboBox QAbstractItemView {{
            background: {CARD};
            color: {TEXT};
            border: 1px solid {BORDER};
            selection-background-color: {ACCENT_LIGHT};
            selection-color: {TEXT};
        }}
        QTreeWidget {{
            padding: 0px;
        }}
        QTreeWidget::item {{
            height: 28px;
        }}
        QHeaderView::section {{
            background: #eef4ff;
            color: {TEXT};
            font-weight: 700;
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 8px;
        }}
        QProgressBar {{
            border: 1px solid {BORDER};
            border-radius: 8px;
            background: #eef3fb;
            min-height: 18px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            border-radius: 7px;
            background: {ACCENT};
        }}
        QPushButton {{
            border-radius: 8px;
            padding: 10px 16px;
            min-height: 18px;
            border: 1px solid {BORDER};
            background: #eef4ff;
            color: {ACCENT_DARK};
        }}
        QPushButton:hover {{
            background: #e2ecff;
        }}
        QPushButton:disabled {{
            background: #eef2f8;
            color: #9aa8bf;
        }}
        QPushButton[variant="primary"] {{
            background: {ACCENT};
            color: white;
            border: 1px solid {ACCENT};
            font-weight: 700;
        }}
        QPushButton[variant="primary"]:hover {{
            background: {ACCENT_DARK};
        }}
        QPushButton[variant="danger"] {{
            background: #fff1f2;
            color: {ERROR};
            border: 1px solid #ffcad0;
        }}
        QPushButton[variant="danger"]:hover {{
            background: #ffe3e6;
        }}
        QCheckBox {{
            spacing: 8px;
            background: transparent;
        }}
        QCheckBox[role="stateCheck"] {{
            spacing: 10px;
            padding: 2px 0;
            color: {TEXT};
        }}
        QCheckBox[role="stateCheck"]:disabled {{
            color: #97aac8;
        }}
        QCheckBox[role="stateCheck"]::indicator {{
            width: 0px;
            height: 0px;
        }}
        #statusLabel {{
            font-weight: 700;
            color: {TEXT};
        }}
        #detailsLabel {{
            color: {TEXT_SOFT};
        }}
        #infoButton {{
            border: none;
            background: transparent;
            color: {ACCENT_DARK};
            font-size: 12pt;
            padding: 0px;
            min-width: 18px;
            max-width: 18px;
        }}
        #inAppTooltip {{
            background: #143760;
            border: 1px solid #2e5a90;
            border-radius: 10px;
        }}
        #inAppTooltipLabel {{
            color: white;
            min-width: 240px;
            max-width: 320px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 4px 0 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: #c9d8ef;
            border-radius: 5px;
            min-height: 28px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #adc4e8;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
            border: none;
            height: 0px;
        }}
        """

    def _tab_icon(self, kind):
        mapping = {
            "local": ("disk", "cloud"),
            "download": ("cloud", "disk"),
            "remote": ("cloud", "cloud"),
            "settings": ("gear", None),
        }
        source, target = mapping[kind]
        return self._make_flow_icon(source, target)

    def _make_flow_icon(self, source, target=None):
        width = 56 if target else 22
        pixmap = QPixmap(width, 20)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if target:
            self._draw_symbol(painter, source, 0, 1)
            pen = QPen(QColor(ACCENT_DARK), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(19, 10, 35, 10)
            painter.drawLine(29, 5, 35, 10)
            painter.drawLine(29, 15, 35, 10)
            self._draw_symbol(painter, target, 36, 1)
        else:
            self._draw_symbol(painter, source, 1, 1)

        painter.end()
        return QIcon(pixmap)

    def _draw_symbol(self, painter, kind, x, y):
        color = QColor(ACCENT_DARK)
        pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if kind == "disk":
            painter.drawRoundedRect(QRectF(x + 1.5, y + 5.0, 14.5, 9.0), 2.4, 2.4)
            painter.drawLine(x + 4.0, y + 8.2, x + 13.0, y + 8.2)
            painter.drawPoint(x + 12.5, y + 11.3)
            return

        if kind == "cloud":
            path = QPainterPath()
            path.addEllipse(QRectF(x + 2.2, y + 6.0, 5.2, 5.2))
            path.addEllipse(QRectF(x + 6.0, y + 3.3, 6.2, 6.2))
            path.addEllipse(QRectF(x + 10.0, y + 5.3, 5.4, 5.4))
            path.addRoundedRect(QRectF(x + 4.0, y + 8.0, 10.0, 4.6), 2.0, 2.0)
            painter.drawPath(path)
            return

        if kind == "gear":
            painter.drawEllipse(QRectF(x + 3.8, y + 3.8, 9.4, 9.4))
            painter.drawEllipse(QRectF(x + 6.6, y + 6.6, 3.8, 3.8))
            painter.drawLine(x + 8.5, y + 1.2, x + 8.5, y + 3.6)
            painter.drawLine(x + 8.5, y + 13.4, x + 8.5, y + 15.8)
            painter.drawLine(x + 1.8, y + 8.5, x + 4.2, y + 8.5)
            painter.drawLine(x + 12.8, y + 8.5, x + 15.2, y + 8.5)
            painter.drawLine(x + 3.8, y + 3.8, x + 5.2, y + 5.2)
            painter.drawLine(x + 11.8, y + 11.8, x + 13.2, y + 13.2)
            painter.drawLine(x + 11.8, y + 5.2, x + 13.2, y + 3.8)
            painter.drawLine(x + 3.8, y + 13.2, x + 5.2, y + 11.8)

    def _build_header(self):
        frame = QFrame()
        frame.setObjectName("heroCard")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        left = QWidget()
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(18)

        hero_circle = QLabel("☁")
        hero_circle.setObjectName("heroCircle")
        hero_circle.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(hero_circle, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(8)
        title = QLabel("Backup Manager")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Gerencie cópias entre pastas locais e remotes do rclone com mais segurança, visibilidade e controle."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        left_layout.addLayout(text_box, 1)

        layout.addWidget(left, 1)

        summary = QFrame()
        summary.setObjectName("summaryCard")
        summary.setMinimumWidth(350)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(18, 18, 18, 18)
        summary_layout.setSpacing(12)

        summary_title = QLabel("Lembretes")
        summary_title.setObjectName("summaryTitle")
        summary_layout.addWidget(summary_title)

        self.remote_count_label = QLabel("0 remotes carregados")
        self.remote_count_label.setObjectName("summaryText")
        summary_layout.addWidget(self._summary_row(self.style().standardIcon(QStyle.SP_DirIcon), self.remote_count_label))

        summary_layout.addWidget(
            self._summary_row(
                self.style().standardIcon(QStyle.SP_FileDialogDetailedView),
                QLabel("Arquivo de configuração ativo"),
            )
        )

        self.conf_preview_label = QLabel(self._shorten_path(self.conf_path))
        self.conf_preview_label.setWordWrap(True)
        self.conf_preview_label.setObjectName("summaryText")
        summary_layout.addWidget(
            self._summary_row(self.style().standardIcon(QStyle.SP_FileIcon), self.conf_preview_label)
        )

        layout.addWidget(summary, 0, Qt.AlignTop)
        return frame

    def _summary_row(self, icon, text_widget):
        row = QWidget()
        row.setObjectName("summaryRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(16, 16))
        layout.addWidget(icon_label, 0, Qt.AlignTop)
        if isinstance(text_widget, QLabel):
            text_widget.setObjectName(text_widget.objectName() or "summaryText")
            layout.addWidget(text_widget, 1)
        else:
            label = QLabel(str(text_widget))
            label.setObjectName("summaryText")
            layout.addWidget(label, 1)
        return row

    def _build_tab_local_to_remote(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        source_card, source_body = self._create_card("Origem local", "Escolha um arquivo ou uma pasta do computador para enviar ao remote.")
        self.src_path_edit = QLineEdit()
        source_body.addWidget(self.src_path_edit)
        source_actions = QHBoxLayout()
        source_actions.setSpacing(10)
        source_actions.addWidget(self._register_button(self._make_button("Arquivo", self._pick_file)))
        source_actions.addWidget(self._register_button(self._make_button("Pasta", self._pick_folder)))
        source_actions.addStretch(1)
        source_body.addLayout(source_actions)
        self._set_card_compact(source_card)
        left_layout.addWidget(source_card)

        remote_browser_card, browser = self._build_remote_browser(
            "Remote destino",
            "Liste o remote e escolha a pasta de destino onde o conteúdo local será copiado.",
            allow_files=False,
        )
        self.lr_browser = browser
        self._set_card_expanding(remote_browser_card, min_height=330)
        left_layout.addWidget(remote_browser_card, 1)

        op_card, op_body = self._create_card(
            "Copiar para remote",
            "Inicia ou cancela a cópia do item local para a pasta remota selecionada.",
        )
        desc = QLabel("Envia o arquivo ou a pasta local para o caminho remoto selecionado.")
        desc.setObjectName("mutedLabel")
        desc.setWordWrap(True)
        op_body.addWidget(desc)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._register_button(self._make_button("Iniciar cópia", self._start_local_to_remote, "primary")))
        actions.addWidget(self._register_cancel_button(self._make_button("Cancelar cópia", self._cancel_copy, "danger")))
        actions.addStretch(1)
        op_body.addLayout(actions)
        self._set_card_compact(op_card)
        left_layout.addWidget(op_card)

        activity_panel, progress, progress_label, log = self._build_activity_panel(
            "Aqui você acompanha o progresso da operação e o log detalhado retornado pelo rclone."
        )
        self.progress_lr = progress
        self.progress_lr_label = progress_label
        self.log_lr = log
        self._set_card_expanding(activity_panel, min_height=420)

        outer.addWidget(ResponsiveShell(self._wrap_scroll_panel(left_panel), activity_panel))
        return page

    def _build_tab_remote_to_local(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        remote_browser_card, browser = self._build_remote_browser(
            "Remote origem",
            "Liste o remote e escolha a pasta ou arquivo que será baixado para o computador.",
            allow_files=True,
        )
        self.rl_browser = browser
        self._set_card_expanding(remote_browser_card, min_height=330)
        left_layout.addWidget(remote_browser_card, 1)

        folder_card, folder_body = self._create_card(
            "Destino local",
            "Escolha a pasta local que receberá os arquivos copiados do remote.",
        )
        self.dest_local_edit = QLineEdit()
        folder_body.addWidget(self.dest_local_edit)
        folder_body.addWidget(self._register_button(self._make_button("Selecionar pasta", self._pick_dest_folder)))
        self._set_card_compact(folder_card)
        left_layout.addWidget(folder_card)

        op_card, op_body = self._create_card(
            "Copiar para local",
            "Inicia ou cancela a cópia do remote para a pasta local selecionada.",
        )
        desc = QLabel("Baixa o conteúdo remoto para a pasta local escolhida.")
        desc.setObjectName("mutedLabel")
        desc.setWordWrap(True)
        op_body.addWidget(desc)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._register_button(self._make_button("Iniciar cópia", self._start_remote_to_local, "primary")))
        actions.addWidget(self._register_cancel_button(self._make_button("Cancelar cópia", self._cancel_copy, "danger")))
        actions.addStretch(1)
        op_body.addLayout(actions)
        self._set_card_compact(op_card)
        left_layout.addWidget(op_card)

        activity_panel, progress, progress_label, log = self._build_activity_panel(
            "Aqui você acompanha o progresso da operação e o log detalhado retornado pelo rclone."
        )
        self.progress_rl = progress
        self.progress_rl_label = progress_label
        self.log_rl = log
        self._set_card_expanding(activity_panel, min_height=420)

        outer.addWidget(ResponsiveShell(self._wrap_scroll_panel(left_panel), activity_panel))
        return page

    def _build_tab_remote_to_remote(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        browsers_wrapper = QWidget()
        browsers_layout = QVBoxLayout(browsers_wrapper)
        browsers_layout.setContentsMargins(0, 0, 0, 0)
        browsers_layout.setSpacing(0)

        src_card, src_browser = self._build_remote_browser(
            "Remote origem",
            "Escolha a pasta ou arquivo remoto que será usado como origem da transferência.",
            allow_files=True,
        )
        dst_card, dst_browser = self._build_remote_browser(
            "Remote destino",
            "Escolha a pasta remota de destino onde o conteúdo será copiado.",
            allow_files=False,
        )
        self.rr_src_browser = src_browser
        self.rr_dst_browser = dst_browser
        self._set_card_expanding(src_card, min_height=260)
        self._set_card_expanding(dst_card, min_height=260)
        browsers_layout.addWidget(ResponsiveShell(src_card, dst_card, threshold=1180, left_stretch=1, right_stretch=1))
        left_layout.addWidget(browsers_wrapper, 1)

        op_card, op_body = self._create_card(
            "Transferência entre remotes",
            "Controla a transferência entre dois remotes sem passar pelo disco local.",
        )
        desc = QLabel("Replica o conteúdo do remote de origem para o remote de destino escolhido.")
        desc.setObjectName("mutedLabel")
        desc.setWordWrap(True)
        op_body.addWidget(desc)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._register_button(self._make_button("Iniciar cópia", self._start_remote_to_remote, "primary")))
        actions.addWidget(self._register_cancel_button(self._make_button("Cancelar cópia", self._cancel_copy, "danger")))
        actions.addStretch(1)
        op_body.addLayout(actions)
        self._set_card_compact(op_card)
        left_layout.addWidget(op_card)

        activity_panel, progress, progress_label, log = self._build_activity_panel(
            "Aqui você acompanha o progresso da operação e o log detalhado retornado pelo rclone."
        )
        self.progress_rr = progress
        self.progress_rr_label = progress_label
        self.log_rr = log
        self._set_card_expanding(activity_panel, min_height=420)

        outer.addWidget(
            ResponsiveShell(self._wrap_scroll_panel(left_panel), activity_panel, left_stretch=12, right_stretch=10)
        )
        return page

    def _build_tab_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        conf_card, conf_body = self._create_card(
            "Arquivo rclone.conf",
            "Define qual arquivo rclone.conf será usado para carregar os remotes e executar os comandos.",
        )
        self.conf_path_edit = QLineEdit()
        conf_body.addWidget(self.conf_path_edit)
        conf_actions = QHBoxLayout()
        conf_actions.setSpacing(10)
        conf_actions.addWidget(self._register_button(self._make_button("Procurar", self._pick_conf)))
        conf_actions.addWidget(self._register_button(self._make_button("Recarregar remotes", lambda: self.load_remotes(show_errors=True))))
        conf_actions.addWidget(self._register_button(self._make_button("Abrir rclone config", self._run_rclone_config, "primary")))
        conf_actions.addStretch(1)
        conf_body.addLayout(conf_actions)
        self._set_card_compact(conf_card)
        content_layout.addWidget(conf_card)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        content_layout.addWidget(body, 1)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        body_layout.addLayout(left_col, 1)
        body_layout.addLayout(right_col, 1)

        behavior_card = self._build_settings_group(
            "Comportamento da cópia",
            [
                ("create_empty_src_dirs", "Criar diretórios vazios"),
                ("error_on_no_transfer", "Falhar se nada for transferido"),
                ("fast_list", "Usar fast-list"),
                ("dry_run", "Executar em dry-run"),
                ("checksum", "Comparar por checksum"),
                ("size_only", "Comparar só por tamanho"),
                ("ignore_existing", "Ignorar arquivos já existentes"),
                ("update", "Copiar apenas se a origem for mais nova"),
            ],
            "Define como o rclone decide o que copiar, quando considerar sucesso e se deve simular a operação.",
        )
        self._set_card_compact(behavior_card)
        left_col.addWidget(behavior_card)
        transfer_card = self._build_settings_group(
            "Transferência",
            [
                ("stats", "Intervalo de stats"),
                ("transfers", "Transfers"),
                ("checkers", "Checkers"),
                ("retries", "Retries"),
                ("low_level_retries", "Low-level retries"),
                ("multi_thread_streams", "Multi-thread streams"),
                ("buffer_size", "Buffer size"),
                ("tpslimit", "TPS limit"),
            ],
            "Ajusta desempenho, concorrência, retentativas e consumo de recursos durante a cópia.",
        )
        self._set_card_compact(transfer_card)
        left_col.addWidget(transfer_card)
        left_col.addStretch(1)

        log_card = self._build_settings_group(
            "Log e diagnóstico",
            [
                ("log_level", "Nível de log"),
                ("use_json_log", "Usar log em JSON"),
            ],
            "Controla a verbosidade do log mostrado na área de atividade e a forma de saída das mensagens.",
        )
        self._set_card_compact(log_card)
        right_col.addWidget(log_card)
        summary_card = self._build_settings_summary(
            "Mostra a combinação final de argumentos que será anexada aos próximos comandos de cópia."
        )
        self._set_card_expanding(summary_card, min_height=300)
        right_col.addWidget(summary_card, 1)
        right_col.addStretch(1)
        return page

    def _create_card(self, title, help_text=None):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        header.addWidget(title_label)
        header.addStretch(1)
        if help_text:
            header.addWidget(InfoButton(help_text, frame))
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("sectionDivider")
        layout.addWidget(divider)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        layout.addLayout(body, 1)
        return frame, body

    def _set_card_compact(self, card):
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    def _set_card_expanding(self, card, min_height=None):
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if min_height is not None:
            card.setMinimumHeight(min_height)

    def _wrap_scroll_panel(self, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def _build_activity_panel(self, help_text):
        card, body = self._create_card("Atividade", help_text)
        progress_title = QLabel("Progresso da operação")
        progress_title.setObjectName("cardTitle")
        progress_title.setStyleSheet("font-size: 11pt;")
        body.addWidget(progress_title)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        progress = QProgressBar()
        progress.setRange(0, 1)
        progress.setValue(0)
        progress.setTextVisible(False)
        percent_label = QLabel("0%")
        percent_label.setObjectName("mutedLabel")
        percent_label.setMinimumWidth(34)
        progress_row.addWidget(progress, 1)
        progress_row.addWidget(percent_label, 0, Qt.AlignRight)
        body.addLayout(progress_row)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMinimumHeight(320)
        body.addWidget(log, 1)
        return card, progress, percent_label, log

    def _build_remote_browser(self, title, help_text, allow_files):
        card, body = self._create_card(title, help_text)

        top = QHBoxLayout()
        top.setSpacing(10)
        combo = QComboBox()
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top.addWidget(combo, 1)
        list_button = self._register_button(self._make_button("Listar"))
        top.addWidget(list_button)
        body.addLayout(top)

        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels(["Nome", "Tipo", "Caminho"])
        tree.setRootIsDecorated(True)
        tree.setAlternatingRowColors(False)
        tree.setMinimumHeight(160)
        tree.header().setStretchLastSection(True)
        tree.header().resizeSection(0, 260)
        tree.header().resizeSection(1, 110)
        tree.itemExpanded.connect(lambda item, b=None: self._open_tree_node(browser, item))
        tree.itemSelectionChanged.connect(lambda b=None: self._sync_selected_path(browser))
        body.addWidget(tree, 1)

        path_edit = QLineEdit("/")
        path_edit.setPlaceholderText("Caminho selecionado")
        body.addWidget(path_edit)

        browser = {
            "combo": combo,
            "button": list_button,
            "tree": tree,
            "path_edit": path_edit,
            "allow_files": allow_files,
        }
        list_button.clicked.connect(lambda: self._refresh_tree_async(browser, "", None))
        return card, browser

    def _build_settings_group(self, title, fields, help_text):
        card, body = self._create_card(title, help_text)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        body.addLayout(grid)

        for row, (key, label) in enumerate(fields):
            default_value = DEFAULT_COPY_SETTINGS[key]
            if isinstance(default_value, bool):
                widget = StateCheckBox(label)
                widget.setChecked(default_value)
                widget.stateChanged.connect(self._refresh_flags_preview)
                grid.addWidget(widget, row, 0)
                grid.addWidget(InfoButton(COPY_SETTING_HELP.get(key, ""), card), row, 1)
                grid.setColumnStretch(0, 1)
            else:
                label_widget = QLabel(label)
                label_widget.setObjectName("mutedLabel")
                grid.addWidget(label_widget, row, 0)
                grid.addWidget(InfoButton(COPY_SETTING_HELP.get(key, ""), card), row, 1)
                if key == "log_level":
                    widget = QComboBox()
                    widget.addItems(list(LOG_LEVELS))
                    widget.currentTextChanged.connect(self._refresh_flags_preview)
                else:
                    widget = QLineEdit(str(default_value))
                    widget.textChanged.connect(self._refresh_flags_preview)
                grid.addWidget(widget, row, 2)
                grid.setColumnStretch(2, 1)
            self.copy_settings_widgets[key] = widget
        return card

    def _build_settings_summary(self, help_text):
        card, body = self._create_card("Resumo aplicado", help_text)
        hint = QLabel("As opções abaixo serão anexadas aos próximos comandos de cópia.")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        body.addWidget(hint)

        self.flags_preview_widget = QPlainTextEdit()
        self.flags_preview_widget.setReadOnly(True)
        self.flags_preview_widget.setMinimumHeight(220)
        body.addWidget(self.flags_preview_widget, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._register_button(self._make_button("Salvar configurações", lambda: self._save_app_settings(show_feedback=True), "primary")))
        actions.addWidget(self._register_button(self._make_button("Restaurar padrão", self._reset_settings_ui)))
        actions.addStretch(1)
        body.addLayout(actions)
        return card

    def _make_button(self, text, callback=None, variant="secondary"):
        button = QPushButton(text)
        button.setProperty("variant", variant)
        button.style().unpolish(button)
        button.style().polish(button)
        if callback:
            button.clicked.connect(callback)
        return button

    def _register_button(self, button):
        self.action_buttons.append(button)
        return button

    def _register_cancel_button(self, button):
        self.cancel_buttons.append(button)
        self.action_buttons.append(button)
        return button

    def _collect_copy_settings(self):
        settings = {}
        for key, widget in self.copy_settings_widgets.items():
            if isinstance(widget, QCheckBox):
                settings[key] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                settings[key] = widget.currentText().strip()
            else:
                settings[key] = widget.text().strip()
        return settings

    def _load_app_settings(self):
        settings = {"conf_path": self.conf_path, "copy": dict(DEFAULT_COPY_SETTINGS)}
        try:
            if os.path.isfile(self.settings_path):
                with open(self.settings_path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    settings["conf_path"] = loaded.get("conf_path", settings["conf_path"])
                    if isinstance(loaded.get("copy"), dict):
                        settings["copy"].update(loaded["copy"])
        except Exception:
            pass

        self.conf_path = settings["conf_path"]
        self.conf_path_edit.setText(self.conf_path)
        self.conf_preview_label.setText(self._shorten_path(self.conf_path))
        for key, value in settings["copy"].items():
            widget = self.copy_settings_widgets.get(key)
            if widget is None:
                continue
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            else:
                widget.setText(str(value))

    def _save_app_settings(self, show_feedback=False):
        payload = {
            "conf_path": self.conf_path_edit.text().strip(),
            "copy": self._collect_copy_settings(),
        }
        with open(self.settings_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        self._refresh_flags_preview()
        if show_feedback:
            self._show_message("info", "Configurações", "Configurações salvas com sucesso.")

    def _reset_copy_settings(self):
        for key, value in DEFAULT_COPY_SETTINGS.items():
            widget = self.copy_settings_widgets.get(key)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            else:
                widget.setText(str(value))

    def _reset_settings_ui(self):
        self._reset_copy_settings()
        self.conf_path_edit.setText(self.conf_path)
        self.conf_preview_label.setText(self._shorten_path(self.conf_path_edit.text().strip()))
        self._refresh_flags_preview()

    def _build_copy_flags(self):
        settings = self._collect_copy_settings()
        flags = list(RCLONE_FLAGS)

        if settings["stats"]:
            flags.append(f"--stats={settings['stats']}")
        if settings["create_empty_src_dirs"]:
            flags.append("--create-empty-src-dirs")
        if settings["error_on_no_transfer"]:
            flags.append("--error-on-no-transfer")
        if settings["fast_list"]:
            flags.append("--fast-list")
        if settings["dry_run"]:
            flags.append("--dry-run")
        if settings["checksum"]:
            flags.append("--checksum")
        elif settings["size_only"]:
            flags.append("--size-only")
        if settings["ignore_existing"]:
            flags.append("--ignore-existing")
        if settings["update"]:
            flags.append("--update")
        if settings["use_json_log"]:
            flags.append("--use-json-log")

        for key, flag in (
            ("transfers", "--transfers"),
            ("checkers", "--checkers"),
            ("retries", "--retries"),
            ("low_level_retries", "--low-level-retries"),
            ("multi_thread_streams", "--multi-thread-streams"),
            ("buffer_size", "--buffer-size"),
            ("tpslimit", "--tpslimit"),
            ("log_level", "--log-level"),
        ):
            value = settings.get(key, "")
            if value:
                flags.extend([flag, value])
        return flags

    def _refresh_flags_preview(self):
        if not hasattr(self, "flags_preview_widget"):
            return
        preview = " ".join(self._build_copy_flags()) or "(sem flags)"
        self.flags_preview_widget.setPlainText(preview)

    def _show_message(self, kind, title, message):
        if kind == "info":
            QMessageBox.information(self, title, message)
        elif kind == "warning":
            QMessageBox.warning(self, title, message)
        else:
            QMessageBox.critical(self, title, message)

    def _set_status(self, headline, details=None):
        self.status_text = headline
        self.status_label.setText(headline)
        if details is not None:
            self.details_text = details
            self.details_label.setText(details)

    def _set_busy(self, busy, operation_name=""):
        for button in self.action_buttons:
            button.setEnabled(not busy)
        if busy:
            for button in self.cancel_buttons:
                button.setEnabled(True)
            self._set_status(f"Executando: {operation_name}", "Aguardando retorno do rclone...")
        else:
            if not self.status_text.startswith("Erro"):
                self._set_status("Pronto para iniciar.", self.details_text)

    def _append_log(self, widget, text, reset=False):
        if reset:
            widget.clear()
        cursor = widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        widget.setTextCursor(cursor)
        widget.ensureCursorVisible()

    def _set_progress(self, progress_widget, label_widget, current, total):
        if total <= 0:
            progress_widget.setRange(0, 1)
            progress_widget.setValue(0)
            label_widget.setText("0%")
            return
        progress_widget.setRange(0, total)
        progress_widget.setValue(min(current, total))
        percent = int((current / total) * 100) if total else 0
        label_widget.setText(f"{percent}%")

    def _update_progress_from_line(self, progress_widget, label_widget, line):
        bytes_match = PAT_BYTES.search(line)
        if bytes_match:
            try:
                current = parse_size(bytes_match.group(1))
                total = parse_size(bytes_match.group(2))
            except ValueError:
                current = total = 0
            if total > 0:
                self._set_progress(progress_widget, label_widget, current, total)
                self.details_label.setText(
                    f"Transferido {bytes_match.group(1)} de {bytes_match.group(2)}."
                )
                return

        files_match = PAT_FILES.search(line)
        if files_match:
            current = int(files_match.group(1))
            total = int(files_match.group(2))
            if total > 0:
                self._set_progress(progress_widget, label_widget, current, total)
                self.details_label.setText(f"Arquivos transferidos: {current}/{total}.")

    def _shorten_path(self, value, max_len=46):
        if len(value) <= max_len:
            return value
        return f"...{value[-(max_len - 3):]}"

    def _config_args(self, config_path=None):
        path = (config_path if config_path is not None else self.conf_path_edit.text()).strip()
        if path:
            return ["--config", path]
        return []

    def _rclone_base_cmd(self, config_path=None):
        if not os.path.isfile(self.rclone_bin):
            raise FileNotFoundError(
                "Não foi possível localizar o rclone.exe. Mantenha o arquivo ao lado do app."
            )
        return [self.rclone_bin, *self._config_args(config_path)]

    def _remote_target(self, remote, subdir):
        clean = (subdir or "").strip().strip("/")
        if clean:
            return f"{remote}:/{clean}"
        return f"{remote}:/"

    def _build_copy_command(self, source, target):
        return [*self._rclone_base_cmd(), "copy", source, target, *self._build_copy_flags()]

    def _parent_remote_path(self, path):
        clean = (path or "").strip().strip("/")
        if not clean:
            return "/"
        if "/" not in clean:
            return "/"
        return clean.rsplit("/", 1)[0] or "/"

    def _kind_label(self, kind):
        return {
            "dir": "Pasta",
            "file": "Arquivo",
            "loading": "...",
        }.get((kind or "").strip().lower(), kind)

    def _kind_icon(self, kind):
        style = self.style()
        mapping = {
            "dir": QStyle.SP_DirIcon,
            "file": QStyle.SP_FileIcon,
            "loading": QStyle.SP_BrowserReload,
        }
        return style.standardIcon(mapping.get(kind, QStyle.SP_FileIcon))

    def _add_tree_item(self, parent_item, name, kind, full_path):
        item = QTreeWidgetItem([name, self._kind_label(kind), full_path or "/"])
        item.setData(0, ROLE_KIND, kind)
        item.setData(0, ROLE_PATH, full_path or "/")
        item.setData(0, ROLE_LOADED, kind != "dir")
        item.setIcon(0, self._kind_icon(kind))
        parent_item.addChild(item)
        if kind == "dir":
            dummy = QTreeWidgetItem(["Carregando...", self._kind_label("loading"), ""])
            dummy.setData(0, ROLE_KIND, "loading")
            item.addChild(dummy)
        return item

    def _clear_tree_children(self, parent_item):
        while parent_item.childCount():
            parent_item.takeChild(0)

    def _sync_selected_path(self, browser):
        tree = browser["tree"]
        item = tree.currentItem()
        if not item:
            return
        selected_path = item.data(0, ROLE_PATH) or "/"
        kind = item.data(0, ROLE_KIND) or "dir"
        if kind == "file" and not browser["allow_files"]:
            parent_path = self._parent_remote_path(selected_path)
            browser["path_edit"].setText(parent_path)
            self.details_label.setText(
                "Arquivo selecionado como referência visual. O destino usa a pasta pai."
            )
            return
        browser["path_edit"].setText(selected_path)

    def _open_tree_node(self, browser, item):
        if not item or item.data(0, ROLE_KIND) != "dir":
            self._sync_selected_path(browser)
            return
        if item.data(0, ROLE_LOADED):
            return
        self._refresh_tree_async(browser, item.data(0, ROLE_PATH) or "/", item)

    def _refresh_tree_async(self, browser, path="", parent_item=None):
        remote = browser["combo"].currentText().strip()
        if not remote:
            self._show_message("warning", "Remote obrigatório", "Selecione um remote para listar os itens.")
            return

        tree = browser["tree"]
        if parent_item is None:
            tree.clear()
            root_parent = tree.invisibleRootItem()
        else:
            root_parent = parent_item
            self._clear_tree_children(root_parent)

        loading = QTreeWidgetItem(["Carregando...", self._kind_label("loading"), "carregando"])
        loading.setData(0, ROLE_KIND, "loading")
        loading.setIcon(0, self._kind_icon("loading"))
        root_parent.addChild(loading)
        browser["path_edit"].setText(path or "/")
        self._set_status("Carregando itens...", f"Lendo {self._remote_target(remote, path)}")

        cmd = [*self._rclone_base_cmd(), "lsjson", self._remote_target(remote, path)]
        context = {
            "browser": browser,
            "path": path,
            "parent_item": parent_item,
            "remote": remote,
        }
        worker = RcloneListWorker(cmd, context)
        self.list_workers.add(worker)
        worker.loaded.connect(self._populate_tree_result)
        worker.finished.connect(lambda: self._cleanup_list_worker(worker))
        worker.start()

    def _cleanup_list_worker(self, worker):
        self.list_workers.discard(worker)
        worker.deleteLater()

    def _populate_tree_result(self, context, items, error):
        browser = context["browser"]
        tree = browser["tree"]
        parent_item = context["parent_item"]
        path = context["path"]

        target = parent_item or tree.invisibleRootItem()
        self._clear_tree_children(target)

        if error:
            self._set_status("Erro ao listar itens.", error)
            self._show_message("error", "Falha ao listar itens", error)
            return

        for entry in items:
            clean_path = "/".join([part for part in [path.strip("/"), entry["name"]] if part])
            self._add_tree_item(target, entry["name"], entry["kind"], clean_path)

        if parent_item is not None:
            parent_item.setData(0, ROLE_LOADED, True)

        self._set_status("Itens carregados.", "A estrutura remota foi atualizada.")

    def _start_operation(self, name, cmd, log_widget, progress_widget, progress_label):
        if self.active_operation:
            self._show_message("warning", "Operação em andamento", "Já existe uma cópia em execução.")
            return

        worker = RcloneCopyWorker(cmd)
        operation = {
            "name": name,
            "worker": worker,
            "log": log_widget,
            "progress": progress_widget,
            "progress_label": progress_label,
        }
        self.active_operation = operation
        self._append_log(log_widget, "", reset=True)
        self._set_progress(progress_widget, progress_label, 0, 1)
        self._set_busy(True, name)
        self.details_label.setText("Aguardando retorno do rclone...")

        worker.started_ok.connect(lambda: self._append_log(log_widget, "Comando iniciado com sucesso.\n\n"))
        worker.line_received.connect(lambda line: self._append_log(log_widget, line))
        worker.line_received.connect(lambda line: self._update_progress_from_line(progress_widget, progress_label, line))
        worker.failed.connect(self._finish_operation_error)
        worker.finished_result.connect(self._finish_operation_result)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_operation_error(self, message):
        self.active_operation = None
        self._set_busy(False)
        self._set_status("Erro ao iniciar a operação.", message)
        self._show_message("error", "Erro", f"Não foi possível iniciar a cópia:\n{message}")

    def _finish_operation_result(self, return_code, cancelled):
        operation = self.active_operation
        if not operation:
            return

        self.active_operation = None
        self._set_busy(False)

        if cancelled:
            self._set_status("Operação cancelada.", "A cópia foi interrompida pelo usuário.")
            self._show_message("info", "Cancelado", "Cópia interrompida.")
            return

        if return_code == 0:
            operation["progress"].setValue(operation["progress"].maximum())
            operation["progress_label"].setText("100%")
            self._set_status("Operação concluída com sucesso.", "O rclone finalizou sem erros.")
            self._show_message("info", "Concluído", "Operação finalizada com sucesso.")
            return

        self._set_status("Erro durante a operação.", f"O rclone finalizou com código {return_code}.")
        self._show_message(
            "error",
            "Falha na cópia",
            f"O rclone finalizou com erro (código {return_code}). Consulte o log da operação.",
        )

    def _start_local_to_remote(self):
        source = self.src_path_edit.text().strip()
        remote = self.lr_browser["combo"].currentText().strip()
        if not source or not remote:
            self._show_message("warning", "Campos obrigatórios", "Informe a origem local e o remote de destino.")
            return
        if not os.path.exists(source):
            self._show_message("error", "Origem inválida", "O caminho local informado não existe.")
            return

        target = self._remote_target(remote, self.lr_browser["path_edit"].text())
        self._start_operation(
            "Local para Remote",
            self._build_copy_command(source, target),
            self.log_lr,
            self.progress_lr,
            self.progress_lr_label,
        )

    def _start_remote_to_local(self):
        remote = self.rl_browser["combo"].currentText().strip()
        destination = self.dest_local_edit.text().strip()
        if not remote or not destination:
            self._show_message("warning", "Campos obrigatórios", "Informe o remote de origem e a pasta local de destino.")
            return
        if not os.path.isdir(destination):
            self._show_message("error", "Destino inválido", "Selecione uma pasta local válida.")
            return

        source = self._remote_target(remote, self.rl_browser["path_edit"].text())
        self._start_operation(
            "Remote para Local",
            self._build_copy_command(source, destination),
            self.log_rl,
            self.progress_rl,
            self.progress_rl_label,
        )

    def _start_remote_to_remote(self):
        source_remote = self.rr_src_browser["combo"].currentText().strip()
        destination_remote = self.rr_dst_browser["combo"].currentText().strip()
        if not source_remote or not destination_remote:
            self._show_message("warning", "Campos obrigatórios", "Selecione os remotes de origem e destino.")
            return

        source = self._remote_target(source_remote, self.rr_src_browser["path_edit"].text())
        target = self._remote_target(destination_remote, self.rr_dst_browser["path_edit"].text())
        self._start_operation(
            "Remote para Remote",
            self._build_copy_command(source, target),
            self.log_rr,
            self.progress_rr,
            self.progress_rr_label,
        )

    def _cancel_copy(self):
        if not self.active_operation:
            self._show_message("info", "Sem atividade", "Nenhuma cópia em andamento.")
            return

        worker = self.active_operation["worker"]
        if not worker.isRunning():
            self._show_message("info", "Sem atividade", "Nenhuma cópia em andamento.")
            return

        self.details_label.setText("Solicitando cancelamento...")
        worker.cancel()

    def _run_rclone_config(self):
        try:
            subprocess.Popen(
                [*self._rclone_base_cmd(), "config"],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        except Exception as exc:
            self._show_message("error", "Erro", f"Não foi possível abrir o configurador do rclone:\n{exc}")

    def _pick_conf(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o arquivo rclone.conf",
            self.conf_path_edit.text().strip() or "",
            "Config Rclone (rclone.conf);;Todos (*.*)",
        )
        if filename:
            self.conf_path = filename
            self.conf_path_edit.setText(filename)
            self.conf_preview_label.setText(self._shorten_path(filename))
            self.load_remotes(show_errors=True)

    def _pick_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Selecione um arquivo")
        if filename:
            self.src_path_edit.setText(filename)

    def _pick_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Selecione uma pasta")
        if directory:
            self.src_path_edit.setText(directory)

    def _pick_dest_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Selecione a pasta de destino")
        if directory:
            self.dest_local_edit.setText(directory)

    def load_remotes(self, show_errors=True):
        path = self.conf_path_edit.text().strip()
        self.conf_path = path
        self.conf_preview_label.setText(self._shorten_path(path))

        if not os.path.isfile(path):
            self.remotes = []
            self.remote_count_label.setText("0 remotes carregados")
            self._update_remote_combos()
            if show_errors:
                self._show_message("error", "Arquivo não encontrado", path or "Caminho não informado.")
            return

        parser = configparser.RawConfigParser()
        parser.read(path, encoding="utf-8")
        self.remotes = parser.sections()
        self.remote_count_label.setText(f"{len(self.remotes)} remotes carregados")
        self._update_remote_combos()
        self._set_status(
            "Configuração atualizada.",
            "Remotes recarregados a partir do arquivo selecionado.",
        )

    def _update_remote_combos(self):
        combos = [
            self.lr_browser["combo"],
            self.rl_browser["combo"],
            self.rr_src_browser["combo"],
            self.rr_dst_browser["combo"],
        ]
        for combo in combos:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self.remotes)
            if current and current in self.remotes:
                combo.setCurrentText(current)
            elif self.remotes:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Backup Manager")
    window = RcloneManagerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
