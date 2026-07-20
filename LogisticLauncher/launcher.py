"""Logistic Launcher — main application shell.

A single panel to launch websites, folders, apps and local Python servers.
v2.0 — 16 new features: sidebar, dashboard, pins, groups, tooltips,
       multi-language, keyboard shortcuts, splash, auto-update, logging,
       fade-in, favicon, export/import, server status, grammar fix, installer.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from app_logging import logger
from i18n import available_languages, get_language, set_language, t
from models import (
    BASE_DIR,
    COLORS,
    CONFIG_PATH,
    DEFAULT_GROUPS,
    DEFAULT_LOCAL_URL,
    GITHUB_REPO,
    IMPORT_EXTENSIONS,
    PYTHON_SERVER_FILES,
    START_FILE_NAMES,
    TYPE_LABELS,
    VERSION,
    export_config,
    import_config,
    initials,
    load_apps,
    load_settings,
    normalize_app,
    save_apps,
    save_settings,
)
from theme import (
    FONT_BODY,
    FONT_FAMILY,
    FONT_FAMILY_BODY,
    FONT_SEARCH,
    FONT_SMALL,
    FONT_TITLE,
    ThemeManager,
)
from widgets import (
    AppEditor,
    CardBuilder,
    DashboardBar,
    DragDropManager,
    GroupTabBar,
    Sidebar,
    SplashScreen,
    render_empty_state,
)

# ---------------------------------------------------------------------------
# Window base dimensions (scaled by DPI factor at runtime)
# ---------------------------------------------------------------------------
BASE_WIDTH = 1100
BASE_HEIGHT = 750
BASE_MIN_WIDTH = 820
BASE_MIN_HEIGHT = 560

# Fade-in animation constants
_FADE_STEPS = 5
_FADE_DELAY = 35  # ms


# ---------------------------------------------------------------------------
# DPI awareness (Windows-only, must be called before Tk() is created)
# ---------------------------------------------------------------------------

def enable_dpi_awareness() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Server health checker
# ---------------------------------------------------------------------------

class ServerStatusChecker:
    """Periodically pings python_server URLs to check if they are online."""

    INTERVAL = 15_000  # ms

    def __init__(self, root: tk.Tk):
        self._root = root
        self.status: dict[str, bool] = {}
        self._urls: list[str] = []

    def set_urls(self, urls: list[str]) -> None:
        self._urls = urls

    def start(self) -> None:
        self._check()

    def _check(self) -> None:
        if not self._urls:
            self._root.after(self.INTERVAL, self._check)
            return

        def _ping() -> None:
            try:
                import urllib.request
                for url in self._urls:
                    try:
                        urllib.request.urlopen(url, timeout=3)
                        self.status[url] = True
                    except Exception:
                        self.status[url] = False
            except Exception:
                pass

        threading.Thread(target=_ping, daemon=True).start()
        self._root.after(self.INTERVAL, self._check)


# ---------------------------------------------------------------------------
# Auto-update checker
# ---------------------------------------------------------------------------

def check_for_updates(root: tk.Tk) -> None:
    """Controlla GitHub per una nuova release in una repo privata."""

    def _work() -> None:
        try:
            import urllib.request
            
            # Sostituisci QUESTA STRINGA con il tuo vero token segreto di GitHub
            token = "IL_TUO_TOKEN_GITHUB"

            # URL corretto per interrogare le release tramite API di GitHub
            url = "https://github.com/Marcu08/App_Gestionale"
            
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("User-Agent", "LogisticLauncher-App")
            
            # Inserisce il token per sbloccare la lettura della repo privata
            if token and token != "IL_TUO_TOKEN_GITHUB":
                req.add_header("Authorization", f"token {token}")
                
            resp = urllib.request.urlopen(req, timeout=5)
            releases = json.loads(resp.read().decode())
            
            # Controlla se ci sono effettivamente delle release create su GitHub
            if not releases or not isinstance(releases, list):
                return
                
            # Prende la versione dall'ultima release pubblicata (il primo elemento della lista)
            latest = releases[0]["tag_name"].lstrip("v")
            
            if latest != VERSION:
                root.after(0, lambda: _notify_update(root, latest))
        except Exception as exc:
            logger.debug("Auto-update check failed: %s", exc)

    threading.Thread(target=_work, daemon=True).start()


def _notify_update(root: tk.Tk, version: str) -> None:
    ok = messagebox.askyesno(
        t("update_title"),
        t("update_msg", version=version),
    )
    if ok:
        # Apre la pagina delle release sul browser
        webbrowser.open("https://github.com/Marcu08/App_Gestionale")
# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class LogisticLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self._apply_dpi_scaling()
        self.title("Logistic Launcher")

        # Load persisted settings (theme, language, groups, etc.)
        self._settings = load_settings()

        # Language
        lang = self._settings.get("language", "it")
        set_language(lang)

        # Theme
        initial_theme = self._settings.get("theme", "light")
        self.theme = ThemeManager(self, initial=initial_theme)

        # Splash screen
        self._splash = SplashScreen(self, self.theme, duration=1500)
        self.withdraw()  # hide main window during splash

        # Data
        self.apps = [normalize_app(a) for a in load_apps()]
        self._placeholder_active = False
        self._category_filter = ""
        self._group_filter = ""
        self.search_text = tk.StringVar()
        self.search_text.trace_add("write", lambda *_: self.render_cards())

        # Server status
        self._server_checker = ServerStatusChecker(self)
        self._update_server_urls()

        # Sub-systems
        self.drag_manager = DragDropManager(self)
        self.card_builder = CardBuilder(
            parent_frame=None,
            theme=self.theme,
            on_launch=self.launch,
            on_edit=self.open_editor,
            on_delete=self.delete_app,
            on_pin=self.toggle_pin,
        )

        self._build_shell()
        self.render_cards()

        # Keyboard shortcuts
        self._bind_shortcuts()

        # Tray icon (optional, Windows-only)
        self._tray_icon = None
        self._setup_tray()

        # Show main window after splash
        self.after(1600, self._show_after_splash)

        # Start server checker
        self._server_checker.start()

        # Auto-update check
        self.after(3000, lambda: check_for_updates(self))

        logger.info("Logistic Launcher v%s started", VERSION)

    def _show_after_splash(self) -> None:
        self.deiconify()
        self.lift()

    # ---- DPI ---------------------------------------------------------------

    def _apply_dpi_scaling(self) -> None:
        try:
            dpi = self.winfo_fpixels("1i")
        except Exception:
            dpi = 96.0
        if not dpi or dpi <= 0:
            dpi = 96.0

        try:
            self.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

        factor = dpi / 96.0
        w = int(BASE_WIDTH * factor)
        h = int(BASE_HEIGHT * factor)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{min(w, sw)}x{min(h, sh)}")
        self.minsize(min(int(BASE_MIN_WIDTH * factor), sw),
                     min(int(BASE_MIN_HEIGHT * factor), sh))

    # ---- Shell (header, sidebar, body) -------------------------------------

    def _build_shell(self) -> None:
        p = self.theme.palette

        # ---- Header ----
        header = ttk.Frame(self, style="Top.TFrame", padding=(36, 24, 36, 20))
        header.pack(fill="x")
        header.columnconfigure(1, weight=1)

        brand = tk.Label(
            header, text="\u25c6", bg=p["accent"], fg="#ffffff",
            font=(FONT_FAMILY_BODY, 20, "bold"), width=3, height=1,
        )
        brand.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 18))

        ttk.Label(header, text="Logistic Launcher", style="Title.TLabel").grid(
            row=0, column=1, sticky="sw",
        )
        self._subtitle_label = ttk.Label(
            header, text=t("app_subtitle"), style="Subtitle.TLabel",
        )
        self._subtitle_label.grid(row=1, column=1, sticky="nw", pady=(4, 0))

        btn_frame = ttk.Frame(header, style="Top.TFrame")
        btn_frame.grid(row=0, column=2, rowspan=2, sticky="e")

        self._add_btn = ttk.Button(btn_frame, text=t("add"), style="Primary.TButton",
                                   command=lambda: self.open_editor())
        self._add_btn.pack(side="left", padx=(0, 8))
        self._import_folder_btn = ttk.Button(btn_frame, text=t("import_folder"), style="Quiet.TButton",
                                             command=self.import_folder)
        self._import_folder_btn.pack(side="left", padx=(0, 8))

        # Export / Import config buttons
        self._export_btn = ttk.Button(btn_frame, text=t("export"), style="Quiet.TButton",
                                      command=self._export_config)
        self._export_btn.pack(side="left", padx=(0, 4))
        self._import_btn = ttk.Button(btn_frame, text=t("import_btn"), style="Quiet.TButton",
                                      command=self._import_config)
        self._import_btn.pack(side="left", padx=(0, 8))

        self._reload_btn = ttk.Button(btn_frame, text=t("reload"), style="Quiet.TButton",
                                      command=self.reload_apps)
        self._reload_btn.pack(side="left", padx=(0, 8))

        # Language toggle
        self._lang_btn = ttk.Button(
            btn_frame, text=get_language().upper(),
            style="Quiet.TButton", command=self._toggle_language,
        )
        self._lang_btn.pack(side="left", padx=(0, 4))

        # Theme toggle
        self._theme_btn = ttk.Button(
            btn_frame, text="\u263e" if self.theme.mode == "light" else "\u2600",
            style="Quiet.TButton", command=self._toggle_theme,
        )
        self._theme_btn.pack(side="left")

        # ---- Group tab bar ----
        groups = self._settings.get("groups", DEFAULT_GROUPS)
        self.group_bar = GroupTabBar(
            self, self.theme, groups, on_change=self._on_group_change,
        )
        self.group_bar.pack(fill="x")

        # ---- Content area (sidebar + main) ----
        content = tk.Frame(self, bg=p["surface"])
        content.pack(fill="both", expand=True)
        self._content_frame = content

        # Sidebar
        categories = sorted({a.get("category", "") for a in self.apps} - {""})
        self.sidebar = Sidebar(
            content, self.theme, categories,
            on_category=self._on_category_change,
        )
        self.sidebar.pack(side="left", fill="y")

        # Main panel
        main = tk.Frame(content, bg=p["surface"])
        main.pack(side="left", fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        self._main_frame = main

        # Search bar row
        search_row = tk.Frame(main, bg=p["surface"])
        search_row.pack(fill="x", padx=36, pady=(12, 0))
        search_row.columnconfigure(0, weight=1)

        self.search_entry = ttk.Entry(
            search_row, textvariable=self.search_text, style="Search.TEntry",
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")

        config_link = tk.Label(
            search_row, text=t("open_config"), bg=p["surface"],
            fg=p["accent"], cursor="hand2",
            font=(FONT_FAMILY_BODY, FONT_BODY),
        )
        config_link.grid(row=0, column=1, sticky="e", padx=(18, 0))
        config_link.bind("<Button-1>", lambda _e: self.open_config_file())
        self._config_link = config_link

        # Dashboard bar
        self._dash_container = tk.Frame(main, bg=p["surface"])
        self._dash_container.pack(fill="x", padx=36, pady=(8, 0))
        self._rebuild_dashboard()

        # Count
        count_frame = tk.Frame(main, bg=p["surface"])
        count_frame.pack(fill="x", padx=36)
        self.count_label = ttk.Label(count_frame, style="Count.TLabel")
        self.count_label.pack(anchor="w", pady=(8, 4))

        # Scrollable canvas for cards
        canvas_frame = tk.Frame(main, bg=p["surface"])
        canvas_frame.pack(fill="both", expand=True, padx=(36, 36), pady=(0, 20))
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, bg=p["surface"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.cards_frame = tk.Frame(self.canvas, bg=p["surface"])
        self.cards_window = self.canvas.create_window(
            (0, 0), window=self.cards_frame, anchor="nw",
        )
        self.cards_frame.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_cards_window)
        self.canvas.bind("<Enter>", lambda _e: self._bind_mousewheel())
        self.canvas.bind("<Leave>", lambda _e: self._unbind_mousewheel())

        self._setup_search_placeholder()

    # ---- Theme toggle ------------------------------------------------------

    def _toggle_theme(self) -> None:
        mode = self.theme.toggle()
        self._theme_btn.configure(text="\u263e" if mode == "light" else "\u2600")
        self._settings["theme"] = mode
        save_settings(self._settings)
        self.sidebar.refresh_theme()
        self.group_bar.refresh_theme()
        p = self.theme.palette
        self._config_link.configure(bg=p["surface"], fg=p["accent"])
        self._content_frame.configure(bg=p["surface"])
        self._main_frame.configure(bg=p["surface"])
        self.canvas.configure(bg=p["surface"])
        self.cards_frame.configure(bg=p["surface"])
        self._rebuild_dashboard()
        self.render_cards()

    # ---- Language toggle ---------------------------------------------------

    def _toggle_language(self) -> None:
        langs = available_languages()
        current = get_language()
        idx = (langs.index(current) + 1) % len(langs)
        new_lang = langs[idx]
        set_language(new_lang)
        self._settings["language"] = new_lang
        save_settings(self._settings)
        self._lang_btn.configure(text=new_lang.upper())
        self._refresh_labels()
        self.render_cards()

    def _refresh_labels(self) -> None:
        self._subtitle_label.configure(text=t("app_subtitle"))
        self._add_btn.configure(text=t("add"))
        self._import_folder_btn.configure(text=t("import_folder"))
        self._reload_btn.configure(text=t("reload"))
        self._export_btn.configure(text=t("export"))
        self._import_btn.configure(text=t("import_btn"))
        self._config_link.configure(text=t("open_config"))

    # ---- Category filter ---------------------------------------------------

    def _on_category_change(self, category: str) -> None:
        self._category_filter = category
        self.render_cards()

    # ---- Group filter ------------------------------------------------------

    def _on_group_change(self, group: str) -> None:
        if group == "__new__":
            name = simpledialog.askstring(
                t("group_name_title"), t("group_name_msg"), parent=self,
            )
            if name and name.strip():
                groups = self._settings.get("groups", list(DEFAULT_GROUPS))
                if name.strip() not in groups:
                    groups.append(name.strip())
                    self._settings["groups"] = groups
                    save_settings(self._settings)
                    self._rebuild_group_bar()
            return
        self._group_filter = group
        self.render_cards()

    def _rebuild_group_bar(self) -> None:
        self.group_bar.destroy()
        groups = self._settings.get("groups", DEFAULT_GROUPS)
        self.group_bar = GroupTabBar(
            self, self.theme, groups, on_change=self._on_group_change,
        )
        # Pack after the header (which is self.winfo_children()[0])
        children = self.winfo_children()
        if len(children) > 1:
            self.group_bar.pack(fill="x", after=children[0])
        else:
            self.group_bar.pack(fill="x")

    # ---- Search placeholder ------------------------------------------------

    def _setup_search_placeholder(self) -> None:
        self._placeholder_active = False
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self._placeholder_active = True
        self.search_entry.configure(foreground=self.theme.palette["muted_soft"])
        self.search_text.set(t("search_placeholder"))

    def _on_search_focus_in(self, _event: tk.Event = None) -> None:
        if self._placeholder_active:
            self._placeholder_active = False
            self.search_entry.configure(foreground=self.theme.palette["ink"])
            self.search_text.set("")

    def _on_search_focus_out(self, _event: tk.Event = None) -> None:
        if not self.search_text.get().strip():
            self._show_placeholder()

    # ---- Keyboard shortcuts ------------------------------------------------

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-n>", lambda _e: self.open_editor())
        self.bind_all("<Control-f>", lambda _e: self._focus_search())
        self.bind_all("<Control-Key-1>", lambda _e: self._launch_nth(0))
        self.bind_all("<Control-Key-2>", lambda _e: self._launch_nth(1))
        self.bind_all("<Control-Key-3>", lambda _e: self._launch_nth(2))

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        if self._placeholder_active:
            self._on_search_focus_in()

    def _launch_nth(self, n: int) -> None:
        apps = self.filtered_apps()
        if n < len(apps):
            self.launch(apps[n])

    # ---- Mousewheel --------------------------------------------------------

    def _bind_mousewheel(self) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        elif event.delta:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _update_scroll_region(self, _event: tk.Event = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_cards_window(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.cards_window, width=event.width)
        self.render_cards()

    # ---- Dashboard ---------------------------------------------------------

    def _rebuild_dashboard(self) -> None:
        for child in self._dash_container.winfo_children():
            child.destroy()
        DashboardBar(
            self._dash_container, self.theme, self.apps, on_launch=self.launch,
        ).pack(fill="x")

    # ---- Card rendering ----------------------------------------------------

    def filtered_apps(self) -> list[dict]:
        if self._placeholder_active:
            apps = list(self.apps)
        else:
            term = self.search_text.get().strip().lower()
            if term:
                apps = [
                    a for a in self.apps
                    if term in a["name"].lower()
                    or term in a["description"].lower()
                    or term in TYPE_LABELS.get(a["type"], a["type"]).lower()
                    or term in a.get("category", "").lower()
                ]
            else:
                apps = list(self.apps)

        if self._category_filter:
            apps = [a for a in apps if a.get("category") == self._category_filter]

        if self._group_filter:
            apps = [a for a in apps if a.get("group") == self._group_filter]

        # Pinned items first
        apps.sort(key=lambda a: (not a.get("pinned", False),))

        return apps

    def render_cards(self) -> None:
        for child in self.cards_frame.winfo_children():
            child.destroy()

        apps = self.filtered_apps()

        # Grammar fix: singular / plural for both noun and adjective
        if len(apps) == 1:
            count_text = t("links_available_s", n=len(apps))
        else:
            count_text = t("links_available_p", n=len(apps))
        self.count_label.configure(text=count_text)

        width = max(self.canvas.winfo_width(), 780)
        columns = 3 if width >= 980 else 2 if width >= 650 else 1
        for idx in range(columns):
            self.cards_frame.columnconfigure(idx, weight=1, uniform="cards")

        if not apps:
            render_empty_state(self.cards_frame, columns, self.theme)
            return

        self.card_builder.parent = self.cards_frame
        wraplength = max(200, min(340, int(width / columns) - 110))
        for index, app in enumerate(apps):
            card = self.card_builder.build(
                app, index // columns, index % columns, wraplength,
                server_status=self._server_checker.status,
            )
            self.drag_manager.bind_card(card, index)
            # Fade-in animation: stagger card appearance
            card.grid_remove()

            def _show_card(c=card):
                try:
                    if c.winfo_exists():
                        c.grid()
                except tk.TclError:
                    pass

            self.after(_FADE_DELAY * (index + 1), _show_card)

    # ---- Pin / Favorite ----------------------------------------------------

    def toggle_pin(self, app: dict) -> None:
        for item in self.apps:
            if item is app:
                item["pinned"] = not item.get("pinned", False)
                break
        save_apps(self.apps)
        self.render_cards()

    # ---- CRUD operations ---------------------------------------------------

    def open_editor(self, app: dict | None = None) -> None:
        AppEditor(self, self.theme, app)

    def upsert_app(self, original: dict | None, updated: dict) -> None:
        if original is None:
            self.apps.append(updated)
        else:
            for idx, item in enumerate(self.apps):
                if item is original:
                    self.apps[idx] = updated
                    break
        save_apps(self.apps)
        self._refresh_categories()
        self._rebuild_dashboard()
        self.render_cards()

    def delete_app(self, app: dict) -> None:
        self.apps = [a for a in self.apps if a is not app]
        save_apps(self.apps)
        self._refresh_categories()
        self._rebuild_dashboard()
        self.render_cards()

    def reload_apps(self) -> None:
        self.apps = [normalize_app(a) for a in load_apps()]
        self._refresh_categories()
        self._rebuild_dashboard()
        self._update_server_urls()
        self.render_cards()

    def _refresh_categories(self) -> None:
        cats = sorted({a.get("category", "") for a in self.apps} - {""})
        self.sidebar.update_categories(cats)

    def _update_server_urls(self) -> None:
        urls = [
            a.get("url", DEFAULT_LOCAL_URL)
            for a in self.apps
            if a.get("type") == "python_server"
        ]
        self._server_checker.set_urls(urls)

    def open_config_file(self) -> None:
        self.launch({"type": "app", "target": str(CONFIG_PATH), "name": "apps.json"})

    # ---- Export / Import config --------------------------------------------

    def _export_config(self) -> None:
        dest = filedialog.asksaveasfilename(
            title=t("export_title"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="apps_backup.json",
        )
        if dest:
            try:
                export_config(Path(dest))
                messagebox.showinfo(t("export_title"), t("export_done"))
                logger.info("Config exported to %s", dest)
            except Exception as exc:
                logger.error("Export failed: %s", exc)
                messagebox.showerror(t("export_title"), str(exc))

    def _import_config(self) -> None:
        src = filedialog.askopenfilename(
            title=t("import_title"),
            filetypes=[("JSON", "*.json")],
        )
        if not src:
            return
        ok = messagebox.askyesno(t("import_confirm_title"), t("import_confirm_msg"))
        if not ok:
            return
        try:
            data = import_config(Path(src))
            save_apps(data)
            self.apps = [normalize_app(a) for a in data]
            self._refresh_categories()
            self._rebuild_dashboard()
            self._update_server_urls()
            self.render_cards()
            messagebox.showinfo(t("import_title"), t("import_done"))
            logger.info("Config imported from %s", src)
        except ValueError as exc:
            logger.error("Import failed: %s", exc)
            messagebox.showerror(t("import_error_title"), t("import_error_msg"))

    # ---- Launch logic ------------------------------------------------------

    def launch(self, app: dict) -> None:
        target = app.get("target", "").strip()
        kind = app.get("type", "website")
        if not target:
            messagebox.showwarning(t("missing_target_title"), t("missing_target_msg"))
            return

        # Increment open count
        for item in self.apps:
            if item.get("name") == app.get("name") and item.get("target") == app.get("target"):
                item["open_count"] = item.get("open_count", 0) + 1
                break
        save_apps(self.apps)
        self._rebuild_dashboard()

        try:
            if kind == "website":
                webbrowser.open(target)
            elif kind == "python_server":
                self._launch_python_server(app)
            elif kind in {"folder", "app"}:
                if sys.platform.startswith("win"):
                    os.startfile(target)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", target])
                else:
                    subprocess.Popen(["xdg-open", target])
            else:
                webbrowser.open(target)
            logger.info("Launched: %s (%s)", app.get("name", "?"), kind)
        except Exception as exc:
            logger.error("Launch failed for %s: %s", target, exc)
            messagebox.showerror(
                t("open_failed_title"),
                t("open_failed_msg", target=target, error=exc),
            )

    def _launch_python_server(self, app: dict) -> None:
        folder = Path(app.get("target", "")).expanduser()
        script_name = app.get("script", "")
        script = folder / script_name if script_name else self._find_server_entry(folder)
        url = app.get("url", DEFAULT_LOCAL_URL)

        if not folder.exists():
            raise FileNotFoundError(f"La cartella non esiste: {folder}")

        if script and script.suffix.lower() == ".bat":
            os.startfile(str(script))
        elif script and script.exists():
            subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(folder),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if sys.platform.startswith("win") else 0),
            )
        else:
            raise FileNotFoundError(
                "Non ho trovato un file di avvio. "
                "Cerco prima un .bat, poi appy.py, app.py o main.py."
            )
        self.after(1800, lambda: webbrowser.open(url))

    @staticmethod
    def _find_server_entry(folder: Path) -> Path | None:
        for filename in PYTHON_SERVER_FILES:
            path = folder / filename
            if path.exists():
                return path
        return None

    # ---- Import folder -----------------------------------------------------

    def import_folder(self) -> None:
        selected = filedialog.askdirectory(title=t("select_folder"))
        if not selected:
            return

        root = Path(selected)
        found: list[dict] = []
        existing_targets = {a["target"].lower() for a in self.apps}

        root_target = str(root)
        if root_target.lower() not in existing_targets:
            server_entry = self._find_server_entry(root)
            if server_entry:
                entry_type = "python_server"
                description = t("server_desc")
                script = server_entry.name
            else:
                entry_type = "folder"
                description = t("folder_desc")
                script = ""

            imported = {
                "name": root.name.replace("_", " ").replace("-", " ").title(),
                "description": description,
                "type": entry_type,
                "target": root_target,
                "icon": initials(root.name),
                "color": COLORS[0],
            }
            if script:
                imported["script"] = script
                imported["url"] = DEFAULT_LOCAL_URL

            normalized = normalize_app(imported)
            for key in ("script", "url"):
                if key in imported:
                    normalized[key] = imported[key]
            found.append(normalized)
            existing_targets.add(root_target.lower())

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMPORT_EXTENSIONS:
                continue
            target = str(path)
            if target.lower() in existing_targets:
                continue
            name = path.stem.replace("_", " ").replace("-", " ").strip() or path.name
            priority_name = path.stem.lower() in START_FILE_NAMES
            found.append(normalize_app({
                "name": name.title(),
                "description": (t("launch_found", name=root.name) if priority_name
                                else t("imported_from", name=root.name)),
                "type": "app",
                "target": target,
                "icon": initials(name),
                "color": COLORS[len(found) % len(COLORS)],
            }))
            existing_targets.add(target.lower())

        if not found:
            messagebox.showinfo(t("no_links_title"), t("no_links_msg"))
            return

        self.apps.extend(found)
        save_apps(self.apps)
        self._refresh_categories()
        self._rebuild_dashboard()
        self._update_server_urls()
        self.render_cards()
        messagebox.showinfo(t("import_done_title"), t("import_done_msg", n=len(found)))
        logger.info("Imported %d links from %s", len(found), selected)

    # ---- System tray (optional) --------------------------------------------

    def _setup_tray(self) -> None:
        if not sys.platform.startswith("win"):
            return
        try:
            import pystray
            from PIL import Image as PILImage
        except ImportError:
            return

        icon_img = PILImage.new("RGB", (64, 64), "#3b82f6")
        menu = pystray.Menu(
            pystray.MenuItem(t("show"), lambda: self._show_from_tray()),
            pystray.MenuItem(t("quit"), lambda: self._quit_from_tray()),
        )
        self._tray_icon = pystray.Icon("LogisticLauncher", icon_img, "Logistic Launcher", menu)
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        import threading
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _hide_to_tray(self) -> None:
        self.withdraw()

    def _show_from_tray(self) -> None:
        self.deiconify()
        self.lift()

    def _quit_from_tray(self) -> None:
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    enable_dpi_awareness()
    app = LogisticLauncher()
    app.mainloop()
