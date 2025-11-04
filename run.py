import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import threading
import os
import time
from urllib.parse import urlparse

# --- Constantes ---
NUM_THREADS = 8  # <--- AQUI A "MÁGICA": 8 threads!

# --- Variáveis Globais para Comunicação ---
global_progress = 0
global_speed = "0 MB/s"
download_active = False
global_total_downloaded = 0
global_total_size = 0
global_lock = threading.Lock() # "Cadeado" para sincronizar as threads

def update_progress_bar():
    """
    Função que roda na thread principal (GUI) para atualizar
    a barra de progresso e o texto de status de forma segura.
    """
    global global_speed
    
    if not download_active:
        return

    # Guarda o valor baixado para calcular a velocidade
    last_downloaded = global_total_downloaded
    last_time = time.time()
    
    # Pausa por 500ms
    root.after(500, lambda: _update_speed_logic(last_downloaded, last_time))

def _update_speed_logic(last_downloaded, last_time):
    """
    Lógica de cálculo de velocidade, separada para funcionar com o 'after'.
    """
    global global_speed, global_progress
    
    if not download_active:
        return

    current_time = time.time()
    time_diff = current_time - last_time
    
    with global_lock:
        current_downloaded = global_total_downloaded
        if global_total_size > 0:
            global_progress = (current_downloaded / global_total_size) * 100
        else:
            global_progress = 0

    bytes_diff = current_downloaded - last_downloaded
    
    if time_diff > 0:
        speed_bps = bytes_diff / time_diff # Bytes por segundo
        speed_MBps = (speed_bps / 1024 / 1024)
        speed_KBps = (speed_bps / 1024)

        if speed_MBps > 1:
            global_speed = f"{speed_MBps:.2f} MB/s"
        else:
            global_speed = f"{speed_KBps:.2f} KB/s"
    
    progress_bar['value'] = global_progress
    status_label.config(text=f"Progresso: {global_progress:.2f}% | Velocidade: {global_speed}")

    # Agenda a si mesma para rodar novamente
    update_progress_bar()


def download_file_chunk(url, filename, start_byte, end_byte):
    """
    A função "Trabalhadora". Baixa um único "pedaço" do arquivo.
    """
    global global_total_downloaded
    try:
        # Pede ao servidor APENAS o pedaço (range) de bytes
        headers = {'Range': f'bytes={start_byte}-{end_byte}'}
        response = requests.get(url, headers=headers, stream=True, timeout=20)
        response.raise_for_status()

        # Abre o arquivo em modo 'r+b' (leitura/escrita binária)
        # Isso permite escrever em qualquer posição do arquivo sem apagar
        with open(filename, 'r+b') as f:
            f.seek(start_byte)  # <-- Pula para a posição certa!
            
            for chunk in response.iter_content(chunk_size=8192):
                if not download_active: # Permite cancelar o download
                    return
                if chunk:
                    f.write(chunk)
                    
                    # Usa o "cadeado" para atualizar o total baixado
                    # Isso evita que duas threads escrevam ao mesmo tempo
                    with global_lock:
                        global_total_downloaded += len(chunk)

    except Exception as e:
        # Se uma thread falhar, é melhor parar tudo
        print(f"Erro na thread ({start_byte}-{end_byte}): {e}")
        stop_download(error=e)


def download_file_single(url, filename, total_size):
    """
    Função de fallback (o nosso script antigo)
    Usada se o servidor não suportar "Ranges".
    """
    global global_total_downloaded, global_total_size
    try:
        response = requests.get(url, stream=True, allow_redirects=True)
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if not download_active:
                    return
                if chunk:
                    f.write(chunk)
                    with global_lock:
                         global_total_downloaded += len(chunk)

    except Exception as e:
        print(f"Erro no download (single): {e}")
        stop_download(error=e)


