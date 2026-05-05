import asyncio

from gui.main_gui import main
from gui.interface import TkAppClosed

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВыход")
    except ExceptionGroup as eg:
        if eg.subgroup(TkAppClosed) is not None:
            print("Окно чата закрыто")
        else:
            raise
    except TkAppClosed:
        print("Окно чата закрыто")
