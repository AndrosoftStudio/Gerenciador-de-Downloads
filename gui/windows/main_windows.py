# gui/windows/main_windows.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import json
import sqlite3
import webbrowser
import sys
from urllib.parse import urlparse
from PIL import Image, ImageTk
import sv_ttk 

# --- INJEÇÃO DE CAMINHO ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(project_root)

# --- IMPORTS DO NOSSO CORE ---
from core.i18n import LanguageManager
from core.downloader import DownloadLogic
# (Vamos usar a versão local de open_folder por enquanto)

# --- 0. FUNÇÃO HELPER (Específica da GUI) ---

def resource_path(relative_path):
    """ 
    Retorna o caminho absoluto para o recurso.
    Esta versão é para ser usada DENTRO do script principal da GUI.
    Ela assume que __file__ está em 'gui/windows' e sobe dois níveis.
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    return os.path.join(base_path, relative_path)

# --- 1. CONFIGURAÇÕES E DADOS (APPDATA) ---
APP_NAME = "GerenciadorDownloadsAcelerado"
APP_VERSION = "v1.5"

if os.name == 'nt':
    APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), APP_NAME)
else:
    APP_DATA_PATH = os.path.join(os.path.expanduser('~'), '.config', APP_NAME)

SETTINGS_FILE = os.path.join(APP_DATA_PATH, 'settings.json')
DB_FILE = os.path.join(APP_DATA_PATH, 'history.db')

os.makedirs(APP_DATA_PATH, exist_ok=True)

DEFAULT_SETTINGS = {
    "thread_mode": "Automático",
    "custom_threads": 16,
    "auto_level": "Alto",
    "language": "pt_BR",
    "theme": "Sistema",
    "start_with_windows": False,
    "start_with_windows_minimized": False
}

# --- 3. BANCO DE DADOS DO HISTÓICO ---
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            path TEXT NOT NULL,
            filename TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()

def get_history():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url, path, filename, timestamp FROM downloads ORDER BY timestamp DESC")
            return cursor.fetchall()
    except Exception as e:
        print(f"Erro ao ler o histórico: {e}")
        return []

# --- 4. DEFINIÇÃO DAS PÁGINAS (FRAMES) ---

class DownloadFrame(ttk.Frame):
    def __init__(self, master, app_instance):
        super().__init__(master, padding="15")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager
        self.style = app_instance.style
        
        callbacks = {
            "on_progress": self.on_download_progress,
            "on_complete": self.on_download_complete,
            "on_error": self.on_download_error,
            "on_status_change": self.on_status_change,
            "on_show_monitor": self.on_show_monitor,
            "on_set_downloading_state": self.on_set_downloading_state
        }
        self.downloader = DownloadLogic(self.lang, callbacks)
        
        self.create_widgets()
        self.update_text()
        self.status_label.config(text=self.lang.get_string('status_awaiting'))

    def create_widgets(self):
        self.url_label = ttk.Label(self)
        self.url_label.pack(padx=5, pady=(5, 2), anchor='w') 
        self.url_entry = ttk.Entry(self, width=60)
        self.url_entry.pack(padx=5, pady=2, fill='x')

        self.path_label = ttk.Label(self)
        self.path_label.pack(padx=5, pady=(10, 5), anchor='w') 
        self.folder_frame = ttk.Frame(self)
        self.folder_frame.pack(fill='x', expand=False) 

        self.folder_entry = ttk.Entry(self.folder_frame, width=50)
        self.folder_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(5, 2))
        
        last_path = self.app_instance.settings.get('last_path', os.path.expanduser('~/Downloads'))
        if not os.path.isdir(last_path):
             last_path = os.path.expanduser('~/Downloads')
        self.folder_entry.insert(0, last_path)

        self.browse_button = ttk.Button(self.folder_frame, command=self.browse_folder)
        self.browse_button.pack(side=tk.LEFT, padx=(2, 5))

        self.download_button = ttk.Button(self, command=self.start_download_thread, style="Accent.TButton")
        self.download_button.pack(pady=20, fill='x', ipady=5) 
        self.style.configure("Accent.TButton", font=("-size 10 -weight bold"))
        
        self.cancel_button = ttk.Button(self, command=self.cancel_download, style="Accent.TButton")
        self.cancel_button.pack_forget()

        self.progress_frame = ttk.Frame(self)
        self.progress_frame.pack(fill=tk.X)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=100, mode='determinate')
        self.progress_bar.pack(pady=5, fill='x', expand=True, side=tk.LEFT)
        
        self.monitor_button = ttk.Button(self.progress_frame, text="...", width=3, command=self.open_monitor)
        self.monitor_button.pack_forget()
        
        self.status_label = ttk.Label(self)
        self.status_label.pack(pady=(10, 5), anchor='w') 

    # --- FUNÇÕES DE CALLBACK (CORRIGIDAS) ---
    # Elas são chamadas pela thread de download e usam 'self.after'
    # para agendar a atualização da GUI na thread principal.
    
    def on_status_change(self, message):
        self.after(0, self._update_status_ui, message)

    def on_download_progress(self, progress, speed):
        self.after(0, self._update_progress_ui, progress, speed)

    def on_download_complete(self, filename):
        self.after(0, self._update_complete_ui, filename)

    def on_download_error(self, title, message):
        self.after(0, self._update_error_ui, title, message)

    def on_set_downloading_state(self, is_downloading):
        self.after(0, self._update_button_state_ui, is_downloading)
            
    def on_show_monitor(self, show: bool):
        self.after(0, self._update_monitor_button_ui, show)

    # --- Funções de Atualização da GUI (Helpers) ---
    # Estas são as funções que REALMENTE mexem na GUI.
    
    def _update_status_ui(self, message):
        self.status_label.config(text=message)

    def _update_progress_ui(self, progress, speed):
        self.progress_bar['value'] = progress
        status_msg = self.lang.get_string("status_progress", progress=progress, speed=speed)
        self.status_label.config(text=status_msg)
    
    def _update_complete_ui(self, filename):
        self.progress_bar['value'] = 100
        msg = self.lang.get_string("status_completed", file=filename)
        self.status_label.config(text=msg)
        messagebox.showinfo("Sucesso", msg, parent=self)

    def _update_error_ui(self, title, message):
        self.status_label.config(text=f"Erro: {message[:100]}...")
        messagebox.showerror(title, message, parent=self)

    def _update_button_state_ui(self, is_downloading):
        if is_downloading:
            self.download_button.pack_forget()
            self.cancel_button.config(text=self.lang.get_string("button_cancel"))
            self.cancel_button.pack(pady=20, fill='x', ipady=5)
        else:
            self.cancel_button.pack_forget()
            self.download_button.config(text=self.lang.get_string("button_download"))
            self.download_button.pack(pady=20, fill='x', ipady=5)
    
    def _update_monitor_button_ui(self, show):
        if show:
            self.monitor_button.pack(side=tk.LEFT, padx=(5,0))
        else:
            self.monitor_button.pack_forget()

    # --- Funções de Widget (Restantes) ---
            
    def update_text(self):
        self.url_label.config(text=self.lang.get_string('label_url'))
        self.path_label.config(text=self.lang.get_string('label_path'))
        self.browse_button.config(text=self.lang.get_string('button_browse'))
        self.download_button.config(text=self.lang.get_string('button_download'))
        self.cancel_button.config(text=self.lang.get_string('button_cancel'))
        
    def get_thread_count(self):
        mode = self.app_instance.settings['thread_mode']
        
        if mode == "Automático":
            level = self.app_instance.settings['auto_level']
            cpus = os.cpu_count() or 4 
            if level == "Baixo":
                return max(1, cpus // 2)
            elif level == "Médio":
                return cpus
            elif level == "Alto":
                return cpus * 2
            elif level == "Máximo":
                return max(16, cpus * 4)
        elif mode == "Personalizado":
            try:
                val = int(self.app_instance.settings['custom_threads'])
                return max(1, val)
            except ValueError:
                return 8 
        else: 
            try:
                return int(mode)
            except ValueError:
                return 1

    def browse_folder(self):
        foldername = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if foldername:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, foldername)
            self.app_instance.settings['last_path'] = foldername
            self.app_instance.save_settings(self.app_instance.settings)

    def start_download_thread(self):
        url = self.url_entry.get()
        folder = self.folder_entry.get()
        
        if not url or not folder:
            messagebox.showwarning(self.lang.get_string("warn_empty_fields"), 
                                     self.lang.get_string("warn_empty_fields_msg"))
            return
            
        if not os.path.isdir(folder):
            messagebox.showerror(self.lang.get_string("error_invalid_folder"), 
                                   self.lang.get_string("error_invalid_folder_msg"))
            return
        
        num_threads = self.get_thread_count()
        
        # A própria lógica de download chamará o callback
        # 'on_set_downloading_state' para atualizar o botão.
        
        download_thread = threading.Thread(target=self.downloader.download_file_manager, 
                                           args=(url, folder, num_threads))
        download_thread.daemon = True
        download_thread.start()
        
        self.downloader.update_progress_bar()
        
    def cancel_download(self):
        print("Cancelamento solicitado pelo usuário.")
        self.downloader.stop_download(cancelled=True)
        
    def open_monitor(self):
        self.app_instance.open_monitor()


class AboutFrame(ttk.Frame):
    def __init__(self, master, app_instance):
        super().__init__(master, padding="20")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager
        
        try:
            img = Image.open(resource_path("icon.ico")).resize((128, 128), Image.Resampling.LANCZOS)
            self.icon_photo = ImageTk.PhotoImage(img)
            self.icon_label = ttk.Label(self, image=self.icon_photo)
            self.icon_label.pack(pady=10)
        except Exception as e:
            print(f"Erro ao carregar 'icon.ico' para a janela 'Sobre': {e}")
            self.icon_label = ttk.Label(self, text="[Ícone não encontrado]")
            self.icon_label.pack(pady=10)

        self.title_label = ttk.Label(self, font=("-size 12 -weight bold"))
        self.title_label.pack(pady=5)
        
        self.created_by_label = ttk.Label(self, wraplength=300, justify="center")
        self.created_by_label.pack(pady=10)

        self.linkedin_button = ttk.Button(self, command=lambda: webbrowser.open_new_tab("https://linkedin.com/in/andrejorge-devandre/"))
        self.linkedin_button.pack(pady=(10, 5), fill='x', padx=20)

        self.github_button = ttk.Button(self, command=lambda: webbrowser.open_new_tab("https://github.com/AndrosoftStudio"))
        self.github_button.pack(pady=5, fill='x', padx=20)

        self.youtube_button = ttk.Button(self, command=lambda: webbrowser.open_new_tab("https://www.youtube.com/@devandre2970"))
        self.youtube_button.pack(pady=5, fill='x', padx=20)
        
        self.repo_button = ttk.Button(self, command=lambda: webbrowser.open_new_tab("https://github.com/AndrosoftStudio/Gerenciador-de-Downloads"), style="Accent.TButton")
        self.repo_button.pack(pady=(20, 5), fill='x', padx=20)
        
        self.update_text()

    def update_text(self):
        self.title_label.config(text=f"{self.lang.get_string('app_title')} {self.lang.get_string('version')}")
        self.created_by_label.config(text=self.lang.get_string('win_about_created_by'))
        self.linkedin_button.config(text=self.lang.get_string('win_about_linkedin'))
        self.github_button.config(text=self.lang.get_string('win_about_github'))
        self.youtube_button.config(text=self.lang.get_string('win_about_youtube'))
        self.repo_button.config(text=self.lang.get_string('win_about_repo'))


class HistoryFrame(ttk.Frame):
    def __init__(self, master, app_instance):
        super().__init__(master, padding="10")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager

        button_frame = ttk.Frame(self, padding="10")
        button_frame.pack(fill=tk.X, side=tk.BOTTOM) 

        self.btn_copy = ttk.Button(button_frame, command=self.copy_link)
        self.btn_copy.pack(side=tk.LEFT, padx=5)
        
        self.btn_open = ttk.Button(button_frame, command=self.open_folder)
        self.btn_open.pack(side=tk.LEFT, padx=5)

        self.btn_redownload = ttk.Button(button_frame, command=self.redownload)
        self.btn_redownload.pack(side=tk.LEFT, padx=5)
        
        tree_frame = ttk.Frame(self)
        tree_frame.pack(expand=True, fill=tk.BOTH, side=tk.TOP, pady=(0, 5))

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.cols = ('Data', 'Arquivo', 'Link', 'Pasta')
        self.tree = ttk.Treeview(tree_frame, columns=self.cols, show='headings', yscrollcommand=scrollbar.set)
        self.tree.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)
        
        scrollbar.config(command=self.tree.yview)
        
        self.update_text()
        
    def on_show(self):
        self.load_history()
        
    def load_history(self):
        self.tree.delete(*self.tree.get_children()) 
        history_data = get_history()
        for item in history_data:
            url, path, filename, timestamp = item
            date_str = timestamp.split(" ")[0]
            self.tree.insert("", tk.END, values=(date_str, filename, url, path))
            
    def update_text(self):
        self.tree.heading('Data', text=self.lang.get_string('win_history_date'))
        self.tree.heading('Arquivo', text=self.lang.get_string('win_history_file'))
        self.tree.heading('Link', text=self.lang.get_string('win_history_link'))
        self.tree.heading('Pasta', text=self.lang.get_string('win_history_folder'))
        self.btn_copy.config(text=self.lang.get_string('win_history_copy'))
        self.btn_open.config(text=self.lang.get_string('win_history_open'))
        self.btn_redownload.config(text=self.lang.get_string('win_history_redownload'))

    def get_selected_item_data(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning(self.lang.get_string("error_no_selection"),
                                     self.lang.get_string("error_no_selection_msg"))
            return None
        return self.tree.item(selected_item)['values']

    def copy_link(self):
        data = self.get_selected_item_data()
        if data:
            url = data[2]
            self.clipboard_clear()
            self.clipboard_append(url)
            messagebox.showinfo(self.lang.get_string("info_copied"), 
                                self.lang.get_string("info_copied_msg"))

    def open_folder(self):
        data = self.get_selected_item_data()
        if data:
            folder_path = data[3]
            if os.path.isdir(folder_path):
                if os.name == 'nt':
                    os.startfile(folder_path)
                else:
                    webbrowser.open(f'file:///{folder_path}')
            else:
                messagebox.showerror(self.lang.get_string("error_folder_not_found"), 
                                     self.lang.get_string("error_folder_not_found_msg", path=folder_path))
    
    def redownload(self):
        data = self.get_selected_item_data()
        if data:
            url = data[2]
            self.app_instance.set_url_from_history(url)
            self.app_instance.show_page("home")


class SettingsFrame(ttk.Frame):
    def __init__(self, master, app_instance):
        super().__init__(master, padding="15")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager
        
        self.settings = app_instance.settings.copy()

        self.thread_mode_var = tk.StringVar(master=self, value=self.settings['thread_mode'])
        self.auto_level_var = tk.StringVar(master=self, value=self.settings['auto_level'])
        self.custom_thread_var = tk.StringVar(master=self, value=str(self.settings['custom_threads']))
        self.theme_var = tk.StringVar(master=self, value=self.settings['theme'])
        self.lang_var = tk.StringVar(master=self, value=self.settings['language'])
        self.startup_var = tk.BooleanVar(master=self, value=self.settings['start_with_windows'])
        self.startup_minimized_var = tk.BooleanVar(master=self, value=self.settings.get('start_with_windows_minimized', False))

        self.threads_frame = ttk.LabelFrame(self, padding="10")
        self.threads_frame.pack(fill=tk.X, pady=5)
        
        self.thread_options_frame = ttk.Frame(self.threads_frame)
        self.thread_options_frame.pack(fill=tk.X, pady=5)
        
        thread_options = ["Automático", "Personalizado", "1", "2", "3", "4", "5", "6", "7", "8"]
        self.thread_combo = ttk.Combobox(self.thread_options_frame, textvariable=self.thread_mode_var, 
                                         values=thread_options, state='readonly', width=15)
        self.thread_combo.pack(side=tk.LEFT, padx=5)
        
        auto_options = ["Baixo", "Médio", "Alto", "Máximo"]
        self.auto_level_combo = ttk.Combobox(self.thread_options_frame, textvariable=self.auto_level_var,
                                             values=auto_options, state='readonly', width=10)
        
        validate_cmd = (self.register(self.validate_integer), '%P')
        self.custom_thread_entry = ttk.Entry(self.thread_options_frame, textvariable=self.custom_thread_var, 
                                             width=5, validate='key', validatecommand=validate_cmd)
        
        self.thread_mode_var.trace_add('write', self.on_thread_mode_change)
        
        self.auto_level_frame = ttk.Frame(self.threads_frame)
        self.auto_level_frame.pack(fill=tk.X, pady=5)
        self.auto_level_label = ttk.Label(self.auto_level_frame, text="Nível Automático:")
        self.auto_level_label.pack(side=tk.LEFT, padx=5)
        self.auto_level_combo_2 = ttk.Combobox(self.auto_level_frame, textvariable=self.auto_level_var,
                                             values=auto_options, state='readonly', width=10)
        
        self.appearance_frame = ttk.LabelFrame(self, padding="10")
        self.appearance_frame.pack(fill=tk.X, pady=5)
        
        self.theme_frame = ttk.Frame(self.appearance_frame)
        self.theme_frame.pack(fill=tk.X, pady=5)
        self.theme_label = ttk.Label(self.theme_frame, text="Tema:")
        self.theme_label.pack(side=tk.LEFT, padx=5)
        theme_options = ["Sistema", "Claro", "Escuro"]
        self.theme_combo = ttk.Combobox(self.theme_frame, textvariable=self.theme_var,
                                        values=theme_options, state='readonly', width=15)
        self.theme_combo.pack(side=tk.LEFT, padx=5)
        
        self.lang_frame = ttk.Frame(self.appearance_frame)
        self.lang_frame.pack(fill=tk.X, pady=5)
        self.lang_label = ttk.Label(self.lang_frame, text="Idioma:")
        self.lang_label.pack(side=tk.LEFT, padx=5)
        lang_options = self.lang.get_available_languages()
        self.lang_combo = ttk.Combobox(self.lang_frame, textvariable=self.lang_var,
                                       values=lang_options, state='readonly', width=15)
        self.lang_combo.pack(side=tk.LEFT, padx=5)
        
        self.general_frame = ttk.LabelFrame(self, padding="10")
        self.general_frame.pack(fill=tk.X, pady=5)
        
        self.startup_check = ttk.Checkbutton(self.general_frame, variable=self.startup_var,
                                             command=self.on_startup_change) 
        self.startup_check.pack(side=tk.TOP, padx=5, anchor='w')
        
        self.startup_minimized_check = ttk.Checkbutton(self.general_frame, variable=self.startup_minimized_var)
        self.startup_minimized_check.pack(side=tk.TOP, padx=(25, 5), anchor='w') 
        
        self.save_button = ttk.Button(self, command=self.save_and_return)
        self.save_button.pack(side=tk.BOTTOM, pady=20)
        
        self.update_text() 
        self.on_thread_mode_change() 
        self.on_startup_change() 

    def validate_integer(self, value_if_allowed):
        if value_if_allowed.isdigit() and len(value_if_allowed) < 4:
            return True
        if value_if_allowed == "":
            return True
        return False

    def on_thread_mode_change(self, *args):
        mode = self.thread_mode_var.get()
        
        self.custom_thread_entry.pack_forget()
        self.auto_level_frame.pack_forget()

        if mode == self.lang.get_string("win_settings_mode_auto"):
            self.auto_level_frame.pack(fill=tk.X, pady=5)
        elif mode == self.lang.get_string("win_settings_mode_custom"): 
            self.custom_thread_entry.pack(side=tk.LEFT, padx=5)
            
    def on_startup_change(self, *args):
        if self.startup_var.get():
            self.startup_minimized_check.config(state=tk.NORMAL)
        else:
            self.startup_minimized_check.config(state=tk.DISABLED)
    
    def update_text(self):
        self.threads_frame.config(text=self.lang.get_string('win_settings_threads'))
        self.appearance_frame.config(text=self.lang.get_string('win_settings_appearance'))
        self.general_frame.config(text=self.lang.get_string('win_settings_general'))
        
        thread_options = [
            self.lang.get_string("win_settings_mode_auto"),
            self.lang.get_string("win_settings_mode_custom"),
            "1", "2", "3", "4", "5", "6", "7", "8"
        ]
        self.thread_combo.config(values=thread_options)
        
        auto_options = [
            self.lang.get_string("win_settings_auto_low"),
            self.lang.get_string("win_settings_auto_medium"),
            self.lang.get_string("win_settings_auto_high"),
            self.lang.get_string("win_settings_auto_max")
        ]
        self.auto_level_combo.config(values=auto_options)
        self.auto_level_combo_2.config(values=auto_options)
        self.auto_level_label.config(text=self.lang.get_string('win_settings_auto_level'))
        
        theme_options = [
            self.lang.get_string("win_settings_theme_system"),
            self.lang.get_string("win_settings_theme_light"),
            self.lang.get_string("win_settings_theme_dark")
        ]
        self.theme_combo.config(values=theme_options)
        self.theme_label.config(text=self.lang.get_string('win_settings_theme'))
        self.lang_label.config(text=self.lang.get_string('win_settings_lang'))
        
        self.startup_check.config(text=self.lang.get_string('win_settings_startup'))
        self.startup_minimized_check.config(text=self.lang.get_string('win_settings_startup_minimized'))
        
        self.save_button.config(text=self.lang.get_string('win_settings_save'))

    def save_and_return(self):
        old_theme = self.app_instance.settings['theme']
        
        mode_str = self.thread_mode_var.get()
        if mode_str == self.lang.get_string("win_settings_mode_auto"):
            self.settings['thread_mode'] = "Automático"
        elif mode_str == self.lang.get_string("win_settings_mode_custom"):
            self.settings['thread_mode'] = "Personalizado"
        else:
            self.settings['thread_mode'] = mode_str
            
        level_str = self.auto_level_var.get()
        if level_str == self.lang.get_string("win_settings_auto_low"):
            self.settings['auto_level'] = "Baixo"
        elif level_str == self.lang.get_string("win_settings_auto_medium"):
            self.settings['auto_level'] = "Médio"
        elif level_str == self.lang.get_string("win_settings_auto_high"):
            self.settings['auto_level'] = "Alto"
        elif level_str == self.lang.get_string("win_settings_auto_max"):
            self.settings['auto_level'] = "Máximo"
            
        try:
            self.settings['custom_threads'] = int(self.custom_thread_var.get())
        except ValueError:
            self.settings['custom_threads'] = 8 
            
        theme_str = self.theme_var.get()
        if theme_str == self.lang.get_string("win_settings_theme_system"):
            self.settings['theme'] = "Sistema"
        elif theme_str == self.lang.get_string("win_settings_theme_light"):
            self.settings['theme'] = "Claro"
        elif theme_str == self.lang.get_string("win_settings_theme_dark"):
            self.settings['theme'] = "Escuro"
            
        self.settings['language'] = self.lang_var.get()
        self.settings['start_with_windows'] = self.startup_var.get()
        self.settings['start_with_windows_minimized'] = self.startup_minimized_var.get()
        
        new_theme = self.settings['theme']

        self.app_instance.save_settings(self.settings)
        self.app_instance.apply_settings()
        
        if new_theme == "Sistema" and old_theme != "Sistema":
            messagebox.showinfo("Tema Alterado", 
                                "O tema foi definido como 'Sistema'.\nReinicie o aplicativo para que a mudança tenha efeito.",
                                parent=self)
        
        self.app_instance.show_page("home")


class ThreadMonitorWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.app_instance = master
        self.lang = master.lang_manager
        self.downloader = master.pages["home"].downloader
        
        self.geometry("500x350")
        
        try:
            self.iconbitmap(resource_path('icon.ico'))
        except tk.TclError:
            pass
            
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.is_running = True

        frame = ttk.Frame(self, padding="10")
        frame.pack(expand=True, fill=tk.BOTH)

        self.cols = ('ID', 'Progresso', 'Velocidade')
        self.tree = ttk.Treeview(frame, columns=self.cols, show='headings')
        self.tree.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)
        
        self.tree.column('ID', width=80, anchor='center')
        self.tree.column('Progresso', width=200, anchor='w')
        self.tree.column('Velocidade', width=120, anchor='e')

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        
        self.close_button = ttk.Button(self, text="Fechar", command=self.on_close)
        self.close_button.pack(pady=10)
        
        self.update_text()
        self.start_monitoring()

    def update_text(self):
        self.title(self.lang.get_string('win_monitor_title'))
        self.tree.heading('ID', text=self.lang.get_string('win_monitor_thread_id'))
        self.tree.heading('Progresso', text=self.lang.get_string('win_monitor_progress'))
        self.tree.heading('Velocidade', text=self.lang.get_string('win_monitor_speed'))
        self.close_button.config(text=self.lang.get_string('win_history_close'))

    def start_monitoring(self):
        if not self.is_running:
            return
            
        if not self.downloader.download_active or not self.downloader.is_multithreaded:
            self.is_running = False
            self.title(self.lang.get_string('win_monitor_title') + " (Inativo)")
            return

        with self.downloader.global_lock:
            stats_copy = self.downloader.thread_stats.copy()
        
        for row in self.tree.get_children():
            self.tree.delete(row)
        
        for thread_id, data in stats_copy.items():
            downloaded = data['downloaded']
            speed_str = data['speed_str']
            chunk_size = data['total_size']
            progress_percent = (downloaded / chunk_size) * 100 if chunk_size > 0 else 0
            
            progress_bar = "█" * int(progress_percent / 5) + " " * (20 - int(progress_percent / 5))
            progress_text = f"[{progress_bar}] {progress_percent:.1f}%"
            
            self.tree.insert("", tk.END, iid=thread_id, 
                             values=(f"Thread {thread_id}", progress_text, speed_str))

        self.after(500, self.start_monitoring)
        
    def on_close(self):
        self.is_running = False
        self.destroy()

# --- 6. APLICAÇÃO PRINCIPAL (GUI) ---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        
        try:
            self.lang_manager = LanguageManager(self.settings)
        except Exception as e:
            messagebox.showerror("Erro Crítico", f"Não foi possível carregar os idiomas:\n{e}\n\O programa será encerrado.")
            self.quit()
            return

        self.lang = self.lang_manager 
        self.style = ttk.Style()
        self.monitor_window = None 
        
        self.apply_theme(on_startup=True) 
        
        self.create_widgets()
        self.apply_settings() 

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                for key, value in DEFAULT_SETTINGS.items():
                    if key not in settings:
                        settings[key] = value
                return settings
        except (FileNotFoundError, json.JSONDecodeError):
            return DEFAULT_SETTINGS.copy()

    def save_settings(self, new_settings=None):
        if new_settings:
            self.settings = new_settings.copy()
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")
            
        if self.settings['start_with_windows']:
            print("AVISO: 'Iniciar com Windows' está marcado, mas a implementação é complexa e não está ativa.")

    def apply_settings(self):
        if self.lang.current_language != self.settings['language']:
            self.lang.set_language(self.settings['language'])
            self.update_all_text()
        self.apply_theme()
        
    def apply_theme(self, on_startup=False):
        theme = self.settings.get('theme', 'Sistema')
        if on_startup:
            if theme == 'Claro':
                sv_ttk.set_theme("light")
            elif theme == 'Escuro':
                sv_ttk.set_theme("dark")
        else:
            if theme == 'Claro':
                sv_ttk.set_theme("light")
            elif theme == 'Escuro':
                sv_ttk.set_theme("dark")

    def create_widgets(self):
        self.geometry("960x540") 
        self.wm_aspect(16, 9, 16, 9)
        
        try:
            self.iconbitmap(resource_path('icon.ico'))
        except tk.TclError:
            print("Aviso: 'icon.ico' não encontrado ou inválido.")

        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        
        self.menu_file = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Menu", menu=self.menu_file) 
        self.menu_file.add_command(label="Download", command=lambda: self.show_page("home"))
        self.menu_file.add_command(label="Histórico", command=lambda: self.show_page("history"))
        self.menu_file.add_command(label="Configurações", command=lambda: self.show_page("settings"))
        self.menu_file.add_command(label="Sobre", command=lambda: self.show_page("about"))
        self.menu_file.add_separator()
        self.menu_file.add_command(label="Sair", command=self.quit)
        
        self.main_container = ttk.Frame(self)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        self.pages = {
            "home": DownloadFrame(self.main_container, self),
            "history": HistoryFrame(self.main_container, self),
            "settings": SettingsFrame(self.main_container, self),
            "about": AboutFrame(self.main_container, self)
        }
        
        self.current_page_name = None
        self.show_page("home")
        self.update_all_text() 

    def show_page(self, page_name):
        if self.current_page_name == page_name:
            return 
            
        if self.current_page_name:
            current_page = self.pages[self.current_page_name]
            current_page.pack_forget()
            
        self.current_page_name = page_name
        page = self.pages[page_name]
        page.pack(fill=tk.BOTH, expand=True)
        
        if hasattr(page, 'on_show'):
            page.on_show()

    def update_all_text(self):
        self.title(f"{self.lang.get_string('app_title')} {self.lang.get_string('version')}")
        self.menu_bar.entryconfig(1, label=self.lang.get_string('menu_file'))
        self.menu_file.entryconfig(0, label="Download")
        self.menu_file.entryconfig(1, label=self.lang.get_string('menu_history'))
        self.menu_file.entryconfig(2, label=self.lang.get_string('menu_settings'))
        self.menu_file.entryconfig(3, label=self.lang.get_string('menu_about'))
        self.menu_file.entryconfig(5, label=self.lang.get_string('menu_exit'))
        
        for page in self.pages.values():
            if hasattr(page, 'update_text'):
                page.update_text()
        
        if self.pages["home"].downloader and not self.pages["home"].downloader.download_active:
             self.pages["home"].status_label.config(text=self.lang.get_string('status_awaiting'))

    def open_monitor(self):
        if self.monitor_window and self.monitor_window.winfo_exists():
            self.monitor_window.lift() 
        else:
            self.monitor_window = ThreadMonitorWindow(self)

    def set_url_from_history(self, url):
        self.pages["home"].url_entry.delete(0, tk.END)
        self.pages["home"].url_entry.insert(0, url)
        self.attributes('-topmost', 1)
        self.attributes('-topmost', 0)


# --- 7. INICIALIZAÇÃO ---

def start_windows_app():
    """Função de inicialização para ser chamada pelo run.py"""
    init_db() 
    
    app = App() 
    app.mainloop() 

if __name__ == "__main__":
    # Este bloco permite que você rode este arquivo
    # diretamente para testar a GUI do Windows,
    # sem precisar passar pelo run.py
    start_windows_app()