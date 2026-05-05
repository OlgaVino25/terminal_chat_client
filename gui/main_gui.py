import asyncio
import datetime
import logging
import os
import tkinter as tk
from tkinter import messagebox
import socket

import aiofiles
import anyio
import async_timeout
import configargparse

from gui.interface import (
    ReadConnectionStateChanged,
    SendingConnectionStateChanged,
    NicknameReceived,
    draw,
)
from src.api import connect, authorise, read_until_greeting, submit_message
from src.paths import GUI_CONFIG_PATH, TOKEN_FILE_PATH, HISTORY_LOG_PATH

logging.basicConfig(level=logging.DEBUG, format="DEBUG:%(message)s")
logger = logging.getLogger(__name__)

watchdog_logger = logging.getLogger("watchdog")
watchdog_logger.setLevel(logging.DEBUG)

PING_INTERVAL = 30


class InvalidToken(Exception):
    """Неверный токен авторизации."""

    pass


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
    """Возвращает токен из аргументов командной строки,
    либо из файла TOKEN_FILE_PATH, если аргумент не задан.
    """

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


async def create_authorized_connection(host, port, token, watchdog_queue):
    """Устанавливает соединение с сервером, выполняет авторизацию по токену.
    Возвращает кортеж (reader, writer, user_data).
    При ошибке закрывает соединение и поднимает исключение.
    """
    reader, writer = await connect(host, port)
    try:
        greeting = await read_until_greeting(reader)
        watchdog_queue.put_nowait(("Connection is alive. Prompt before auth",))
        logger.debug(greeting)
        user_data = await authorise(reader, writer, token)
        if user_data is None:
            raise InvalidToken("Неверный токен")
        watchdog_queue.put_nowait(("Connection is alive. Authorization done",))
        return reader, writer, user_data
    except Exception:
        writer.close()
        await writer.wait_closed()
        raise


async def authorize_and_get_nickname(host, port, token, watchdog_queue):
    """Возвращает никнейм пользователя после успешной авторизации.
    Использует create_authorized_connection и закрывает соединение.
    """
    reader, writer, user_data = await create_authorized_connection(
        host, port, token, watchdog_queue
    )
    try:
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


async def process_sending_task(
    sending_queue, host, port, token, status_updates_queue, watchdog_queue
):
    """Читает сообщения из очереди и отправляет их на сервер.
    Обновляет статус отправки и отправляет события в watchdog_queue.
    """

    while True:
        message = await sending_queue.get()
        logger.info(f"Отправка сообщения: {message}")
        reader = writer = None
        status_updates_queue.put_nowait(SendingConnectionStateChanged.INITIATED)
        try:
            reader, writer, user_data = await create_authorized_connection(
                host, port, token, watchdog_queue
            )
            status_updates_queue.put_nowait(SendingConnectionStateChanged.ESTABLISHED)
            logger.debug(f"Авторизован как {user_data.get('nickname')}")
            success = await submit_message(reader, writer, message)
            if success:
                logger.debug("Сообщение успешно отправлено")
                watchdog_queue.put_nowait(("Connection is alive. Message sent",))
            else:
                logger.error("Сервер не подтвердил отправку")
                watchdog_queue.put_nowait(("Connection is alive. Message send failed",))
        except InvalidToken as e:
            logger.error(f"Ошибка авторизации при отправке: {e}")
            status_updates_queue.put_nowait(SendingConnectionStateChanged.CLOSED)
        except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
            logger.error(f"Сетевая ошибка при отправке: {e}")
            status_updates_queue.put_nowait(SendingConnectionStateChanged.CLOSED)
        except Exception as e:
            logger.exception(f"Неожиданная ошибка при отправке: {e}")
            status_updates_queue.put_nowait(SendingConnectionStateChanged.CLOSED)
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
                status_updates_queue.put_nowait(SendingConnectionStateChanged.CLOSED)


async def watchdog_task(watchdog_queue):
    """Слушает очередь watchdog и выводит сообщения с таймстемпом."""
    while True:
        event = await watchdog_queue.get()
        if isinstance(event, tuple):
            message = event[0]
        else:
            message = event
        timestamp = int(datetime.datetime.now().timestamp())
        watchdog_logger.info(f"[{timestamp}] {message}")


