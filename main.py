import asyncio
from chat import connect_to_chat, read_messages
from logger import ChatLogger

HOST = "minechat.dvmn.org"
PORT = 5000


async def main():
    logger = ChatLogger("chat_history.log")
    await logger.log_message("Установлено соединение")

    try:
        reader, writer = await connect_to_chat(HOST, PORT)
        await read_messages(reader, logger.log_message)
    except (ConnectionError, OSError, asyncio.IncompleteReadError) as e:
        print(f"Ошибка: {e}. Попробуйте перезапустить.")
    finally:
        if "writer" in locals():
            writer.close()
            await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
