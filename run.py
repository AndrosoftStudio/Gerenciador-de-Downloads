import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import threading
import os
import time
import json
import sqlite3
import webbrowser
import glob
from urllib.parse import urlparse
from PIL import Image, ImageTk
import sv_ttk # <--- Nova importação de Tema

# --- 1. CONFIGURAÇÕES E DADOS (APPDATA) ---

APP_NAME = "GerenciadorDownloadsAcelerado"
APP_VERSION = "v1.1"

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
    "start_with_windows": False
}

# --- 2. GERENCIADOR DE IDIOMAS (i18n) ---

class LanguageManager:
    """Carrega e gerencia os idiomas a partir dos arquivos JSON."""
    def __init__(self, settings):
        self.languages = {}
        self.current_language = settings.get('language', 'pt_BR')
        self.load_languages()
        self.set_language(self.current_language)

    def load_languages(self):
        """Carrega todos os arquivos .json da pasta 'idiomas'."""
        try:
            lang_files = glob.glob(os.path.join("idiomas", "*.json"))
            if not lang_files:
                print("ERRO: Pasta 'idiomas' não encontrada ou vazia.")
                messagebox.showerror("Erro Crítico", 
                    "A pasta 'idiomas' não foi encontrada ou está vazia.\nO programa não pode funcionar sem ela.")
                exit()
                
            for file in lang_files:
                lang_code = os.path.basename(file).replace(".json", "")
                with open(file, 'r', encoding='utf-8') as f:
                    self.languages[lang_code] = json.load(f)
        except Exception as e:
            print(f"Erro ao carregar idiomas: {e}")
            messagebox.showerror("Erro Crítico", f"Erro ao carregar arquivos de idioma: {e}")
            exit()

    def set_language(self, lang_code):
        if lang_code in self.languages:
            self.current_language = lang_code
            self.strings = self.languages[lang_code]
        else:
            print(f"Idioma {lang_code} não encontrado, usando pt_BR como padrão.")
            self.current_language = 'pt_BR'
            self.strings = self.languages.get('pt_BR', {})

    def get_string(self, key, **kwargs):
        """Retorna a string traduzida, formatando-a se necessário."""
        string = self.strings.get(key, f"_{key}_") # Retorna a chave se não encontrar
        try:
            return string.format(**kwargs)
        except KeyError:
            return string # Retorna a string sem formatação se os kwargs estiverem errados

    def get_available_languages(self):
        return list(self.languages.keys())

# --- 3. BANCO DE DADOS DO HISTÓRICO ---
# (Idêntico ao anterior, sem mudanças)
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

def add_to_history(url, file_path):
    try:
        filename = os.path.basename(file_path)
        folder_path = os.path.dirname(file_path)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO downloads (url, path, filename) VALUES (?, ?, ?)", 
                           (url, folder_path, filename))
            conn.commit()
    except Exception as e:
        print(f"Erro ao salvar no histórico: {e}")

def get_history():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url, path, filename, timestamp FROM downloads ORDER BY timestamp DESC")
            return cursor.fetchall()
    except Exception as e:
        print(f"Erro ao ler o histórico: {e}")
        return []

# --- 4. JANELAS POP-UP (Sobre, Histórico, Config, Monitor) ---