async def handle_connection(
    args, token, messages_queue, save_queue, status_updates_queue, watchdog_queue
):
    """Управляет соединением для чтения. Переподключается при обрыве или долгом простое.
    Использует anyio.create_task_group для запуска reader, idle_watchdog и ping_task.
    """

    while True:
        try:
            reader, writer = await connect(args.host, args.port_read)
            logger.debug(f"Установлено чтение: {args.host}:{args.port_read}")
            status_updates_queue.put_nowait(ReadConnectionStateChanged.ESTABLISHED)
            watchdog_queue.put_nowait(
                ("Connection is alive. Connection established for reading",)
            )

            last_message_time = datetime.datetime.now()

            async with anyio.create_task_group() as tg:

                async def reader_task():
                    nonlocal last_message_time
                    try:
                        while True:
                            try:
                                async with async_timeout.timeout(1.0):
                                    line = await reader.readline()
                                if not line:
                                    break

                                last_message_time = datetime.datetime.now()
                                raw_message = line.decode().strip()
                                timestamp = last_message_time.strftime(
                                    "[%y.%m.%d %H:%M]"
                                )
                                formatted = f"{timestamp} {raw_message}"
                                await messages_queue.put(formatted)
                                await save_queue.put(formatted)
                                watchdog_queue.put_nowait(
                                    ("Connection is alive. New message in chat",)
                                )
                            except TimeoutError:
                                watchdog_queue.put_nowait(("1s timeout is elapsed",))
                    except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
                        logger.error(f"Ошибка чтения: {e}")
                        tg.cancel_scope.cancel()
                    except asyncio.CancelledError:
                        raise
                    finally:
                        writer.close()
                        await writer.wait_closed()

                async def idle_watchdog():
                    nonlocal last_message_time
                    while True:
                        await anyio.sleep(5)
                        idle_seconds = (
                            datetime.datetime.now() - last_message_time
                        ).total_seconds()
                        if idle_seconds > 10:
                            watchdog_queue.put_nowait(
                                ("Connection lost: idle timeout",)
                            )
                            logger.warning(
                                "Слишком долго нет сообщений, переподключаемся..."
                            )
                            tg.cancel_scope.cancel()

                async def ping_task():
                    """Регулярно отправляет пустые сообщения (ping) для поддержания соединения."""

                    while True:
                        await anyio.sleep(PING_INTERVAL)

                        try:
                            writer.write(b"\n\n")
                            await writer.drain()
                            watchdog_queue.put_nowait(("Ping sent",))
                            logger.debug("Ping sent")
                        except (ConnectionError, OSError, BrokenPipeError) as e:
                            logger.error(f"Ошибка при отправке ping: {e}")
                            tg.cancel_scope.cancel()

                tg.start_soon(reader_task)
                tg.start_soon(idle_watchdog)
                tg.start_soon(ping_task)

            break

        except (
            ConnectionError,
            OSError,
            asyncio.IncompleteReadError,
            socket.gaierror,
        ) as e:
            logger.error(f"Сетевая ошибка в handle_connection: {e}")
            status_updates_queue.put_nowait(ReadConnectionStateChanged.CLOSED)
            await asyncio.sleep(3)

        except anyio.ExceptionGroup as eg:
            logger.error(f"ExceptionGroup в handle_connection: {eg}")
            status_updates_queue.put_nowait(ReadConnectionStateChanged.CLOSED)
            await asyncio.sleep(3)

        except asyncio.CancelledError:
            break

        finally:
            if "writer" in locals():
                writer.close()
                await writer.wait_closed()


async def main():
    args = parse_args()

    token = get_token(args.token)
    if not token:
        messagebox.showerror(
            "Ошибка",
            "Токен не найден.\nСначала зарегистрируйтесь:\npython -m src.register --nickname ВашНик",
        )
        return

    watchdog_queue = asyncio.Queue()

    try:
        nickname = await authorize_and_get_nickname(
            args.host, args.port_send, token, watchdog_queue
        )
        print(f"Выполнена авторизация. Пользователь {nickname}.")
    except InvalidToken as e:
        messagebox.showerror(
            "Ошибка авторизации",
            f"Неверный токен.\nПроверьте его или зарегистрируйтесь заново.\n{e}",
        )
        return

    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось подключиться к серверу: {e}")
        return

    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    save_queue = asyncio.Queue()

    history = load_history(args.history)

    for msg in history:
        await messages_queue.put(msg)

    status_updates_queue.put_nowait(NicknameReceived(nickname))

    async with anyio.create_task_group() as tg:
        tg.start_soon(draw, messages_queue, sending_queue, status_updates_queue),
        tg.start_soon(
            handle_connection,
            args,
            token,
            messages_queue,
            save_queue,
            status_updates_queue,
            watchdog_queue,
        ),
        tg.start_soon(save_messages_task, args.history, save_queue),
        tg.start_soon(
            process_sending_task,
            sending_queue,
            args.host,
            args.port_send,
            token,
            status_updates_queue,
            watchdog_queue,
        ),
        tg.start_soon(watchdog_task, watchdog_queue),


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Выход")
