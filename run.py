# run.py (NOVO ARQUIVO - Salve na Raiz)
import sys
import os
import platform

# Adiciona o diretório raiz ao path para que os imports de 'gui' e 'core' funcionem
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

def detect_system():
    """Detecta o sistema operacional."""
    
    # O Kivy (para Android) define esta variável de ambiente
    if 'ANDROID_ARGUMENT' in os.environ:
        return 'android'
        
    # Uma segunda forma de checagem, caso a primeira falhe
    try:
        from kivy.utils import platform as kivy_platform
        if kivy_platform == 'android':
            return 'android'
    except ImportError:
        pass # Kivy não está instalado, assume que não é Android

    # Checagem padrão do Python para sistemas desktop
    if sys.platform.startswith('win'):
        return 'windows'
    if sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
        # Trata Linux e macOS como "desktop" (usando Tkinter)
        return 'desktop'
        
    return 'unknown'

def main():
    """Ponto de entrada principal."""
    system = detect_system()

    if system == 'windows' or system == 'desktop':
        print(f"Sistema Desktop detectado ({system}). Iniciando GUI com Tkinter...")
        try:
            # Importa e inicia a app do Windows (Tkinter)
            from gui.windows.main_windows import start_windows_app
            start_windows_app()
        except ImportError as e:
            print(f"Erro Fatal: Não foi possível carregar a GUI do Windows.")
            print(f"Verifique se o arquivo 'gui/windows/main_windows.py' existe.")
            print(f"Detalhe do Erro: {e}")
            input("Pressione Enter para sair...")
        except Exception as e:
            print(f"Erro fatal ao iniciar a GUI do Windows: {e}")
            input("Pressione Enter para sair...")

    elif system == 'android':
        print("Sistema Android detectado. Iniciando GUI com Kivy...")
        try:
            # Importa e inicia a app do Android (Kivy)
            # (Você precisará criar este arquivo 'main_android.py' com Kivy)
            from gui.android.main_android import start_android_app
            start_android_app()
        except ImportError as e:
            print(f"Erro Fatal: Não foi possível carregar a GUI do Android.")
            print(f"Verifique se o arquivo 'gui/android/main_android.py' existe.")
            print(f"Detalhe do Erro: {e}")
        except Exception as e:
            print(f"Erro fatal ao iniciar a GUI do Android (Kivy): {e}")

    else:
        print(f"Sistema operacional '{system}' não suportado.")
        input("Pressione Enter para sair...")

if __name__ == "__main__":
    main()