import asyncio
import configargparse
import os

from src.api import connect
from src.logger import ChatLogger
from src.paths import READ_CONFIG_PATH, HISTORY_LOG_PATH


async def read_messages(reader, message_handler):
    """Читает строки из чата и передаёт каждое сообщение в обработчик."""
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            message = line.decode().strip()
            await message_handler(message)
    except (asyncio.CancelledError, ConnectionError, OSError) as e:
        print(f"Потеря соединения: {e}")
        raise


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=[READ_CONFIG_PATH],
        description="Клиент для чата Minecraft.",
    )

    parser.add_argument(
        "-c", "--config", is_config_file=True, help="Путь к файлу конфигурации"
    )
    parser.add_argument(
        "--host",
        help="Хост чат-сервера",
        env_var="MINECHAT_HOST",
        default="minechat.dvmn.org",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Порт чат-сервера",
        env_var="MINECHAT_PORT",
        default=5000,
    )
    parser.add_argument(
        "--history",
        help="Путь к файлу истории",
        env_var="MINECHAT_HISTORY",
        default=HISTORY_LOG_PATH,
    )

    args = parser.parse_args()
    return args.host, args.port, args.history


async def main():
    host, port, history_file = parse_args()

    os.makedirs(os.path.dirname(history_file), exist_ok=True)

    logger = ChatLogger(history_file)
    await logger.log_message("Установлено соединение")

    try:
        reader, writer = await connect(host, port)
        await read_messages(reader, logger.log_message)
    except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
        print(f"Ошибка: {e}. Попробуйте перезапустить.")
    finally:
        if "writer" in locals():
            writer.close()
            await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