def download_file_manager(url, save_path):
    """
    A função "Gerente". Decide se o download será segmentado ou único.
    Esta função roda na THREAD SEPARADA.
    """
    global global_progress, global_speed, download_active, global_total_downloaded, global_total_size
    
    # Reseta as variáveis globais
    download_active = True
    global_progress = 0
    global_total_downloaded = 0
    global_total_size = 0
    global_speed = "Calculando..."
    
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url.lstrip('/')
            
        # 1. FAZ A CHECAGEM INICIAL (com HEAD, mais rápido)
        response = requests.head(url, allow_redirects=True, timeout=10)
        response.raise_for_status()
        
        # Pega o tamanho total
        global_total_size = int(response.headers.get('content-length', 0))
        
        # Pega o nome do arquivo limpo
        parsed_path = urlparse(response.url).path # Usa response.url para caso de redirect
        base_filename = os.path.basename(parsed_path)
        filename = os.path.join(save_path, base_filename or "downloaded_file")

        # 2. DECIDE A ESTRATÉGIA
        supports_ranges = response.headers.get('Accept-Ranges') == 'bytes'
        
        if supports_ranges and global_total_size > 0 and NUM_THREADS > 1:
            # --- ESTRATÉGIA MULTITHREAD (ACELERADA) ---
            status_label.config(text=f"Modo acelerado (8 threads) ativado...")
            
            # Cria um arquivo "vazio" com o tamanho total
            with open(filename, 'wb') as f:
                f.seek(global_total_size - 1)
                f.write(b'\0')
            
            # Calcula o tamanho de cada "pedaço"
            chunk_size = global_total_size // NUM_THREADS
            threads = []
            
            for i in range(NUM_THREADS):
                start_byte = i * chunk_size
                # O último pedaço vai até o fim do arquivo
                end_byte = start_byte + chunk_size - 1 if i < NUM_THREADS - 1 else global_total_size - 1
                
                # Cria e inicia a thread "trabalhadora"
                t = threading.Thread(target=download_file_chunk, args=(response.url, filename, start_byte, end_byte))
                t.daemon = True
                t.start()
                threads.append(t)
            
            # Espera todas as threads terminarem
            for t in threads:
                t.join()

        else:
            # --- ESTRATÉGIA SINGLE-THREAD (FALLBACK) ---
            status_label.config(text=f"Servidor não suporta aceleração. Baixando em modo normal...")
            download_file_single(response.url, filename, global_total_size)
        
        # 3. FINALIZAÇÃO
        if download_active: # Se não foi cancelado por um erro
            global_progress = 100
            progress_bar['value'] = 100
            status_label.config(text=f"Download Concluído! Salvo em: {filename}")
            messagebox.showinfo("Sucesso", f"Download Concluído!\nSalvo em: {filename}")

    except requests.exceptions.MissingSchema:
        stop_download(error_msg=f"A URL parece estar incompleta.\nFaltou 'http://' ou 'https://'?\nURL: {url}")
    except requests.exceptions.RequestException as e:
        stop_download(error=e)
    except Exception as e:
        stop_download(error=e)
    finally:
        stop_download()


def stop_download(error=None, error_msg=None):
    """
    Para todas as operações e reabilita o botão.
    """
    global download_active
    download_active = False
    download_button.config(state=tk.NORMAL)
    
    if error:
        status_label.config(text=f"Erro: {error}")
        messagebox.showerror("Erro de Download", f"Ocorreu um erro:\n{error}")
    elif error_msg:
        status_label.config(text=f"Erro: {error_msg}")
        messagebox.showerror("Erro", error_msg)


def start_download_thread():
    url = url_entry.get()
    folder = folder_entry.get()
    
    if not url or not folder:
        messagebox.showwarning("Campos Vazios", "Por favor, preencha o link e a pasta de destino.")
        return
        
    if not os.path.isdir(folder):
        messagebox.showerror("Pasta Inválida", "O caminho da pasta de destino não é válido.")
        return

    download_button.config(state=tk.DISABLED)
    status_label.config(text="Iniciando download...")
    
    # Inicia a thread "Gerente"
    download_thread = threading.Thread(target=download_file_manager, args=(url, folder))
    download_thread.daemon = True
    download_thread.start()
    
    # Inicia o loop de atualização da interface
    root.after(100, update_progress_bar)

def browse_folder():
    foldername = filedialog.askdirectory()
    if foldername:
        folder_entry.delete(0, tk.END)
        folder_entry.insert(0, foldername)

# --- Configuração da Interface Gráfica (GUI) ---
root = tk.Tk()
root.title("Gerenciador de Downloads (Acelerado)")
root.geometry("500x250")

frame = ttk.Frame(root, padding="10")
frame.pack(fill=tk.BOTH, expand=True)

ttk.Label(frame, text="Link para Download:").pack(padx=5, pady=2, anchor='w')
url_entry = ttk.Entry(frame, width=60)
url_entry.pack(padx=5, pady=2, fill='x')

ttk.Label(frame, text="Salvar na Pasta:").pack(padx=5, pady=5, anchor='w')
folder_frame = ttk.Frame(frame)
folder_frame.pack(fill='x', expand=True)

folder_entry = ttk.Entry(folder_frame, width=50)
folder_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=(5, 2))

browse_button = ttk.Button(folder_frame, text="Procurar...", command=browse_folder)
browse_button.pack(side=tk.LEFT, padx=(2, 5))

download_button = ttk.Button(frame, text="Baixar Arquivo", command=start_download_thread)
download_button.pack(pady=15, fill='x')

progress_bar = ttk.Progressbar(frame, orient='horizontal', length=100, mode='determinate')
progress_bar.pack(pady=5, fill='x')

status_label = ttk.Label(frame, text="Aguardando...")
status_label.pack(pady=5, anchor='w')

# Inicia o loop principal da interface
root.mainloop()