class AboutWindow(tk.Toplevel):
    """Janela 'Sobre' (Agora não-modal e com texto traduzível)."""
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.lang = master.lang_manager
        
        self.transient(master)
        # self.grab_set() # Removido para ser "assíncrono" (não-modal)

        try:
            self.iconbitmap('icon.ico')
        except tk.TclError:
            print("Aviso: 'icon.ico' não encontrado para a janela 'Sobre'.")
            
        frame = ttk.Frame(self, padding="20")
        frame.pack(expand=True, fill=tk.BOTH)

        try:
            img = Image.open("icon.ico").resize((128, 128), Image.Resampling.LANCZOS)
            self.icon_photo = ImageTk.PhotoImage(img)
            self.icon_label = ttk.Label(frame, image=self.icon_photo)
            self.icon_label.pack(pady=10)
        except Exception as e:
            print(f"Erro ao carregar 'icon.ico' para a janela 'Sobre': {e}")
            self.icon_label = ttk.Label(frame, text="[Ícone não encontrado]")
            self.icon_label.pack(pady=10)

        self.title_label = ttk.Label(frame, font=("-size 12 -weight bold"))
        self.title_label.pack(pady=5)
        
        self.created_by_label = ttk.Label(frame, wraplength=300, justify="center")
        self.created_by_label.pack(pady=10)

        self.links = [
            ("LinkedIn", "https://linkedin.com/in/andrejorge-devandre/"),
            ("GitHub (Pessoal)", "https://github.com/AndrosoftStudio"),
            ("YouTube", "https://www.youtube.com/@devandre2970"),
        ]
        
        for text, url in self.links:
            self.create_link(frame, text, url)
            
        self.repo_link = self.create_link(frame, "", "https://github.com/AndrosoftStudio/Gerenciador-de-Downloads")
        
        self.close_button = ttk.Button(frame, command=self.destroy)
        self.close_button.pack(pady=20)
        
        self.update_text()

    def create_link(self, parent, text, url):
        link_label = ttk.Label(parent, text=text, foreground="blue", cursor="hand2", style="Link.TLabel")
        link_label.pack()
        link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open_new_tab(u))
        self.master.style.configure("Link.TLabel", font=("-underline 1"))
        return link_label

    def update_text(self):
        self.title(self.lang.get_string("win_about_title"))
        self.title_label.config(text=f"{self.lang.get_string('app_title')} {self.lang.get_string('version')}")
        self.created_by_label.config(text=self.lang.get_string('win_about_created_by'))
        self.repo_link.config(text=self.lang.get_string('win_about_repo'))
        self.close_button.config(text=self.lang.get_string('win_history_close'))


class HistoryWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.lang = master.lang_manager
        self.geometry("800x500")
        
        try:
            self.iconbitmap('icon.ico')
        except tk.TclError:
            print("Aviso: 'icon.ico' não encontrado para a janela 'Histórico'.")

        frame = ttk.Frame(self, padding="10")
        frame.pack(expand=True, fill=tk.BOTH)

        self.cols = ('Data', 'Arquivo', 'Link', 'Pasta')
        self.tree = ttk.Treeview(frame, columns=self.cols, show='headings')
        self.tree.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        button_frame = ttk.Frame(self, padding="10")
        button_frame.pack(fill=tk.X)

        self.btn_copy = ttk.Button(button_frame, command=self.copy_link)
        self.btn_copy.pack(side=tk.LEFT, padx=5)
        
        self.btn_open = ttk.Button(button_frame, command=self.open_folder)
        self.btn_open.pack(side=tk.LEFT, padx=5)

        self.btn_redownload = ttk.Button(button_frame, command=self.redownload)
        self.btn_redownload.pack(side=tk.LEFT, padx=5)
        
        self.btn_close = ttk.Button(button_frame, command=self.destroy)
        self.btn_close.pack(side=tk.RIGHT, padx=5)
        
        self.load_history()
        self.update_text()
        
    def load_history(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        history_data = get_history()
        for item in history_data:
            url, path, filename, timestamp = item
            date_str = timestamp.split(" ")[0]
            self.tree.insert("", tk.END, values=(date_str, filename, url, path))
            
    def update_text(self):
        self.title(self.lang.get_string('win_history_title'))
        self.tree.heading('Data', text=self.lang.get_string('win_history_date'))
        self.tree.heading('Arquivo', text=self.lang.get_string('win_history_file'))
        self.tree.heading('Link', text=self.lang.get_string('win_history_link'))
        self.tree.heading('Pasta', text=self.lang.get_string('win_history_folder'))
        self.btn_copy.config(text=self.lang.get_string('win_history_copy'))
        self.btn_open.config(text=self.lang.get_string('win_history_open'))
        self.btn_redownload.config(text=self.lang.get_string('win_history_redownload'))
        self.btn_close.config(text=self.lang.get_string('win_history_close'))

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
            self.master_app.set_url_from_history(url)
            self.destroy()

class SettingsWindow(tk.Toplevel):
    """Nova Janela de Configurações."""
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.lang = master.lang_manager
        
        self.transient(master)
        self.grab_set() # Modal para forçar o salvamento
        self.geometry("450x450")
        
        # Carrega as configurações atuais
        self.settings = master.settings.copy()

        # --- Variáveis de Controle ---
        self.thread_mode_var = tk.StringVar(value=self.settings['thread_mode'])
        self.auto_level_var = tk.StringVar(value=self.settings['auto_level'])
        self.custom_thread_var = tk.StringVar(value=str(self.settings['custom_threads']))
        self.theme_var = tk.StringVar(value=self.settings['theme'])
        self.lang_var = tk.StringVar(value=self.settings['language'])
        self.startup_var = tk.BooleanVar(value=self.settings['start_with_windows'])

        # --- Criação dos Widgets ---
        self.main_frame = ttk.Frame(self, padding="15")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Seção de Threads
        self.threads_frame = ttk.LabelFrame(self.main_frame, padding="10")
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
        
        # Nível Automático (para tradução)
        self.auto_level_frame = ttk.Frame(self.threads_frame)
        self.auto_level_frame.pack(fill=tk.X, pady=5)
        self.auto_level_label = ttk.Label(self.auto_level_frame, text="Nível Automático:")
        self.auto_level_label.pack(side=tk.LEFT, padx=5)
        self.auto_level_combo_2 = ttk.Combobox(self.auto_level_frame, textvariable=self.auto_level_var,
                                             values=auto_options, state='readonly', width=10)
        
        
        # Seção de Aparência
        self.appearance_frame = ttk.LabelFrame(self.main_frame, padding="10")
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
        
        # Seção Geral
        self.general_frame = ttk.LabelFrame(self.main_frame, padding="10")
        self.general_frame.pack(fill=tk.X, pady=5)
        
        self.startup_check = ttk.Checkbutton(self.general_frame, variable=self.startup_var)
        self.startup_check.pack(side=tk.LEFT, padx=5)
        
        # Botão Salvar
        self.save_button = ttk.Button(self.main_frame, command=self.save_and_close)
        self.save_button.pack(side=tk.BOTTOM, pady=20)
        
        self.update_text() # Aplica traduções
        self.on_thread_mode_change() # Aplica a lógica de UI

    def validate_integer(self, value_if_allowed):
        if value_if_allowed.isdigit() and len(value_if_allowed) < 4:
            return True
        if value_if_allowed == "":
            return True
        return False

    def on_thread_mode_change(self, *args):
        mode = self.thread_mode_var.get()
        
        # Esconde todos os widgets dinâmicos
        self.custom_thread_entry.pack_forget()
        self.auto_level_frame.pack_forget()

        if mode == self.lang.get_string("win_settings_mode_auto"): # "Automático"
            self.auto_level_frame.pack(fill=tk.X, pady=5)
        elif mode == self.lang.get_string("win_settings_mode_custom"): # "Personalizado"
            self.custom_thread_entry.pack(side=tk.LEFT, padx=5)
    
    def update_text(self):
        """Atualiza todo o texto da janela com base no idioma."""
        self.title(self.lang.get_string('win_settings_title'))
        
        # Labels das seções
        self.threads_frame.config(text=self.lang.get_string('win_settings_threads'))
        self.appearance_frame.config(text=self.lang.get_string('win_settings_appearance'))
        self.general_frame.config(text=self.lang.get_string('win_settings_general'))
        
        # Opções de Threads (precisamos traduzir as opções também)
        thread_options = [
            self.lang.get_string("win_settings_mode_auto"),
            self.lang.get_string("win_settings_mode_custom"),
            "1", "2", "3", "4", "5", "6", "7", "8"
        ]
        self.thread_combo.config(values=thread_options)
        
        # Opções de Nível Automático
        auto_options = [
            self.lang.get_string("win_settings_auto_low"),
            self.lang.get_string("win_settings_auto_medium"),
            self.lang.get_string("win_settings_auto_high"),
            self.lang.get_string("win_settings_auto_max")
        ]
        self.auto_level_combo.config(values=auto_options)
        self.auto_level_combo_2.config(values=auto_options)
        self.auto_level_label.config(text=self.lang.get_string('win_settings_auto_level'))
        
        # Opções de Aparência
        theme_options = [
            self.lang.get_string("win_settings_theme_system"),
            self.lang.get_string("win_settings_theme_light"),
            self.lang.get_string("win_settings_theme_dark")
        ]
        self.theme_combo.config(values=theme_options)
        self.theme_label.config(text=self.lang.get_string('win_settings_theme'))
        self.lang_label.config(text=self.lang.get_string('win_settings_lang'))
        
        # Opções Gerais
        self.startup_check.config(text=self.lang.get_string('win_settings_startup'))
        
        # Botão Salvar
        self.save_button.config(text=self.lang.get_string('win_settings_save'))

    def save_and_close(self):
        """Salva as configurações no app principal e fecha a janela."""
        # Converte as strings traduzidas de volta para chaves
        
        # Threads
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
            self.settings['custom_threads'] = 8 # Padrão
            
        # Aparência
        theme_str = self.theme_var.get()
        if theme_str == self.lang.get_string("win_settings_theme_system"):
            self.settings['theme'] = "Sistema"
        elif theme_str == self.lang.get_string("win_settings_theme_light"):
            self.settings['theme'] = "Claro"
        elif theme_str == self.lang.get_string("win_settings_theme_dark"):
            self.settings['theme'] = "Escuro"
            
        self.settings['language'] = self.lang_var.get()
        
        # Geral
        self.settings['start_with_windows'] = self.startup_var.get()
        
        # Aplica as configurações
        self.master_app.save_settings(self.settings)
        self.master_app.apply_settings()
        self.destroy()

class ThreadMonitorWindow(tk.Toplevel):
    """Nova Janela para Monitorar Threads Individuais."""
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.lang = master.lang_manager
        self.downloader = master.downloader
        
        self.geometry("500x350")
        
        try:
            self.iconbitmap('icon.ico')
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
        """Inicia o loop de atualização da janela."""
        if not self.is_running:
            return
            
        if not self.downloader.download_active or not self.downloader.is_multithreaded:
            # Se o download acabar ou for de thread única, para de atualizar
            self.is_running = False
            self.title(self.lang.get_string('win_monitor_title') + " (Inativo)")
            return

        with self.downloader.global_lock:
            stats_copy = self.downloader.thread_stats.copy()
            total_size = self.downloader.global_total_size
        
        # Limpa a árvore
        for row in self.tree.get_children():
            self.tree.delete(row)
        
        # Preenche com os novos dados
        for thread_id, data in stats_copy.items():
            downloaded = data['downloaded']
            speed_str = data['speed_str']
            
            chunk_size = data['total_size']
            progress_percent = (downloaded / chunk_size) * 100 if chunk_size > 0 else 0
            
            progress_bar = "█" * int(progress_percent / 5) + " " * (20 - int(progress_percent / 5))
            progress_text = f"[{progress_bar}] {progress_percent:.1f}%"
            
            self.tree.insert("", tk.END, iid=thread_id, 
                             values=(f"Thread {thread_id}", progress_text, speed_str))

        # Reagenda a atualização
        self.after(500, self.start_monitoring)
        
    def on_close(self):
        self.is_running = False
        self.destroy()

# --- 5. LÓGICA DE DOWNLOAD (Atualizada para Cancelamento e Monitoramento) ---

class DownloadLogic:
    def __init__(self, app_instance):
        self.app = app_instance
        self.lang = app_instance.lang_manager
        self.reset_globals()
        
    def reset_globals(self):
        self.download_active = False
        self.is_multithreaded = False
        self.global_progress = 0
        self.global_speed = "0 MB/s"
        self.global_total_downloaded = 0
        self.global_total_size = 0
        self.global_lock = threading.Lock()
        self.url_para_historico = ""
        # Novas variáveis para monitoramento de thread
        self.thread_stats = {} # Ex: {0: {"downloaded": 0, "total_size": 1000, "speed_str": "0 KB/s", "last_time": 0, "last_downloaded": 0}}

    def update_progress_bar(self):
        if not self.download_active:
            return

        last_downloaded = self.global_total_downloaded
        last_time = time.time()
        
        self.app.after(500, lambda: self._update_speed_logic(last_downloaded, last_time))

    def _update_speed_logic(self, last_downloaded, last_time):
        if not self.download_active:
            return

        current_time = time.time()
        time_diff = current_time - last_time
        
        with self.global_lock:
            current_downloaded = self.global_total_downloaded
            if self.global_total_size > 0:
                self.global_progress = (current_downloaded / self.global_total_size) * 100
            else:
                self.global_progress = 0

        bytes_diff = current_downloaded - last_downloaded
        
        if time_diff > 0:
            speed_bps = bytes_diff / time_diff
            speed_MBps = (speed_bps / 1024 / 1024)
            speed_KBps = (speed_bps / 1024)

            if speed_MBps >= 1:
                self.global_speed = f"{speed_MBps:.2f} MB/s"
            else:
                self.global_speed = f"{speed_KBps:.2f} KB/s"
        
        self.app.progress_bar['value'] = self.global_progress
        self.app.status_label.config(text=self.lang.get_string("status_progress", 
                                       progress=self.global_progress, speed=self.global_speed))

        # Re-agenda o loop
        self.update_progress_bar()

    def download_file_chunk(self, session, url, filename, start_byte, end_byte, thread_id):
        """Baixa um "pedaço" e reporta o progresso individual."""
        try:
            headers = {'Range': f'bytes={start_byte}-{end_byte}'}
            with session.get(url, headers=headers, stream=True, timeout=20) as response:
                response.raise_for_status()

                with open(filename, 'r+b') as f:
                    f.seek(start_byte)
                    for chunk in response.iter_content(chunk_size=1024*128):
                        if not self.download_active: return # <--- PONTO DE CANCELAMENTO
                        if chunk:
                            f.write(chunk)
                            len_chunk = len(chunk)
                            
                            with self.global_lock:
                                self.global_total_downloaded += len_chunk
                                # Atualiza stats da thread
                                stats = self.thread_stats[thread_id]
                                stats['downloaded'] += len_chunk
                                
                                # Calcula velocidade da thread
                                current_time = time.time()
                                time_diff = current_time - stats['last_time']
                                if time_diff > 0.5: # Atualiza a cada 0.5s
                                    bytes_diff = stats['downloaded'] - stats['last_downloaded']
                                    speed_bps = bytes_diff / time_diff
                                    speed_MBps = (speed_bps / 1024 / 1024)
                                    speed_KBps = (speed_bps / 1024)
                                    if speed_MBps >= 1:
                                        stats['speed_str'] = f"{speed_MBps:.2f} MB/s"
                                    else:
                                        stats['speed_str'] = f"{speed_KBps:.2f} KB/s"
                                    stats['last_time'] = current_time
                                    stats['last_downloaded'] = stats['downloaded']

        except Exception as e:
            if self.download_active:
                print(f"Erro na thread {thread_id}: {e}")
                self.stop_download(error=e)

    def download_file_single(self, session, url, filename, total_size):
        try:
            with session.get(url, stream=True, allow_redirects=True, timeout=20) as response:
                response.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024*128):
                        if not self.download_active: return # <--- PONTO DE CANCELAMENTO
                        if chunk:
                            f.write(chunk)
                            with self.global_lock:
                                 self.global_total_downloaded += len(chunk)
        except Exception as e:
            if self.download_active:
                print(f"Erro no download (single): {e}")
                self.stop_download(error=e)

    def download_file_manager(self, url, save_path, num_threads):
        self.reset_globals()
        self.download_active = True
        self.url_para_historico = url
        self.is_multithreaded = False

        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url.lstrip('/')
            
            with requests.Session() as session:
                response = session.head(url, allow_redirects=True, timeout=10)
                response.raise_for_status()
                
                self.global_total_size = int(response.headers.get('content-length', 0))
                
                final_url = response.url 
                parsed_path = urlparse(final_url).path
                base_filename = os.path.basename(parsed_path)
                filename = os.path.join(save_path, base_filename or "downloaded_file")

                supports_ranges = response.headers.get('Accept-Ranges') == 'bytes'
                
                if supports_ranges and self.global_total_size > 0 and num_threads > 1:
                    # --- ESTRATÉGIA MULTITHREAD ---
                    self.is_multithreaded = True
                    self.app.status_label.config(text=self.lang.get_string("status_accelerated", count=num_threads))
                    self.app.show_monitor_button(True) # Mostra o botão do monitor
                    
                    with open(filename, 'wb') as f:
                        f.seek(self.global_total_size - 1)
                        f.write(b'\0')
                    
                    chunk_size = self.global_total_size // num_threads
                    threads = []
                    
                    for i in range(num_threads):
                        start_byte = i * chunk_size
                        end_byte = start_byte + chunk_size - 1 if i < num_threads - 1 else self.global_total_size - 1
                        
                        # Prepara os stats da thread
                        this_chunk_size = (end_byte - start_byte) + 1
                        self.thread_stats[i] = {"downloaded": 0, "total_size": this_chunk_size, 
                                                "speed_str": "0 KB/s", "last_time": time.time(), 
                                                "last_downloaded": 0}
                        
                        t = threading.Thread(target=self.download_file_chunk, 
                                             args=(session, final_url, filename, start_byte, end_byte, i))
                        t.daemon = True
                        t.start()
                        threads.append(t)
                    
                    for t in threads:
                        t.join()

                else:
                    # --- ESTRATÉGIA SINGLE-THREAD ---
                    self.is_multithreaded = False
                    self.app.show_monitor_button(False)
                    if num_threads > 1:
                        self.app.status_label.config(text=self.lang.get_string("status_unsupported"))
                    else:
                         self.app.status_label.config(text=self.lang.get_string("status_normal"))
                    
                    self.download_file_single(session, final_url, filename, self.global_total_size)
                
                # --- FINALIZAÇÃO ---
                if self.download_active:
                    self.global_progress = 100
                    self.app.progress_bar['value'] = 100
                    self.app.status_label.config(text=self.lang.get_string("status_completed", file=filename))
                    messagebox.showinfo("Sucesso", self.lang.get_string("status_completed", file=filename))
                    add_to_history(self.url_para_historico, filename)

        except requests.exceptions.MissingSchema:
            self.stop_download(error_msg=self.lang.get_string("error_url_msg", url=url), title=self.lang.get_string("error_url"))
        except requests.exceptions.RequestException as e:
            self.stop_download(error=e)
        except Exception as e:
            self.stop_download(error=e)
        finally:
            if self.download_active: # Se terminou normally
                self.stop_download()
            # Se foi cancelado, a label já foi setada

    def stop_download(self, error=None, error_msg=None, title=None, cancelled=False):
        if not self.download_active and not cancelled: # Evita rodar múltiplas vezes
            return 
            
        self.download_active = False
        self.is_multithreaded = False
        self.app.show_monitor_button(False)
        self.app.set_download_button_state(is_downloading=False) # Reseta o botão
        
        if cancelled:
            self.app.status_label.config(text=self.lang.get_string("status_cancelled"))
            return

        if error:
            error_str = str(error)
            if "Errno 22" in error_str:
                 self.app.status_label.config(text=self.lang.get_string("status_file_error"))
                 messagebox.showerror(self.lang.get_string("error_file"),
                                      self.lang.get_string("error_file_msg", error=error))
            else:
                self.app.status_label.config(text=self.lang.get_string("status_error", error=error_str))
                messagebox.showerror(self.lang.get_string("error_download"), 
                                     self.lang.get_string("error_download_msg", error=error_str))
        elif error_msg:
            self.app.status_label.config(text=self.lang.get_string("status_error", error=error_msg))
            messagebox.showerror(title or self.lang.get_string("error_title"), error_msg)
        else:
             # Download concluído com sucesso, não mostra erro
             pass

