import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")

READ_CONFIG_PATH = os.path.join(CONFIG_DIR, "read.ini")
SEND_CONFIG_PATH = os.path.join(CONFIG_DIR, "send.ini")
REG_CONFIG_PATH = os.path.join(CONFIG_DIR, "reg.ini")

HISTORY_LOG_PATH = os.path.join(DATA_DIR, "chat_history.log")
TOKEN_FILE_PATH = os.path.join(DATA_DIR, "token.txt")
