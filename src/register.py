import asyncio
import configargparse
import json
import logging
import sys
import os

from src.api import connect, sanitize_text
from src.paths import REG_CONFIG_PATH, TOKEN_FILE_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("register")


def parse_args():
    parser = configargparse.ArgParser(default_config_files=[REG_CONFIG_PATH])
    parser.add_argument(
        "-c", "--config", is_config_file=True, help="Путь к файлу конфигурации"
    )
    parser.add_argument("--host", help="Хост чат-сервера", default="minechat.dvmn.org")
    parser.add_argument("--port", type=int, help="Порт для регистрации", default=5050)
    parser.add_argument(
        "--output", help="Файл для сохранения токена", default=TOKEN_FILE_PATH
    )
    parser.add_argument(
        "--nickname", help="Никнейм (если не указан, будет запрошен)", default=None
    )
    args = parser.parse_args()
    return args.host, args.port, args.output, args.nickname


async def register(host, port, output_file, nickname):
    reader, writer = await connect(host, port)
    try:
        greeting = await reader.readline()
        logger.info(greeting.decode().strip())

        writer.write(b"\n")
        await writer.drain()

        line = await reader.readline()
        if not line:
            logger.error("Сервер не ответил")
            return
        response_text = line.decode().strip()
        logger.debug(response_text)

        if "preferred nickname" in response_text.lower():
            if not nickname:
                print("Введите ваш никнейм (можно придумать любой):")
                nickname = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                nickname = nickname.strip()
                if not nickname:
                    nickname = "Anonymous_" + str(hash(str(host)))
                    print(f"Используем автоматический ник: {nickname}")

            nickname = sanitize_text(nickname)
            writer.write((nickname + "\n").encode())
            await writer.drain()

            json_line = await reader.readline()
            if not json_line:
                logger.error("Сервер не вернул JSON")
                return
            response_text = json_line.decode().strip()
            logger.debug(response_text)

        try:
            user_info = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка разбора JSON: {e}")
            return

        if user_info is None:
            logger.error("Сервер вернул null, что-то пошло не так")
            return

        nickname = user_info.get("nickname", nickname)
        account_hash = user_info.get("account_hash")
        if not account_hash:
            logger.error("Токен не получен")
            return

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w") as f:
            f.write(account_hash)

        print(f"Регистрация успешна!")
        print(f"Ваш ник: {nickname}")
        print(f"Ваш токен: {account_hash}")
        print(f"Токен сохранён в файл: {output_file}")

    except Exception as e:
        logger.exception(f"Ошибка: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info("Соединение закрыто")


async def main():
    host, port, output, nickname = parse_args()
    await register(host, port, output, nickname)


if __name__ == "__main__":
    asyncio.run(main())