# --- 6. APLICAÇÃO PRINCIPAL (GUI) ---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        self.lang_manager = LanguageManager(self.settings)
        self.lang = self.lang_manager # Atalho
        
        self.downloader = DownloadLogic(self)
        self.style = ttk.Style()
        
        self.monitor_window = None # Placeholder para a janela do monitor
        
        self.apply_theme() # Aplica o tema ANTES de criar os widgets
        self.create_widgets()
        self.apply_settings() # Aplica as configurações (inclui idioma)

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
        """Salva as configurações. Usado pela janela de Configurações."""
        if new_settings:
            self.settings = new_settings.copy()
            
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")
            
        # Implementação "Iniciar com Windows"
        # TODO: Isso é complexo e requer permissões/libs (ex: pywin32)
        # Por enquanto, apenas salvamos a configuração.
        if self.settings['start_with_windows']:
            print("AVISO: 'Iniciar com Windows' está marcado, mas a implementação é complexa e não está ativa.")
            # Aqui entraria a lógica de registro ou atalho na pasta Startup

    def apply_settings(self):
        """Aplica todas as configurações salvas na aplicação."""
        # 1. Idioma (deve ser o primeiro)
        if self.lang.current_language != self.settings['language']:
            self.lang.set_language(self.settings['language'])
            self.update_all_text()
        
        # 2. Tema
        self.apply_theme()
        
        # 3. Configurações da GUI (na Janela Principal)
        # (O código para preencher os widgets foi movido para a Janela de Configurações)
        pass 
        
    def apply_theme(self):
        theme = self.settings.get('theme', 'Sistema')
        if theme == 'Claro':
            sv_ttk.set_theme("light")
        elif theme == 'Escuro':
            sv_ttk.set_theme("dark")
        else: # Sistema
            # A função correta para voltar ao tema do sistema é "system"
            sv_ttk.set_theme("system") # <--- CORREÇÃO APLICADA

    def create_widgets(self):
        self.geometry("600x400")
        
        try:
            self.iconbitmap('icon.ico')
        except tk.TclError:
            print("Aviso: 'icon.ico' não encontrado ou inválido.")

        # --- Menu Bar ---
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        
        self.menu_file = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Menu", menu=self.menu_file) # Traduzido em update_all_text
        self.menu_file.add_command(label="Histórico", command=self.open_history)
        self.menu_file.add_command(label="Configurações", command=self.open_settings)
        self.menu_file.add_command(label="Sobre", command=self.open_about)
        self.menu_file.add_separator()
        self.menu_file.add_command(label="Sair", command=self.quit)

        # --- Frame Principal ---
        frame = ttk.Frame(self, padding="15")
        frame.pack(fill=tk.BOTH, expand=True)

        # --- Seção de Download ---
        self.url_label = ttk.Label(frame)
        self.url_label.pack(padx=5, pady=2, anchor='w')
        self.url_entry = ttk.Entry(frame, width=60)
        self.url_entry.pack(padx=5, pady=2, fill='x')

        self.path_label = ttk.Label(frame)
        self.path_label.pack(padx=5, pady=5, anchor='w')
        self.folder_frame = ttk.Frame(frame)
        self.folder_frame.pack(fill='x', expand=True)

        self.folder_entry = ttk.Entry(self.folder_frame, width=50)
        self.folder_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(5, 2))
        
        last_path = self.settings.get('last_path', os.path.expanduser('~/Downloads'))
        if not os.path.isdir(last_path):
             last_path = os.path.expanduser('~/Downloads')
        self.folder_entry.insert(0, last_path)

        self.browse_button = ttk.Button(self.folder_frame, command=self.browse_folder)
        self.browse_button.pack(side=tk.LEFT, padx=(2, 5))

        # --- Botão de Download (agora dinâmico) ---
        self.download_button = ttk.Button(frame, command=self.start_download_thread, style="Accent.TButton")
        self.download_button.pack(pady=15, fill='x', ipady=5)
        self.style.configure("Accent.TButton", font=("-size 10 -weight bold"))
        
        # Botão de Cancelar (oculto, mesmo estilo)
        self.cancel_button = ttk.Button(frame, command=self.cancel_download, style="Accent.TButton")
        # self.cancel_button.pack() # Não mostra ainda
        self.cancel_button.pack_forget() # Garante que está oculto

        # --- Progresso ---
        self.progress_frame = ttk.Frame(frame)
        self.progress_frame.pack(fill=tk.X)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=100, mode='determinate')
        self.progress_bar.pack(pady=5, fill='x', expand=True, side=tk.LEFT)
        
        # Botão do Monitor de Threads (oculto)
        self.monitor_button = ttk.Button(self.progress_frame, text="...", width=3, command=self.open_monitor)
        # self.monitor_button.pack_forget() # Oculto por padrão

        self.status_label = ttk.Label(frame)
        self.status_label.pack(pady=5, anchor='w')
        
        self.update_all_text() # Aplica o idioma inicial

    def set_download_button_state(self, is_downloading: bool):
        """Alterna entre o botão 'Baixar' e 'Cancelar'."""
        if is_downloading:
            self.download_button.pack_forget()
            self.cancel_button.config(text=self.lang.get_string("button_cancel"))
            self.cancel_button.pack(pady=15, fill='x', ipady=5)
        else:
            self.cancel_button.pack_forget()
            self.download_button.config(text=self.lang.get_string("button_download"))
            self.download_button.pack(pady=15, fill='x', ipady=5)
            
    def show_monitor_button(self, show: bool):
        if show:
            self.monitor_button.pack(side=tk.LEFT, padx=(5,0))
        else:
            self.monitor_button.pack_forget()

    def update_all_text(self):
        """Atualiza TODO o texto da GUI principal para o idioma atual."""
        self.title(f"{self.lang.get_string('app_title')} {self.lang.get_string('version')}")
        # Menu
        self.menu_bar.entryconfig(1, label=self.lang.get_string('menu_file'))
        self.menu_file.entryconfig(0, label=self.lang.get_string('menu_history'))
        self.menu_file.entryconfig(1, label=self.lang.get_string('menu_settings'))
        self.menu_file.entryconfig(2, label=self.lang.get_string('menu_about'))
        self.menu_file.entryconfig(4, label=self.lang.get_string('menu_exit'))
        # Widgets
        self.url_label.config(text=self.lang.get_string('label_url'))
        self.path_label.config(text=self.lang.get_string('label_path'))
        self.browse_button.config(text=self.lang.get_string('button_browse'))
        self.download_button.config(text=self.lang.get_string('button_download'))
        self.cancel_button.config(text=self.lang.get_string('button_cancel'))
        self.status_label.config(text=self.lang.get_string('status_awaiting'))

    def get_thread_count(self):
        """Lê as configurações (não a GUI) para decidir o número de threads."""
        mode = self.settings['thread_mode']
        
        if mode == "Automático":
            level = self.settings['auto_level']
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
            return int(self.settings['custom_threads'])
        
        else: # Casos "1" a "8"
            try:
                return int(mode)
            except ValueError:
                return 1

    def browse_folder(self):
        foldername = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if foldername:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, foldername)
            self.settings['last_path'] = foldername
            self.save_settings(self.settings) # Salva o caminho novo

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

        self.set_download_button_state(is_downloading=True)
        self.status_label.config(text=self.lang.get_string("status_starting"))
        
        num_threads = self.get_thread_count()
        
        download_thread = threading.Thread(target=self.downloader.download_file_manager, 
                                           args=(url, folder, num_threads))
        download_thread.daemon = True
        download_thread.start()
        
        self.after(100, self.downloader.update_progress_bar)
        
    def cancel_download(self):
        """Função chamada pelo botão 'Cancelar'."""
        print("Cancelamento solicitado pelo usuário.")
        self.downloader.stop_download(cancelled=True)

    def open_history(self):
        HistoryWindow(self) # A janela se atualiza sozinha

    def open_about(self):
        AboutWindow(self) # A janela se atualiza sozinha
        
    def open_settings(self):
        SettingsWindow(self) # A janela cuida de salvar e aplicar
        
    def open_monitor(self):
        """Abre o monitor de threads se não estiver aberto."""
        if self.monitor_window and self.monitor_window.winfo_exists():
            self.monitor_window.lift() # Traz para frente
        else:
            self.monitor_window = ThreadMonitorWindow(self)

    def set_url_from_history(self, url):
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, url)
        self.attributes('-topmost', 1)
        self.attributes('-topmost', 0)


# --- 7. INICIALIZAÇÃO ---

if __name__ == "__main__":
    init_db()
    
    # Carrega as configurações apenas para definir o tema antes da janela ser criada
    temp_settings = App.load_settings(None) # Chama o método estático
    temp_lang = LanguageManager(temp_settings)
    
    theme = temp_settings.get('theme', 'Sistema')
    if theme == 'Claro':
        sv_ttk.set_theme("light")
    elif theme == 'Escuro':
        sv_ttk.set_theme("dark")
    else:
        sv_ttk.set_theme("system") # <--- CORREÇÃO APLICADA

    app = App()
    app.mainloop()