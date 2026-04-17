import asyncio


async def main():
    reader, writer = await asyncio.open_connection("minechat.dvmn.org", 5000)
    print("Подключено к чату. Вывод переписки:")

    try:
        while True:
            data = await reader.readline()

            if not data:
                break

            message = data.decode().strip()
            print(message)

    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
