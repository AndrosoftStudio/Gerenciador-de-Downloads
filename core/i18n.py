# core/i18n.py
import json
import glob
import os
import sys

def resource_path_core(relative_path):
    """ 
    Retorna o caminho absoluto para o recurso.
    Esta versão é para ser usada DENTRO da pasta 'core'.
    Ela assume que __file__ está em 'core/' e sobe um nível para a raiz do projeto.
    """
    try:
        # PyInstaller
        base_path = sys._MEIPASS
    except Exception:
        # Dev mode: __file__ é .../core/i18n.py. Sobe um nível.
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    return os.path.join(base_path, relative_path)


class LanguageManager:
    """Carrega e gerencia os idiomas a partir dos arquivos JSON."""
    # Baseado em run.py
    def __init__(self, settings):
        self.languages = {}
        self.current_language = settings.get('language', 'pt_BR')
        self.load_languages()
        self.set_language(self.current_language)

    def load_languages(self):
        """Carrega todos os arquivos .json da pasta 'idiomas'."""
        try:
            # Usa o resource_path_core para achar 'idiomas' na raiz
            lang_path = os.path.join(resource_path_core("idiomas"), "*.json") #
            lang_files = glob.glob(lang_path)
            
            if not lang_files:
                msg = f"A pasta 'idiomas' não foi encontrada ou está vazia. (Caminho: {lang_path})"
                print(f"ERRO: {msg}")
                # A GUI será responsável por tratar este erro
                raise FileNotFoundError(msg)
                
            for file in lang_files:
                lang_code = os.path.basename(file).replace(".json", "")
                with open(file, 'r', encoding='utf-8') as f:
                    self.languages[lang_code] = json.load(f)
        except Exception as e:
            print(f"Erro ao carregar idiomas: {e}")
            # Propaga o erro para a GUI
            raise IOError(f"Erro ao carregar arquivos de idioma: {e}")

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
        #
        string = self.strings.get(key, f"_{key}_")
        try:
            return string.format(**kwargs)
        except KeyError:
            return string 

    def get_available_languages(self):
        return list(self.languages.keys())