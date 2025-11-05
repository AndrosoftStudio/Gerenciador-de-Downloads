# core/settings.py
import os
import json
import sys

APP_NAME = "GerenciadorDownloadsAcelerado"
APP_VERSION = "v1.5"

DEFAULT_SETTINGS = {
    "thread_mode": "Automático",
    "custom_threads": 16,
    "auto_level": "Alto",
    "language": "pt_BR",
    "theme": "Sistema",
    "start_with_windows": False,
    "start_with_windows_minimized": False
}

def get_app_data_path():
    """Retorna o caminho de dados do app de forma independente de plataforma."""
    # Detecta se está rodando no Android (via Kivy, por exemplo)
    if 'ANDROID_ARGUMENT' in os.environ:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        app_dir = context.getFilesDir().getAbsolutePath()
        return app_dir
    
    # Lógica para Windows
    if os.name == 'nt':
        app_data_path = os.path.join(os.getenv('APPDATA'), APP_NAME)
    # Lógica para Linux/macOS
    else:
        app_data_path = os.path.join(os.path.expanduser('~'), '.config', APP_NAME)
        
    os.makedirs(app_data_path, exist_ok=True)
    return app_data_path

APP_DATA_PATH = get_app_data_path()
SETTINGS_FILE = os.path.join(APP_DATA_PATH, 'settings.json')
DB_FILE = os.path.join(APP_DATA_PATH, 'history.db')

def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            for key, value in DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()

def save_settings(new_settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(new_settings, f, indent=4)
    except Exception as e:
        print(f"Erro ao salvar configurações: {e}")