import asyncio
import configargparse
import sys
import json
import logging


logging.basicConfig(level=logging.DEBUG, format="DEBUG:sender:%(message)s")
logger = logging.getLogger("sender")


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=["settings_send.ini"],
        description="Отправка сообщения в чат.",
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
        help="Порт для отправки сообщений",
        env_var="MINECHAT_SEND_PORT",
        default=5050,
    )
    parser.add_argument(
        "--token",
        help="Токен авторизации",
        env_var="MINECHAT_TOKEN",
        required=True,
    )
    parser.add_argument(
        "--message",
        help="Текст сообщения (если не указан, читается из stdin)",
        env_var="MINECHAT_MESSAGE",
        default=None,
    )

    args = parser.parse_args()
    return args.host, args.port, args.token, args.message


async def send_messages(host, port, token, initial_message):
    reader, writer = await asyncio.open_connection(host, port)

    try:
        greeting = await reader.readline()
        greeting_text = greeting.decode().strip()
        logger.debug(greeting_text)

        logger.debug(f"Отправка токена: {token}")
        writer.write((token + "\n").encode())
        await writer.drain()

        response_line = await reader.readline()

        if not response_line:
            logger.error("Сервер не ответил на токен.")
            return

        response_text = response_line.decode().strip()
        logger.debug(response_text)

        try:
            response = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка разбора JSON: {e}")
            print("Ошибка: сервер вернул не JSON. Возможно, токен неверен.")
            return

        welcome_line = await reader.readline()
        welcome_text = welcome_line.decode().strip()
        logger.debug(welcome_text)

        if initial_message:
            logger.debug(f"Отправка начального сообщения: {initial_message}")
            writer.write((initial_message + "\n\n").encode())
            await writer.drain()
            ack = await reader.readline()
            if ack:
                ack_text = ack.decode().strip()
                logger.debug(ack_text)

        print("Вводите сообщения. Для выхода введите /exit или нажмите Ctrl+C.")
        loop = asyncio.get_event_loop()

        while True:
            user_input = await loop.run_in_executor(None, sys.stdin.readline)
            if not user_input:
                break
            user_input = user_input.strip()
            if user_input == "/exit":
                break
            if not user_input:
                continue

            logger.debug(f"Отправка сообщения: {user_input}")
            writer.write((user_input + "\n\n").encode())
            await writer.drain()

            ack = await reader.readline()
            if ack:
                ack_text = ack.decode().strip()
                logger.debug(ack_text)
            else:
                logger.warning("Сервер не подтвердил отправку.")
                break

    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Завершение работы по запросу пользователя.")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.debug("Соединение закрыто.")


async def main():
    host, port, token, message = parse_args()
    await send_messages(host, port, token, message)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВыход.")
