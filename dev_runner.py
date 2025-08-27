import subprocess
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os

BOT_FILE = "gemini_bot.py"
IGNORE_PATHS = ["screenshots", "bot_database.db"]  # Пути, за которыми не следим

class RestartOnChangeHandler(FileSystemEventHandler):
    def __init__(self, restart_func):
        self.restart_func = restart_func

    def on_modified(self, event):
        # Игнорируем файлы/папки из списка
        for ignore in IGNORE_PATHS:
            if ignore in event.src_path:
                return

        if event.src_path.endswith(".py"):
            print(f"[Watchdog] Изменён файл: {event.src_path}, перезапуск бота...")
            self.restart_func()

def run_bot():
    return subprocess.Popen([sys.executable, BOT_FILE])

if __name__ == "__main__":
    process = run_bot()

    def restart_bot():
        global process
        process.terminate()
        process.wait()
        time.sleep(1)
        process = run_bot()

    event_handler = RestartOnChangeHandler(restart_bot)
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()

    print("[Watchdog] Запущен. Следим за изменениями в коде...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
