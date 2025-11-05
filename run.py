import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import threading
import os
import time
import json
import sqlite3
import webbrowser
import os # <-- Importação correta
import glob
import sys
from urllib.parse import urlparse
from PIL import Image, ImageTk
import sv_ttk 

# --- 0. FUNÇÃO HELPER PARA PYINSTALLER ---

def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))

    return os.path.join(base_path, relative_path)

# --- 1. CONFIGURAÇÕES E DADOS (APPDATA) ---

APP_NAME = "GerenciadorDownloadsAcelerado"
APP_VERSION = "v1.3" # Versão atualizada

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
    "start_with_windows_minimized": False # <--- NOVO
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
            lang_path = os.path.join(resource_path("idiomas"), "*.json")
            lang_files = glob.glob(lang_path)
            
            if not lang_files:
                print(f"ERRO: Nenhum arquivo JSON encontrado em '{lang_path}'")
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
        string = self.strings.get(key, f"_{key}_")
        try:
            return string.format(**kwargs)
        except KeyError:
            return string 

    def get_available_languages(self):
        return list(self.languages.keys())

# --- 3. BANCO DE DADOS DO HISTÓRICO ---
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

# --- 4. DEFINIÇÃO DAS PÁGINAS (FRAMES) ---

class DownloadFrame(ttk.Frame):
    """A 'página' principal de download."""
    def __init__(self, master, app_instance):
        super().__init__(master, padding="15")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager
        self.downloader = app_instance.downloader
        self.style = app_instance.style
        
        self.create_widgets()
        self.update_text()

    def create_widgets(self):
        # --- Seção de Download ---
        self.url_label = ttk.Label(self)
        self.url_label.pack(padx=5, pady=(5, 2), anchor='w') # <-- Mais espaço em cima
        self.url_entry = ttk.Entry(self, width=60)
        self.url_entry.pack(padx=5, pady=2, fill='x')

        self.path_label = ttk.Label(self)
        self.path_label.pack(padx=5, pady=(10, 5), anchor='w') # <-- Mais espaço
        self.folder_frame = ttk.Frame(self)
        self.folder_frame.pack(fill='x', expand=False) # <-- Não expandir

        self.folder_entry = ttk.Entry(self.folder_frame, width=50)
        self.folder_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(5, 2))
        
        last_path = self.app_instance.settings.get('last_path', os.path.expanduser('~/Downloads'))
        if not os.path.isdir(last_path):
             last_path = os.path.expanduser('~/Downloads')
        self.folder_entry.insert(0, last_path)

        self.browse_button = ttk.Button(self.folder_frame, command=self.browse_folder)
        self.browse_button.pack(side=tk.LEFT, padx=(2, 5))

        # --- Botão de Download (dinâmico) ---
        self.download_button = ttk.Button(self, command=self.start_download_thread, style="Accent.TButton")
        self.download_button.pack(pady=20, fill='x', ipady=5) # <-- Mais espaço
        self.style.configure("Accent.TButton", font=("-size 10 -weight bold"))
        
        self.cancel_button = ttk.Button(self, command=self.cancel_download, style="Accent.TButton")
        self.cancel_button.pack_forget()

        # --- Progresso ---
        self.progress_frame = ttk.Frame(self)
        self.progress_frame.pack(fill=tk.X)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient='horizontal', length=100, mode='determinate')
        self.progress_bar.pack(pady=5, fill='x', expand=True, side=tk.LEFT)
        
        self.monitor_button = ttk.Button(self.progress_frame, text="...", width=3, command=self.open_monitor)
        
        self.status_label = ttk.Label(self)
        self.status_label.pack(pady=(10, 5), anchor='w') # <-- Mais espaço

    def set_download_button_state(self, is_downloading: bool):
        if is_downloading:
            self.download_button.pack_forget()
            self.cancel_button.config(text=self.lang.get_string("button_cancel"))
            self.cancel_button.pack(pady=20, fill='x', ipady=5)
        else:
            self.cancel_button.pack_forget()
            self.download_button.config(text=self.lang.get_string("button_download"))
            self.download_button.pack(pady=20, fill='x', ipady=5)
            
    def show_monitor_button(self, show: bool):
        if show:
            self.monitor_button.pack(side=tk.LEFT, padx=(5,0))
        else:
            self.monitor_button.pack_forget()
            
    def update_text(self):
        """Atualiza o texto desta página."""
        self.url_label.config(text=self.lang.get_string('label_url'))
        self.path_label.config(text=self.lang.get_string('label_path'))
        self.browse_button.config(text=self.lang.get_string('button_browse'))
        self.download_button.config(text=self.lang.get_string('button_download'))
        self.cancel_button.config(text=self.lang.get_string('button_cancel'))
        # Não atualiza o status_label para não sobrescrever o progresso
        
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

        self.set_download_button_state(is_downloading=True)
        self.status_label.config(text=self.lang.get_string("status_starting"))
        
        num_threads = self.get_thread_count()
        
        download_thread = threading.Thread(target=self.downloader.download_file_manager, 
                                           args=(url, folder, num_threads))
        download_thread.daemon = True
        download_thread.start()
        
        self.app_instance.after(100, self.downloader.update_progress_bar)
        
    def cancel_download(self):
        print("Cancelamento solicitado pelo usuário.")
        self.downloader.stop_download(cancelled=True)
        
    def open_monitor(self):
        self.app_instance.open_monitor()


