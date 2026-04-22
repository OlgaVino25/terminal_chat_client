"""Отправка одного сообщения в чат.
Примеры:
  # Отправить сообщение с указанием токена
  python -m src.sender "Hello, world!" --token 11111c11-1c1d-11f1-a1a1-1111ac111111 (ваш токен)

  # Использовать переменные окружения
  export MINECHAT_TOKEN=11111c11-1c1d-11f1-a1a1-1111ac111111
  export MINECHAT_HOST=minechat.dvmn.org
  export MINECHAT_SEND_PORT=5050
  python -m src.sender "Привет из консоли"

  # Использовать файл конфигурации config/send.ini
  python -m src.sender "Сообщение"
"""

import asyncio
import configargparse
import sys
import logging

from src.api import (
    connect,
    read_until_greeting,
    authorise,
    submit_message,
    sanitize_text,
)
from src.paths import SEND_CONFIG_PATH

logging.basicConfig(level=logging.DEBUG, format="DEBUG:sender:%(message)s")
logger = logging.getLogger("sender")


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=[SEND_CONFIG_PATH],
        description="Отправка сообщения в чат.",
        epilog="Токен можно указать в переменной окружения MINECHAT_TOKEN или в файле config/send.ini",
    )
    parser.add_argument(
        "-c", "--config", is_config_file=True, help="Путь к файлу конфигурации"
    )
    parser.add_argument(
        "--host",
        default="minechat.dvmn.org",
        env_var="MINECHAT_HOST",
        help="Хост чат-сервера (по умолчанию: minechat.dvmn.org)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5050,
        env_var="MINECHAT_SEND_PORT",
        help="Порт для отправки сообщений (по умолчанию: 5050)",
    )
    parser.add_argument(
        "--token",
        required=True,
        env_var="MINECHAT_TOKEN",
        help="Токен авторизации (обязателен, если не указан в конфиге)",
    )
    parser.add_argument(
        "--username",
        default=None,
        env_var="MINECHAT_USERNAME",
        help="Имя пользователя (опционально, не используется сервером, но может быть полезно для логов)",
    )
    parser.add_argument("message", help="Текст сообщения (обязательный аргумент)")
    return parser.parse_args()


async def send_one_message(host, port, token, message):
    """Подключается, авторизуется и отправляет одно сообщение."""
    reader, writer = await connect(host, port)
    try:
        greeting = await read_until_greeting(reader)
        logger.debug(greeting)

        user_data = await authorise(reader, writer, token)
        if user_data is None:
            print("Неизвестный токен. Проверьте его или зарегистрируйте заново.")
            return

        welcome = await reader.readline()
        welcome_text = welcome.decode().strip()
        logger.debug(welcome_text)

        success = await submit_message(reader, writer, message)
        if success:
            print("Сообщение отправлено.")
        else:
            print("Ошибка при отправке сообщения.")
        return success
    except Exception as e:
        logger.exception(f"Ошибка: {e}")
        return False
    finally:
        writer.close()
        await writer.wait_closed()
        logger.debug("Соединение закрыто.")


async def main():
    args = parse_args()

    if args.username:
        logger.info(f"Отправка от имени пользователя: {args.username}")
    await send_one_message(args.host, args.port, args.token, args.message)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВыход.")
