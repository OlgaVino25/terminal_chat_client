import asyncio
import json
import logging
import re


logger = logging.getLogger(__name__)


def sanitize_text(text):
    """Заменяет управляющие символы (\\n, \\r) на пробелы, чтобы не ломать протокол."""
    return re.sub(r"[\n\r]+", " ", text)


async def connect(host, port):
    """Устанавливает соединение с сервером и возвращает reader, writer."""
    return await asyncio.open_connection(host, port)


async def read_until_greeting(reader):
    """Читает первую строку (приветствие) и возвращает её."""
    line = await reader.readline()
    return line.decode().strip() if line else ""


async def authorise(reader, writer, token):
    """Отправляет токен, читает ответ.
    Возвращает словарь с данными пользователя (nickname, account_hash)
    или None, если токен невалиден.
    """
    clean_token = sanitize_text(token)
    writer.write((clean_token + "\n").encode())
    await writer.drain()

    response_line = await reader.readline()
    if not response_line:
        logger.error("Сервер не ответил на токен.")
        return None

    response_text = response_line.decode().strip()
    logger.debug(response_text)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка разбора JSON: {e}")
        return None

    if data is None:
        logger.error("Невалидный токен: сервер вернул null")
        return None

    return data


async def submit_message(reader, writer, message):
    """Отправляет одно сообщение (с завершающей пустой строкой).
    Возвращает True, если сервер подтвердил отправку, иначе False.
    """
    clean_message = sanitize_text(message)
    writer.write((clean_message + "\n\n").encode())
    await writer.drain()

    ack = await reader.readline()
    if ack:
        ack_text = ack.decode().strip()
        logger.debug(ack_text)
        return True
    else:
        logger.warning("Сервер не подтвердил отправку.")
        return False
