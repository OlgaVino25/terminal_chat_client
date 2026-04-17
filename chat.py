import asyncio


async def connect_to_chat(host, port):
    """Возвращает reader, writer для чата."""

    reader, writer = await asyncio.open_connection(host, port)
    return reader, writer


async def read_messages(reader, message_handler):
    """Читает строки из чата и передаёт каждое сообщение в обработчик.
    message_handler – асинхронная функция (message: str) -> None.
    """

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
