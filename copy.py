import os
import re
import sys
import threading
import subprocess
import configparser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

PAT_BYTES = re.compile(
    r"Transferred:\s*([\d\.]+\s*(?:[KMGT]?iB|B))\s*/\s*([\d\.]+\s*(?:[KMGT]?iB|B))",
    re.IGNORECASE
)
PAT_FILES = re.compile(r"Transferred:\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)

def parse_size(s):
    num, unit = re.match(r"([\d\.]+)\s*([KMGT]?iB|B)", s, re.IGNORECASE).groups()
    num = float(num)
    unit = unit.upper()
    mult = {"B":1, "KIB":1024, "MIB":1024**2, "GIB":1024**3, "TIB":1024**4}
    return int(num * mult[unit])

class RcloneManagerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rclone Copy Manager")
        self.geometry("900x650")

        # Caminho absoluto do rclone.exe (na pasta do exe/script)
        self.rclone_bin = os.path.join(os.path.dirname(sys.executable), "rclone.exe")

        self.current_proc = None
        self.conf_path = os.path.join(
            os.environ["USERPROFILE"], r"AppData\Roaming\rclone\rclone.conf"
        )
        self.remotes = []

        self._build_ui()
        self.load_remotes()

    def _build_ui(self):
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)

        t1 = ttk.Frame(nb); nb.add(t1, text="Local → Remote")
        self._build_tab_local_to_remote(t1)

        t2 = ttk.Frame(nb); nb.add(t2, text="Remote → Local")
        self._build_tab_remote_to_local(t2)

        t3 = ttk.Frame(nb); nb.add(t3, text="Remote → Remote")
        self._build_tab_remote_to_remote(t3)

        t4 = ttk.Frame(nb); nb.add(t4, text="Configurações")
        self._build_tab_settings(t4)

    # ─── TAB 1 ────────────────────────────────────────────────────────────────
    def _build_tab_local_to_remote(self, p):
        frm = ttk.LabelFrame(p, text="Origem Local"); frm.pack(fill="x", padx=10, pady=5)
        self.src_path = tk.StringVar()
        ttk.Button(frm, text="Arquivo", command=self._pick_file).pack(side="left", padx=5)
        ttk.Button(frm, text="Pasta",   command=self._pick_folder).pack(side="left", padx=5)
        ttk.Label(frm, textvariable=self.src_path).pack(side="left", padx=10)

        frm2 = ttk.LabelFrame(p, text="Remote Destino"); frm2.pack(fill="x", padx=10, pady=5)
        self.cmb_lr_remote = ttk.Combobox(frm2, state="readonly"); self.cmb_lr_remote.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(frm2, text="Listar Raiz", command=self._list_lr_root).pack(side="left", padx=5)

        self.tree_lr = ttk.Treeview(p, columns=("fullpath",), show="tree")
        self.tree_lr.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_lr.bind("<<TreeviewOpen>>",   self._on_open_lr)
        self.tree_lr.bind("<<TreeviewSelect>>", self._on_select_lr)

        frm3 = ttk.LabelFrame(p, text="Pasta Destino"); frm3.pack(fill="x", padx=10, pady=5)
        self.lr_subdir = tk.StringVar(value="/"); ttk.Entry(frm3, textvariable=self.lr_subdir).pack(fill="x", expand=True, padx=5)

        ttk.Button(p, text="Iniciar Cópia", command=self._start_local_to_remote).pack(pady=5)
        ttk.Button(p, text="Cancelar Cópia", command=self._cancel_copy).pack()
        self.progress_lr = ttk.Progressbar(p, orient="horizontal", mode="determinate", length=600)
        self.progress_lr.pack(padx=10, pady=5)
        self.log_lr = ScrolledText(p, height=10); self.log_lr.pack(fill="both", expand=True, padx=10, pady=5)

    def _list_lr_root(self):
        r = self.cmb_lr_remote.get()
        if not r:
            messagebox.showwarning("Selecione um remote", "")
            return
        self.tree_lr.delete(*self.tree_lr.get_children())
        self._populate_tree(self.tree_lr, r, "", "")

    def _on_open_lr(self, e):
        tr, item = self.tree_lr, self.tree_lr.focus()
        tr.delete(*tr.get_children(item))
        path = tr.set(item, "fullpath")
        self._populate_tree(tr, self.cmb_lr_remote.get(), path, item)
        self.lr_subdir.set(path or "/")

    def _on_select_lr(self, e):
        item = self.tree_lr.focus()
        if item:
            self.lr_subdir.set(self.tree_lr.set(item, "fullpath") or "/")

    def _start_local_to_remote(self):
        src = self.src_path.get(); r = self.cmb_lr_remote.get()
        sub = self.lr_subdir.get().strip("/") or ""
        if not src or not r:
            messagebox.showwarning("Origem e remote necessários", "Preencha todos os campos!")
            return
        dest = f"{r}:/{sub}"
        cmd = [
            self.rclone_bin, "copy", src, dest,
            "--progress", "--stats=1s",
            "--fast-list","--update","--size-only",
            "--buffer-size","2G","--retries","5","--low-level-retries","10",
            "--transfers","2","--checkers","6","--tpslimit","1",
            "--drive-chunk-size","256M","--drive-pacer-min-sleep","100ms",
            "--drive-pacer-burst","100","--multi-thread-streams","4"
        ]
        threading.Thread(target=self._run_cmd,
                         args=(cmd, self.log_lr, self.progress_lr),
                         daemon=True).start()

    # ─── TAB 2 ────────────────────────────────────────────────────────────────
    def _build_tab_remote_to_local(self, p):
        frm = ttk.LabelFrame(p, text="Remote Origem"); frm.pack(fill="x", padx=10, pady=5)
        self.cmb_rl_remote = ttk.Combobox(frm, state="readonly"); self.cmb_rl_remote.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(frm, text="Listar Raiz", command=self._list_rl_root).pack(side="left", padx=5)

        self.tree_rl = ttk.Treeview(p, columns=("fullpath",), show="tree")
        self.tree_rl.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_rl.bind("<<TreeviewOpen>>",   self._on_open_rl)
        self.tree_rl.bind("<<TreeviewSelect>>", self._on_select_rl)

        frm2 = ttk.LabelFrame(p, text="Pasta Origem"); frm2.pack(fill="x", padx=10, pady=5)
        self.rl_subdir = tk.StringVar(value="/"); ttk.Entry(frm2, textvariable=self.rl_subdir).pack(fill="x", expand=True, padx=5)

        frm3 = ttk.LabelFrame(p, text="Destino Local"); frm3.pack(fill="x", padx=10, pady=5)
        self.dest_local = tk.StringVar()
        ttk.Button(frm3, text="Selecionar Pasta", command=self._pick_dest_folder).pack(side="left", padx=5)
        ttk.Label(frm3, textvariable=self.dest_local).pack(side="left", padx=10)

        ttk.Button(p, text="Iniciar Cópia", command=self._start_remote_to_local).pack(pady=5)
        ttk.Button(p, text="Cancelar Cópia", command=self._cancel_copy).pack()
        self.progress_rl = ttk.Progressbar(p, orient="horizontal", mode="determinate", length=600)
        self.progress_rl.pack(padx=10, pady=5)
        self.log_rl = ScrolledText(p, height=10); self.log_rl.pack(fill="both", expand=True, padx=10, pady=5)

    def _list_rl_root(self):
        r = self.cmb_rl_remote.get()
        if not r: return
        self.tree_rl.delete(*self.tree_rl.get_children())
        self._populate_tree(self.tree_rl, r, "", "")

    def _on_open_rl(self, e):
        tr, item = self.tree_rl, self.tree_rl.focus()
        tr.delete(*tr.get_children(item))
        path = tr.set(item, "fullpath")
        self._populate_tree(tr, self.cmb_rl_remote.get(), path, item)
        self.rl_subdir.set(path or "/")

    def _on_select_rl(self, e):
        item = self.tree_rl.focus()
        if item:
            self.rl_subdir.set(self.tree_rl.set(item, "fullpath") or "/")

    def _start_remote_to_local(self):
        r = self.cmb_rl_remote.get(); sub = self.rl_subdir.get().strip("/") or ""
        dst = self.dest_local.get()
        if not r or not dst:
            messagebox.showwarning("Remote e destino necessários", "Preencha todos os campos!")
            return
        cmd = [
            self.rclone_bin, "copy", f"{r}:/{sub}", dst,
            "--progress", "--stats=1s",
            "--fast-list","--update","--size-only",
            "--buffer-size","2G","--retries","5","--low-level-retries","10",
            "--transfers","2","--checkers","6","--tpslimit","1",
            "--drive-chunk-size","256M","--drive-pacer-min-sleep","100ms",
            "--drive-pacer-burst","100","--multi-thread-streams","4"
        ]
        threading.Thread(target=self._run_cmd,
                         args=(cmd, self.log_rl, self.progress_rl),
                         daemon=True).start()

    # ─── TAB 3 ────────────────────────────────────────────────────────────────
    def _build_tab_remote_to_remote(self, p):
        frm1 = ttk.LabelFrame(p, text="Remote Origem"); frm1.pack(fill="x", padx=10, pady=5)
        self.cmb_rr_src = ttk.Combobox(frm1, state="readonly"); self.cmb_rr_src.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(frm1, text="Listar Raiz", command=self._list_rr_src).pack(side="left", padx=5)

        self.tree_rr_src = ttk.Treeview(p, columns=("fullpath",), show="tree")
        self.tree_rr_src.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_rr_src.bind("<<TreeviewOpen>>",   self._on_open_rr_src)
        self.tree_rr_src.bind("<<TreeviewSelect>>", self._on_select_rr_src)

        frm2 = ttk.LabelFrame(p, text="Pasta Origem"); frm2.pack(fill="x", padx=10, pady=5)
        self.rr_src_sub = tk.StringVar(value="/"); ttk.Entry(frm2, textvariable=self.rr_src_sub).pack(fill="x", expand=True, padx=5)

        frm3 = ttk.LabelFrame(p, text="Remote Destino"); frm3.pack(fill="x", padx=10, pady=5)
        self.cmb_rr_dst = ttk.Combobox(frm3, state="readonly"); self.cmb_rr_dst.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(frm3, text="Listar Raiz", command=self._list_rr_dst).pack(side="left", padx=5)

        self.tree_rr_dst = ttk.Treeview(p, columns=("fullpath",), show="tree")
        self.tree_rr_dst.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree_rr_dst.bind("<<TreeviewOpen>>",   self._on_open_rr_dst)
        self.tree_rr_dst.bind("<<TreeviewSelect>>", self._on_select_rr_dst)

        frm4 = ttk.LabelFrame(p, text="Pasta Destino"); frm4.pack(fill="x", padx=10, pady=5)
        self.rr_dst_sub = tk.StringVar(value="/"); ttk.Entry(frm4, textvariable=self.rr_dst_sub).pack(fill="x", expand=True, padx=5)

        ttk.Button(p, text="Iniciar Cópia",     command=self._start_remote_to_remote).pack(pady=5)
        ttk.Button(p, text="Cancelar Cópia",     command=self._cancel_copy).pack()
        self.progress_rr = ttk.Progressbar(p, orient="horizontal", mode="determinate", length=600)
        self.progress_rr.pack(padx=10, pady=5)
        self.log_rr = ScrolledText(p, height=10); self.log_rr.pack(fill="both", expand=True, padx=10, pady=5)

    def _list_rr_src(self):
        r = self.cmb_rr_src.get()
        if not r: return
        self.tree_rr_src.delete(*self.tree_rr_src.get_children())
        self._populate_tree(self.tree_rr_src, r, "", "")

    def _on_open_rr_src(self, e):
        tr, item = self.tree_rr_src, self.tree_rr_src.focus()
        tr.delete(*tr.get_children(item))
        path = tr.set(item, "fullpath")
        self._populate_tree(tr, self.cmb_rr_src.get(), path, item)
        self.rr_src_sub.set(path or "/")

    def _on_select_rr_src(self, e):
        item = self.tree_rr_src.focus()
        if item:
            self.rr_src_sub.set(self.tree_rr_src.set(item, "fullpath") or "/")

    def _list_rr_dst(self):
        r = self.cmb_rr_dst.get()
        if not r: return
        self.tree_rr_dst.delete(*self.tree_rr_dst.get_children())
        self._populate_tree(self.tree_rr_dst, r, "", "")

    def _on_open_rr_dst(self, e):
        tr, item = self.tree_rr_dst, self.tree_rr_dst.focus()
        tr.delete(*tr.get_children(item))
        path = tr.set(item, "fullpath")
        self._populate_tree(tr, self.cmb_rr_dst.get(), path, item)
        self.rr_dst_sub.set(path or "/")

    def _on_select_rr_dst(self, e):
        item = self.tree_rr_dst.focus()
        if item:
            self.rr_dst_sub.set(self.tree_rr_dst.set(item, "fullpath") or "/")

    def _start_remote_to_remote(self):
        src = self.cmb_rr_src.get(); dst = self.cmb_rr_dst.get()
        a   = self.rr_src_sub.get().strip("/") or ""
        b   = self.rr_dst_sub.get().strip("/") or ""
        if not src or not dst:
            messagebox.showwarning("Escolha ambos os remotes", "Preencha todos os campos!")
            return
        cmd = [
            self.rclone_bin, "copy", f"{src}:/{a}", f"{dst}:/{b}",
            "--progress", "--stats=1s",
            "--fast-list","--update","--size-only",
            "--buffer-size","2G","--retries","5","--low-level-retries","10",
            "--transfers","2","--checkers","6","--tpslimit","1",
            "--drive-chunk-size","256M","--drive-pacer-min-sleep","100ms",
            "--drive-pacer-burst","100","--multi-thread-streams","4"
        ]
        threading.Thread(
            target=self._run_cmd,
            args=(cmd, self.log_rr, self.progress_rr),
            daemon=True
        ).start()

    # ─── SETTINGS ────────────────────────────────────────────────────────────────
    def _build_tab_settings(self, p):
        frm = ttk.LabelFrame(p, text="rclone.conf"); frm.pack(fill="x", padx=10, pady=10)
        self.conf_var = tk.StringVar(value=self.conf_path)
        ttk.Entry(frm, textvariable=self.conf_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(frm, text="Procurar...", command=self._pick_conf).pack(side="left", padx=5)
        ttk.Button(frm, text="Recarregar Remotes", command=self.load_remotes).pack(side="left", padx=5)
        ttk.Button(frm, text="Configurar Novo Remote", command=self._run_rclone_config).pack(side="left", padx=5)

    def _run_rclone_config(self):
        try:
            # Abre o cmd já apontando para rclone.exe da raiz
            subprocess.Popen(f'start cmd /K "{self.rclone_bin} config"', shell=True)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o rclone config:\n{e}")

    def _pick_conf(self):
        fn = filedialog.askopenfilename(
            title="Selecione rclone.conf", initialfile="rclone.conf",
            filetypes=[("Config Rclone","rclone.conf"),("Todos","*.*")]
        )
        if fn:
            self.conf_var.set(fn)
            self.conf_path = fn

    def load_remotes(self):
        path = self.conf_var.get()
        if not os.path.isfile(path):
            messagebox.showerror("Arquivo não encontrado", path)
            return
        cfg = configparser.ConfigParser()
        cfg.read(path)
        self.remotes = cfg.sections()
        for cmb in (self.cmb_lr_remote, self.cmb_rl_remote, self.cmb_rr_src, self.cmb_rr_dst):
            cmb["values"] = self.remotes
            if self.remotes: cmb.current(0)

    def _populate_tree(self, tree, remote, path, parent_iid):
        # Usa sempre aspas duplas para lidar com espaços/caracteres especiais no caminho
        arg = f'{remote}:/{path}' if path else f'{remote}:/'
        cmd = [self.rclone_bin, "lsd", arg]
        try:
            raw = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            lines = raw.decode("utf-8", errors="replace").splitlines()
        except subprocess.CalledProcessError as e:
            lines = e.output.decode("utf-8", errors="replace").splitlines()

        for line in lines:
            line = line.rstrip()
            # Divide por espaços, mas preserva o nome da pasta completo (após a quarta coluna)
            parts = line.split()
            if not parts or not parts[0].lstrip("-").isdigit():
                continue
            if len(parts) < 5:
                continue
            name = " ".join(parts[4:])  # Nome da pasta pode ter espaço/til/acentos
            full = f"{path}/{name}".lstrip("/")
            iid, dummy = full, f"{full}-dummy"
            if not tree.exists(iid):
                tree.insert(parent_iid, "end", iid=iid, text=name, values=(full,))
            if not tree.exists(dummy):
                tree.insert(iid, "end", iid=dummy)

    def _run_cmd(self, cmd, log_widget, progress_widget):
        log_widget.delete("1.0", tk.END)
        progress_widget["value"]   = 0
        progress_widget["maximum"] = 1
        self.current_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        while True:
            line = self.current_proc.stdout.readline()
            if not line:
                break
            try:
                decoded = line.decode("utf-8", errors="replace")
            except Exception:
                continue
            log_widget.insert(tk.END, decoded)
            log_widget.see(tk.END)

            m = PAT_BYTES.search(decoded)
            if m:
                try:
                    cur = parse_size(m.group(1))
                    tot = parse_size(m.group(2))
                    if tot > 0:
                        self.after(0, lambda c=cur, t=tot: (
                            progress_widget.config(value=c, maximum=t)
                        ))
                except Exception:
                    pass
            mf = PAT_FILES.search(decoded)
            if mf:
                try:
                    cur_f = int(mf.group(1))
                    tot_f = int(mf.group(2))
                    self.after(0, lambda c=cur_f, t=tot_f: (
                        progress_widget.config(value=c, maximum=t)
                    ))
                except Exception:
                    pass

        self.current_proc.wait()
        self.current_proc = None
        messagebox.showinfo("Concluído", "Operação finalizada!")

    def _cancel_copy(self):
        if self.current_proc and self.current_proc.poll() is None:
            self.current_proc.terminate()
            self.current_proc = None
            messagebox.showinfo("Cancelado", "Cópia interrompida.")
        else:
            messagebox.showinfo("Info", "Nenhuma cópia em andamento.")

    def _pick_file(self):
        fn = filedialog.askopenfilename()
        if fn: self.src_path.set(fn)

    def _pick_folder(self):
        dn = filedialog.askdirectory()
        if dn: self.src_path.set(dn)

    def _pick_dest_folder(self):
        dn = filedialog.askdirectory()
        if dn: self.dest_local.set(dn)

if __name__ == "__main__":
    app = RcloneManagerGUI()
    app.mainloop()
