import time
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Importar a função mágica que criámos no indexar.py
# (Como a função já sabe ignorar os ficheiros antigos via processed_files.json, é 100% segura para rodar as vezes que forem precisas)
from indexar import indexar_ficheiros

caminho_base = Path.home() / "Desktop" / "pdfs"

class PDFHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.last_trigger = 0
        self.debounce_seconds = 5  # Esperar uns segundos para não disparar 100x se colares 100 PDFs de uma vez

    def on_modified(self, event):
        self._verificar(event)

    def on_created(self, event):
        self._verificar(event)

    def _verificar(self, event):
        # Ignoramos eventos em pastas ou noutros ficheiros (ex: docx, txt)
        if event.is_directory or not event.src_path.lower().endswith('.pdf'):
            return

        agora = time.time()
        
        # O Debounce garante que se o Windows/Mac dispararem várias notificações
        # seguidas pelo mesmo ficheiro (ou cópia em lote), só processa 1 vez de X em X tempo.
        if agora - self.last_trigger > self.debounce_seconds:
            self.last_trigger = agora
            
            print(f"\n[👁️ Watcher] Alteração detetada: {os.path.basename(event.src_path)}")
            print(f"[👁️ Watcher] A aguardar {self.debounce_seconds}s para que a cópia dos ficheiros termine...")
            time.sleep(self.debounce_seconds)
            
            print("[👁️ Watcher] A disparar a indexação para o Supabase!")
            try:
                # Chama exatamente o script base
                indexar_ficheiros()
            except Exception as e:
                print(f"[👁️ Watcher] Erro na indexação: {e}")
                
            print("[👁️ Watcher] Indexação concluída. De volta a vigiar o turno da noite... 🌙\n")


def iniciar_watcher():
    if not caminho_base.exists():
         print(f"Erro: A pasta principal não foi encontrada em {caminho_base}")
         return

    observador = Observer()
    handler = PDFHandler()
    
    # recursive=True permite que ele oiça as subpastas todas dentro da principal
    observador.schedule(handler, str(caminho_base), recursive=True)
    
    print("=" * 60)
    print(f"👀 WATCHER ATIVADO | A vigiar: {caminho_base}")
    print("-> Podes agora arrastar pastas e PDFs lá para dentro.")
    print("-> Eles serão convertidos e enviados para o Supabase automaticamente.")
    print("-> Pressiona Ctrl+C para desligar o guarda.")
    print("=" * 60 + "\n")
    
    observador.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observador.stop()
        print("\n[👁️ Watcher] O vigilante foi desligado pelo utilizador.")
    
    observador.join()

if __name__ == "__main__":
    iniciar_watcher()