class AboutFrame(ttk.Frame):
    """A 'página' Sobre."""
    def __init__(self, master, app_instance):
        super().__init__(master, padding="20")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager
        
        try:
            # --- CORREÇÃO DO ÍCONE ---
            # Usa resource_path para encontrar o ícone
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

        self.links = [
            ("LinkedIn", "https://linkedin.com/in/andrejorge-devandre/"),
            ("GitHub (Pessoal)", "https://github.com/AndrosoftStudio"),
            ("YouTube", "https://www.youtube.com/@devandre2970"),
        ]
        
        for text, url in self.links:
            self.create_link(self, text, url)
            
        self.repo_link = self.create_link(self, "", "https://github.com/AndrosoftStudio/Gerenciador-de-Downloads")
        
        self.update_text()

    def create_link(self, parent, text, url):
        link_label = ttk.Label(parent, text=text, foreground="blue", cursor="hand2", style="Link.TLabel")
        link_label.pack()
        link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open_new_tab(u))
        self.app_instance.style.configure("Link.TLabel", font=("-underline 1"))
        return link_label

    def update_text(self):
        self.title_label.config(text=f"{self.lang.get_string('app_title')} {self.lang.get_string('version')}")
        self.created_by_label.config(text=self.lang.get_string('win_about_created_by'))
        self.repo_link.config(text=self.lang.get_string('win_about_repo'))


class HistoryFrame(ttk.Frame):
    """A 'página' de Histórico."""
    def __init__(self, master, app_instance):
        super().__init__(master, padding="10")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager

        # --- CORREÇÃO DE LAYOUT ---
        # 1. Botões vêm primeiro, na parte de baixo
        button_frame = ttk.Frame(self, padding="10")
        button_frame.pack(fill=tk.X, side=tk.BOTTOM) 

        self.btn_copy = ttk.Button(button_frame, command=self.copy_link)
        self.btn_copy.pack(side=tk.LEFT, padx=5)
        
        self.btn_open = ttk.Button(button_frame, command=self.open_folder)
        self.btn_open.pack(side=tk.LEFT, padx=5)

        self.btn_redownload = ttk.Button(button_frame, command=self.redownload)
        self.btn_redownload.pack(side=tk.LEFT, padx=5)
        
        # 2. Frame da Árvore (Treeview) + Scrollbar
        tree_frame = ttk.Frame(self)
        tree_frame.pack(expand=True, fill=tk.BOTH, side=tk.TOP, pady=(0, 5))

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.cols = ('Data', 'Arquivo', 'Link', 'Pasta')
        self.tree = ttk.Treeview(tree_frame, columns=self.cols, show='headings', yscrollcommand=scrollbar.set)
        self.tree.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)
        
        scrollbar.config(command=self.tree.yview)
        # --- FIM DA CORREÇÃO DE LAYOUT ---
        
        self.update_text()
        
    def on_show(self):
        """Chamado pela App quando esta página é mostrada."""
        self.load_history()
        
    def load_history(self):
        self.tree.delete(*self.tree.get_children()) # Limpa a árvore
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
            self.app_instance.show_page("home") # Volta para a página de download


