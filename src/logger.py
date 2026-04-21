import aiofiles
import datetime


class ChatLogger:
    def __init__(self, filepath="chat_history.log"):
        self.filepath = filepath

    async def log_message(self, message):
        """Добавляет временную метку, пишет в файл и печатает в консоль."""

        timestamp = datetime.datetime.now().strftime("[%y.%m.%d %H:%M]")
        formatted = f"{timestamp} {message}"

        print(formatted)

        async with aiofiles.open(self.filepath, mode="a", encoding="utf-8") as f:
            await f.write(formatted + "\n")
