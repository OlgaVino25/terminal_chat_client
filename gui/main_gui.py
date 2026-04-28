import asyncio
import configargparse
import logging
import datetime
import aiofiles
import os

from src.api import connect, authorise, read_until_greeting, submit_message
from gui.interface import (
    ReadConnectionStateChanged,
    SendingConnectionStateChanged,
    NicknameReceived,
    draw,
)
from src.paths import GUI_CONFIG_PATH, TOKEN_FILE_PATH, HISTORY_LOG_PATH


logging.basicConfig(level=logging.DEBUG, format="DEBUG:%(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=[GUI_CONFIG_PATH],
        description="Графический чат",
    )
    parser.add_argument("-c", "--config", is_config_file=True, help="Путь к конфигу")
    parser.add_argument(
        "--host",
        default="minechat.dvmn.org",
        env_var="MINECHAT_HOST",
        help="Хост чат-сервера",
    )
    parser.add_argument(
        "--port_read",
        type=int,
        default=5000,
        env_var="MINECHAT_READ_PORT",
        help="Порт для чтения сообщений",
    )
    parser.add_argument(
        "--port_send",
        type=int,
        default=5050,
        env_var="MINECHAT_SEND_PORT",
        help="Порт для отправки сообщений",
    )
    parser.add_argument(
        "--history",
        default=HISTORY_LOG_PATH,
        env_var="MINECHAT_HISTORY",
        help="Путь к файлу истории переписки",
    )
    parser.add_argument(
        "--token",
        default=None,
        env_var="MINECHAT_TOKEN",
        help="Токен пользователя (можно оставить пустым, будет прочитан из файла)",
    )

    return parser.parse_args()


def get_token(args_token):
    if args_token:
        return args_token

    try:
        with open(TOKEN_FILE_PATH, "r") as f:
            token = f.read().strip()

            if token:
                return token

    except FileNotFoundError:
        pass

    return None


async def authorize_and_get_nickname(host, port, token):
    """Подключается к серверу, отправляет токен и возвращает ник пользователя."""
    reader, writer = await connect(host, port)

    try:
        await read_until_greeting(reader)

        user_data = await authorise(reader, writer, token)

        if user_data is None:
            raise ValueError("Неверный токен")
        return user_data.get("nickname", "Unknown")
    
    finally:
        writer.close()
        await writer.wait_closed()


async def save_messages_task(filepath, save_queue):
    """Читает сообщения из очереди и дописывает их в файл."""

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    while True:
        formatted = await save_queue.get()

        async with aiofiles.open(filepath, mode="a", encoding="utf-8") as f:
            await f.write(formatted + "\n")


def load_history(filepath):
    """Загружает историю из файла и возвращает список строк (сообщений)."""

    history = []

    if not os.path.exists(filepath):
        return history

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                history.append(line)

    return history


async def read_messages_task(
    host, port, messages_queue, save_queue, status_updates_queue
):
    """Подключается к порту 5000, читает сообщения и кладёт их в обе очереди."""

    status_updates_queue.put_nowait(ReadConnectionStateChanged.INITIATED)

    while True:
        try:
            reader, writer = await connect(host, port)
            logger.debug(f"Установлено чтение: {host}:{port}")
            status_updates_queue.put_nowait(ReadConnectionStateChanged.ESTABLISHED)

            while True:
                line = await reader.readline()

                if not line:
                    break

                raw_message = line.decode().strip()
                timestamp = datetime.datetime.now().strftime("[%y.%m.%d %H:%M]")
                formatted = f"{timestamp} {raw_message}"

                await messages_queue.put(formatted)
                await save_queue.put(formatted)

            status_updates_queue.put_nowait(ReadConnectionStateChanged.CLOSED)
            logger.warning(
                "Чтение: потеряно соединение, переподключение через 3 сек..."
            )

            await asyncio.sleep(3)

        except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
            logger.error(f"Ошибка чтения: {e}")
            status_updates_queue.put_nowait(ReadConnectionStateChanged.CLOSED)
            await asyncio.sleep(3)

        finally:
            if "writer" in locals():
                writer.close()
                await writer.wait_closed()


async def process_sending_task(sending_queue, host, port, token):
    """Читает сообщения из очереди и отправляет их на сервер."""
    while True:
        message = await sending_queue.get()
        logger.info(f"Отправка сообщения: {message}")
        reader = writer =None

        try:
            reader, writer = await connect(host, port)
            await read_until_greeting(reader)

            user_data = await authorise(reader, writer, token)
            if user_data is None:
                logger.error("Не удалось авторизоваться для отправки")
                continue
            success = await submit_message(reader, writer, message)
            if success:
                logger.debug("Сообщение успешно отправлено")
            else:
                logger.error("Сервер не подтвердил отправку")
        except Exception as e:
            logger.exception(f"Ошибка при отправке: {e}")
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()


async def main():
    args = parse_args()

    token = get_token(args.token)
    if not token:
        print(
            "Токен не найден. Сначала зарегистрируйтесь командой: python -m src.register --nickname ВашНик"
        )
        return

    try:
        nickname = await authorize_and_get_nickname(args.host, args.port_send, token)
        print(f"Выполнена авторизация. Пользователь {nickname}.")
    except Exception as e:
        print(f"Ошибка авторизации: {e}. Проверьте токен.")
        return

    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    save_queue = asyncio.Queue()

    history = load_history(args.history)

    for msg in history:
        await messages_queue.put(msg)

    status_updates_queue.put_nowait(NicknameReceived(nickname))

    await asyncio.gather(
        draw(messages_queue, sending_queue, status_updates_queue),
        read_messages_task(
            args.host, args.port_read, messages_queue, save_queue, status_updates_queue
        ),
        save_messages_task(args.history, save_queue),
        process_sending_task(sending_queue, args.host, args.port_send, token),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Выход")
