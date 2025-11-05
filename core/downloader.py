# core/downloader.py
import requests
import threading
import os
import time
import sqlite3
from urllib.parse import urlparse

# --- Lógica de DB (de run.py) ---
# (Idealmente, estaria em core/database.py, mas incluído aqui para ser completo)

# Bloco de run.py
APP_NAME = "GerenciadorDownloadsAcelerado"
if os.name == 'nt':
    APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), APP_NAME)
else:
    APP_DATA_PATH = os.path.join(os.path.expanduser('~'), '.config', APP_NAME)
DB_FILE = os.path.join(APP_DATA_PATH, 'history.db')
os.makedirs(APP_DATA_PATH, exist_ok=True)
# ---

def add_to_history(url, file_path):
    # Bloco de run.py
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

# --- Classe de Lógica de Download ---

class DownloadLogic:
    """
    Contém toda a lógica de download, de forma independente da GUI.
    Baseado em run.py
    """
    def __init__(self, lang_manager, callbacks):
        self.lang = lang_manager
        self.callbacks = callbacks # Dicionário de funções da GUI
        self.reset_globals()
        
    def reset_globals(self):
        #
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
        # Esta função agora é um loop interno, não um 'after' do Tkinter
        if not self.download_active:
            return

        last_downloaded = self.global_total_downloaded
        last_time = time.time()
        
        # Inicia o loop de monitoramento
        threading.Thread(target=self._update_speed_logic, 
                         args=(last_downloaded, last_time), daemon=True).start()

    def _update_speed_logic(self, last_downloaded, last_time):
        # Baseado em run.py
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
        
        # CHAMA O CALLBACK DA GUI
        if self.callbacks.get("on_progress"):
            self.callbacks["on_progress"](self.global_progress, self.global_speed)

        # Reagenda (usando time.sleep em vez de app.after)
        time.sleep(0.5) # Atualiza a cada 0.5s
        if self.download_active:
            self._update_speed_logic(self.global_total_downloaded, time.time())

    def download_file_chunk(self, session, url, filename, start_byte, end_byte, thread_id):
        #
        # (Esta função é idêntica à original em run.py)
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
        #
        # (Esta função é idêntica à original em run.py, com a correção do bug)
        try:
            with session.get(url, stream=True, allow_redirects=True, timeout=20) as response:
                response.raise_for_status()
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024*128):
                        if not self.download_active: return 
                        if chunk:
                            f.write(chunk)
                            len_chunk = len(chunk) # <--- Correção
                            with self.global_lock:
                                 self.global_total_downloaded += len_chunk
        except Exception as e:
            if self.download_active:
                print(f"Erro no download (single): {e}")
                self.stop_download(error=e)

    def download_file_manager(self, url, save_path, num_threads):
        #
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
                
                # --- CHAMADAS DE CALLBACK ---
                self._callback_status("status_starting")

                if supports_ranges and self.global_total_size > 0 and num_threads > 1:
                    self.is_multithreaded = True
                    self._callback_status("status_accelerated", count=num_threads)
                    if self.callbacks.get("on_show_monitor"):
                        self.callbacks["on_show_monitor"](True)
                    
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
                    if self.callbacks.get("on_show_monitor"):
                        self.callbacks["on_show_monitor"](False)
                    
                    if num_threads > 1:
                        self._callback_status("status_unsupported")
                    else:
                        self._callback_status("status_normal")
                    
                    self.download_file_single(session, final_url, filename, self.global_total_size)
                
                if self.download_active:
                    self.global_progress = 100
                    # CHAMA O CALLBACK DE CONCLUSÃO
                    if self.callbacks.get("on_complete"):
                        self.callbacks["on_complete"](filename)
                    add_to_history(self.url_para_historico, filename) #

        except requests.exceptions.MissingSchema:
            self._callback_error(self.lang.get_string("error_url_msg", url=url), 
                                 self.lang.get_string("error_url"))
        except requests.exceptions.RequestException as e:
            self._callback_error(self.lang.get_string("error_download"), str(e))
        except Exception as e:
            self._callback_error(self.lang.get_string("error_file"), str(e))
        finally:
            if self.download_active:
                self.stop_download()

    def stop_download(self, error=None, error_msg=None, title=None, cancelled=False):
        #
        if not self.download_active and not cancelled:
            return 
            
        self.download_active = False
        self.is_multithreaded = False
        
        # CHAMA CALLBACKS DA GUI
        if self.callbacks.get("on_show_monitor"):
            self.callbacks["on_show_monitor"](False)
        if self.callbacks.get("on_set_downloading_state"):
            self.callbacks["on_set_downloading_state"](False)
        
        if cancelled:
            self._callback_status("status_cancelled")
            return

        if error:
            error_str = str(error)
            if "Errno 22" in error_str:
                 self.download_frame.status_label.config(text=self.lang.get_string("status_file_error"))
                 self._callback_error(self.lang.get_string("error_file"), 
                                      self.lang.get_string("error_file_msg", error=error))
            else:
                self._callback_error(self.lang.get_string("error_download"), 
                                     self.lang.get_string("error_download_msg", error=error_str))
        elif error_msg:
            self._callback_error(title, error_msg)
        else:
             pass # Conclusão normal, já tratada em download_file_manager

    # --- Métodos Helper de Callback ---
    def _callback_status(self, lang_key, **kwargs):
        """Helper para enviar uma string de status traduzida para a GUI."""
        if self.callbacks.get("on_status_change"):
            msg = self.lang.get_string(lang_key, **kwargs)
            self.callbacks["on_status_change"](msg)
    
    def _callback_error(self, title, message):
        """Helper para enviar um erro formatado para a GUI."""
        if self.callbacks.get("on_error"):
            self.callbacks["on_error"](title or self.lang.get_string("error_title"), message)