class SettingsFrame(ttk.Frame):
    """A 'página' de Configurações."""
    def __init__(self, master, app_instance):
        super().__init__(master, padding="15")
        self.app_instance = app_instance
        self.lang = app_instance.lang_manager
        
        # Carrega as configurações atuais
        self.settings = app_instance.settings.copy()

        # --- Variáveis de Controle ---
        self.thread_mode_var = tk.StringVar(master=self, value=self.settings['thread_mode'])
        self.auto_level_var = tk.StringVar(master=self, value=self.settings['auto_level'])
        self.custom_thread_var = tk.StringVar(master=self, value=str(self.settings['custom_threads']))
        self.theme_var = tk.StringVar(master=self, value=self.settings['theme'])
        self.lang_var = tk.StringVar(master=self, value=self.settings['language'])
        self.startup_var = tk.BooleanVar(master=self, value=self.settings['start_with_windows'])
        # --- NOVO ---
        self.startup_minimized_var = tk.BooleanVar(master=self, value=self.settings['start_with_windows_minimized'])

        # --- Criação dos Widgets ---

        # Seção de Threads
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
        
        
        # Seção de Aparência
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
        
        # Seção Geral
        self.general_frame = ttk.LabelFrame(self, padding="10")
        self.general_frame.pack(fill=tk.X, pady=5)
        
        self.startup_check = ttk.Checkbutton(self.general_frame, variable=self.startup_var,
                                             command=self.on_startup_change) # <-- Adiciona comando
        self.startup_check.pack(side=tk.TOP, padx=5, anchor='w')
        
        # --- NOVO CHECKBOX ---
        self.startup_minimized_check = ttk.Checkbutton(self.general_frame, variable=self.startup_minimized_var)
        self.startup_minimized_check.pack(side=tk.TOP, padx=(25, 5), anchor='w') # <-- Indentado
        
        # Botão Salvar
        self.save_button = ttk.Button(self, command=self.save_and_return)
        self.save_button.pack(side=tk.BOTTOM, pady=20)
        
        self.update_text() 
        self.on_thread_mode_change() 
        self.on_startup_change() # <-- Chama para definir o estado inicial

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

        if mode == self.lang.get_string("win_settings_mode_auto"): # "Automático"
            self.auto_level_frame.pack(fill=tk.X, pady=5)
        elif mode == self.lang.get_string("win_settings_mode_custom"): # "Personalizado"
            self.custom_thread_entry.pack(side=tk.LEFT, padx=5)
            
    def on_startup_change(self, *args):
        """Ativa ou desativa o checkbox 'iniciar minimizado'."""
        if self.startup_var.get():
            self.startup_minimized_check.config(state=tk.NORMAL)
        else:
            self.startup_minimized_check.config(state=tk.DISABLED)
    
    def update_text(self):
        """Atualiza todo o texto da janela com base no idioma."""
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
        # --- NOVO ---
        self.startup_minimized_check.config(text=self.lang.get_string('win_settings_startup_minimized'))
        
        self.save_button.config(text=self.lang.get_string('win_settings_save'))

    def save_and_return(self):
        """Salva as configurações no app principal e volta para Home."""
        
        old_theme = self.app_instance.settings['theme']
        
        # Converte as strings traduzidas de volta para chaves
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
            
        theme_str = self.theme_var.get()
        if theme_str == self.lang.get_string("win_settings_theme_system"):
            self.settings['theme'] = "Sistema"
        elif theme_str == self.lang.get_string("win_settings_theme_light"):
            self.settings['theme'] = "Claro"
        elif theme_str == self.lang.get_string("win_settings_theme_dark"):
            self.settings['theme'] = "Escuro"
            
        self.settings['language'] = self.lang_var.get()
        self.settings['start_with_windows'] = self.startup_var.get()
        # --- NOVO ---
        self.settings['start_with_windows_minimized'] = self.startup_minimized_var.get()
        
        new_theme = self.settings['theme']

        # Aplica as configurações
        self.app_instance.save_settings(self.settings)
        self.app_instance.apply_settings()
        
        if new_theme == "Sistema" and old_theme != "Sistema":
            messagebox.showinfo("Tema Alterado", 
                                "O tema foi definido como 'Sistema'.\nReinicie o aplicativo para que a mudança tenha efeito.",
                                parent=self)
        
        # Volta para a página principal
        self.app_instance.show_page("home")


class ThreadMonitorWindow(tk.Toplevel):
    """Monitor de Threads (continua Toplevel de propósito)."""
    def __init__(self, master):
        super().__init__(master)
        self.app_instance = master
        self.lang = master.lang_manager
        self.downloader = master.downloader
        
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

# --- 5. LÓGICA DE DOWNLOAD (Atualizada) ---

