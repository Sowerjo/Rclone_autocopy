import configparser
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

PAT_BYTES = re.compile(
    r"Transferred:\s*([\d\.]+\s*(?:[KMGT]?iB|B))\s*/\s*([\d\.]+\s*(?:[KMGT]?iB|B))",
    re.IGNORECASE,
)
PAT_FILES = re.compile(r"Transferred:\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
RCLONE_FLAGS = [
    "--progress",
]
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
ACCENT = "#2f6fed"
ACCENT_DARK = "#1f4fb3"
SURFACE = "#f3f6fb"
CARD = "#ffffff"
TEXT = "#16324f"
MUTED = "#66758a"
SUCCESS = "#198754"
WARNING = "#b26a00"
ERROR = "#bb2d3b"


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


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.label = None
        self.widget.bind("<Enter>", self.show, add="+")
        self.widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None):
        if self.tipwindow or not self.text:
            return
        root = self.widget.winfo_toplevel()
        self.tipwindow = tw = tk.Frame(
            root,
            bg="#16324f",
            highlightbackground="#284d78",
            highlightthickness=1,
            bd=0,
        )
        self.label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            wraplength=320,
            bg="#16324f",
            fg="white",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        self.label.pack()
        tw.place(x=0, y=0)
        tw.update_idletasks()

        root.update_idletasks()
        root_x = root.winfo_rootx()
        root_y = root.winfo_rooty()
        x = self.widget.winfo_rootx() - root_x + self.widget.winfo_width() + 10
        y = self.widget.winfo_rooty() - root_y
        max_x = max(8, root.winfo_width() - tw.winfo_reqwidth() - 8)
        max_y = max(8, root.winfo_height() - tw.winfo_reqheight() - 8)
        x = min(max(8, x), max_x)
        y = min(max(8, y), max_y)
        tw.place(x=x, y=y)

    def hide(self, _event=None):
        if self.tipwindow is not None:
            self.tipwindow.place_forget()
            self.tipwindow.destroy()
            self.tipwindow = None
            self.label = None


class RcloneManagerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Backup Manager")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        self.configure(bg=SURFACE)

        self.rclone_bin = self._resolve_rclone_bin()
        self.settings_path = self._resolve_settings_path()
        self.conf_path = os.path.join(
            os.environ["USERPROFILE"], r"AppData\Roaming\rclone\rclone.conf"
        )
        self.remotes = []
        self.active_operation = None
        self.action_buttons = []
        self.cancel_buttons = []
        self.log_widgets = []
        self.tooltips = []

        self.status_var = tk.StringVar(value="Pronto para iniciar.")
        self.details_var = tk.StringVar(
            value="Selecione uma origem, um destino e inicie a copia."
        )
        self.conf_var = tk.StringVar(value=self.conf_path)
        self.remote_count_var = tk.StringVar(value="0 remotes carregados")
        self.src_path = tk.StringVar()
        self.dest_local = tk.StringVar()
        self.lr_subdir = tk.StringVar(value="/")
        self.rl_subdir = tk.StringVar(value="/")
        self.rr_src_sub = tk.StringVar(value="/")
        self.rr_dst_sub = tk.StringVar(value="/")
        self.copy_settings_vars = self._create_settings_vars()

        self._load_app_settings()

        self._configure_styles()
        self._build_ui()
        self.load_remotes()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _resolve_rclone_bin(self):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        bundled = os.path.join(base_dir, "rclone.exe")
        if os.path.isfile(bundled):
            return bundled

        fallback = os.path.join(os.path.dirname(sys.executable), "rclone.exe")
        if os.path.isfile(fallback):
            return fallback

        return bundled

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
                with open(probe, "w", encoding="utf-8") as fh:
                    fh.write("ok")
                os.remove(probe)
                return os.path.join(base_dir, "backup_manager.settings.json")
            except Exception:
                continue
        return os.path.join(tempfile.gettempdir(), "backup_manager.settings.json")

    def _create_settings_vars(self):
        return {
            key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value)))
            for key, value in DEFAULT_COPY_SETTINGS.items()
        }

    def _collect_copy_settings(self):
        settings = {}
        for key, var in self.copy_settings_vars.items():
            value = var.get()
            if isinstance(var, tk.BooleanVar):
                settings[key] = bool(value)
            else:
                settings[key] = str(value).strip()
        return settings

    def _load_app_settings(self):
        settings = {"conf_path": self.conf_path, "copy": dict(DEFAULT_COPY_SETTINGS)}
        try:
            if os.path.isfile(self.settings_path):
                with open(self.settings_path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    settings["conf_path"] = loaded.get("conf_path", settings["conf_path"])
                    if isinstance(loaded.get("copy"), dict):
                        settings["copy"].update(loaded["copy"])
        except Exception:
            pass

        self.conf_path = settings["conf_path"]
        self.conf_var.set(self.conf_path)
        for key, value in settings["copy"].items():
            if key in self.copy_settings_vars:
                self.copy_settings_vars[key].set(value)

    def _save_app_settings(self, show_feedback=False):
        payload = {
            "conf_path": self.conf_var.get().strip(),
            "copy": self._collect_copy_settings(),
        }
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        if hasattr(self, "flags_preview_var"):
            self._refresh_flags_preview()
        if show_feedback:
            self._show_message("info", "Configuracoes", "Configuracoes salvas com sucesso.")

    def _reset_copy_settings(self):
        for key, value in DEFAULT_COPY_SETTINGS.items():
            self.copy_settings_vars[key].set(value)
        if hasattr(self, "flags_preview_var"):
            self._refresh_flags_preview()

    def _on_close(self):
        try:
            self._save_app_settings(show_feedback=False)
        except Exception:
            pass
        self.destroy()

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        self.option_add("*Font", "{Segoe UI} 10")
        self.option_add("*TCombobox*Listbox.font", "{Segoe UI} 10")

        style.configure(".", background=SURFACE, foreground=TEXT)
        style.configure("App.TFrame", background=SURFACE)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Hero.TFrame", background=ACCENT)
        style.configure(
            "HeroTitle.TLabel",
            background=ACCENT,
            foreground="white",
            font=("Segoe UI Semibold", 18),
        )
        style.configure(
            "HeroBody.TLabel",
            background=ACCENT,
            foreground="#dbe7ff",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background=CARD,
            foreground=TEXT,
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Value.TLabel",
            background=CARD,
            foreground=TEXT,
            font=("Segoe UI Semibold", 14),
        )
        style.configure(
            "Muted.TLabel",
            background=CARD,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="white",
            borderwidth=0,
            focusthickness=0,
            focuscolor=ACCENT,
            padding=(16, 10),
        )
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_DARK), ("disabled", "#8db1f5")],
            foreground=[("disabled", "#f5f8ff")],
        )
        style.configure(
            "Secondary.TButton",
            background="#e7eefc",
            foreground=ACCENT_DARK,
            padding=(14, 9),
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#d5e3ff"), ("disabled", "#eff3fa")],
            foreground=[("disabled", "#8da2bf")],
        )
        style.configure(
            "Danger.TButton",
            background="#fde6e8",
            foreground=ERROR,
            padding=(14, 9),
            borderwidth=0,
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#f9d5d9"), ("disabled", "#f8ecee")],
            foreground=[("disabled", "#c59197")],
        )
        style.configure(
            "App.TNotebook",
            background=SURFACE,
            borderwidth=0,
            tabmargins=(0, 8, 0, 0),
        )
        style.configure(
            "App.TNotebook.Tab",
            padding=(16, 9),
            background="#dce7fb",
            foreground=TEXT,
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", CARD), ("active", "#e7efff")],
            foreground=[("selected", ACCENT_DARK)],
        )
        style.configure(
            "App.TLabelframe",
            background=CARD,
            bordercolor="#d6e0f0",
            borderwidth=1,
            relief="solid",
            padding=12,
        )
        style.configure(
            "App.TLabelframe.Label",
            background=CARD,
            foreground=TEXT,
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Treeview",
            background="#fbfcff",
            foreground=TEXT,
            fieldbackground="#fbfcff",
            bordercolor="#d6e0f0",
            rowheight=28,
        )
        style.map(
            "Treeview",
            background=[("selected", "#dce7fb")],
            foreground=[("selected", TEXT)],
        )
        style.configure(
            "Treeview.Heading",
            background="#edf3ff",
            foreground=TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor="#e5ebf5",
            background=ACCENT,
            thickness=10,
            borderwidth=0,
        )
        style.configure(
            "Status.TLabel",
            background=SURFACE,
            foreground=TEXT,
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "Hint.TLabel",
            background=SURFACE,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )

    def _build_ui(self):
        root = ttk.Frame(self, style="App.TFrame", padding=14)
        root.pack(fill="both", expand=True)

        self._build_header(root)

        notebook = ttk.Notebook(root, style="App.TNotebook")
        notebook.pack(fill="both", expand=True, pady=(12, 10))

        t1 = ttk.Frame(notebook, style="App.TFrame", padding=2)
        t2 = ttk.Frame(notebook, style="App.TFrame", padding=2)
        t3 = ttk.Frame(notebook, style="App.TFrame", padding=2)
        t4 = ttk.Frame(notebook, style="App.TFrame", padding=2)

        notebook.add(t1, text="Local para Remote")
        notebook.add(t2, text="Remote para Local")
        notebook.add(t3, text="Remote para Remote")
        notebook.add(t4, text="Configuracoes")

        self._build_tab_local_to_remote(t1)
        self._build_tab_remote_to_local(t2)
        self._build_tab_remote_to_remote(t3)
        self._build_tab_settings(t4)

        status = ttk.Frame(root, style="App.TFrame")
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor="w"
        )
        ttk.Label(status, textvariable=self.details_var, style="Hint.TLabel").pack(
            anchor="w", pady=(2, 0)
        )

    def _build_header(self, parent):
        header = ttk.Frame(parent, style="Hero.TFrame", padding=18)
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)

        left = ttk.Frame(header, style="Hero.TFrame")
        left.grid(row=0, column=0, sticky="nsew")
        ttk.Label(left, text="Backup Manager", style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text=(
                "Gerencie copias entre pastas locais e remotes do rclone "
                "com mais seguranca, visibilidade e controle."
            ),
            style="HeroBody.TLabel",
            wraplength=650,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        metrics = ttk.Frame(header, style="Card.TFrame", padding=16)
        metrics.grid(row=0, column=1, sticky="ne", padx=(18, 0))
        ttk.Label(metrics, text="Remotes", style="Section.TLabel").pack(anchor="w")
        ttk.Label(metrics, textvariable=self.remote_count_var, style="Value.TLabel").pack(
            anchor="w", pady=(4, 0)
        )
        ttk.Label(
            metrics,
            text="Arquivo de configuracao ativo",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        self.conf_preview = ttk.Label(
            metrics,
            text=self._shorten_path(self.conf_var.get()),
            style="Muted.TLabel",
            wraplength=260,
            justify="left",
        )
        self.conf_preview.pack(anchor="w", pady=(2, 0))

    def _build_tab_local_to_remote(self, parent):
        form, activity = self._create_transfer_tab_shell(parent)
        self.progress_lr, self.log_lr = self._build_activity_panel(activity)
        self._build_source_picker(
            form,
            0,
            "Origem local",
            self.src_path,
            [("Arquivo", self._pick_file), ("Pasta", self._pick_folder)],
            "Escolha um arquivo ou uma pasta do computador para enviar ao remote.",
        )
        self.cmb_lr_remote, self.tree_lr = self._build_remote_browser(
            form,
            1,
            "Remote destino",
            self._list_lr_root,
            self.lr_subdir,
            "Liste o remote e escolha a pasta de destino onde o conteudo local sera copiado.",
        )
        self._build_operation_panel(
            form,
            2,
            "Copiar para remote",
            "Envia o arquivo ou a pasta local para o caminho remoto selecionado.",
            self._start_local_to_remote,
            "Inicia ou cancela a copia do item local para a pasta remota selecionada.",
        )

        self.tree_lr.bind("<<TreeviewOpen>>", self._on_open_lr)
        self.tree_lr.bind("<<TreeviewSelect>>", self._on_select_lr)

    def _build_tab_remote_to_local(self, parent):
        form, activity = self._create_transfer_tab_shell(parent)
        self.progress_rl, self.log_rl = self._build_activity_panel(activity)
        self.cmb_rl_remote, self.tree_rl = self._build_remote_browser(
            form,
            0,
            "Remote origem",
            self._list_rl_root,
            self.rl_subdir,
            "Liste o remote e escolha a pasta ou arquivo que sera baixado para o computador.",
        )
        self._build_folder_picker(
            form,
            1,
            "Destino local",
            self.dest_local,
            "Selecionar pasta",
            self._pick_dest_folder,
            "Escolha a pasta local que recebera os arquivos copiados do remote.",
        )
        self._build_operation_panel(
            form,
            2,
            "Copiar para local",
            "Baixa o conteudo remoto para a pasta local escolhida.",
            self._start_remote_to_local,
            "Inicia ou cancela a copia do remote para a pasta local selecionada.",
        )

        self.tree_rl.bind("<<TreeviewOpen>>", self._on_open_rl)
        self.tree_rl.bind("<<TreeviewSelect>>", self._on_select_rl)

    def _build_tab_remote_to_remote(self, parent):
        workspace, activity = self._create_transfer_tab_shell(parent, left_weight=12, right_weight=10)
        self.progress_rr, self.log_rr = self._build_activity_panel(activity)

        browser_row = ttk.Frame(workspace, style="Card.TFrame")
        browser_row.grid(row=0, column=0, sticky="nsew")
        browser_row.columnconfigure(0, weight=1)
        browser_row.columnconfigure(1, weight=1)
        browser_row.rowconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)

        left = ttk.Frame(browser_row, style="Card.TFrame")
        right = ttk.Frame(browser_row, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.cmb_rr_src, self.tree_rr_src = self._build_remote_browser(
            left,
            0,
            "Remote origem",
            self._list_rr_src,
            self.rr_src_sub,
            "Escolha a pasta ou arquivo remoto que sera usado como origem da transferencia.",
        )
        self.cmb_rr_dst, self.tree_rr_dst = self._build_remote_browser(
            right,
            0,
            "Remote destino",
            self._list_rr_dst,
            self.rr_dst_sub,
            "Escolha a pasta remota de destino onde o conteudo sera copiado.",
        )
        self._build_dual_operation_panel(
            workspace,
            1,
            "Controla a transferencia entre dois remotes sem passar pelo disco local.",
        )

        self.tree_rr_src.bind("<<TreeviewOpen>>", self._on_open_rr_src)
        self.tree_rr_src.bind("<<TreeviewSelect>>", self._on_select_rr_src)
        self.tree_rr_dst.bind("<<TreeviewOpen>>", self._on_open_rr_dst)
        self.tree_rr_dst.bind("<<TreeviewSelect>>", self._on_select_rr_dst)

    def _build_tab_settings(self, parent):
        scroll_host = self._create_scrollable_surface(parent)
        frame = ttk.LabelFrame(scroll_host, text="Configuracao do rclone", style="App.TLabelframe")
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        top_card = ttk.Frame(frame, style="Card.TFrame")
        top_card.grid(row=0, column=0, sticky="ew")
        top_card.columnconfigure(0, weight=1)
        self._attach_help_icon(
            top_card,
            "Define qual arquivo rclone.conf sera usado para carregar os remotes e executar os comandos.",
        )
        ttk.Label(top_card, text="Arquivo rclone.conf", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(top_card, textvariable=self.conf_var).grid(
            row=1, column=0, sticky="ew", pady=(8, 16)
        )

        actions = ttk.Frame(top_card, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="w")
        self._register_button(
            self._make_button(actions, "Procurar", self._pick_conf, variant="secondary")
        ).pack(side="left", padx=(0, 8))
        self._register_button(
            self._make_button(
                actions, "Recarregar remotes", self.load_remotes, variant="secondary"
            )
        ).pack(side="left", padx=(0, 8))
        self._register_button(
            self._make_button(
                actions, "Abrir rclone config", self._run_rclone_config, variant="primary"
            )
        ).pack(side="left")

        body = ttk.Frame(frame, style="Card.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Card.TFrame")
        right = ttk.Frame(body, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        left.columnconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_settings_group(
            left,
            0,
            "Comportamento da copia",
            [
                ("create_empty_src_dirs", "Criar diretorios vazios"),
                ("error_on_no_transfer", "Falhar se nada for transferido"),
                ("fast_list", "Usar fast-list"),
                ("dry_run", "Executar em dry-run"),
                ("checksum", "Comparar por checksum"),
                ("size_only", "Comparar so por tamanho"),
                ("ignore_existing", "Ignorar arquivos ja existentes"),
                ("update", "Copiar apenas se a origem for mais nova"),
            ],
            "Define como o rclone decide o que copiar, quando considerar sucesso e se deve simular a operacao.",
        )
        self._build_settings_group(
            left,
            1,
            "Transferencia",
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
            "Ajusta desempenho, concorrencia, retentativas e consumo de recursos durante a copia.",
        )
        self._build_settings_group(
            right,
            0,
            "Log e diagnostico",
            [
                ("log_level", "Nivel de log"),
                ("use_json_log", "Usar log em JSON"),
            ],
            "Controla a verbosidade do log mostrado na area de atividade e a forma de saida das mensagens.",
        )
        self._build_settings_summary(
            right,
            1,
            "Mostra a combinacao final de argumentos que sera anexada aos proximos comandos de copia.",
        )

    def _create_scrollable_surface(self, parent):
        shell = ttk.Frame(parent, style="App.TFrame")
        shell.pack(fill="both", expand=True)
        content, _, _ = self._create_scrollable_body(
            shell,
            background=SURFACE,
            content_style="App.TFrame",
            content_padding=(0, 0, 4, 0),
        )
        return content

    def _create_scrollable_body(
        self,
        parent,
        background,
        content_style="App.TFrame",
        content_padding=(0, 0, 0, 0),
    ):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            parent,
            background=background,
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        content = ttk.Frame(canvas, style=content_style, padding=content_padding)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _fit_content_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        def _on_mousewheel(event):
            step = -int(event.delta / 120) if event.delta else 0
            if step:
                canvas.yview_scroll(step, "units")

        def _on_linux_scroll_up(_event):
            canvas.yview_scroll(-1, "units")

        def _on_linux_scroll_down(_event):
            canvas.yview_scroll(1, "units")

        def _bind_mousewheel(_event=None):
            canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
            canvas.bind_all("<Button-4>", _on_linux_scroll_up, add="+")
            canvas.bind_all("<Button-5>", _on_linux_scroll_down, add="+")

        def _unbind_mousewheel(_event=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        content.bind("<Configure>", _sync_scrollregion, add="+")
        canvas.bind("<Configure>", _fit_content_width, add="+")
        for widget in (parent, canvas, content):
            widget.bind("<Enter>", _bind_mousewheel, add="+")
            widget.bind("<Leave>", _unbind_mousewheel, add="+")

        return content, canvas, scrollbar

    def _build_settings_group(self, parent, row, title, fields, help_text=None):
        card = ttk.LabelFrame(parent, text=title, style="App.TLabelframe")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.columnconfigure(2, weight=1)
        if help_text:
            self._attach_help_icon(card, help_text)

        current_row = 0
        for key, label in fields:
            var = self.copy_settings_vars[key]
            if isinstance(var, tk.BooleanVar):
                check = ttk.Checkbutton(
                    card,
                    text=label,
                    variable=var,
                    command=self._refresh_flags_preview,
                )
                check.grid(row=current_row, column=0, sticky="w", pady=4)
                self._attach_help_icon(
                    card,
                    COPY_SETTING_HELP.get(key, f"Ajuda indisponivel para {label.lower()}."),
                    row=current_row,
                    column=1,
                    padx=(4, 10),
                    pady=4,
                )
            else:
                ttk.Label(card, text=label, style="Muted.TLabel").grid(
                    row=current_row, column=0, sticky="w", pady=4, padx=(0, 10)
                )
                self._attach_help_icon(
                    card,
                    COPY_SETTING_HELP.get(key, f"Ajuda indisponivel para {label.lower()}."),
                    row=current_row,
                    column=1,
                    padx=(0, 10),
                    pady=4,
                )
                if key == "log_level":
                    field = ttk.Combobox(card, textvariable=var, values=LOG_LEVELS, state="readonly")
                    field.bind("<<ComboboxSelected>>", lambda _event: self._refresh_flags_preview())
                else:
                    field = ttk.Entry(card, textvariable=var)
                    var.trace_add("write", self._on_setting_var_changed)
                field.grid(row=current_row, column=2, sticky="ew", pady=4)
            current_row += 1

    def _build_settings_summary(self, parent, row, help_text=None):
        card = ttk.LabelFrame(parent, text="Resumo aplicado", style="App.TLabelframe")
        card.grid(row=row, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        parent.rowconfigure(row, weight=1)
        if help_text:
            self._attach_help_icon(card, help_text)

        ttk.Label(
            card,
            text="As opcoes abaixo serao anexadas aos proximos comandos de copia.",
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.flags_preview_var = tk.StringVar()
        preview = ScrolledText(
            card,
            height=10,
            wrap="word",
            bg="#f8fbff",
            fg=TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#d6e0f0",
            highlightcolor="#d6e0f0",
            insertbackground=TEXT,
            font=("Consolas", 9),
        )
        preview.grid(row=1, column=0, sticky="nsew")
        preview.configure(state="disabled")
        self.flags_preview_widget = preview

        footer = ttk.Frame(card, style="Card.TFrame")
        footer.grid(row=2, column=0, sticky="w", pady=(12, 0))
        self._register_button(
            self._make_button(footer, "Salvar configuracoes", lambda: self._save_app_settings(show_feedback=True), variant="primary")
        ).pack(side="left", padx=(0, 8))
        self._register_button(
            self._make_button(footer, "Restaurar padrao", self._reset_settings_ui, variant="secondary")
        ).pack(side="left")
        self._refresh_flags_preview()

    def _create_transfer_tab_shell(self, parent, left_weight=11, right_weight=10):
        container = ttk.Frame(parent, style="App.TFrame")
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=left_weight)
        container.columnconfigure(1, weight=right_weight)
        container.rowconfigure(0, weight=1)
        container.rowconfigure(1, weight=0)

        form = ttk.LabelFrame(container, text="Selecao", style="App.TLabelframe")
        side = ttk.LabelFrame(container, text="Atividade", style="App.TLabelframe")
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        side.columnconfigure(0, weight=1)
        side.rowconfigure(2, weight=1)
        form.columnconfigure(0, weight=1)

        def _reflow_transfer_shell(event=None):
            width = event.width if event is not None else container.winfo_width()
            if width and width < 1120:
                container.columnconfigure(0, weight=1)
                container.columnconfigure(1, weight=0)
                container.rowconfigure(0, weight=1)
                container.rowconfigure(1, weight=1)
                form.grid_configure(row=0, column=0, padx=0, pady=(0, 8))
                side.grid_configure(row=1, column=0, padx=0, pady=(8, 0))
            else:
                container.columnconfigure(0, weight=left_weight)
                container.columnconfigure(1, weight=right_weight)
                container.rowconfigure(0, weight=1)
                container.rowconfigure(1, weight=0)
                form.grid_configure(row=0, column=0, padx=(0, 8), pady=0)
                side.grid_configure(row=0, column=1, padx=(8, 0), pady=0)

        container.bind("<Configure>", _reflow_transfer_shell, add="+")
        self._attach_help_icon(
            form,
            "Use esta area para definir origem, destino e o caminho selecionado antes de iniciar a copia.",
        )
        self._attach_help_icon(
            side,
            "Aqui voce acompanha o progresso da operacao e o log detalhado retornado pelo rclone.",
        )
        return form, side

    def _attach_help_icon(self, parent, text, row=None, column=None, padx=0, pady=0):
        icon = tk.Label(
            parent,
            text="ⓘ",
            bg=CARD,
            fg=MUTED,
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
        )
        if row is None or column is None:
            icon.place(relx=1.0, x=-8, y=2, anchor="ne")
        else:
            icon.grid(row=row, column=column, sticky="w", padx=padx, pady=pady)
        self.tooltips.append(ToolTip(icon, text))
        return icon

    def _build_activity_panel(self, parent):
        ttk.Label(
            parent,
            text="Progresso da operacao",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        progress_widget = ttk.Progressbar(
            parent, style="App.Horizontal.TProgressbar", mode="determinate"
        )
        progress_widget.grid(row=1, column=0, sticky="ew", pady=(10, 12))
        log_widget = self._create_log(parent)
        log_widget.grid(row=2, column=0, sticky="nsew")
        return progress_widget, log_widget

    def _build_source_picker(self, parent, row, title, variable, actions, help_text=None):
        frame = ttk.LabelFrame(parent, text=title, style="App.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        frame.columnconfigure(0, weight=1)
        if help_text:
            self._attach_help_icon(frame, help_text)
        ttk.Entry(frame, textvariable=variable).pack(fill="x", pady=(0, 10))
        buttons = ttk.Frame(frame, style="Card.TFrame")
        buttons.pack(anchor="w")
        for label, command in actions:
            self._register_button(
                self._make_button(buttons, label, command, variant="secondary")
            ).pack(side="left", padx=(0, 8))

    def _build_folder_picker(self, parent, row, title, variable, button_text, command, help_text=None):
        frame = ttk.LabelFrame(parent, text=title, style="App.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        frame.columnconfigure(0, weight=1)
        if help_text:
            self._attach_help_icon(frame, help_text)
        ttk.Entry(frame, textvariable=variable).pack(fill="x", pady=(0, 10))
        self._register_button(
            self._make_button(frame, button_text, command, variant="secondary")
        ).pack(anchor="w")

    def _build_remote_browser(self, parent, row, title, list_command, path_variable, help_text=None):
        frame = ttk.LabelFrame(parent, text=title, style="App.TLabelframe")
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        parent.rowconfigure(row, weight=1)
        if help_text:
            self._attach_help_icon(frame, help_text)

        top = ttk.Frame(frame, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        combo = ttk.Combobox(top, state="readonly")
        combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._register_button(
            self._make_button(top, "Listar", list_command, variant="secondary")
        ).grid(row=0, column=1, sticky="e")

        tree = self._create_tree(frame)
        tree.grid(row=1, column=0, sticky="nsew", pady=(12, 12))

        ttk.Label(frame, text="Caminho selecionado", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(frame, textvariable=path_variable).grid(
            row=3, column=0, sticky="ew", pady=(6, 0)
        )
        return combo, tree

    def _build_operation_panel(self, parent, row, title, description, command, help_text=None):
        panel = ttk.LabelFrame(parent, text=title, style="App.TLabelframe")
        panel.grid(row=row, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)
        if help_text:
            self._attach_help_icon(panel, help_text)
        ttk.Label(
            panel,
            text=description,
            style="Muted.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.grid(row=1, column=0, sticky="w")
        self._register_button(
            self._make_button(actions, "Iniciar copia", command, variant="primary")
        ).pack(side="left", padx=(0, 8))
        self._register_cancel_button(
            self._make_button(actions, "Cancelar copia", self._cancel_copy, variant="danger")
        ).pack(side="left")

    def _build_dual_operation_panel(self, parent, row, help_text=None):
        panel = ttk.LabelFrame(parent, text="Transferencia entre remotes", style="App.TLabelframe")
        panel.grid(row=row, column=0, sticky="ew")
        panel.columnconfigure(0, weight=1)
        if help_text:
            self._attach_help_icon(panel, help_text)
        ttk.Label(
            panel,
            text="Replica o conteudo do remote de origem para o remote de destino escolhido.",
            style="Muted.TLabel",
            wraplength=900,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.grid(row=1, column=0, sticky="w")
        self._register_button(
            self._make_button(
                actions, "Iniciar copia", self._start_remote_to_remote, variant="primary"
            )
        ).pack(side="left", padx=(0, 8))
        self._register_cancel_button(
            self._make_button(actions, "Cancelar copia", self._cancel_copy, variant="danger")
        ).pack(side="left")

    def _create_tree(self, parent):
        tree = ttk.Treeview(parent, columns=("kind", "fullpath"), show="tree headings", height=10)
        tree.heading("#0", text="Nome")
        tree.heading("kind", text="Tipo")
        tree.heading("fullpath", text="Caminho")
        tree.column("#0", width=240, anchor="w")
        tree.column("kind", width=90, anchor="center")
        tree.column("fullpath", width=300, anchor="w")
        return tree

    def _kind_label(self, kind):
        labels = {
            "dir": "Pasta",
            "file": "Arquivo",
            "loading": "...",
        }
        return labels.get((kind or "").strip().lower(), kind)

    def _kind_icon(self, kind):
        icons = {
            "dir": "📁",
            "file": "📄",
            "loading": "⏳",
        }
        return icons.get((kind or "").strip().lower(), "•")

    def _item_text(self, name, kind):
        return f"{self._kind_icon(kind)} {name}"

    def _create_log(self, parent):
        log = ScrolledText(
            parent,
            height=12,
            wrap="word",
            bg="#f8fbff",
            fg=TEXT,
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#d6e0f0",
            highlightcolor="#d6e0f0",
            insertbackground=TEXT,
            font=("Consolas", 9),
        )
        log.configure(state="disabled")
        self.log_widgets.append(log)
        return log

    def _make_button(self, parent, text, command, variant="secondary"):
        palette = {
            "primary": {
                "bg": ACCENT,
                "fg": "white",
                "activebackground": ACCENT_DARK,
                "activeforeground": "white",
            },
            "secondary": {
                "bg": "#e7eefc",
                "fg": ACCENT_DARK,
                "activebackground": "#d5e3ff",
                "activeforeground": ACCENT_DARK,
            },
            "danger": {
                "bg": "#fde6e8",
                "fg": ERROR,
                "activebackground": "#f7cfd4",
                "activeforeground": ERROR,
            },
        }[variant]
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=palette["bg"],
            fg=palette["fg"],
            activebackground=palette["activebackground"],
            activeforeground=palette["activeforeground"],
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI Semibold" if variant == "primary" else "Segoe UI", 10),
        )

    def _register_button(self, button):
        self.action_buttons.append(button)
        return button

    def _register_cancel_button(self, button):
        self.cancel_buttons.append(button)
        return self._register_button(button)

    def _shorten_path(self, value, max_len=42):
        if len(value) <= max_len:
            return value
        return f"...{value[-(max_len - 3):]}"

    def _rclone_base_cmd(self, config_path=None):
        if not os.path.isfile(self.rclone_bin):
            raise FileNotFoundError(
                "Nao foi possivel localizar o rclone.exe. Mantenha o arquivo ao lado do app."
            )
        return [self.rclone_bin, *self._config_args(config_path)]

    def _config_args(self, config_path=None):
        path = (config_path if config_path is not None else self.conf_var.get()).strip()
        if path:
            return ["--config", path]
        return []

    def _remote_target(self, remote, subdir):
        clean = (subdir or "").strip().strip("/")
        if clean:
            return f"{remote}:/{clean}"
        return f"{remote}:/"

    def _on_setting_var_changed(self, *_args):
        if hasattr(self, "flags_preview_var"):
            self._refresh_flags_preview()

    def _reset_settings_ui(self):
        self._reset_copy_settings()
        self.conf_var.set(self.conf_path)
        self.conf_preview.configure(text=self._shorten_path(self.conf_var.get()))
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
        preview = " ".join(self._build_copy_flags()) or "(sem flags)"
        self.flags_preview_widget.configure(state="normal")
        self.flags_preview_widget.delete("1.0", tk.END)
        self.flags_preview_widget.insert(tk.END, preview)
        self.flags_preview_widget.configure(state="disabled")

    def _build_copy_command(self, source, target):
        return [*self._rclone_base_cmd(), "copy", source, target, *self._build_copy_flags()]

    def _set_status(self, headline, details=None):
        self.status_var.set(headline)
        if details is not None:
            self.details_var.set(details)

    def _set_busy(self, busy, operation_name=""):
        for button in self.action_buttons:
            try:
                button.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if busy:
            for button in self.cancel_buttons:
                try:
                    button.configure(state="normal")
                except tk.TclError:
                    pass

        if busy:
            self.status_var.set(f"Executando: {operation_name}")
        else:
            if not self.status_var.get().startswith("Erro"):
                self.status_var.set("Pronto para iniciar.")

    def _append_log(self, widget, text, reset=False):
        widget.configure(state="normal")
        if reset:
            widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.see(tk.END)
        widget.configure(state="disabled")

    def _show_message(self, kind, title, message):
        if kind == "info":
            messagebox.showinfo(title, message)
        elif kind == "warning":
            messagebox.showwarning(title, message)
        else:
            messagebox.showerror(title, message)

    def _run_on_ui(self, callback, *args, **kwargs):
        self.after(0, lambda: callback(*args, **kwargs))

    def _start_operation(self, name, cmd, log_widget, progress_widget):
        if self.active_operation:
            self._show_message("warning", "Operacao em andamento", "Ja existe uma copia em execucao.")
            return

        self.active_operation = {
            "name": name,
            "proc": None,
            "cancelled": False,
            "log": log_widget,
            "progress": progress_widget,
        }
        self._append_log(log_widget, "", reset=True)
        progress_widget.configure(value=0, maximum=1)
        self._set_busy(True, name)
        self.details_var.set("Aguardando retorno do rclone...")

        threading.Thread(
            target=self._run_copy_worker,
            args=(cmd, self.active_operation),
            daemon=True,
        ).start()

    def _run_copy_worker(self, cmd, operation):
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            self._run_on_ui(self._finish_operation_error, operation, str(exc))
            return

        operation["proc"] = proc
        self._run_on_ui(
            self._append_log,
            operation["log"],
            "Comando iniciado com sucesso.\n\n",
        )

        for line in iter(proc.stdout.readline, ""):
            self._run_on_ui(self._append_log, operation["log"], line)
            self._run_on_ui(self._update_progress_from_line, operation["progress"], line)

        rc = proc.wait()
        self._run_on_ui(self._finish_operation_result, operation, rc)

    def _update_progress_from_line(self, progress_widget, line):
        bytes_match = PAT_BYTES.search(line)
        if bytes_match:
            try:
                current = parse_size(bytes_match.group(1))
                total = parse_size(bytes_match.group(2))
            except ValueError:
                current = total = 0
            if total > 0:
                progress_widget.configure(value=current, maximum=total)
                self.details_var.set(
                    f"Transferido {bytes_match.group(1)} de {bytes_match.group(2)}."
                )
                return

        files_match = PAT_FILES.search(line)
        if files_match:
            current = int(files_match.group(1))
            total = int(files_match.group(2))
            if total > 0:
                progress_widget.configure(value=current, maximum=total)
                self.details_var.set(f"Arquivos transferidos: {current}/{total}.")

    def _finish_operation_error(self, operation, message):
        self.active_operation = None
        self._set_busy(False)
        self.status_var.set("Erro ao iniciar a operacao.")
        self.details_var.set(message)
        self._show_message("error", "Erro", f"Nao foi possivel iniciar a copia:\n{message}")

    def _finish_operation_result(self, operation, return_code):
        if self.active_operation is not operation:
            return

        self.active_operation = None
        self._set_busy(False)

        if operation["cancelled"]:
            self.status_var.set("Operacao cancelada.")
            self.details_var.set("A copia foi interrompida pelo usuario.")
            self._show_message("info", "Cancelado", "Copia interrompida.")
            return

        if return_code == 0:
            operation["progress"].configure(value=operation["progress"]["maximum"])
            self.status_var.set("Operacao concluida com sucesso.")
            self.details_var.set("O rclone finalizou sem erros.")
            self._show_message("info", "Concluido", "Operacao finalizada com sucesso.")
            return

        self.status_var.set("Erro durante a operacao.")
        self.details_var.set(f"O rclone finalizou com codigo {return_code}.")
        self._show_message(
            "error",
            "Falha na copia",
            f"O rclone finalizou com erro (codigo {return_code}). Consulte o log da operacao.",
        )

    def _start_local_to_remote(self):
        source = self.src_path.get().strip()
        remote = self.cmb_lr_remote.get().strip()
        if not source or not remote:
            self._show_message("warning", "Campos obrigatorios", "Informe a origem local e o remote de destino.")
            return
        if not os.path.exists(source):
            self._show_message("error", "Origem invalida", "O caminho local informado nao existe.")
            return

        target = self._remote_target(remote, self.lr_subdir.get())
        self._start_operation(
            "Local para Remote",
            self._build_copy_command(source, target),
            self.log_lr,
            self.progress_lr,
        )

    def _start_remote_to_local(self):
        remote = self.cmb_rl_remote.get().strip()
        destination = self.dest_local.get().strip()
        if not remote or not destination:
            self._show_message("warning", "Campos obrigatorios", "Informe o remote de origem e a pasta local de destino.")
            return
        if not os.path.isdir(destination):
            self._show_message("error", "Destino invalido", "Selecione uma pasta local valida.")
            return

        source = self._remote_target(remote, self.rl_subdir.get())
        self._start_operation(
            "Remote para Local",
            self._build_copy_command(source, destination),
            self.log_rl,
            self.progress_rl,
        )

    def _start_remote_to_remote(self):
        source_remote = self.cmb_rr_src.get().strip()
        destination_remote = self.cmb_rr_dst.get().strip()
        if not source_remote or not destination_remote:
            self._show_message("warning", "Campos obrigatorios", "Selecione os remotes de origem e destino.")
            return

        source = self._remote_target(source_remote, self.rr_src_sub.get())
        target = self._remote_target(destination_remote, self.rr_dst_sub.get())
        self._start_operation(
            "Remote para Remote",
            self._build_copy_command(source, target),
            self.log_rr,
            self.progress_rr,
        )

    def _cancel_copy(self):
        if not self.active_operation or self.active_operation["proc"] is None:
            self._show_message("info", "Sem atividade", "Nenhuma copia em andamento.")
            return

        proc = self.active_operation["proc"]
        if proc.poll() is not None:
            self._show_message("info", "Sem atividade", "Nenhuma copia em andamento.")
            return

        self.active_operation["cancelled"] = True
        self.details_var.set("Solicitando cancelamento...")
        try:
            proc.terminate()
        except Exception as exc:
            self._show_message("error", "Erro", f"Nao foi possivel cancelar a copia:\n{exc}")

    def _run_rclone_config(self):
        try:
            subprocess.Popen(
                [*self._rclone_base_cmd(), "config"],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        except Exception as exc:
            self._show_message(
                "error",
                "Erro",
                f"Nao foi possivel abrir o configurador do rclone:\n{exc}",
            )

    def _pick_conf(self):
        filename = filedialog.askopenfilename(
            title="Selecione o arquivo rclone.conf",
            initialfile="rclone.conf",
            filetypes=[("Config Rclone", "rclone.conf"), ("Todos", "*.*")],
        )
        if filename:
            self.conf_path = filename
            self.conf_var.set(filename)
            self.conf_preview.configure(text=self._shorten_path(filename))
            self.load_remotes()

    def load_remotes(self):
        path = self.conf_var.get().strip()
        self.conf_path = path
        if not os.path.isfile(path):
            self.remote_count_var.set("0 remotes carregados")
            self.conf_preview.configure(text=self._shorten_path(path))
            self._show_message("error", "Arquivo nao encontrado", path)
            return

        parser = configparser.RawConfigParser()
        parser.read(path, encoding="utf-8")
        self.remotes = parser.sections()
        self.remote_count_var.set(f"{len(self.remotes)} remotes carregados")
        self.conf_preview.configure(text=self._shorten_path(path))

        combos = (
            self.cmb_lr_remote,
            self.cmb_rl_remote,
            self.cmb_rr_src,
            self.cmb_rr_dst,
        )
        for combo in combos:
            combo["values"] = self.remotes
            if self.remotes:
                combo.current(0)
            else:
                combo.set("")

        self._set_status(
            "Configuracao atualizada.",
            "Remotes recarregados a partir do arquivo selecionado.",
        )

    def _list_lr_root(self):
        self._refresh_tree_async(self.tree_lr, self.cmb_lr_remote.get(), "", "")

    def _list_rl_root(self):
        self._refresh_tree_async(self.tree_rl, self.cmb_rl_remote.get(), "", "")

    def _list_rr_src(self):
        self._refresh_tree_async(self.tree_rr_src, self.cmb_rr_src.get(), "", "")

    def _list_rr_dst(self):
        self._refresh_tree_async(self.tree_rr_dst, self.cmb_rr_dst.get(), "", "")

    def _on_open_lr(self, _event):
        self._open_tree_node(self.tree_lr, self.cmb_lr_remote.get(), self.lr_subdir, allow_files=False)

    def _on_select_lr(self, _event):
        self._sync_selected_path(self.tree_lr, self.lr_subdir, allow_files=False)

    def _on_open_rl(self, _event):
        self._open_tree_node(self.tree_rl, self.cmb_rl_remote.get(), self.rl_subdir, allow_files=True)

    def _on_select_rl(self, _event):
        self._sync_selected_path(self.tree_rl, self.rl_subdir, allow_files=True)

    def _on_open_rr_src(self, _event):
        self._open_tree_node(self.tree_rr_src, self.cmb_rr_src.get(), self.rr_src_sub, allow_files=True)

    def _on_select_rr_src(self, _event):
        self._sync_selected_path(self.tree_rr_src, self.rr_src_sub, allow_files=True)

    def _on_open_rr_dst(self, _event):
        self._open_tree_node(self.tree_rr_dst, self.cmb_rr_dst.get(), self.rr_dst_sub, allow_files=False)

    def _on_select_rr_dst(self, _event):
        self._sync_selected_path(self.tree_rr_dst, self.rr_dst_sub, allow_files=False)

    def _item_kind(self, tree, item):
        raw_kind = (tree.set(item, "kind") or "dir").strip().lower()
        aliases = {
            "pasta": "dir",
            "arquivo": "file",
            "...": "loading",
        }
        return aliases.get(raw_kind, raw_kind)

    def _parent_remote_path(self, path):
        clean = (path or "").strip().strip("/")
        if not clean:
            return "/"
        if "/" not in clean:
            return "/"
        return clean.rsplit("/", 1)[0] or "/"

    def _sync_selected_path(self, tree, variable, allow_files):
        item = tree.focus()
        if item:
            selected_path = tree.set(item, "fullpath") or "/"
            if self._item_kind(tree, item) == "file" and not allow_files:
                parent_path = self._parent_remote_path(selected_path)
                variable.set(parent_path)
                self.details_var.set(
                    "Arquivo selecionado como referencia visual. O destino usa a pasta pai."
                )
                return
            variable.set(selected_path)

    def _open_tree_node(self, tree, remote, variable, allow_files):
        item = tree.focus()
        if not item:
            return

        if self._item_kind(tree, item) != "dir":
            self._sync_selected_path(tree, variable, allow_files=allow_files)
            return

        path = tree.set(item, "fullpath")
        variable.set(path or "/")
        tree.delete(*tree.get_children(item))
        self._refresh_tree_async(tree, remote, path, item)

    def _refresh_tree_async(self, tree, remote, path, parent_iid):
        remote = (remote or "").strip()
        if not remote:
            self._show_message("warning", "Remote obrigatorio", "Selecione um remote para listar os itens.")
            return

        if not parent_iid:
            tree.delete(*tree.get_children())

        placeholder = "__loading__" if not parent_iid else f"{parent_iid}__loading__"
        if tree.exists(placeholder):
            tree.delete(placeholder)
        tree.insert(
            parent_iid,
            "end",
            iid=placeholder,
            text=self._item_text("Carregando...", "loading"),
            values=(self._kind_label("loading"), "carregando"),
        )
        self._set_status("Carregando itens...", f"Lendo {self._remote_target(remote, path)}")

        config_path = self.conf_var.get().strip()

        threading.Thread(
            target=self._load_tree_worker,
            args=(tree, remote, path, parent_iid, placeholder, config_path),
            daemon=True,
        ).start()

    def _load_tree_worker(self, tree, remote, path, parent_iid, placeholder, config_path):
        try:
            target = self._remote_target(remote, path)
            cmd = [*self._rclone_base_cmd(config_path), "lsjson", target]
            result = subprocess.run(
                cmd,
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
            self._run_on_ui(
                self._populate_tree_result,
                tree,
                path,
                parent_iid,
                placeholder,
                items,
                None,
            )
        except Exception as exc:
            self._run_on_ui(
                self._populate_tree_result,
                tree,
                path,
                parent_iid,
                placeholder,
                [],
                str(exc),
            )

    def _populate_tree_result(self, tree, path, parent_iid, placeholder, items, error):
        if tree.exists(placeholder):
            tree.delete(placeholder)

        if error:
            self.status_var.set("Erro ao listar itens.")
            self.details_var.set(error)
            self._show_message("error", "Falha ao listar itens", error)
            return

        for entry in items:
            name = entry["name"]
            kind = entry["kind"]
            full = f"{path}/{name}".strip("/")
            iid = full or name
            if not tree.exists(iid):
                tree.insert(
                    parent_iid,
                    "end",
                    iid=iid,
                    text=self._item_text(name, kind),
                    values=(self._kind_label(kind), full),
                )
                if kind == "dir":
                    tree.insert(iid, "end", iid=f"{iid}__dummy__", text="")

        self._set_status("Itens carregados.", "A estrutura remota foi atualizada.")

    def _pick_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            self.src_path.set(filename)

    def _pick_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self.src_path.set(directory)

    def _pick_dest_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dest_local.set(directory)


if __name__ == "__main__":
    app = RcloneManagerGUI()
    app.mainloop()
