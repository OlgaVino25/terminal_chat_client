import asyncio
import sys
import os
import json
import logging
import tkinter as tk
from tkinter import messagebox, ttk

import configargparse

from src.api import connect, read_until_greeting
from src.paths import REG_CONFIG_PATH, TOKEN_FILE_PATH

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("register_gui")

WINDOW_WIDTH = 400
WINDOW_HEIGHT = 250
CLOSE_AFTER_SUCCESS_MS = 2000


class RegistrationApp:
    def __init__(self, root, host, port):
        """Инициализирует окно регистрации, запоминает хост и порт сервера."""

        self.root = root
        self.host = host
        self.port = port
        self.root.title("Регистрация в чате Minecraft")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(False, False)

        self.nickname_var = tk.StringVar()

        ttk.Label(root, text="Придумайте никнейм:").pack(pady=10)
        self.nick_entry = ttk.Entry(root, textvariable=self.nickname_var, width=30)
        self.nick_entry.pack(pady=5)

        self.register_btn = ttk.Button(
            root, text="Зарегистрироваться", command=self.register
        )
        self.register_btn.pack(pady=10)

        self.status_label = ttk.Label(root, text="", foreground="gray")
        self.status_label.pack(pady=10)

        root.update_idletasks()
        x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
        y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
        root.geometry(f"+{x}+{y}")

    def register(self):
        """Обработчик нажатия кнопки. Запускает асинхронную регистрацию."""

        nickname = self.nickname_var.get().strip()
        if not nickname:
            messagebox.showerror("Ошибка", "Никнейм не может быть пустым")
            return

        asyncio.run_coroutine_threadsafe(
            self.async_register(nickname), asyncio.get_event_loop()
        )
        self.status_label.config(text="Регистрация...", foreground="blue")
        self.register_btn.config(state="disabled")

    async def async_register(self, nickname):
        """Асинхронно регистрирует пользователя на сервере и сохраняет токен."""

        reader = writer = None
        try:
            reader, writer = await connect(self.host, self.port)
            greeting = await read_until_greeting(reader)
            logger.debug(greeting)

            writer.write(b"\n")
            await writer.drain()

            line = await reader.readline()
            if not line:
                raise ConnectionError("Сервер не ответил")
            response_text = line.decode().strip()
            logger.debug(response_text)
            if "preferred nickname" not in response_text.lower():
                raise ConnectionError("Сервер не ожидает ник")

            writer.write((nickname + "\n").encode())
            await writer.drain()

            json_line = await reader.readline()
            if not json_line:
                raise ConnectionError("Сервер не вернул токен")
            data = json.loads(json_line.decode().strip())
            account_hash = data.get("account_hash")
            if not account_hash:
                raise KeyError("Токен не получен")

            os.makedirs(os.path.dirname(TOKEN_FILE_PATH), exist_ok=True)
            with open(TOKEN_FILE_PATH, "w") as f:
                f.write(account_hash)

            self.root.after(
                0, self.on_success, data.get("nickname", nickname), account_hash
            )
        except asyncio.CancelledError:
            return
        except (
            ConnectionError,
            OSError,
            asyncio.IncompleteReadError,
            json.JSONDecodeError,
            KeyError,
        ) as e:
            logger.exception("Ошибка регистрации")
            self.root.after(0, self.on_error, str(e))
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

    def on_success(self, nickname, token):
        """Вызывается при успешной регистрации. Показывает сообщение и закрывает окно."""

        self.status_label.config(text="Регистрация успешна!", foreground="green")
        messagebox.showinfo(
            "Успех",
            f"Вы зарегистрированы как {nickname}\nТокен сохранён в {TOKEN_FILE_PATH}",
        )
        self.register_btn.config(state="normal")
        self.root.after(CLOSE_AFTER_SUCCESS_MS, self.root.destroy)

    def on_error(self, error_msg):
        """Вызывается при ошибке регистрации. Показывает сообщение об ошибке."""

        self.status_label.config(text="Ошибка", foreground="red")
        messagebox.showerror("Ошибка", f"Не удалось зарегистрироваться:\n{error_msg}")
        self.register_btn.config(state="normal")


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=[REG_CONFIG_PATH],
        description="Графическая утилита регистрации в чате Minecraft",
    )
    parser.add_argument("-c", "--config", is_config_file=True, help="Путь к конфигу")
    parser.add_argument(
        "--host",
        default="minechat.dvmn.org",
        env_var="MINECHAT_HOST",
        help="Хост чат-сервера",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5050,
        env_var="MINECHAT_SEND_PORT",
        help="Порт для регистрации (обычно 5050)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    root = tk.Tk()
    app = RegistrationApp(root, args.host, args.port)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    import threading

    def run_loop():
        loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    root.mainloop()
    loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    main()
