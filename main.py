import asyncio
import configargparse

from chat import connect_to_chat, read_messages
from logger import ChatLogger


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=["settings_read.ini"],
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
        default="chat_history.log",
    )

    args = parser.parse_args()
    return args.host, args.port, args.history


async def main():
    host, port, history_file = parse_args()

    logger = ChatLogger(history_file)
    await logger.log_message("Установлено соединение")

    try:
        reader, writer = await connect_to_chat(host, port)
        await read_messages(reader, logger.log_message)
    except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
        print(f"Ошибка: {e}. Попробуйте перезапустить.")
    finally:
        if "writer" in locals():
            writer.close()
            await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
