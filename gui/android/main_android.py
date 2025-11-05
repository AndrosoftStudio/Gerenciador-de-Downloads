# gui/android/main_android.py
# (Este é um pseudo-código para Kivy, mostrando como ele usaria o core)

import os
import sys
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import mainthread # Para atualizar a GUI a partir de threads

# Adiciona o diretório raiz ao sys.path para encontrar a pasta 'core'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# --- IMPORTANDO O MESMO CORE! ---
from core.settings import load_settings
from core.database import init_db
from core.i18n import LanguageManager
from core.downloader import DownloadLogic

class AndroidDownloaderGUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        
        self.settings = load_settings()
        self.lang = LanguageManager(self.settings)
        
        # Define os callbacks do Kivy
        callbacks = {
            "on_progress": self.on_download_progress,
            "on_complete": self.on_download_complete,
            "on_error": self.on_download_error,
            "on_status_change": self.on_status_change,
            "on_set_downloading_state": self.set_download_button_state
        }
        
        self.downloader = DownloadLogic(self.lang, callbacks)
        
        self.status_label = Label(text=self.lang.get_string("status_awaiting"))
        self.add_widget(self.status_label)
        
        self.download_button = Button(text=self.lang.get_string("button_download"))
        self.download_button.bind(on_press=self.start_download)
        self.add_widget(self.download_button)

    def start_download(self, instance):
        # Lógica de pegar URL e pasta (do Kivy)
        url = "http://exemplo.com/arquivo.zip"
        # No Android, você usaria caminhos específicos
        save_path = "/storage/emulated/0/Download"
        num_threads = 8 # Pego das settings
        
        # Roda o MESMO downloader.py em uma thread
        threading.Thread(target=self.downloader.download_file_manager, 
                         args=(url, save_path, num_threads), daemon=True).start()

    # --- Callbacks do Kivy ---
    @mainthread
    def on_status_change(self, message):
        self.status_label.text = message

    @mainthread
    def on_download_progress(self, progress, speed):
        self.status_label.text = f"Progresso: {progress:.2f}% | Vel: {speed}"

    @mainthread
    def on_download_complete(self, filename):
        self.status_label.text = f"Concluído: {filename}"

    @mainthread
    def on_download_error(self, title, message):
        self.status_label.text = f"Erro: {message}"
        
    @mainthread
    def set_download_button_state(self, is_downloading):
        self.download_button.disabled = is_downloading


class KivyApp(App):
    def build(self):
        return AndroidDownloaderGUI()

if __name__ == "__main__":
    init_db() # O MESMO init_db!
    KivyApp().run()