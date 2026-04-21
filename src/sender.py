import asyncio
import configargparse
import sys
import logging

from src.api import connect, read_until_greeting, authorise, submit_message
from src.paths import SEND_CONFIG_PATH

logging.basicConfig(level=logging.DEBUG, format="DEBUG:sender:%(message)s")
logger = logging.getLogger("sender")


def parse_args():
    parser = configargparse.ArgParser(
        default_config_files=[SEND_CONFIG_PATH],
        description="Отправка сообщения в чат.",
    )
    parser.add_argument("-c", "--config", is_config_file=True)
    parser.add_argument("--host", default="minechat.dvmn.org", env_var="MINECHAT_HOST")
    parser.add_argument("--port", type=int, default=5050, env_var="MINECHAT_SEND_PORT")
    parser.add_argument("--token", required=True, env_var="MINECHAT_TOKEN")
    parser.add_argument("--message", default=None, env_var="MINECHAT_MESSAGE")
    return parser.parse_args()


async def main_loop(host, port, token, initial_message):
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

        if initial_message:
            await submit_message(reader, writer, initial_message)

        print("Вводите сообщения. Для выхода введите /exit или Ctrl+C.")
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

            if await submit_message(reader, writer, user_input):
                print("Сообщение отправлено.")
            else:
                break
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Завершение работы.")
    except Exception as e:
        logger.exception(f"Ошибка: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.debug("Соединение закрыто.")


async def main():
    args = parse_args()
    await main_loop(args.host, args.port, args.token, args.message)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВыход.")