class DownloadLogic:
    def __init__(self, app_instance):
        self.app = app_instance # Referência ao App (tk.Tk)
        self.lang = app_instance.lang_manager
        self.download_frame = None # Será definido por set_download_frame
        self.reset_globals()
        
    def set_download_frame(self, frame):
        """Define a página de download para que a lógica possa atualizar seus widgets."""
        self.download_frame = frame
        
    def reset_globals(self):
        self.download_active = False
        self.is_multithreaded = False
        self.global_progress = 0
        self.global_speed = "0 MB/s"
        self.global_total_downloaded = 0
        self.global_total_size = 0
        self.global_lock = threading.Lock()
        self.url_para_historico = ""
        self.thread_stats = {} 

    def update_progress_bar(self):
        if not self.download_active or not self.download_frame:
            return

        last_downloaded = self.global_total_downloaded
        last_time = time.time()
        
        self.app.after(500, lambda: self._update_speed_logic(last_downloaded, last_time))

    def _update_speed_logic(self, last_downloaded, last_time):
        if not self.download_active or not self.download_frame:
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
        
        # Atualiza os widgets na DownloadFrame
        self.download_frame.progress_bar['value'] = self.global_progress
        self.download_frame.status_label.config(text=self.lang.get_string("status_progress", 
                                       progress=self.global_progress, speed=self.global_speed))

        self.update_progress_bar() # Reagenda o loop

    def download_file_chunk(self, session, url, filename, start_byte, end_byte, thread_id):
        try:
            headers = {'Range': f'bytes={start_byte}-{end_byte}'}
            with session.get(url, headers=headers, stream=True, timeout=20) as response:
                response.raise_for_status()

                with open(filename, 'r+b') as f:
                    f.seek(start_byte)
                    for chunk in response.iter_content(chunk_size=1024*128):
                        if not self.download_active: return 
                        if chunk:
                            f.write(chunk)
                            len_chunk = len(chunk)
                            
                            with self.global_lock:
                                self.global_total_downloaded += len_chunk
                                stats = self.thread_stats[thread_id]
                                stats['downloaded'] += len_chunk
                                
                                current_time = time.time()
                                time_diff = current_time - stats['last_time']
                                if time_diff > 0.5: 
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
                        if not self.download_active: return 
                        if chunk:
                            f.write(chunk)
                            with self.global_lock:
                                 self.global_total_downloaded += len_chunk
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
                    self.is_multithreaded = True
                    self.download_frame.status_label.config(text=self.lang.get_string("status_accelerated", count=num_threads))
                    self.download_frame.show_monitor_button(True)
                    
                    with open(filename, 'wb') as f:
                        f.seek(self.global_total_size - 1)
                        f.write(b'\0')
                    
                    chunk_size = self.global_total_size // num_threads
                    threads = []
                    
                    for i in range(num_threads):
                        start_byte = i * chunk_size
                        end_byte = start_byte + chunk_size - 1 if i < num_threads - 1 else self.global_total_size - 1
                        
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
                    self.is_multithreaded = False
                    self.download_frame.show_monitor_button(False)
                    if num_threads > 1:
                        self.download_frame.status_label.config(text=self.lang.get_string("status_unsupported"))
                    else:
                         self.download_frame.status_label.config(text=self.lang.get_string("status_normal"))
                    
                    self.download_file_single(session, final_url, filename, self.global_total_size)
                
                if self.download_active:
                    self.global_progress = 100
                    self.download_frame.progress_bar['value'] = 100
                    self.download_frame.status_label.config(text=self.lang.get_string("status_completed", file=filename))
                    messagebox.showinfo("Sucesso", self.lang.get_string("status_completed", file=filename))
                    add_to_history(self.url_para_historico, filename)

        except requests.exceptions.MissingSchema:
            self.stop_download(error_msg=self.lang.get_string("error_url_msg", url=url), title=self.lang.get_string("error_url"))
        except requests.exceptions.RequestException as e:
            self.stop_download(error=e)
        except Exception as e:
            self.stop_download(error=e)
        finally:
            if self.download_active:
                self.stop_download()

    def stop_download(self, error=None, error_msg=None, title=None, cancelled=False):
        if not self.download_active and not cancelled:
            return 
            
        self.download_active = False
        self.is_multithreaded = False
        
        if not self.download_frame: # Se o frame ainda não foi setado
            return 
            
        self.download_frame.show_monitor_button(False)
        self.download_frame.set_download_button_state(is_downloading=False)
        
        if cancelled:
            self.download_frame.status_label.config(text=self.lang.get_string("status_cancelled"))
            return

        if error:
            error_str = str(error)
            if "Errno 22" in error_str:
                 self.download_frame.status_label.config(text=self.lang.get_string("status_file_error"))
                 messagebox.showerror(self.lang.get_string("error_file"),
                                      self.lang.get_string("error_file_msg", error=error))
            else:
                self.download_frame.status_label.config(text=self.lang.get_string("status_error", error=error_str))
                messagebox.showerror(self.lang.get_string("error_download"), 
                                     self.lang.get_string("error_download_msg", error=error_str))
        elif error_msg:
            self.download_frame.status_label.config(text=self.lang.get_string("status_error", error=error_msg))
            messagebox.showerror(title or self.lang.get_string("error_title"), error_msg)
        else:
             pass

