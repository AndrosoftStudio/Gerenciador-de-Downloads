# core/utils.py
import os
import webbrowser
import sys

def open_folder_in_explorer(folder_path):
    """
    Abre a pasta no gerenciador de arquivos (cross-platform).
    Baseado no código original de HistoryFrame.open_folder
    """
    if not os.path.isdir(folder_path):
        print(f"Erro: Pasta não encontrada {folder_path}")
        return False
    
    try:
        if os.name == 'nt': # Windows
            os.startfile(folder_path)
        else: # macOS/Linux
            # Usa webbrowser para compatibilidade básica
            webbrowser.open(f'file:///{folder_path}')
        return True
    except Exception as e:
        print(f"Erro ao abrir pasta: {e}")
        return False