# --- 6. APLICAÇÃO PRINCIPAL (GUI) ---

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        self.lang_manager = LanguageManager(self.settings)
        self.lang = self.lang_manager 
        
        self.downloader = DownloadLogic(self)
        self.style = ttk.Style()
        self.monitor_window = None 
        
        # --- CORREÇÃO DA "TELINHA FANTASMA" ---
        # O tema é aplicado DEPOIS que a janela 'self' (tk.Tk) existe,
        # mas ANTES de criar os widgets.
        self.apply_theme(on_startup=True) 
        
        self.create_widgets()
        self.downloader.set_download_frame(self.pages["home"]) # Conecta a lógica à página
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
        # --- MUDANÇA: Proporção 16:9 ---
        self.geometry("960x540") # Tamanho inicial 16:9
        self.wm_aspect(16, 9, 16, 9) # Força a proporção 16:9
        # --- FIM DA MUDANÇA ---
        
        try:
            self.iconbitmap(resource_path('icon.ico'))
        except tk.TclError:
            print("Aviso: 'icon.ico' não encontrado ou inválido.")

        # --- Menu Bar ---
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
        
        # --- Container Principal das Páginas ---
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
        self.update_all_text() # Aplica o idioma inicial

    def show_page(self, page_name):
        """Esconde a página atual e mostra a nova página."""
        if self.current_page_name == page_name:
            return # Já está na página
            
        if self.current_page_name:
            current_page = self.pages[self.current_page_name]
            current_page.pack_forget()
            
        self.current_page_name = page_name
        page = self.pages[page_name]
        page.pack(fill=tk.BOTH, expand=True)
        
        # Chama hooks de atualização se existirem
        if hasattr(page, 'on_show'):
            page.on_show()

    def update_all_text(self):
        """Atualiza o texto de todas as partes da GUI."""
        self.title(f"{self.lang.get_string('app_title')} {self.lang.get_string('version')}")
        # Menu
        self.menu_bar.entryconfig(1, label=self.lang.get_string('menu_file'))
        self.menu_file.entryconfig(0, label="Download") # Home
        self.menu_file.entryconfig(1, label=self.lang.get_string('menu_history'))
        self.menu_file.entryconfig(2, label=self.lang.get_string('menu_settings'))
        self.menu_file.entryconfig(3, label=self.lang.get_string('menu_about'))
        self.menu_file.entryconfig(5, label=self.lang.get_string('menu_exit'))
        
        # Atualiza todas as páginas
        for page in self.pages.values():
            if hasattr(page, 'update_text'):
                page.update_text()
        
        # Garante que o status da home_page não seja sobrescrito
        if self.downloader and not self.downloader.download_active:
             self.pages["home"].status_label.config(text=self.lang.get_string('status_awaiting'))

    def open_monitor(self):
        if self.monitor_window and self.monitor_window.winfo_exists():
            self.monitor_window.lift() 
        else:
            self.monitor_window = ThreadMonitorWindow(self)

    def set_url_from_history(self, url):
        """Chamado pelo HistoryFrame para preencher o link na DownloadFrame."""
        self.pages["home"].url_entry.delete(0, tk.END)
        self.pages["home"].url_entry.insert(0, url)
        self.attributes('-topmost', 1)
        self.attributes('-topmost', 0)


# --- 7. INICIALIZAÇÃO ---

if __name__ == "__main__":
    init_db()
    
    # --- CORREÇÃO DA TELINHA FANTASMA ---
    # A lógica de aplicar o tema foi movida para DENTRO
    # da classe App (linha 946).
    
    app = App()
    app.mainloop()