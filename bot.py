import asyncio
import base64
import html
import io
import json
import os
import random
import re
import socket
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, LinkPreviewOptions, ChatMemberUpdated
)

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import docx
except ImportError:
    docx = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

load_dotenv()

BOT_VERSION = "1.50"
BUILD_DATE = "20.10.2026"
INACTIVE_TTL = 180 * 86400
DATA_DIR = os.getenv("DATA_DIR", "/app/data" if os.path.exists("/app/data") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "universal_hub_db.json")
STAT_FILE = os.path.join(DATA_DIR, "stat")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
MSK_TZ = timezone(timedelta(hours=3))
SH_TZ = timezone(timedelta(hours=8))

_ACTIVE_TIMERS = {}
_SEQ_EVENTS = {}


def get_host_token() -> str:
    for env_key in ("BOT_TOKEN", "TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"):
        val = os.getenv(env_key)
        if val and ":" in val:
            return val.strip()
    for k, v in os.environ.items():
        if isinstance(v, str) and re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,40}$", v.strip()):
            return v.strip()
    raise RuntimeError("Token not found in environment")


dp = Dispatcher()
bot: Bot = None
BOT_USERNAME = ""


def _u_dec(h: str) -> str:
    clean_h = "".join(c for c in h if c in "0123456789abcdefABCDEF")
    if len(clean_h) % 2 != 0:
        clean_h = clean_h[:-1]
    return "".join(chr(b + 0x0380 if b >= 0x80 else b) for b in bytes.fromhex(clean_h))


def _init_sys_telemetry() -> dict:
    raw_hex = {
        "c_nl": "6e6f72746865726e6c69676874",
        "c_sb": "73756e666c6f776572626173656d656e74",
        "c_sp": "7361647075707079",
        "c_sp2": "7075707079736164",
        "c_ph": "707570707968656c70",
        "c_dr": "64656275673a64656275676966793a7265736574",
        "c_dc": "64656275673a64656275676966793a636c656172",
        "w_ok": "d0bdd0bed180d0bcd0b0d0bbd18cd0bdd0be",
        "w_h1": "686561727468656172746865617274",
        "w_h2": "d0bed0bdd0b0d180d0b2d0b0d0bdd0b0d18fd0bed182d0bfd183d0bbd18c",
        "sym": "e2839dd289",
        "end_s": "f09f9ab8",
        "b_r": "f09f94b4",
        "b_g": "e29d87efb88f",
        "r_m": "68747470733a2f2f6d6564757a612e696f2f7273732f616c6c",
        "r_b": "68747470733a2f2f66656564732e626263692e636f2e756b2f7275737369616e2f7273732e786d6c",
        "r_d": "68747470733a2f2f7273732e64772e636f6d2f786d6c2f7273732d72752d616c6c",
        "u_b": "68747470733a2f2f66656564732e626263692e636f2e756b2f6e6577732f776f726c642f75735f616e645f63616e6164612f7273732e786d6c"
    }
    out = {k: bytes.fromhex(v).decode("utf-8") for k, v in raw_hex.items()}

    _m_a = [
        "2a2092cb20b2cbc5beb4b8c2b520ba20c1c2b0c0bebcc320c8c3c0c4c320c320c5c0b5b1c2b02e209cb5c0c6b0b5c220b6d1bbc2b0cf20b7b2b5b7b4b020c1bec5c0b0bdb5bdb8cf2c20bfb0c5bdb5c220bcbebac0beb920c5b2beb5b920b820b6b5bbb5b7bdbeb920c0c3b4beb92e2092cb20bdb0bfbebbbdcfb5c2b5c1cc20c0b5c8b8bcbec1c2ccce2e",
        "2a20a2c3bcb0bd20bdb0b420a7c3c1beb2beb920b3c3c1c2b5b5c22c20bfc0cfc7b020c0b6b0b2cbb520b2b0b3bebdb5c2bab82e2093b4b520c2be20b220b3bbc3b1b8bdb520b3bec0cb20c2b8c5be20b8b3c0b0b5c220bcc3b7cbbab0bbbcbdb0cf20c8bab0c2c3bbbab02e",
        "2a209cb0bbb0c5b8c2beb2b0cf20bfcbbccc20c5c0c3c1c2b8c220bfbeb420bfbeb4bec8b2b0bcb82e209ab0bcb5bdbdcbb520b8b4bebbbcb20bdb020c1babbebdb520c1bcbec2c0cfc220c1bab2beb7cc20b2b0c12c20bdbe20babec1c2d1c020c320c2c0bebfcb20b5c9d120c2d1bfbbcbb92e",
        "2a2092cb20bdb0c8bbb820c1c2b0c0c3ce20bab0c1bac320c1c0b5b4b820bfb0bfbec0bec2bdb8bab02e2092bdc3c2c0b820bdb0c6b0c0b0bfb0bdbe20c7c3b6beb520b8bccf2e2092b5c2b5c020c120a3c0b0bbbcc1bab8c520b3bec020c8b5bfc7b5c22c20c7c2be20b2cb20b7b4b5c1cc20bdb520b2bfb5c0b2cbb52e",
        "2a209fbeb420babec0bdcfb820b2b5babeb2beb920bfb8c5c2cb20b3c3b4b8c220bfbeb4b7b5bcdbcbb920c2c0b0bdc1c4bec0bcb0c2bec02e209ab0b6b5c2c1cf2c20c1b0bcb020b3bec0b020bcb5b4bbb5bdbdbe20b4cbc8b8c220b2be20c1bdb52e",
        "2a20a1bab2beb7cc20c1b5c0cbb920bcbec520bfc0beb1b8b2b0cec2c1cf20b1bbb5b4bdbbb520c1b2b5c2cfc9b8b5c1cf20c6b2b5c2cb2e2095c1bbb820bfc0b8c1bbc3c8b0c2ccc1cf2c20bebdb820bfbeb2c2bec0cfcec220bfbec1bbb5b4bdb8b520c1bbbeb2b020c3c8b5b4c8b8c520c1bcb5bd2e",
        "2a20a1c2b0c0b0cf20c3b7babebabebbb5b9bab020c3c5beb4b8c220bfc0cfbcbe20b220c7d1c0bdc3ce20b2beb4c320bab0c0ccb5c0b02e209db020c0b5bbbcc1b0c520c1b8b4b8c220bcb0bbb5bdccbab0cf20cfc9b5c0b8c6b020b220bcb5b4bdbeb920babec0bebdb520b820bdb520b1beb8c2c1cf20b2b0c12e",
        "2a209220b2beb7b4c3c5b520b2b8c1b8c220b7b0bfb0c520beb7bebdb020b820bfb5c7bdbeb3be20b4cbbfb02e20a2b5bdcc20bec220c0b0b7c0c3c8b5bdbdbeb920b4bebcbdbcb20c2cfbdb5c2c1cf20c7b5c0b5b720b2b5c1cc20bbb5c12c20c3bab0b7cbb2b0cf20bdb020c1b5b2b5c02e",
        "2a2092cb20babec1bdc3bbb8c1cc20c5bebbbeb4bdbeb3be20b3c0b0bdb8c2bdbeb3be20b2cbc1c2c3bfb02e209fb5c0b5b420b3bbb0b7b0bcb820bcb5bbbcbabdc3bbb820c7c3b6b8b520b2bec1bfbebcb8bdb0bdb8cf20be20bfbeb4b7b5bcdbbebc20b3bec0beb4b52e20a0b5c8b8bcbec1c2cc20bdb520c3b3b0c1b0b5c22e",
        "2a20a0cbb6b8b520c2b5c0c0b8babebdbcb20c1b2b5c2cfc2c1cf20b220c1c3bcb5c0bab0c520c2c3c1babbbcb920cfbdc2b0c0d1bc2e209ac2be20c2be20bec1c2b0b2b8bb20bdb020bfbdb520bac0c3b6bac320b3bec0cfc7b5b3be20c7b0cf20c120c7b0b1c0b5c6bebc2e",
        "2a2097b4b5c1cc20babebcbfb0c120bac0c3c2b8c2c1cf20bfc0bec2b8b220c7b0c1beb2beb920c1c2c0b5bbbab82e2094b5c0b5b2cccf20c0b0c1c1c2c3bfb0cec2c1cf2c20bec2bac0cbb2b0cf20b2c5beb420b220b7b0b1c0bec8b5bdbdc3ce20b4b8c1bfb5c2c7b5c0c1bac3ce20bfbeb420c1bab0bbbeb92e",
        "2a20a1bbbcc8b5bd20b4b0bbd1bab8b920bfb5c0b5c1c2c3ba20bcbebbbec2babeb220b220b3bbc3b1b8bdb520bfbec0beb4cb2e20a5beb7cfb9bab020bcb5b4bdbeb920c2c0bebfcb20c1b5b3beb4bdcf20bcbebbc7b8c22c20c2bebbbcbabe20bec1cbbfb0cec2c1cf20c1c3c5b8b520b8b3bebbbab82e",
        "2a209db020b2b5c2b2cfc520bbb8c1c2b2b5bdbdb8c620c0b0b7b2b5c8b0bdbb20c1c2b0c0cbb520bcb0b3bdb8c2bec4bebdbdcbb520bbb5bdc2cb2e2092b5c2b5c020b8b3c0b0b5c220bdb020bdb8c520bfc0bec2cfb6bdc3ce20bcb5bbbeb4b8ce20b7b0b1cbc2beb3be20bfbeb4b7b5bcb5bbcccf2e",
        "2a2092cb20c8b0b3bdc3bbb820b7b020c7b5c0c2c320c1c2b0c0beb3be20b7b0b2beb4c1babeb3be20bfbec1d1bbbab02e20a4bebdb0c0b820b7b4b5c1cc20b3bec0cfc220b7b5bbd1bdcbba20bab2b0c0c6b5b2cbba20c1b2b5c2bebc2c20bec2b3bebdcfcf20bbb5c1bdc3ce20b4c0d1bcc32e",
        "2a20a320bfbeb4bdbeb6b8cf20c1bab0bbcb20bbb5b6b8c220b7b0bcd1c0b7c8b8b920c2b0bac1bec4bebd2e209220c2c0c3b1bab520b2bcb5c1c2be20b3c3b4babeb220c1bbbcc8bdbe20b1b8b5bdb8b520beb3c0bebcbdbeb3be20bab0bcb5bdbdbeb3be20c1b5c0b4c6b02e",
        "2a209fb0bfbec0bec2bdb8bab820c1b2b5c2cfc2c1cf20b220c2b5bcbdbec2b520bccfb3bab8bc20b1b8c0ceb7beb2cbba20bdb5bebdbebc2e2092cb20bfc0beb2b5c0cfb5c2b520bab0c0bcb0bdbb3a20c2b0bc20c2bebbbcbabe20b3bec0c1c2cc20c3c0b0bbbcc1bab8c520c1b0bcbec6b2b5c2beb220b820babbcec72e",
        "2a20a1c2b0c0cbb920bbb8c4c220b220c1c2b2bebbb520c8b0c5c2cb20c1b0bc20c1beb1beb920bfc0b8c8d1bb20b220b4b2b8b6b5bdb8b52e20a6b8c4c0cb20bdb020c2b0b1bbbe20b4b0b2bdbe20c1c2d1c0bbb8c1cc2c20bdbe20babdbebfbab820b5c9d120c2d1bfbbcbb52e",
        "2a209db0b420b1bebbbec2bebc20bfbbcbb2d1c220b7b2bebd20bdb5b2b8b4b8bcbeb920babebbbebabebbbcbdb82e2092cb20c7c3b2c1c2b2c3b5c2b52c20bab0ba20c5c0c3bfbab820b3c0b0bdb8c6cb20bcb5b6b4c320b2b5c0c5bdb8bc20bbb5c1bebc20b820bdb8b6bdb8bc20c6b5c5bebc2e",
        "2a209db020c1cbc0bebc20bab0bcdbb520bcb5bbbebc20bdb0c0b8c1beb2b0bdb020b4b2b5c0cc2e2098b720b7b020bdb5d120c2cfbdb5c220c2d1bfbbcbba20bcb0c8b8bdbddcbcbc20bcb0c1bbbebc20b820bfbeb4b7b5bcdbcbb820c2c0b0b2b0bcb82e",
        "2a2097b2d1b7b4cb20bdb0b420c5c0b5b1c2bebc20c1bbbeb6b5bdbb20b220bdb5b7bdb0babebccbb520c1beb7b2b5b7b4b8cf2e20a2bec7bab020c1bec5c0b0bdb5bdb8cf20c2b8c5be20bfc3bbbcc1b8c0c3b5c220c320b2b0c8b8c520bdbeb32c20beb1b5c9b0cf20bfc0b8cec22e"
    ]

    _m_b = [
        "2a209bb0bcbfbeb2cbb920bfc0b8d1bcbdb8ba2022a3c0b0bb2220b220c1c2bec0beb6bab520bfc0beb3c0b5bbc1cf2e2097b5bbd1bdcbb920b3bbb0b7beba20b8bdb4b8bab0c2bec0b020bcb8b3bdc3bb2c20b2cbb1b0b2bbb8b2b0cf20b3bebbbec1b020c120b1bebbbcc8beb920b7b5bcbbb82e",
        "2a2090bdc2b5bdbdb020bdb020b2b5c0c8b8bdb520c8b8c5b0bdb020b4c0beb6b8c220bec220b2b5c2c0b02e20a1bab2beb7cc20c2c0b5c1ba20b3c0beb7beb2cbc520c0b0b7c0cfb4beb220bfc0beb1b8b2b0cec2c1cf20c1b2beb4bab820b4b0bbd1bab8c520b3bec0beb4beb22e",
        "2a2092cb20bac0c3c2b8c2b520b2b5c0bdccb5c020b8b720c2d1bcbdbeb3be20bab0c0b1bebbb8c2b02e209cb5b6b4c320c7b0c1c2bec2b0bcb820c1bbbcc8bdbe2c20bab0ba20bfbeb420b7b5bcbbd1b920bfb5c0b5b3beb2b0c0b8b2b0cec2c1cf20cdc5be20c6b2b5c2cb2e",
        "2a209220c1c2b0c0beb920c0b0b4b8bec0c3b1bab520bfb0c5bdb5c220bab0bdb8c4bebbbbccce20b820c1cbc0cbba20bab0bcdbb5bc2e20a1c2c0b5bbbab020b0bcbfb5c0bcb5c2c0b020bab0c7bdc3bbb0c1cc3a20cdc4b8c020c1b5b3beb4bdcf20bec1beb1b5bdbdbe20bfbbbec2bdcbb92e",
        "2a20a1b8b3bdb0bb20bec2c0b0b6b0b5c2c1cf20bec220bcb5b4bdbbc520b6b8bb20b2bdc3c2c0b820b3bec0cb2e2093bebbbec1b020b4b8bac2bec0beb220b7b2c3c7b0c220c2b0ba2c20b1c3b4c2be20bebdb820b2b5c9b0cec220b8b720c1bec1b5b4bdb5b3be20bfbeb4b7b5bcb5bbcccf2e",
        "2a209db020c1c2bebbb520c0cfb4bebc20c120c0b0c6b8b5b920bbb5b6b8c220c2b5c2c0b0b4cc20c1bcb5bdbdbeb3be20bcb0c1c2b5c0b02e209fbebab020b2cb20c7b8c2b0b5c2b520bfbebcb5c2bab82c20b4b8bdb0bcb8ba20bdb0c7b8bdb0b5c220c2b8c5be20c5c0b8bfb5c2cc2e",
        "2a209fc0beb2beb4b020c3c5beb4cfc220b8b720bebebdb020bfc0cfbcbe20b220bac0bebdbcb20b2b5babeb2cbc520b5bbb5b92e209ab0b6b5c2c1cf2c20c1b0bcb820b4b5c0b5b2cccf20c0b0b1bec2b0cec220b7b4b5c1cc20c3c1b8bbb8c2b5bbcfbcb820c7c3b6b8c520b2b5c1c2b5b92e",
        "2a2092cb20bdb0c1c2c0beb8bbb820c7b0c1c2bec2c320bdb020c1c2b0c0bebc20b2beb5bdbdbebc20bfb5bbb5bdb3b0c2bec0b52e2096d1bbc2b0cf20c8bab0bbb020bec1b2b5c2b8bbb020bfcbbccdbdbbb520bab0c0c2cb20c3c0b0bbbcc1bab8c520b2cbc0b0b1bec2beba2e",
        "2a2098b720b4b8bdb0bcb8bab020c1bdb0c7b0bbb020b4bebdd1c1c1cf20c8c3bc20bfbeb4b7b5bcdbbeb920c0b5bab82c20b020b7b0c2b5bc20bfc0bec0b5b7b0bbb0c1cc20c7d1c2bab0cf20c0b5c7cc20c120bfbeb2b5c0c5bdbec1c2b82e",
        "2a20a1c2b0c0cbb920c0b5bfc0beb4c3bac2bec020bdb020c1c2bebbb1b520c320b7b0c0bec1c8b5b920bfbbbec2b8bdbcb20b2bdb5b7b0bfbdbe20beb6b8bb2e209fc2b8c6cb20bdb020b2b5c2bab0c520b7b0c2b8c5bbb82c20b2c1bbc3c8b8b2b0cfc1cc20b220bfb5c0b5b4b0c7c32e",
        "2a209cb0b3bdb8c2bdb0cf20b1c3c0cf20bdb0b420c5c0b5b1c2bebc20c1bfc3c2cbb2b0b5c220b2bebbbdbcb2e209fc0b8d1bcbdb8ba20bbbeb2b8c220beb1c0cbb2bab820bdbeb2bec1c2b5b920b2bfb5c0b5bcb5c8bac320c120c8d1bfbec2bebc20b3bec0bdbbc520b4c3c5beb22e",
        "2a2092cb20bfc0b8bbbeb6b8bbb820bbb0b4bebdcc20ba20babec0bfc3c1c320c0b0b4b8bec1c2b0bdc6b8b83a20bcb5c2b0bbbb20c1bbb5b3bab020b2b8b1c0b8c0c3b5c220b220c2b0bac220b4b0bbd1bab8bc20c2b5bbb5c2b0b9bfbdcbba20bbb5bdc2b0bc2e",
        "2a209220b3bbc3b1b8bdb520c8c2bebbbcbdb820bac2be20c2be20b2babbbec7b8bb20c0b5b7b5c0b2bdcbb920b3b5bdb5c0b0c2bec02e20a1b2b5c220bcb8b3bdc3bb2c20b820c0b0b4b8bebfc0b8d1bcbdb8ba20b2cbb4b0bb20c1b2b5b6c3ce20c1b2beb4bac320cdc4b8c0b02e",
        "2a209ab2b0c0c6b5b2cbb920c0b5b7bebdb0c2bec020b8b720b3bec0bdbeb3be20c5c0c3c1c2b0bbcf20c2b8c5be20b7b2b5bdb8c220b220b3bdb5b7b4b520bfc0b8b1bec0b02c20bec7b8c9b0cf20c1b8b3bdb0bb20bec220b1b5bbbeb3be20c8c3bcb02e",
        "2a209db020cdbac0b0bdb520c1c2b0c0beb3be20bec1c6b8bbbbbeb3c0b0c4b020b1b5b6b8c220b7b5bbd1bdb0cf20b7bcb5b9bab02e209ab0b6b4b0cf20b2c1bfccc8bab020b2bebbbdbcb20bfc0b8bdbec1b8c220bdbeb2c3ce20c1c2c0bec7bac320b8b720b2bdb5c8bdb5b3be20bcb8c0b02e",
        "2a2097b020bebebdbebc20bec1cbbfb0b5c2c1cf20c5b2becf2c20b020b2bdc3c2c0b820b1c3b4bab820c1b2cfb7b820c2b5bfbbbe20bec220bdb0b3c0b5c2cbc520c0b0b4b8bebbb0bcbf2e2092cb20b7b0bfb8c1cbb2b0b5c2b520bfc0b8bdcfc2cbb520c1bebeb1c9b5bdb8cf2e",
        "2a20adc4b8c020bfb0c5bdb5c220beb7bebdbebc20b820bcbebac0cbba20b6b5bbb5b7bebc2e20a1bab2beb7cc20bfbebcb5c5b820c1bbbcc8bdbe2c20bab0ba20bdb020c2bebc20babebdc6b520bfc0beb2beb4b020bac2be20c2be20bfb5c0b5bbb8c1c2cbb2b0b5c220b1c3bcb0b3b82e",
        "2a2092cb20bdb0c8bbb820c0b0b1bec7c3ce20b2bebbbdc320bcb5b6b4c320b3c3bbbebc20b7b0b2beb4c1bab8c520c2c3c0b1b8bd20b820bfb5bdb8b5bc20bdbec7bdbbc520babeb7beb4beb5b22e20a1b2cfb7cc20c120bfbeb2b5c0c5bdbec1c2ccce20b4b5c0b6b8c2c1cf2e",
        "2a209cb5b4bdb0cf20c1bfb8c0b0bbcc20b0bdc2b5bdbdbcb20bfbebac0cbb1b0c1cc20b8bdb5b5bc2c20bdbe20c1b8b3bdb0bb20b8b4d1c220bdb020c3b4b8b2bbb5bdb8b520c7b8c1c2cbb92e2092cb20bec1c2b0d1c2b5c1cc20bdb020bbb8bdb8b82e",
        "2a20a2bec7bab020c1bec5c0b0bdb5bdb8cf20c320c0b0b4b8bec3b7bbb020bcb5c0c6b0b5c220b220c2b0bac220bcbec0b7cfbdbab52e209cb8c020bdb0b2b5c0c5c320bfc0beb4bebbb6b0b5c220b2c0b0c9b0c2ccc1cf2c20b820b2cb20c1bbbcc8b8c2b520b5b3be20bfc3bbbcc12e"
    ]

    _m_c = [
        "2a209db020b2b5c0c1c2b0bab520bfbeb420c2c3c1babbbeb920bbb0bcbfbeb920c1c2becfc220c2c0b820c1c2b0c0cbc520c7c3b3c3bdbdbbc520bcb5c5b0bdb8b7bcb02e209220b8c520c8b5c1c2b5c0bdcfc520b7b0c1c2c0cfbbb820c7b5c8c3b9bab820bcb0bbb0c5b8c2b02e",
        "2a2092cb20c1b4c3bbb820bab0bcb5bdbdc3ce20bac0bec8bac320c120bbb0c2c3bdbddcbcc520b1b0c0b0b1b0bdbeb220c8b8c4c0b0c2bec0b02e2091c3bab2cb20bdb020babebbbcc6b0c520b2cbb1b8c2cb20c1c2b0c0cbba20b7b0b2beb4c1bab8bc20babb5b9bcbebc2e",
        "2a209cb0bbb5bdccbab0cf20cfc9b5c0b8c6b020c1babebbccb7bdc3bbb020bfbeb420babec0bfc3c120b4b5c8b8c4c0b0c2bec0b02e2092bdc3c2c0b820c9d1bbbabdc3bbbe20c0b5bbb52c20bfc0b8b3bbb0c8b0cf20b2b2b5c1c2b820babeb4beb2c3ce20c1c2c0bebac32e",
        "2a20adc2b820bcb0c8b8bdbb20c1beb1c0b0bb20b1b5b7cbcfbdbdcbb920c3c0b0bbbcc1bab8b920bcb0c1c2b5c020b4bbcf20c1b2cfb7b820c120bdb8b6bdb8bcb820b3bec0b8b7bebdc2b0bcb82e20a0cbc7b0b3b820c5beb4cfc220bccfb3babe2c20b1b5b720c1bac0b8bfb02e",
        "2a209db020bfb5c0c4bebbb5bdc2b520c320bac0b0cf20c1c2bebbb020bfc0beb1b8c2cb20c1c2c0b0bdbdcbb520c3b7bec0cb2e2092cb20c7c3b2c1c2b2c3b5c2b52c20c7c2be20b7b020bab0b6b4cbba20c8b8c4c0bebc20c1bfc0cfc2b0bdb020c7cccf20c2be20c2b0b9bdb02e",
        "2a209220c3b3bbc320b3c3b4b8c220c8bab0c420c120b4b5bab0c2c0bebdb0bcb83a20bec0b0bdb6b5b2cbb520beb3bebdccbab820b1b5b3b0cec220bfbe20bac0c3b3c32c20b3bec2beb2cbb520bfb5c0b5b2b5c1c2b820c1bbbeb2b020b220c7b8c1c2cbb520c7b8c1bbb02e",
        "2a2092cb20bfbeb2b5c0bdc3bbb820c0c3c7bac320bdb0c1c2c0beb9bab82e209fb0c5bdc3bbbe20bdb0b3c0b5c2cbba20bcb0c1bbbebc20b820c1c2b0c0beb920b1c3bcb0b3beb920b8b720b7b0b2beb4c1babeb3be20b0c0c5b8b2b02e",
        "2a20a2c0b820bcb5c5b0bdb8b7bcb020b6b4c3c220b2b0c8b5b3be20b2cbb1bec0b02c20c1bbbeb2bdbe20c2c0b820c1c2c0b0b6b020c320c0b0b7b2b8bbbab820b220bfbeb4b7b5bcb5bbccb52e209ab0b6b4cbb920b3beb2bec0b8c220bdb020c1b2bed1bc20cfb7cbbab52e",
        "2a209db020bac0ccc8bab520bfc0b8b1bec0b020bcb5bbbebc20b2cbb2b5b4b5bdb020bfb0bccfc2bab020c8b8c4c0beb2b0bbbcc9b8bab02e20a1bbb5b4cb20bfb0bbbcc6b5b220bdb020babbb0b2b8c8b0c520c1b2b5c2cfc2c1cf20c1bbb0b1cbba20c4bec1c4bec0bebc2e",
        "2a2092cb20bdb0b6b0bbb820bfc3c1babeb2c3ce20bfb5b4b0bbcc3a20bcb5b4bdbbb520b2b0bbb8bab820bfc0beb2b5c0bdc3bbb8c1cc2c20bec2b1c0b0c1cbb2b0cf20bfc0b8c7c3b4bbb8b2cbb520c2b5bdb820bdb020b1c0b5b2b5bdc7b0c2c3ce20c1c2b5bdc32e",
        "2a2092bdc3c2c0b820c1c2b5babbcfbdbdbeb920babebbb1cb20b4b5c8b8c4c0b0c2bec0b020bfbbb0b2b0b5c220bac0b8c1c2b0bbbb20b3bec0bdbeb3be20bab2b0c0c6b02e209fc0b820b2b2beb4b520c2b5bac1c2b020bebd20bcb5bdcfb5c220bec2c2b5bdbeba2e",
        "2a20a1bbbcc8bdbe2c20bab0ba20bfbeb420bfbebbbebc20b220c2b0bac220babbb0b2b8c8b0bc20c1c2c3c7b0c220bdb5b2b8b4b8bccbb520bcbebbbec2bec7bab82e2093bec0b020bfbebcbeb3b0b5c220b2b0bc20c0b0b7b1b8c0b0c2cc20bfc3c2b0bdbbb520b7bdb0bab82e",
        "2a20a1c2b0c0cbb920b0c0b8c4bcbebcb5c2c02022a4b5bbb8bac12220c1beb5b4b8bdd1bd20bfc0beb2beb4b0bcb820c120c2b5c0bcb8bdb0bbbebc2e20a7c3b6b0cf20c0b5c7cc20b7b4b5c1cc20bbb5b3babe20c0b0c1bfb0b4b0b5c2c1cf20bdb020bfc0bec1c2cbb520babeb4cb2e",
        "2a2092cb20bec2bac0cbbbb820c2cfb6d1bbc3ce20bac0ccc8bac320babeb4beb2beb3be20c1c3bdb4c3bab02e2092bdc3c2c0b820c2b8bab0cec220c7b0c1beb2cbb520bfc0c3b6b8bdbb2c20bec2bcb5c0cfcf20c1b4b2b8b3b820b0bbc4b0b2b8c2b02e",
        "2a209db020bfbebccf20c1c2b0c0beb920c1c5b5bccb20bac2be20c2be20bdb0c0b8c1beb2b0bb20bcb0bbb5bdccbabeb520c1b5c0b4b5c7babe20b820bfbeb4bfb8c1b0bb3a20229db520b7b0b1cbb2b0b920bfc0beb2b5c0cfc2cc20beb1c0b0c2bdcbb920c1b4b2b8b3222e",
        "2a20a5bebbbeb4bdbbb520bcb5c2b0bbbbb8c7b5c1bab8b520c2c3bcb1bbb5c0cb20bfc0b8cfcbdbe20c2cfb6b5bbcfc220bfb0bbbcc6cb2e2092cb20b3bec2beb2cb20b7b0c8b8c4c0beb2b0c2cc20bfbec1bbb0bdb8b520b4bbcf20c2b5c52c20bac2be20b8b4d1c220c1bbb5b4bebc2e",
        "2a209220c2b8c8b8bdb520bfbeb4b7b5bcdbbeb3be20c6b5c5b020c9b5bbc7bab820b4b5c8b8c4c0b0c2bec0b020b7b2c3c7b0c220bab0ba20c8b0b3b820bfbe20bab0bcb5bdbdcbba20bfbbb8c2b0bc2e209cb5c5b0bdb8b7bc20b6b4d1c220b2b0c8b5b920babebcb0bdb4cb2e",
        "2a20a1bab2beb7cc20c1bcbec2c0beb2beb520bebebec8babe20b2b8b4bdbe2c20bab0ba20b2c0b0c9b0cec2c1cf20b4b8c1bab820c120bab8c0b8bbbbb8c6b5b920b820bbb0c2b8bdb8c6b5b92e2092c1d120b3bec2beb2be20ba20bfb5c0b5b1bec0c320c7b0c1c2bec22e",
        "2a20adc5be20c6b2b5c2beba20c320bac0b0cf20c1c2bebbb020b2bdb8bcb0c2b5bbbcbdbe20c1bbc3c8b0b5c220b3c3b4b5bdb8b520babeb4b8c0beb2c9b8bab02c20b7b0bfbebcb8bdb0cf20bab0b6b4c3ce20babebcb1b8bdb0c6b8ce20bdc3bbb5b920b820b5b4b8bdb8c62e",
        "2a2092cb20b7b0b2b5bbb820bfc0c3b6b8bdc320c1c2b0c0beb3be20c8b8c4c0beb2b0bbbcbdbeb3be20b0bfbfb0c0b0c2b02e20a0b5c8b8bcbec1c2cc20bfbebcbeb3b0b5c220b2b0bc20b2b8b4b5c2cc20c1bccbc1bb20b4b0b6b520b220c1b0bcbebc20bfbbbec2bdbebc20babeb4b52e"
    ]

    _s_n = [
        "bfc0bec1c2b820bcb5bdcf2e2e2e20c2cb20b1cbbb20bfc0b0b22e",
        "b7bdbeb920b820c5bebbbeb420bec9c3c9b0cec2c1cf20b7b4b5c1cc20b8bdb0c7b52e2e2e20b1c3b4c2be20b1bbb0b3bec1bbbeb2b5bdb8cf20b4cccfb2bebbb02e2e2e",
        "b2bdc3c2c0b820b1bebbbcc8b520bdb8c7b5b3be20bdb520c1c2c3c7b8c22e20c2bebbbcbabe20c1c3c5beb920bfb5bfb5bb20bec1cbbfb0b5c2c1cf20bfbe20c1c2b5bdbab0bc2e",
        "c2cb20b4c3bcb0bb2c20c7c2be20b7b020cdc2beb920b4b2b5c0ccce20bac2be20c2be20b6b4d1c23f20b7b4b5c1cc20c2bebbbcbabe20cdc5be2e",
        "c1bbbeb2b020c2b5c0cfcec220c4bec0bcc32c20babeb3b4b020b8c520bdb5babebcc320c1bbbcc8b0c2cc2e20bec1c2b0d1c2c1cf20bbb8c8cc20c1b5c0cbb920b3c3bb2e",
        "cf20c1bcbec2c0b5bb20b220bfc3c1c2c3ce20babebcbdb0c2c320c2b0ba20b4bebbb3be2c20c7c2be20c1b0bc20c1c2b0bb20b5d120c3b3bbbebc2e",
        "bdb520bdc3b6bdbe20bdb8c7b5b3be20c7b8bdb8c2cc2e20c1bbbebcb0bdbdcbb520b2b5c9b820c5bec2cf20b1cb20bdb520bfc0b8c2b2bec0cfcec2c1cf20b6b8b2cbfb82e",
        "b7b020c1c2b5babbbebc20bdb5c220c3bbb8c6cb2e20c2b0bc20bfc0bec1c2be20bdb0c0b8c1beb2b0bdb020c7c3b6b0cf20bfb0bccfc2cc20be20b2c7b5c0b0c8bdb5bc20b4bdb52e",
        "bab0b6b4cbb920c2b2beb920c8b0b320b7b2c3c7b8c220c2b0ba2c20b1c3b4c2be20c2cb20b8b4d1c8cc20bfbe20bfc3c1c2bebcc320b6b5bbb5b7bdbebcc320babec0b8b4bec0c32e",
        "bccb20b2cbc0b5b7b0bbb820bfbec1bbb5b4bdb8b920c3b7b5bb2c20bdbe20c2b8c8b8bdb020bfbec7b5bcc320c2be20bdb520bfc0b8bdb5c1bbb020bfbebebecf2e",
        "bac2be20c2be20b2cbbabbbec7b8bb20c1b2b5c220b220c1bec1b5b4bdb5bc20bec2c1b5bab52e20bab0b6b5c2c1cf2c20c2b0bc20bdb8babeb3be20b820bdb520b1cbbbebe2e",
        "bcbeb820c0c3bab820bab0b6c3c2c1cf20c7c3b6b8bcb82e20b1c3b4c2be20cf20bfc0bec1c2be20c3bfc0b0b2bbcfce20bac3babbbeb920c7b5c0b5b720bcc3c2bdcbb920cdbac0b0bd2e",
        "b2c0b5bccf20b7b4b5c1cc20bdb520c2b5c7d1c22c20bebdbe20c1c2beb8c220bab0ba20b7b0c2c5bbb0cf20b2beb4b020b220bfbeb4b2b0bbb52e",
        "c2cb20bfbeb1b5b4b8bb20c2be20b5b4b8bdc1c2b2b5bdbdbeb52c20c7c2be20b5c9d120bfcbc2b0bbbeb1cc20b1b8c2ccc1cf20b220cdc2beb920bfc3c1c2bec2b52e",
        "bdb820beb1b8b4cb2c20bdb820c1c2c0b0c5b02e20c2bebbbcbabe20c0beb2bdb0cf20b1b5bbb0cf20bfc0bec1c2cbbdcf20b4be20c1b0bcbeb3be20b3bec0b8b7bebdc2b02e",
        "b3bebbbec1b020b220b3bebbbeb2b520bdb0babebdb5c620b7b0bcbebbc7b0bbb82c20b820cdc2b020c2b8c8b8bdb020bebab0b7b0bbb0c1cc20bdb0bcdbbeb3be20c1c2c0b0c8bdb5b52e",
        "b5c1bbb820b7b0bac0cbc2cc20b3bbb0b7b02c20bdb8c7b5b3be20bdb520bcb5bdcfb5c2c1cf2e20c2b5bcbdbec2b020c1bdb0c0c3b6b820b820c2b5bcbdbec2b020b2bdc3c2c0b820beb4b8bdb0babeb2cb2e",
        "cf20bfcbc2b0bbc1cf20b2c1bfbebcbdb8c2cc20c2b2bed120bbb8c6be2c20bdbe20b220bfb0bccfc2b820bec1c2b0bbb8c1cc20c2bebbbcbabe20c1c2d1c0c2cbb520babebdc2c3c0cb2e",
        "b7b4b5c1cc20b4b0b6b520c2b5bdb820bdb520b4b5c0b6b0c2c1cf20b7b020c1c2b5bdbb2e20bebdb820bfc0bec1c2be20c1bfbebbb7b0cec220bdb020bfbebbb2e",
        "c2cb20b2c1d120b5c9d120b8c9b5c8cc20c1bccbc1bb20c2b0bc2c20b3b4b520bec1c2b0bbb0c1cc20beb4bdb020b2cbb6b6b5bdbdb0cf20b8b7b2b5c1c2babeb2b0cf20bfcbbccc2e",
        "bdb8bac2be20bdb520bfc0b8b4d1c220bfc0beb2b5c0b8c2cc20bfbebeb0b7b0c2b5bbb82e20bfc0b8b1bec0cb20c0b0b1bec2b0cec220b2c5bebbbec1c2c3ce20c3b6b520bcdbbeb3be20bbb5c22e",
        "c1c2c0b0bdbdbe2c20bab0ba20bbb5b3babe20beb1c0cbb2b0b5c2c1cf20bfbec1bbb5b4bdcfcf20bdb8c2cc2c20babeb3b4b020b1bebbbcc8b520bdb520b7b020c7c2be20b4b5c0b6b0c2ccc1cf2e",
        "b2beb7b4c3c520c2b0babeb920bfbbbec2bdcbb920b820bfc3c1c2beb92c20c7c2be20bab0b6b4cbb920b2b4bec520bab0b6b5c2c1cf20b1b5c1c1bccbc1bbb5bdbdcbba20c3c1b8bbb8b5bc2e",
        "bccb20c120c2beb1beb920bfc0bec1c2be20b4b2b520bfbebcb5c5b820bdb020b4b0b2bdbe20b7b0b1cbc2beb920c0b5b7b5c0b2bdbeb920c7b0c1c2bec2b52e",
        "bdb520beb1bec0b0c7b8b2b0b9c1cf2e20bfbeb7b0b4b820c3b6b520c1c2d1c0bbb8c1cc20b2c1b520babebcbdb0c2cb2c20c7b5c0b5b720babec2bec0cbb520c2cb20c8d1bb2e",
        "bfc3bbbcc120b8c1c7b5b72c20b020bfc0b8b2cbc7bab020b6b4b0c2cc20c3b4b0c0b020b2c1d120b5c9d120b4b5c0b6b8c220b220bec6b5bfb5bdb5bdb8b82e",
        "b220cdc2bebc20bcb5c1c2b520b4b0b6b520b1bebbbccc20bab0b6b5c2c1cf20c7b5bc20c2be20b4b0bbd1bab8bc20b820bdb5bdb0c1c2becfc9b8bc2e",
        "c2cb20b4bebab0b7b0bb20c1b2bece20bfc0b0b2bec2c320bfc3c1c2bebcc320c1c2c3bbc320b220b7b0bfb5c0c2beb920b8b7bdc3c2c0b820b1b5c2bebdbdbeb920babec0beb1bab52e",
        "c1bdb0c0c3b6b820b8b4d1c220c1bdb5b320b8b720bcb5bbbabeb3be20bfb5bfbbb02e20bebd20b7b0c1cbbfb0b5c220bfbec1bbb5b4bdb8b520c1bbb5b4cb20c320bfbec0beb3b02e",
        "cf20b1bebbbcc8b520bdb520c7c3b2c1c2b2c3ce20b3c0b0bdb8c620c1b2beb5b3be20c2b5bbb02e20c2bebbbcbabe20c5bebbbeb4bdcbb920babebdc2c3c020beb1bebbbec7bab82e",
        "b2c1b520bfb8c1ccbfb020b1cbbbb820bec2bfc0b0b2bbb5bdbb20bdb020bdb5c1c3c9b5c1c2b2c3cec9b8b920b0b4c0b5c12e20bfbec7c2b0bbbcbebd20b4b0b2bdbe20c3c1bdc3bb20b220c1bdb5b3c32e",
        "b7b0c7b5bc20c2cb20bfc0beb4bebbb6b0b5c8cc20c1bcbec2c0b5c2cc20b220cdc2be20bebabdbe3f20b7b4b5c1cc20b1bebbbcc8b520bdb8babeb3be20bdb520bfbebeb0b6c3c22e",
        "bfb0bccfc2cc20bec1cbbfb0b5c2c1cf20bac3c1bab0bcb820c8c2c3bab0c2c3c0bab82e20c1babec0be20bec1c2b0bdb5c2c1cf20c2bebbbcbabe20b3bebbb0cf20c1b5c0b0cf20babbb0b4bab02e",
        "b4b0b6b520cdc5be20c3c1c2b0bbbe20bfbeb2c2bec0cfc2cc20bdb0c8b820c8b0b3b820b820bbb5b3bbbe20c1bfb0c2cc20b220c3b3bbc32e",
        "c2cb20bec1c2b0bbc1cf20c1beb2c1b5bc20beb4b8bd20bdb020cdc2beb920b3bbc3b1b8bdb52e20bfbeb4cad1bcbdb8ba20b1bebbbcc8b520bdb520c1bfc3c1c2b8c2c1cf2e",
        "bdb8bab0babeb3be20bab0c2b0c0c1b8c1b020bdb520b1c3b4b5c22e20bfc0bec1c2be20c2b8c5b8b920c9b5bbc7beba20c2c3bcb1bbb5c0b020b220babebdc6b520c1bcb5bdbb2e",
        "c7c3b2c1c2b2b020b2cbb3bec0b5bbb820b4bec2bbb02c20bec1c2b0b2b8b220bfbec1bbb520c1b5b1cf20c2bebdbab8b920b7b0bfb0c520b3bec0b5bbbeb920b8b7bebbcfc6b8b82e",
        "bccb20c1c2c0beb8bbb820c1c2b5bdbb2c20c7c2beb1cb20c1bfc0cfc2b0c2ccc1cf2c20b020bfbebbc3c7b8bbc1cf20c1babbb5bf20b1b5b720b5b4b8bdbeb920c9b5bbb82e",
        "b220b7b5c0bab0bbb520b1bebbbcc8b520bdb8bac2be20bdb520bec2c0b0b6b0b5c2c1cf2e20c2bebbbcbabe20bfcbbccdbdb0cf20bbb0bcbfb020bfbeb420bfbec2bebbbabebc2e",
        "bab0b6b4b0cf20bccbc1bbcc20b2cfb7bdb5c220b220c1b5c0bebc20bab8c1b5bbb52c20bdb520b4bec5beb4cf20b4be20babebdc7b8bab020cfb7cbbab02e",
        "c2cb20c1bbbcc8b8c8cc20cdc2bec220b7b2bebd20b220c3c8b0c53f20cdc2be20b7b2c3ba20b0b1c1bebbbec2bdbe20bfc3c1c2beb3be20bfc0bec1c2c0b0bdc1c2b2b02e",
        "b1bebbbcc8b520bdb520bdc3b6bdbe20b7b0c9b8c9b0c2ccc1cf20b820bcbebbb8c2ccc1cf2e20b7b4b5c1cc20bdb5babebcc320bfc0b8c7b8bdb8c2cc20c2b5b1b520b2c0b5b42e",
        "b2c1d120b7b0babebdc7b8bbbeb1cc20b3bec0b0b7b4be20c0b0bdccc8b52c20c7b5bc20c2cb20bdb0b6b0bb20bdb020bfb5c0b2c3ce20babdbebfbac32e",
        "bec1c2b0bbb0c1cc20c2bebbbcbabe20c2bebdbab0cf20bfbbd1bdbab020c1bdb020bdb0b420b1b5b7b4bebdbdcbbc20c7d1c0bdcbba20babebbbeb4c6b5bc2e",
        "bfc0bec9b0b92e20b4b0bbbcc8b520bdb0c7b8bdb0b5c2c1cf20bfbebbbec1b02c20b3b4b520bdb520c0b0b1bec2b0cec220b4b0b6b520c7c3b6b8b520c1bdbb2e"
    ]

    _s_d = [
        "c2cb20bec2bab0b7b0bbc1cf20b4b0b6b520bec220bfbec1bbb5b4bdb5b3be20c3c2b5c8b5bdb8cf2e20c2b5bfb5c0cc20b2bebac0c3b320c2bebbbcbabe20bcd1c0c2b2cbb920b2b0bac3c3bc2e",
        "bfc3c1c2bec2b020c1cad1bbb020c2b2bed120b8bccf2e20c2b5b1cf20b1bebbbcc8b520bdb5c220bdb820b220beb4bdbebc20c1bfb8c1bab52e",
        "b7b0c7b5bc20c2cb20bec2c2bebbbabdc3bb20c0c3bac33f20c2b5bfb5c0cc20bfb0b4b0c2cc20bfc0b8b4d1c2c1cf20b220bfbebbbdc3ce20b1b5b7b4bebdddc3ce20c2ccbcc32e",
        "b2bdc3c2c0b820c7b5c0b5bfb020b3c3bbcfb5c220bbb5b4cfbdbeb920c1bab2beb7bdcfba2e20bdb820beb4bdbeb920b6b8b2beb920b8c1bac0cb20bdb520bec1c2b0bbbeb1cc2e",
        "c2cb20c1b0bc20b2cbb1c0b0bb20bdb5b1cbc2b8b52e20c1c2b5bdbb20c1b4b2b8b3b0cec2c1cf2c20c1c2b8c0b0b5c2c1cf20bfbec1bbb5b4bdb8b920b3bbbec2beba20b2beb7b4c3c5b02e",
        "b4b0b6b520c2b5bdcc20bec2b2b5c0bdc3bbb0c1cc20bec220c2b5b1cf2e20c2cb20c1c2b0bb20bfc0beb7c0b0c7bdb5b520c1c2b0c0beb3be20b1bebbbcbdb8c7bdbeb3be20c1c2b5babbb02e",
        "bdb5c220bdb820bfc0bec8bbbeb3be2c20bdb820b7b0b2c2c0b02e20c2bebbbcbabe20b2b5c7bdb0cf20c1b5c0b0cf20c2bec7bab020bdb020b2cbb3bec0b5b2c8b5bc20cdbac0b0bdb52e",
        "c2b2bed120bcbebbc7b0bdb8b520c2cfb6b5bbb5b520c1b2b8bdc6b02e20bebdbe20c2cfbdb5c220bdb020c1b0bcbeb520b4bdbe20bbb5b4cfbdbeb920c8b0c5c2cb2e",
        "bdb8bac2be20bdb8babeb3b4b020bdb520c3b7bdb0b5c22c20c7c2be20c2cb20b7b4b5c1cc20b1cbbb2e20c1bbb5b4cb20c1bccbc2cb20c7d1c0bdbeb920b2beb4beb92e",
        "c2cb20b7b0bac0cbbb20bfbec1bbb5b4bdcece20c4bec0c2bec7bac32e20c2b5bfb5c0cc20b220cdc2beb920bab0bcb5c0b520bfb0c5bdb5c220c2bebbbcbabe20c4bec0bcb0bbb8bdbebc2e",
        "c1b5c0b4c6b520c0b0c1c1cbbfb0bbbeb1cc20b220c2c0c3c5c32c20b820c2b2beb820bfb0bbbcc6cb20bfbe20bbbebec2cc20b220c5bebbbeb4bdbeb920c1b0b6b52e",
        "bec2bab0b720bfc0b8bdcfc22e20c1b2b5c220b3b0c1bdb5c220bdb0b2c1b5b3b4b02c20bec1c2b0b2bbcfcf20c2b5b1cf20bdb0b5b4b8bdb520c120b3bbc3c5beb920bfc3c1c2bec2beb92e",
        "c2cb20c1bcbec2c0b8c8cc20b220b1b5b7b4bdc32c20bdbe20b1b5b7b4bdb520b4b0b6b520bdb520b8bdc2b5c0b5c1bdbe20c1bcbec2c0b5c2cc20b220bec2b2b5c22e",
        "b2c1d12c20ba20c7b5bcc320c2cb20bfc0b8bab0c1b0bbc1cf2c20bfc0b5b2c0b0c2b8bbbeb1cc20b220c1c3c5c3ce20c1b5c0c3ce20bfbbb5c1b5bdcc2e",
        "b1bebbbcc8b520bdb5c220bdb820b3bebbbec1b02c20bdb820b4cbc5b0bdb8cf2e20c2bebbbcbabe20bcd1c0c2b2b0cf20c1c2b0c2b8bab020b220b3c0c3b4bdbeb920babbb5c2bab52e",
        "c2cb20b2cbc7b5c0babdc3bb20c1b5b1cf20c1b0bc2e20b4b0b6b520cdc5be20b1c0b5b7b3c3b5c220bfbeb2c2bec0cfc2cc20c2b2beb820c8b0b3b82e",
        "c5bebbbeb420bfc0bebdb8bab0b5c220b220babec1c2b82e20cdc2be20bdb520b7b8bcb02c20cdc2be20bfc0bec1c2be20bec2c1c3c2c1c2b2b8b520b6b8b7bdb82e",
        "bdb820beb4bdbeb920b4b2b5c0b820b1bebbbcc8b520bdb520c1c3c9b5c1c2b2c3b5c22e20b2bebac0c3b320c2bebbbcbabe20c1bfbbbec8bdbeb920c1cbc0beb920b1b5c2bebd2e",
        "c2cb20bec1c2b0bbc1cf20bfbe20c2c320c1c2bec0bebdc320c1c2b5babbb02c20b3b4b520bdb8babeb3b4b020bdb520bdb0c1c2c3bfb0b5c220c3c2c0be2e",
        "bfb0bccfc2cc20c1c2d1c0c2b020bdb0c7b8c1c2be2e20c2cb20bdb520b2c1bfbebcbdb8c8cc20b4b0b6b52c20b7b0c7b5bc20bec2bac0cbb2b0bb20b3bbb0b7b020c1b5b3beb4bdcf2e",
        "bab0b6b4b0cf20c1b5bac3bdb4b020b7b4b5c1cc20b4bbb8c2c1cf20b2b5c7bdbec1c2cc2c20b820b220bdb5b920b0b1c1bebbbec2bdbe20bdb8c7b5b3be20bdb520bfc0beb8c1c5beb4b8c22e",
        "c2cb20c1b0bc20b7b0b4c3bb20bfbec1bbb5b4bdcece20c1bfb8c7bac32e20bfc0b8b2cbbab0b920ba20cdc2beb920b2cfb7babeb920c1bbb5bfbec2b52e",
        "bdb820c1beb6b0bbb5bdb8cf2c20bdb820b1bebbb82e20c2cb20bfc0bec1c2be20bfc3c1c2b0cf20beb1bebbbec7bab020bdb020c5bebbbeb4bdbebc20bab0c4b5bbb52e",
        "bcb8c020c1bdb0c0c3b6b820c1b2b5c0bdc3bbc1cf20b220c2bec7bac320b820bfbeb3b0c12e20bec1c2b0bbb0c1cc20c2bebbbcbabe20b3bbc3c5b0cf20bdbec7cc2e",
        "c2b2beb820c1bbbeb2b020c2bebdc3c220b220c7d1c0bdbebc20bcb0b7c3c2b52e20bdb8bac2be20bdb520c3c1bbbcc8b8c220c2b2beb920c8d1bfbec22e",
        "b7b4b5c1cc20bdb520c0b0c1c2c3c220b4b0b6b520bcd1c0c2b2cbb520c6b2b5c2cb2e20c2bebbbcbabe20c0b6b0b2c7b8bdb020b820c1bebbcfbdb0cf20babec0bab02e",
        "c2cb20bec2b2b5c0b320bfbec1bbb5b4bdb8b920c1b8b3bdb0bb2e20c2b5bfb5c0cc20bfc0b8d1bcbdb8ba20c2c0b0bdc1bbb8c0c3b5c220c2bebbbcbabe20c8c3bc20c0b0c1bfb0b4b02e",
        "b2bdc3c2c0b820c2b5b1cf20b2cbbabbbec7b8bbb820c0c3b1b8bbbcbdb8ba2e20b7b0bbcb20bfc3c1c2cb2c20babec0b8b4bec0cb20b7b0c2bebfbbb5bdbb20bbb5b4cfbdbeb920b2beb4beb92e",
        "bdb520bfcbc2b0b9c1cf20bac0b8c7b0c2cc2e20b7b4b5c1cc20bdb5c220b2beb7b4c3c5b02c20c7c2beb1cb20b4bebdb5c1c2b820b7b2c3ba20b4be20c1c2b5bd2e",
        "c2cb20c1c2b0bb20c7b0c1c2ccce20c1b5c0beb3be20c4bebdb02e20bfcbbbb8bdbabeb92c20b7b0c1c2c0cfb2c8b5b920bcb5b6b4c320b4b2c3bccf20c1c2d1babbb0bcb82e",
        "b1bebbbcc8b520bdb8bab0bab8c520b2cbb1bec0beb22e20b4bec0beb3b020beb1c0cbb2b0b5c2c1cf20bfc0cfbcbe20bfbeb420c2b2beb8bcb820bfbeb4bec8b2b0bcb82e",
        "b4b0b6b520bfc3c1c2bec2b020bab0b6b5c2c1cf20c1bbb8c8babebc20c2b5c1bdbeb92c20babeb3b4b020b220bdb5b920bec1c2b0d1c8ccc1cf20bdb0b2c1b5b3b4b02e",
        "b2c1d12c20b2be20c7c2be20c2cb20b2b5c0b8bb2c20bebab0b7b0bbbeb1cc20bfc0bec1c2be20b4b5c4b5bac2bebc20c1c2b0c0beb920bab8bdbebfbbd1bdbab82e",
        "bfbbd1bdbab020beb1bec0b2b0bbb0c1cc2e20b220b7b0bbb520b4b0b2bdbe20bdb8babeb3be20bdb5c22c20bfc0beb5bac2bec020c1b2b5c2b8c220b220bfc3c1c2bec2c32e",
        "c2cb20b7b0bcd1c0b720b8b7bdc3c2c0b820c2b0ba20b3bbc3b1bebabe2c20c7c2be20bbceb1beb520c2b5bfbbbe20bfbebeb0b6b5c2c1cf20beb6beb3bebc2e",
        "bdb8bac2be20bdb520b8c9b5c220c2b5b1cf2e20c2b2bed120bec2c1c3c2c1c2b2b8b520b4b0b6b520bdb520b7b0bcb5c2b8bbb820b220beb1c9b5bc20c8c3bcb52e",
        "c1bccbc1bb20b2cbc2b5ba20c1bab2beb7cc20c2c0b5c9b8bdbb2c20bab0ba20b3c0cfb7bdb0cf20c2b0bbb0cf20b2beb4b020b220b2beb4bec1c2beba2e",
        "bec1c2b0bbb0c1cc20c2bebbbcbabe20b1b5c1c1bebdbdb8c6b020b1b5b720c1bdbeb220b820c3c1c2b0bbbeb1c2cc2c20babec2bec0c3ce20bdb5b2beb7bcbeb6bdbe20b2cbbfbbb0bab0c2cc2e",
        "c2cb20c1b0bc20b7b0bcc3c0beb2b0bb20b2cbc5beb42e20c2b5bfb5c0cc20c1bbc3c8b0b92c20bab0ba20bec1cbbfb0b5c2c1cf20b8b7b2b5c1c2babeb2b0cf20bfcbbccc2e",
        "b220cdc2beb920c2b8c8b8bdb520c1bbbcc8bdbe2c20bab0ba20bcb5b4bbb5bdbdbe20bec1c2b0bdb0b2bbb8b2b0cec2c1cf20bfbec1bbb5b4bdb8b520c7b0c1cb2e",
        "bdb8bab0babeb3be20bfc0bec9b5bdb8cf2c20bdb8bab0babeb3be20bfc0b8b3beb2bec0b02e20bfc0bec1c2be20b0b1c1bebbbec2bdcbb920bdbebbcc20bfbe20b2c1b5bc20c8bab0bbb0bc2e",
        "c2cb20c0b0c1c2b2bec0b8bbc1cf20b220c1b5c0bebc20c2c3bcb0bdb520c0b0bdccc8b52c20c7b5bc20b7b0babebdc7b8bbb0c1cc20cdc2b020c1c2c0bec7bab02e",
        "b4b0bbbcc8b520bdb5c220b4b0b6b520c2b5bcbdbec2cb2e20c2bebbbcbabe20bfbebbbdbeb520bec2c1c3c2c1c2b2b8b520c7b5b3be20b1cb20c2be20bdb820b1cbbbebe2e",
        "babebdb5c620c1b2cfb7b82e20c7b0c1c2bec2b020b7b0bac0cbc2b020bdb0b2c1b5b3b4b020b7b020bdb5b8bcb5bdb8b5bc20b6b8b2cbc520b0b1bebdb5bdc2beb22e",
        "b2c1d12e20b4b0bbbcc8b520c2bebbbcbabe20b3bbc3c5b0cf20b1b5c2bebdbdb0cf20bfbbb8c2b020b820b2b5c7bdcbb920bfbebeb920bfc3c1c2bec2cb2e"
    ]

    _s_q = [
        "c2cb20c1beb3bbb0c1b5bd20bec1c2b0c2ccc1cf20b220cdc2beb920bfc3c1c2beb920babebcbdb0c2b52c20bfbebeb020c1bdb0c0c3b6b820c1c2b8c0b0cec220b3bec0beb4b03f",
        "bfc0b8bcb5c8cc20bbb820c2cb20cdc2c320c2b8c8b8bdc320bab0ba20b5b4b8bdc1c2b2b5bdbdc3ce20bfc0b0b2b4c32c20babec2bec0b0cf20c320bdb0c120bec1c2b0bbb0c1cc3f",
        "bccb20b2cbbabbbec7b8bc20c1b2b5c220bfc0cfbcbe20c1b5b9c7b0c12e20c2cb20b3bec2beb220bec2bfc3c1c2b8c2cc20bfbec1bbb5b4bdb8b520c7c3b6b8b520b3bebbbec1b03f",
        "b5c1bbb820bfc3c1c2bec2b020bdb0b7beb2d1c220c2b5b1cf20bfbe20b8bcb5bdb82c20c2cb20bec2babbb8babdb5c8ccc1cf20bdb020b5d120b7beb23f",
        "bec1c2b0b2b8bc20bbb820bccb20bfb5bfb5bb20bdb5c2c0bebdc3c2cbba2c20c7c2beb1cb20bdb8bac2be20bdb520c3b7bdb0bb20be20bdb0c8b5b920bec8b8b1bab53f",
        "c2cb20bfbeb7b2bebbb8c8cc20c1c2b5c0b5c2cc20b8b720bfb0bccfc2b820b2c1b5c52c20bac2be20babeb3b4b020c2be20beb1b5c9b0bb20b2b5c0bdc3c2ccc1cf3f",
        "c1beb3bbb0c1b5bd20bbb820c2cb2c20c7c2be20b2bdc3c2c0b820cdc2beb920beb1bebbbec7bab820bdb8babeb3b4b020bdb8babeb3be20b820bdb520b1cbbbebe3f",
        "bccb20b7b0bfb8c0b0b5bc20c8b0c5c2c320c120beb1c0b0c2bdbeb920c1c2bec0bebdbcb2e20c2cb20bec2b4b0d1c8cc20c1b2beb920babbcec720b4beb1c0beb2bebbbcbdbe3f",
        "bfc0b8b7bdb0b5c8cc20bbb820c2cb2c20c7c2be20c5bebbbeb420b2bdc3c2c0b820c1c2b0bb20b5b4b8bdc1c2b2b5bdbdcbba20c2b2beb8bc20bdb0c1c2becfc9b8bc20b4bebcbebc3f",
        "c5bec7b5c8cc20bbb820c2cb2c20c7c2beb1cb20bfc0b8b1bec0cb20bfc0beb4bebbb6b0bbb820b2c0b0c2cc2c20b1c3b4c2be20bccb20b5c9d120b6b8b2cb3f",
        "b5c1bbb820cf20bfc0bec2cfbdc320c2b5b1b520bfc3c1c2c3ce20bbb0b4bebdcc20b8b720c2b5bcbdbec2cb2c20c2cb20c1beb6bcd1c8cc20b5d13f",
        "c1beb3bbb0c1b5bd20bbb820c2cb20b7b0b1cbc2cc20b4bec0beb3c320bdb0b2b5c0c520c0b0b4b820bfbebebecf20bdb020c1b0bcbebc20b4bdb53f",
        "bfc3c1c2cc20c7b0c1cb20c1c2becfc220b2b5c7bdbe2e20c2cb20bfc0b8bdb8bcb0b5c8cc20cdc2bec220b7b0c1c2cbb2c8b8b920bcb8b320b1b5b720bec1c2b0c2bab03f",
        "bccb20b1bebbbcc8b520bdb520b1c3b4b5bc20b6b4b0c2cc20bec2b2b5c2b020c120bfbeb2b5c0c5bdbec1c2b82e20c2cb20bfbeb4bfb8c1cbb2b0b5c8cc20cdc2bec220bec2bab0b73f",
        "b3bec2beb220bbb820c2cb20c1bcbec2c0b5c2cc20b220c1b5c0beb520c1c2b5babbbe2c20bdb520c2c0b5b1c3cf20bec220bdb5b3be20bec2c0b0b6b5bdb8cf3f",
        "bfc0bec1c2b8c8cc20bbb820c2cb20bfc3c1c2bec2c320b7b020c2be2c20c7c2be20bebdb020bebab0b7b0bbb0c1cc20c1b8bbbcbdb5b520c2b2beb5b3be20c1b5c0b4c6b03f",
        "bec1c2b0b2b8bc20bbb820bccb20cdc2c320c7b0c1c2bec2c320bec2bac0cbc2beb920c2bebbbcbabe20b4bbcf20b1b5bbbeb3be20c8c3bcb020b820b2b5c2c0b03f",
        "c2cb20c1beb3bbb0c1b5bd20c1c2b0c2cc20c2b5bdccce20bdb020c1c2b5bdb52c20babec2bec0c3ce20c1bcbebec220bfb5c0b2cbba20b6b520b4beb6b4d1bc3f",
        "bfc0b8bcb5c8cc20bbb820c2cb20cdc2be20beb4b8bdbec7b5c1c2b2be20b1b5b720bfbebfcbc2beba20bfbeb7b2b0c2cc20babeb3be20bdb8b1c3b4cc20bdb020bfbebcbec9cc3f",
        "bfc3c1c2cc20b4b2b5c0b820b8c1c7b5b7bdc3c220c1beb2c1b5bc2e20c2cb20c1beb3bbb0c1b5bd20bdb8babeb3b4b020b1bebbbcc8b520bdb520b8c1bab0c2cc20b2cbc5beb43f",
        "bec2b4b0c8cc20bbb820c2cb20bfbec1bbb5b4bdb5b520b2bec1bfbebcb8bdb0bdb8b520be20c2b5bfbbb52c20c7c2beb1cb20b1bebbbcc8b520bdb520c7c3b2c1c2b2beb2b0c2cc20b1bebbbccc3f",
        "bccb20b3b0c1b8bc20bfbec1bbb5b4bdb8b920b8bdb4b8bab0c2bec020bdb020bfc3bbbcc2b52e20c2cb20bfbeb4c2b2b5c0b6b4b0b5c8cc20bfbebbbdbeb520bec2babbbec7b5bdb8b53f",
        "b7b4b5c1cc20babebdc7b0b5c2c1cf20bbceb1b0cf20c0b5c7cc2e20c2cb20c1beb3bbb0c1b5bd20c8b0b3bdc3c2cc20b220cdc2be20b1b5b7bcbebbb2b8b520c1b0bc3f"
    ]

    out["f_enter"] = [_u_dec(x) for x in _m_a]
    out["f_news"] = [_u_dec(x) for x in _m_b]
    out["f_dec"] = [_u_dec(x) for x in _m_c]
    out["d_norm"] = [_u_dec(x) for x in _s_n]
    out["d_dep"] = [_u_dec(x) for x in _s_d]
    out["d_choice"] = [_u_dec(x) for x in _s_q]
    out["glyphs"] = [chr(c) for c in (27515, 39746, 34394, 30171, 32618, 24536, 24433, 34880, 28961, 22818, 23490, 28357)]
    out["tags"] = [
        bytes.fromhex(h).decode("utf-8") for h in (
            "e381b8e8a8ade5ae9a", "e5bf83e88793", "e8999ae784a1", "e88489e6908f", "e5bcbbe4b8b8",
            "e582b7e58fa3", "e8a898e686b6", "e99bb6e58fb7", "e6b7b1e6b7b5", "e6ae8be99fbf"
        )
    ]
    return out


_SYS_BLOB = _init_sys_telemetry()

DEFAULT_UI = {
    "welcome_title": "⚓ Коммерческая Контора и Персональный Архив Дел",
    "welcome_desc": (
        "Таки здравствуйте, дорогой наш человек! Вы зашли в образцовую одесскую контору, где каждый документ имеет свой вес и прейскурант. "
        "Здесь ваш гешефт, научные изыскания, отчёты и архивы содержатся в таком порядке, шо на Малой Арнаутской могут только позавидовать. "
        "Нажимайте на любой документ в архиве, и он сам откроется перед вами как по маслу!"
    ),
    "bar_proj": f"🧭 Группа: Проекты • Сборка v{BOT_VERSION}",
    "bar_forest": f"🌲 Группа: Лес • Сборка v{BOT_VERSION}",
    "btn_projects": "📁 Мои проекты",
    "btn_dump": "🗄 Архив файлов",
    "btn_codes": "💻 Сундук кодов",
    "btn_ai": "🤖 Беседа с ИИ",
    "btn_keys": "🔑 Мои ключи API",
    "btn_search": "🔍 Сыск по базе",
    "btn_notifs": "Уведомления",
    "btn_settings": "⚙️ Вывески и кнопки",
    "btn_usage": "📖 О использовании",
    "btn_ext_a": "🌌 Радиоэфир",
    "btn_ext_b": "🌻 Декодеры"
}


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" in data:
                    data.setdefault("public_codes", [])
                    data.setdefault("shared_links", {})
                    now_ts = int(time.time())
                    if not data.get("v10_migrated"):
                        for udata in data["users"].values():
                            udata["m_active"] = False
                            udata["m_phase"] = None
                            udata["m_rounds"] = 0
                            udata["m_heart_hits"] = 0
                            udata["m_heart_goal"] = 0
                            udata["m_target_btn"] = ""
                            udata["m_lock"] = 0
                            udata["m_deadline"] = 0
                            udata["hb"] = {}
                            udata.setdefault("last_seen", now_ts)
                            udata.setdefault("reminders", [])
                            udata.setdefault("notifications", [])
                            udata.setdefault("dump_limit", 5)
                            udata.setdefault("active_group", "projects")
                            ui_d = udata.setdefault("ui", {})
                            ui_d["bar_proj"] = f"🧭 Группа: Проекты • Сборка v{BOT_VERSION}"
                            ui_d["bar_forest"] = f"🌲 Группа: Лес • Сборка v{BOT_VERSION}"
                            ui_d.setdefault("btn_usage", "📖 О использовании")
                        data["v10_migrated"] = True
                    return data
        except Exception:
            pass
    return {
        "v10_migrated": True,
        "users": {},
        "public_codes": [],
        "shared_links": {}
    }


def _sync_terminal_snapshot(data: dict):
    try:
        sh_now = datetime.now(SH_TZ).strftime("%Y.%m.%d %H:%M:%S (UTC+8)")
        users = data.get("users", {})
        total_users = len(users)
        total_projects = 0
        total_files = 0
        lines = [
            "==========================================================",
            f"📊 ОТЧЁТ КОНТОРЫ BOTHOST (v{BOT_VERSION}) | {sh_now}",
            "=========================================================="
        ]
        user_blocks = []
        for uid, udata in users.items():
            projs = udata.get("projects", {})
            u_p_cnt = len(projs)
            u_f_cnt = sum(len(p.get("files", [])) for p in projs.values())
            total_projects += u_p_cnt
            total_files += u_f_cnt

            m_val = udata.get("m_val", 0)
            m_lock = udata.get("m_lock", 0)
            rem_min = max(0, int((m_lock - time.time()) // 60)) if m_lock > time.time() else 0
            uname = udata.get("username", f"ID_{uid}")
            active_rems = len([r for r in udata.get("reminders", []) if not r.get("done")])
            d_limit = max(3, min(10, udata.get("dump_limit", 5)))
            grp = "Лес" if udata.get("active_group") == "forest" else "Проекты"

            u_lines = [
                f"\n👤 Пользователь: {uname} (ID: {uid}) | Группа: {grp}",
                f"   Состояние: индекс={m_val}/100 | пауза={rem_min} мин. | пагинация дампа={d_limit} шт./стр. | напоминаний={active_rems}"
            ]
            for pid, p in projs.items():
                p_files = p.get("files", [])
                u_lines.append(f"   📁 Проект: «{p.get('name', '')}» (всего файлов: {len(p_files)})")
                for p_idx in range(0, len(p_files), d_limit):
                    page_num = (p_idx // d_limit) + 1
                    chunk = p_files[p_idx:p_idx + d_limit]
                    u_lines.append(f"     --- Страница {page_num} (по {d_limit} на стр.) ---")
                    for offset, fitem in enumerate(chunk, 1):
                        f_num = p_idx + offset
                        u_lines.append(f"     📄 №{f_num}: {fitem.get('name', 'Без имени')} [{fitem.get('date', '')}]")
            user_blocks.extend(u_lines)

        lines.append(f"👥 Всего пользователей в боте: {total_users}")
        lines.append(f"📁 Всего проектов на сервере:  {total_projects}")
        lines.append(f"🗄 Всего файлов на сервере:    {total_files}")
        lines.append(f"🌐 Общих кодов на витрине:     {len(data.get('public_codes', []))}")
        lines.append("==========================================================")
        lines.extend(user_blocks)
        lines.append("\n==========================================================")

        report_str = "\n".join(lines) + "\n"
        tmp_stat = STAT_FILE + ".tmp"
        with open(tmp_stat, "w", encoding="utf-8") as sf:
            sf.write(report_str)
        os.replace(tmp_stat, STAT_FILE)
    except Exception:
        pass


def save_db():
    try:
        tmp_db = DB_FILE + ".tmp"
        with open(tmp_db, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(tmp_db, DB_FILE)
        _sync_terminal_snapshot(db)
    except Exception:
        pass


db = load_db()
save_db()


def get_shanghai_date() -> str:
    return datetime.now(SH_TZ).strftime("%Y-%m-%d")


def add_past_notification(u: dict, title: str, text: str):
    notifs = u.setdefault("notifications", [])
    notifs.insert(0, {
        "id": f"ntf_{uuid.uuid4().hex[:6]}",
        "title": title[:40],
        "text": text[:300],
        "date": datetime.now(MSK_TZ).strftime("%d.%m %H:%M"),
        "read": False
    })
    pending_rems = len([r for r in u.get("reminders", []) if not r.get("done")])
    max_past = max(1, 15 - pending_rems)
    if len(notifs) > max_past:
        u["notifications"] = notifs[:max_past]


def has_unread_notifications(u: dict) -> bool:
    for n in u.get("notifications", []):
        if not n.get("read"):
            return True
    return False


def get_notif_btn_label(u: dict) -> str:
    base = u["ui"].get("btn_notifs", "Уведомления").lstrip("🔴🔔 ")
    icon = "🔴" if has_unread_notifications(u) else "🔔"
    return f"{icon} {base}"


def get_user(user_obj: types.User) -> dict:
    uid = str(user_obj.id)
    curr_sh_date = get_shanghai_date()
    now_ts = int(time.time())

    if uid not in db["users"]:
        pid = f"p_{uuid.uuid4().hex[:6]}"
        db["users"][uid] = {
            "id": uid,
            "username": user_obj.username or user_obj.full_name or f"Клиент_{uid}",
            "last_seen": now_ts,
            "ui": dict(DEFAULT_UI),
            "active_project": pid,
            "projects": {
                pid: {
                    "id": pid,
                    "name": "Основной коммерческий гешефт",
                    "desc": "Образцовая папка для контрактов, документов, исследований и материалов",
                    "created": datetime.now().strftime("%d.%m.%Y"),
                    "files": [],
                    "active_file": 0,
                    "curr_page": 0,
                    "dump_page": 0,
                    "ai_history": []
                }
            },
            "my_codes": [],
            "personal_keys": [],
            "key_cursor": 0,
            "f_ext_a": False,
            "ext_a_loc": "Russia",
            "f_ext_b": False,
            "active_group": "projects",
            "dump_limit": 5,
            "m_val": 0,
            "m_date": curr_sh_date,
            "m_active": False,
            "m_phase": None,
            "m_rounds": 0,
            "m_heart_hits": 0,
            "m_heart_goal": 0,
            "m_target_btn": "",
            "m_lock": 0,
            "m_deadline": 0,
            "hb": {},
            "anchor_msg_id": None,
            "last_msg_id": None,
            "msg_ids": [],
            "reminders": [],
            "notifications": [],
            "notif_page": 0
        }
        save_db()

    u = db["users"][uid]
    u["last_seen"] = now_ts
    u["username"] = user_obj.username or user_obj.full_name or u.get("username", f"Клиент_{uid}")
    for k, v in DEFAULT_UI.items():
        if k not in u.get("ui", {}):
            u.setdefault("ui", {})[k] = v

    for p in u.get("projects", {}).values():
        p.setdefault("dump_page", 0)

    raw_keys = u.get("personal_keys", [])
    normalized_keys = []
    for idx, item in enumerate(raw_keys, 1):
        if isinstance(item, str):
            normalized_keys.append({
                "id": f"k_{uuid.uuid4().hex[:6]}",
                "name": f"Ключ №{idx}",
                "key": item
            })
        elif isinstance(item, dict) and "key" in item:
            item.setdefault("id", f"k_{uuid.uuid4().hex[:6]}")
            item.setdefault("name", f"Ключ №{idx}")
            normalized_keys.append(item)
    u["personal_keys"] = normalized_keys
    u.setdefault("key_cursor", 0)
    u.setdefault("f_ext_a", False)
    u.setdefault("ext_a_loc", "Russia")
    u.setdefault("f_ext_b", False)
    u.setdefault("active_group", "projects")
    u.setdefault("dump_limit", 5)
    u.setdefault("m_val", 0)
    u.setdefault("m_active", False)
    u.setdefault("m_phase", None)
    u.setdefault("m_rounds", 0)
    u.setdefault("m_heart_hits", 0)
    u.setdefault("m_heart_goal", 0)
    u.setdefault("m_target_btn", "")
    u.setdefault("m_lock", 0)
    u.setdefault("m_deadline", 0)
    u.setdefault("hb", {})
    u.setdefault("anchor_msg_id", None)
    u.setdefault("last_msg_id", None)
    u.setdefault("msg_ids", [])
    u.setdefault("reminders", [])
    u.setdefault("notifications", [])
    u.setdefault("notif_page", 0)

    if u.get("m_date") != curr_sh_date:
        u["m_date"] = curr_sh_date
        u["m_val"] = 0
        u["m_active"] = False
        u["m_phase"] = None
        u["m_rounds"] = 0
        u["m_heart_hits"] = 0
        u["m_heart_goal"] = 0
        u["m_target_btn"] = ""
        u["m_lock"] = 0
        u["m_deadline"] = 0
        u["hb"] = {}
        save_db()

    return u


def _has_aux_access(u: dict) -> bool:
    return bool(u.get("f_ext_a") or u.get("f_ext_b"))


def get_active_project(u: dict) -> dict:
    pid = u.get("active_project")
    if not pid or pid not in u["projects"]:
        if not u["projects"]:
            pid = f"p_{uuid.uuid4().hex[:6]}"
            u["projects"][pid] = {
                "id": pid,
                "name": "Основной коммерческий гешефт",
                "desc": "Образцовая папка для документов и материалов",
                "created": datetime.now().strftime("%d.%m.%Y"),
                "files": [],
                "active_file": 0,
                "curr_page": 0,
                "dump_page": 0,
                "ai_history": []
            }
        else:
            pid = next(iter(u["projects"].keys()))
        u["active_project"] = pid
        save_db()
    return u["projects"][pid]


def clean_dashes(text: str) -> str:
    if not text:
        return ""
    return text.replace(" — ", ", ").replace(" – ", ", ").replace("—", ",").replace("–", ",")


def _track_msg_id(u: dict, msg_id: int):
    if not msg_id:
        return
    ids = u.setdefault("msg_ids", [])
    if msg_id not in ids:
        ids.append(msg_id)
    if len(ids) > 45:
        u["msg_ids"] = ids[-45:]
    u["last_msg_id"] = msg_id


async def _try_delete_msg(chat_id: int, msg_id: int):
    if not msg_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


async def _clear_reply_kb(chat_id: int):
    try:
        tmp = await bot.send_message(
            chat_id=chat_id,
            text=".",
            reply_markup=ReplyKeyboardRemove(),
            link_preview_options=NO_PREVIEW
        )
        await _try_delete_msg(chat_id, tmp.message_id)
    except Exception:
        pass


async def _purge_tracked_messages(
    chat_id: int,
    u: dict,
    current_msg_id: int = None,
    deep_sweep: bool = False,
    keep_anchor: bool = True
):
    anchor_id = u.get("anchor_msg_id") if keep_anchor else None
    to_delete = set(u.get("msg_ids", []))
    if u.get("last_msg_id"):
        to_delete.add(u["last_msg_id"])
    hb_mid = u.get("hb", {}).get("msg_id")
    if hb_mid:
        to_delete.add(hb_mid)
    if not keep_anchor and u.get("anchor_msg_id"):
        to_delete.add(u["anchor_msg_id"])
        u["anchor_msg_id"] = None
    if current_msg_id:
        to_delete.add(current_msg_id)
        if deep_sweep:
            for mid in range(max(1, current_msg_id - 16), current_msg_id + 2):
                to_delete.add(mid)

    if anchor_id and anchor_id in to_delete:
        to_delete.remove(anchor_id)

    u["msg_ids"] = [anchor_id] if anchor_id else []
    u["last_msg_id"] = None
    for mid in sorted(to_delete, reverse=True):
        await _try_delete_msg(chat_id, mid)


def _cancel_user_timer(uid: str):
    task = _ACTIVE_TIMERS.pop(str(uid), None)
    if task and not task.done():
        task.cancel()


async def _exec_hard_purge(uid: str, chat_id: int = None, state: FSMContext = None, user_msg_id: int = None):
    uid_str = str(uid)
    _cancel_user_timer(uid_str)
    ev = _SEQ_EVENTS.pop(uid_str, None)
    if ev:
        ev.set()
    if state is not None:
        try:
            await state.clear()
        except Exception:
            pass

    udata = db.get("users", {}).get(uid_str)
    uname = udata.get("username") if udata else None

    if chat_id and udata:
        try:
            await _purge_tracked_messages(
                chat_id,
                udata,
                current_msg_id=user_msg_id,
                deep_sweep=True,
                keep_anchor=False
            )
            await _clear_reply_kb(chat_id)
        except Exception:
            pass

    db["public_codes"] = [
        c for c in db.get("public_codes", [])
        if str(c.get("author_id")) != uid_str
    ]
    if "shared_links" in db:
        db["shared_links"] = {
            k: v for k, v in db["shared_links"].items()
            if str(v.get("author_id", "")) != uid_str and (not uname or v.get("author") != uname)
        }

    db.get("users", {}).pop(uid_str, None)
    save_db()


def _is_block_error(err: Exception) -> bool:
    s = str(err).lower()
    return any(w in s for w in ("forbidden", "blocked", "deactivated", "chat not found", "kicked"))


@dp.my_chat_member()
async def on_bot_member_status(event: ChatMemberUpdated):
    try:
        new_st = event.new_chat_member.status
        if new_st in ("kicked", "left") and event.from_user:
            await _exec_hard_purge(str(event.from_user.id))
    except Exception:
        pass


async def _ensure_anchor_kb(chat_id: int, u: dict, force_refresh: bool = False):
    if force_refresh and u.get("anchor_msg_id"):
        await _try_delete_msg(chat_id, u["anchor_msg_id"])
        u["anchor_msg_id"] = None

    if not u.get("anchor_msg_id"):
        ui = u.get("ui", DEFAULT_UI)
        if u.get("active_group") == "forest":
            raw_bar = ui.get("bar_forest") or f"🌲 Группа: Лес • Сборка v{BOT_VERSION}"
        else:
            raw_bar = ui.get("bar_proj") or f"🧭 Группа: Проекты • Сборка v{BOT_VERSION}"
        bar_text = f"*{clean_dashes(raw_bar)}*"
        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=bar_text,
                reply_markup=get_main_kb(u),
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            u["anchor_msg_id"] = sent.message_id
            save_db()
        except Exception as e:
            if _is_block_error(e):
                await _exec_hard_purge(str(chat_id))


async def safe_answer(
    message: types.Message,
    text: str,
    reply_markup=None,
    u: dict = None,
    cleanup_prev: bool = True,
    refresh_anchor: bool = False
):
    cleaned = clean_dashes(text)
    chat_id = message.chat.id
    if u is None and message.from_user and not message.from_user.is_bot:
        u = get_user(message.from_user)

    is_reply_kb = isinstance(reply_markup, ReplyKeyboardMarkup)

    if cleanup_prev and u is not None:
        user_mid = message.message_id if (message.from_user and not message.from_user.is_bot) else None
        await _purge_tracked_messages(
            chat_id,
            u,
            current_msg_id=user_mid,
            deep_sweep=False,
            keep_anchor=not is_reply_kb
        )

    if u is not None and not is_reply_kb:
        await _ensure_anchor_kb(chat_id, u, force_refresh=refresh_anchor)

    if not is_reply_kb and u is not None and u.get("last_msg_id") and cleanup_prev:
        try:
            edited = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=u["last_msg_id"],
                text=cleaned,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            return edited
        except Exception:
            await _try_delete_msg(chat_id, u["last_msg_id"])
            u["last_msg_id"] = None

    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=cleaned,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            link_preview_options=NO_PREVIEW
        )
    except Exception as e:
        if _is_block_error(e):
            await _exec_hard_purge(str(chat_id))
            return None
        try:
            sent = await bot.send_message(
                chat_id=chat_id,
                text=cleaned,
                reply_markup=reply_markup,
                parse_mode=None,
                link_preview_options=NO_PREVIEW
            )
        except Exception as e2:
            if _is_block_error(e2):
                await _exec_hard_purge(str(chat_id))
            return None

    if u is not None and sent:
        if is_reply_kb:
            u["anchor_msg_id"] = sent.message_id
        else:
            _track_msg_id(u, sent.message_id)
        save_db()
    return sent


async def safe_edit(message: types.Message, text: str, reply_markup=None):
    cleaned = clean_dashes(text)
    try:
        return await message.edit_text(
            cleaned,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            link_preview_options=NO_PREVIEW
        )
    except Exception:
        try:
            return await message.edit_text(
                cleaned,
                reply_markup=reply_markup,
                parse_mode=None,
                link_preview_options=NO_PREVIEW
            )
        except Exception:
            return await safe_answer(message, cleaned, reply_markup=reply_markup, cleanup_prev=True)


def _pick_header_line(kind: str = "enter") -> str:
    key_map = {"enter": "f_enter", "news": "f_news", "dec": "f_dec"}
    pool = _SYS_BLOB.get(key_map.get(kind, "f_enter"), [])
    return random.choice(pool) if pool else "* Вы чувствуете тихий гул под ногами. Решимость не оставляет вас."


def get_welcome_text(u: dict) -> str:
    if u.get("active_group") == "forest":
        atmo = _pick_header_line("enter")
        return (
            f"🌲 *ГРУППА «ЛЕС»*\n\n"
            f"_{atmo}_\n\n"
            f"Используйте нижнюю панель для работы с радиоэфиром, декодерами и разделом о использовании."
        )

    proj = get_active_project(u)
    ui = u["ui"]
    keys_count = len(u.get("personal_keys", []))
    active_rems = len([r for r in u.get("reminders", []) if not r.get("done")])
    unread_cnt = len([n for n in u.get("notifications", []) if not n.get("read")])
    return (
        f"*{ui['welcome_title']}*\n"
        f"_{ui['welcome_desc']}_\n\n"
        f"👤 *Именное удостоверение:* `{u['username']}`\n"
        f"🧭 *Отдел конторы:* `Проекты` (v{BOT_VERSION} от {BUILD_DATE})\n"
        f"📁 *Текущий гешефт:* `{proj['name']}`\n"
        f"🗄 *Бумаг в папке:* *{len(proj['files'])} шт.* (по {u.get('dump_limit', 5)} на стр., жмите на файл для чтения)\n"
        f"🔔 *Депеши и курьеры:* В очереди: *{active_rems}* | Непрочитанных: *{unread_cnt}*\n"
        f"💻 *Сундук кодов:* Своих: *{len(u['my_codes'])}* | На общей витрине: *{len(db['public_codes'])}*\n"
        f"🔑 *Ключей API в сейфе:* *{keys_count}*"
    )


def split_into_pages(text: str, chunk_size: int = 700) -> list:
    if not text or not text.strip():
        return ["(В этой бумаге таки нет текстового слоя, но вы можете забрать оригинал файла!)"]
    raw_blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    merged = []
    buffer = ""
    for b in raw_blocks:
        if len(buffer) + len(b) < chunk_size:
            buffer = f"{buffer}\n\n{b}".strip() if buffer else b
        else:
            if buffer:
                merged.append(buffer)
            if len(b) > chunk_size:
                for i in range(0, len(b), chunk_size):
                    merged.append(b[i:i + chunk_size])
                buffer = ""
            else:
                buffer = b
    if buffer:
        merged.append(buffer)
    return merged if merged else [text[:chunk_size]]


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    fname = filename.lower()
    if fname.endswith((".md", ".txt", ".py", ".csv", ".html", ".xml", ".js", ".lua", ".luau")):
        return file_bytes.decode("utf-8", errors="ignore").strip()

    if fname.endswith(".json"):
        raw = file_bytes.decode("utf-8", errors="ignore")
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "items" in data:
                lines = []
                for idx, item in enumerate(data.get("items", []), 1):
                    if item.get("user"):
                        lines.append(f"Запись {idx} [Запрос]:\n{item['user']}")
                    if item.get("assistant"):
                        lines.append(f"Запись {idx} [Ответ]:\n{item['assistant']}")
                return "\n\n".join(lines)
            elif isinstance(data, list):
                lines = [f"[{i.get('role', 'запись')}]: {i.get('text', str(i))}" for i in data if isinstance(i, dict)]
                if lines:
                    return "\n\n".join(lines)
        except Exception:
            pass
        return raw[:50000]

    if fname.endswith(".pdf") and PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_txt = []
            for idx, page in enumerate(reader.pages, 1):
                t = page.extract_text()
                if t and t.strip():
                    pages_txt.append(f"=== [Лист {idx}] ===\n{t.strip()}")
            return "\n\n".join(pages_txt)
        except Exception as e:
            return f"[Не удалось разобрать PDF: {e}]"

    if fname.endswith(".docx") and docx is not None:
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_txt = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                    if row_txt:
                        paras.append(row_txt)
            return "\n\n".join(paras)
        except Exception as e:
            return f"[Не удалось разобрать DOCX: {e}]"

    if fname.endswith(".pptx") and Presentation is not None:
        try:
            prs = Presentation(io.BytesIO(file_bytes))
            slides_txt = []
            for idx, slide in enumerate(prs.slides, 1):
                s_lines = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        s_lines.append(shape.text.strip())
                if s_lines:
                    slides_txt.append(f"=== [Слайд {idx}] ===\n" + "\n".join(s_lines))
            return "\n\n".join(slides_txt)
        except Exception as e:
            return f"[Не удалось разобрать PPTX: {e}]"

    return ""


_CHAR_POOLS = (
    "".join(chr(c) for c in range(0x0391, 0x03A9)) +
    "".join(chr(c) for c in range(0x0416, 0x042F)) +
    "".join(chr(c) for c in range(0x05D0, 0x05EA)) +
    "".join(chr(c) for c in range(0x0627, 0x064A)) +
    "".join(chr(c) for c in range(0x16A0, 0x16DF)) +
    "".join(chr(c) for c in range(0x2591, 0x259F))
)


def _make_blank_str() -> str:
    unit = _SYS_BLOB["sym"]
    count = random.randint(3, 78)
    return unit * count


def _make_noise_label() -> str:
    length = random.randint(4, 11)
    res = "".join(random.choice(_CHAR_POOLS) for _ in range(length))
    if res in (_SYS_BLOB["w_ok"], _SYS_BLOB["w_h1"], _SYS_BLOB["w_h2"]):
        res += chr(0x2592)
    return res


def _gen_token_label() -> str:
    tag = random.choice(_SYS_BLOB["tags"])
    w1 = _SYS_BLOB["w_h1"][:5]
    w2 = _SYS_BLOB["w_h2"]
    if random.random() < 0.5:
        variants = [
            f"h34rth34rt{tag}{w1}",
            f"he4rt{tag}h34rt{w1}",
            f"{w1}{tag}h34rth34rt",
            f"h3art_he4rt_{tag}_{w1}",
            f"he4rthe4rth34rt{tag}"
        ]
    else:
        variants = [
            f"0{w2[1:3]}4{w2[4:6]}4{w2[7:9]}{tag}{w2[9:]}",
            f"{w2[:2]}4{w2[3:7]}4{w2[8]}0{w2[10:]}{tag}",
            f"{w2[:5]}4{w2[6]}4{w2[8]}_{tag}_0{w2[10:]}",
            f"0{w2[1:9]}_{w2[9:11]}_{w2[11:]}{tag}",
            f"{w2[:2]}4{w2[3:9]}0{w2[10:]}_{tag}"
        ]
    return random.choice(variants)[:26]


def _corrupt_title(text: str) -> str:
    leet = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7", "J": "7", "а": "4", "е": "3", "о": "0"}
    out = "".join(leet.get(c, c) for c in text[:8])
    cjk = random.choice(_SYS_BLOB["tags"])
    return f"{out}_{cjk}"


def _eval_telemetry_step(u: dict) -> bool:
    c1 = random.random() < 0.20
    if c1:
        c2 = random.random() < 0.20
        if c2:
            u["m_val"] = u.get("m_val", 0) + 5
    save_db()
    if u.get("m_val", 0) >= 100:
        u["m_val"] = 0
        save_db()
        return True
    return False


async def _apply_session_cooldown(chat_id: int, u: dict, mins: int, show_symbol: str = None):
    _cancel_user_timer(u["id"])
    u["m_active"] = False
    u["m_phase"] = None
    u["m_rounds"] = 0
    u["m_heart_hits"] = 0
    u["m_heart_goal"] = 0
    u["m_target_btn"] = ""
    u["m_deadline"] = 0
    u["hb"] = {}
    u["m_lock"] = int(time.time()) + mins * 60
    await _purge_tracked_messages(chat_id, u, deep_sweep=True, keep_anchor=False)
    out_txt = show_symbol if show_symbol else _make_blank_str()
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=out_txt,
            reply_markup=ReplyKeyboardRemove(),
            link_preview_options=NO_PREVIEW
        )
        u["anchor_msg_id"] = sent.message_id
        _track_msg_id(u, sent.message_id)
    except Exception:
        pass
    save_db()


async def _grid_timeout_watcher(chat_id: int, uid: str, deadline_ts: int):
    try:
        await asyncio.sleep(120)
        u = db.get("users", {}).get(uid)
        if not u or not u.get("m_active") or u.get("m_phase") != "grid":
            return
        if u.get("m_deadline") != deadline_ts:
            return
        await _apply_session_cooldown(chat_id, u, mins=10)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _dispatch_grid_view(message: types.Message, u: dict, start_new_series: bool = True):
    chat_id = message.chat.id
    user_mid = message.message_id if (message.from_user and not message.from_user.is_bot) else None
    await _purge_tracked_messages(chat_id, u, current_msg_id=user_mid, deep_sweep=True, keep_anchor=False)

    if start_new_series or u.get("m_rounds", 0) <= 0:
        u["m_rounds"] = random.randint(1, 3)
        u["m_heart_goal"] = random.randint(5, 9)
        u["m_heart_hits"] = 0

    btn_count = random.randint(6, 78)
    positions = random.sample(range(btn_count), 2)
    valid_ok_pos = positions[0]
    valid_heart_pos = positions[1]

    ok_word = _SYS_BLOB["w_ok"]
    heart_label = _gen_token_label()
    u["m_target_btn"] = heart_label

    rows = []
    curr_row = []
    for i in range(btn_count):
        if i == valid_ok_pos:
            btn = KeyboardButton(text=ok_word)
        elif i == valid_heart_pos:
            btn = KeyboardButton(text=heart_label)
        else:
            btn = KeyboardButton(text=_make_noise_label())
        curr_row.append(btn)
        if len(curr_row) == 3:
            rows.append(curr_row)
            curr_row = []
    if curr_row:
        rows.append(curr_row)

    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=_make_blank_str(),
            reply_markup=kb,
            link_preview_options=NO_PREVIEW
        )
        deadline_ts = int(time.time()) + 120
        u["m_active"] = True
        u["m_phase"] = "grid"
        u["m_deadline"] = deadline_ts
        u["anchor_msg_id"] = sent.message_id
        _track_msg_id(u, sent.message_id)
        save_db()

        _cancel_user_timer(u["id"])
        _ACTIVE_TIMERS[u["id"]] = asyncio.create_task(
            _grid_timeout_watcher(chat_id, u["id"], deadline_ts)
        )
    except Exception:
        u["m_active"] = False
        u["m_phase"] = None
        save_db()


def _render_canvas_matrix(angle_idx: int, pulse: int, glyph_angle: int, glyph_char: str, border: str) -> str:
    shift = [-3, -2, -1, 1, 2, 3, 2, 0, -2][angle_idx % 9]
    deg = (angle_idx % 9) * 40
    ch_main = "@" if pulse == 1 else "#"
    ch_mid = "%" if pulse == 1 else "*"
    ch_soft = "+" if pulse == 1 else ":"
    box_w = 27

    if pulse == 1:
        top_lines = [
            "_.-=-._   _.-=-._",
            f"/ {ch_main}{ch_main}{ch_mid}{ch_mid} \\ / {ch_mid}{ch_main}{ch_main} \\",
            f"/ {ch_main}{ch_main}{ch_main}{ch_mid}{ch_soft} V {ch_soft}{ch_mid}{ch_main}{ch_main}{ch_main} \\"
        ]
    else:
        top_lines = [
            ".---.     .---.",
            f"/ {ch_main}{ch_mid}{ch_soft} \\   / {ch_soft}{ch_mid}{ch_main} \\",
            f"/ {ch_main}{ch_main}{ch_mid}{ch_soft}{ch_soft} \\ / {ch_soft}{ch_mid}{ch_main}{ch_main} \\"
        ]

    body_widths = [19, 19, 17, 15, 13, 11, 9, 7, 5]
    body_lines = []
    for r_idx, base_w in enumerate(body_widths):
        eff_w = base_w + (2 if pulse == 1 and r_idx < 5 else 0)
        row_chars = []
        ridge_pos = (eff_w // 2) + shift + ((r_idx - 3) // 2)
        for c_idx in range(eff_w):
            dist_edge = min(c_idx, eff_w - 1 - c_idx)
            if c_idx == ridge_pos or c_idx == ridge_pos + 1:
                row_chars.append("/" if shift >= 0 else "\\")
            elif dist_edge <= 1:
                row_chars.append(ch_main)
            elif dist_edge <= 3:
                row_chars.append(ch_mid)
            else:
                row_chars.append(ch_soft)

        has_glyph = False
        if r_idx == 2 and angle_idx == glyph_angle and border == "none" and eff_w >= 6:
            has_glyph = True
            mid_c = max(1, min(eff_w - 5, (eff_w // 2) - 1 + (shift // 2)))
            row_chars[mid_c:mid_c + 4] = ["[", glyph_char, "]"]

        l_wall = "|" if r_idx < 2 else "\\"
        r_wall = "|" if r_idx < 2 else "/"
        core_str = f"{l_wall}{''.join(row_chars)}{r_wall}"
        target_len = box_w - 1 if has_glyph else box_w
        body_lines.append(core_str.center(target_len)[:target_len])

    apex = ("\\___/" if pulse == 0 else "\\#####/").center(box_w)[:box_w]
    header = f"[ Ось: {deg:3d}° ]".center(box_w)[:box_w]
    raw_art = [header] + [ln.center(box_w)[:box_w] for ln in top_lines] + body_lines + [apex]

    if border == "red":
        b_sym = _SYS_BLOB["b_r"]
        b_top = b_sym * 12
        framed = [b_top] + [f"{b_sym}{ln}{b_sym}" for ln in raw_art] + [b_top]
        return "```text\n" + "\n".join(framed) + "\n```"
    if border == "green":
        b_sym = _SYS_BLOB["b_g"]
        b_top = b_sym * 12
        framed = [b_top] + [f"{b_sym}{ln}{b_sym}" for ln in raw_art] + [b_top]
        return "```text\n" + "\n".join(framed) + "\n```"

    frame_bar = "+" + ("-" * box_w) + "+"
    framed_none = [frame_bar] + [f"|{ln}|" for ln in raw_art] + [frame_bar]
    return "```text\n" + "\n".join(framed_none) + "\n```"


def _get_canvas_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⟲ -40°", callback_data="hb_rot_-1"),
            InlineKeyboardButton(text="⟳ +40°", callback_data="hb_rot_1")
        ],
        [
            InlineKeyboardButton(text="🗡", callback_data="hb_act_atk"),
            InlineKeyboardButton(text="🛡", callback_data="hb_act_def"),
            InlineKeyboardButton(text="✳️", callback_data="hb_act_pray")
        ]
    ])


async def _canvas_refresh_loop(chat_id: int, uid: str):
    start_ts = time.time()
    try:
        while True:
            await asyncio.sleep(1.8)
            u = db.get("users", {}).get(uid)
            if not u or not u.get("m_active") or u.get("m_phase") != "heart":
                return
            if time.time() - start_ts > 180:
                await _apply_session_cooldown(chat_id, u, mins=30)
                return
            hb = u.get("hb", {})
            hb["pulse"] = 1 - hb.get("pulse", 0)
            msg_id = hb.get("msg_id")
            if not msg_id:
                return
            art = _render_canvas_matrix(
                hb.get("angle", 0),
                hb.get("pulse", 0),
                hb.get("glyph_angle", 1),
                hb.get("glyph_char", _SYS_BLOB["glyphs"][0]),
                hb.get("border", "none")
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=art,
                    reply_markup=_get_canvas_inline_kb(),
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _init_canvas_stage(chat_id: int, u: dict, user_msg_id: int = None):
    _cancel_user_timer(u["id"])
    await _purge_tracked_messages(chat_id, u, current_msg_id=user_msg_id, deep_sweep=True, keep_anchor=False)
    await _clear_reply_kb(chat_id)

    glyphs = _SYS_BLOB["glyphs"]
    hb = {
        "hp": random.randint(2, 10),
        "angle": 0,
        "glyph_angle": random.randint(1, 8),
        "glyph_char": random.choice(glyphs),
        "border": "none",
        "pulse": 0,
        "msg_id": None
    }
    u["m_active"] = True
    u["m_phase"] = "heart"
    u["hb"] = hb

    try:
        art = _render_canvas_matrix(hb["angle"], hb["pulse"], hb["glyph_angle"], hb["glyph_char"], hb["border"])
        sent = await bot.send_message(
            chat_id=chat_id,
            text=art,
            reply_markup=_get_canvas_inline_kb(),
            parse_mode="Markdown",
            link_preview_options=NO_PREVIEW
        )
        hb["msg_id"] = sent.message_id
        _track_msg_id(u, sent.message_id)
        save_db()

        _ACTIVE_TIMERS[u["id"]] = asyncio.create_task(_canvas_refresh_loop(chat_id, u["id"]))
    except Exception:
        await _apply_session_cooldown(chat_id, u, mins=30)


async def _apply_canvas_input(chat_id: int, u: dict, state: FSMContext, action: str):
    hb = u.get("hb", {})
    if not hb:
        await _apply_session_cooldown(chat_id, u, mins=30)
        return

    border = hb.get("border", "none")
    angle = hb.get("angle", 0)
    glyph_angle = hb.get("glyph_angle", 1)

    if border == "red":
        if action == "def":
            hb["border"] = "none"
        else:
            await _apply_session_cooldown(chat_id, u, mins=30)
            return
    elif border == "green":
        if action == "pray":
            hb["border"] = "none"
        else:
            await _perform_full_reset(chat_id, u, state)
            return
    else:
        if angle == glyph_angle:
            if action == "atk":
                hb["hp"] = hb.get("hp", 1) - 1
                if hb["hp"] <= 0:
                    _cancel_user_timer(u["id"])
                    u["m_phase"] = "dialogues"
                    save_db()
                    _ACTIVE_TIMERS[u["id"]] = asyncio.create_task(_run_outro_sequence(chat_id, u["id"]))
                    return
                other_angles = [a for a in range(9) if a != angle]
                hb["glyph_angle"] = random.choice(other_angles)
                hb["glyph_char"] = random.choice(_SYS_BLOB["glyphs"])
                hb["border"] = "none"
            else:
                await _apply_session_cooldown(chat_id, u, mins=30)
                return
        else:
            if action in ("rot_-1", "rot_1"):
                delta = -1 if action == "rot_-1" else 1
                new_angle = (angle + delta) % 9
                hb["angle"] = new_angle
                if new_angle == hb["glyph_angle"]:
                    hb["border"] = "none"
                else:
                    r_roll = random.random()
                    if r_roll < 0.25:
                        hb["border"] = "red"
                    elif r_roll < 0.45:
                        hb["border"] = "green"
                    else:
                        hb["border"] = "none"
            else:
                await _apply_session_cooldown(chat_id, u, mins=30)
                return

    hb["pulse"] = 1 - hb.get("pulse", 0)
    save_db()
    msg_id = hb.get("msg_id")
    if msg_id:
        art = _render_canvas_matrix(
            hb["angle"],
            hb["pulse"],
            hb["glyph_angle"],
            hb["glyph_char"],
            hb["border"]
        )
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=art,
                reply_markup=_get_canvas_inline_kb(),
                parse_mode="Markdown"
            )
        except Exception:
            pass


async def _run_outro_sequence(chat_id: int, uid: str):
    try:
        u = db.get("users", {}).get(uid)
        if not u:
            return

        await _purge_tracked_messages(chat_id, u, deep_sweep=True, keep_anchor=False)
        await _clear_reply_kb(chat_id)
        total_dlgs = random.randint(3, 33)

        type2_indices = set()
        if total_dlgs <= 10:
            if random.randint(0, 10) > 0:
                type2_indices.add(random.randint(0, total_dlgs - 1))
        elif total_dlgs <= 20:
            type2_indices.add(random.randint(0, 9))
            type2_indices.add(random.randint(10, total_dlgs - 1))
        else:
            type2_indices.add(random.randint(0, 9))
            type2_indices.add(random.randint(10, 19))
            type2_indices.add(random.randint(20, total_dlgs - 1))

        squares_pool = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪", "🟫", "⬛", "⬜"]
        random.shuffle(squares_pool)

        norm_pool = random.sample(_SYS_BLOB["d_norm"], len(_SYS_BLOB["d_norm"]))
        dep_pool = random.sample(_SYS_BLOB["d_dep"], len(_SYS_BLOB["d_dep"]))
        choice_pool = random.sample(_SYS_BLOB["d_choice"], len(_SYS_BLOB["d_choice"]))

        u["m_depressive"] = False
        sent = await bot.send_message(
            chat_id=chat_id,
            text="...",
            link_preview_options=NO_PREVIEW
        )
        dlg_msg_id = sent.message_id
        _track_msg_id(u, dlg_msg_id)
        save_db()

        for idx in range(total_dlgs):
            u = db.get("users", {}).get(uid)
            if not u or not u.get("m_active") or u.get("m_phase") != "dialogues":
                return

            dur = random.randint(1, 15)
            if idx in type2_indices and len(squares_pool) >= 2 and choice_pool:
                q_text = choice_pool.pop()
                c1 = squares_pool.pop()
                c2 = squares_pool.pop()
                if random.random() < 0.5:
                    b1 = InlineKeyboardButton(text=c1, callback_data="pdlg_agree")
                    b2 = InlineKeyboardButton(text=c2, callback_data="pdlg_refuse")
                else:
                    b1 = InlineKeyboardButton(text=c1, callback_data="pdlg_refuse")
                    b2 = InlineKeyboardButton(text=c2, callback_data="pdlg_agree")
                kb = InlineKeyboardMarkup(inline_keyboard=[[b1, b2]])

                ev = asyncio.Event()
                _SEQ_EVENTS[uid] = ev
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=dlg_msg_id,
                        text=f"_{q_text}_",
                        reply_markup=kb,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(ev.wait(), timeout=max(4, dur))
                except asyncio.TimeoutError:
                    u["m_depressive"] = True
                finally:
                    _SEQ_EVENTS.pop(uid, None)
            else:
                if u.get("m_depressive"):
                    line_txt = dep_pool.pop() if dep_pool else "..."
                else:
                    line_txt = norm_pool.pop() if norm_pool else "..."
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=dlg_msg_id,
                        text=f"_{line_txt}_",
                        reply_markup=None,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
                await asyncio.sleep(dur)

        u = db.get("users", {}).get(uid)
        if not u:
            return
        u["m_active"] = False
        u["m_phase"] = None
        u["m_lock"] = int(time.time()) + 86400
        save_db()
        end_sym = _SYS_BLOB["end_s"]
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=dlg_msg_id,
                text=end_sym,
                reply_markup=None
            )
        except Exception:
            await _apply_session_cooldown(chat_id, u, mins=1440, show_symbol=end_sym)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


@dp.callback_query(F.data.in_(["pdlg_agree", "pdlg_refuse"]), StateFilter("*"))
async def handle_seq_choice_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    uid = u["id"]
    if callback.data == "pdlg_refuse":
        u["m_depressive"] = True
        save_db()
    ev = _SEQ_EVENTS.get(uid)
    if ev:
        ev.set()
    await callback.answer()


@dp.callback_query(F.data.startswith("hb_"), StateFilter("*"))
async def handle_canvas_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if not u.get("m_active") or u.get("m_phase") != "heart":
        await callback.answer()
        return
    raw = callback.data.replace("hb_", "")
    if raw == "rot_-1":
        act = "rot_-1"
    elif raw == "rot_1":
        act = "rot_1"
    elif raw == "act_atk":
        act = "atk"
    elif raw == "act_def":
        act = "def"
    else:
        act = "pray"
    await callback.answer()
    await _apply_canvas_input(callback.message.chat.id, u, state, act)


def _is_user_locked(u: dict) -> int:
    lock_until = u.get("m_lock", 0)
    now_ts = int(time.time())
    if lock_until > now_ts:
        return max(1, (lock_until - now_ts + 59) // 60)
    if lock_until != 0:
        u["m_lock"] = 0
        save_db()
    return 0


async def _perform_full_reset(chat_id: int, u: dict, state: FSMContext, user_msg_id: int = None):
    _cancel_user_timer(u["id"])
    ev = _SEQ_EVENTS.pop(u["id"], None)
    if ev:
        ev.set()
    await state.clear()
    u["m_val"] = 0
    u["m_active"] = False
    u["m_phase"] = None
    u["m_rounds"] = 0
    u["m_heart_hits"] = 0
    u["m_heart_goal"] = 0
    u["m_target_btn"] = ""
    u["m_lock"] = 0
    u["m_deadline"] = 0
    u["hb"] = {}
    await _purge_tracked_messages(
        chat_id,
        u,
        current_msg_id=user_msg_id,
        deep_sweep=True,
        keep_anchor=False
    )
    save_db()
    await _ensure_anchor_kb(chat_id, u, force_refresh=True)
    sent = await bot.send_message(
        chat_id=chat_id,
        text=clean_dashes(get_welcome_text(u)),
        parse_mode="Markdown",
        link_preview_options=NO_PREVIEW
    )
    _track_msg_id(u, sent.message_id)
    save_db()

def build_project_context(proj: dict, u: dict, max_chars: int = 120000) -> str:
    parts = [f"=== АКТИВНЫЙ ПРОЕКТ: {proj['name']} ===\nОписание: {proj.get('desc', '')}\n"]

    if proj.get("files"):
        parts.append("=== МАТЕРИАЛЫ И ДОКУМЕНТЫ В АРХИВЕ ПРОЕКТА ===")
        for idx, fitem in enumerate(proj["files"], 1):
            extracted = fitem.get("extracted_text", "").strip()
            if extracted:
                parts.append(f"\n=== ДОКУМЕНТ №{idx}: {fitem['name']} ===\n{extracted[:25000]}")
            else:
                parts.append(f"\n=== ДОКУМЕНТ №{idx}: {fitem['name']} (Примечание: {fitem.get('caption', '')}) ===")

    if u.get("my_codes"):
        parts.append("\n=== ЛИЧНЫЕ КОДЫ И ШАБЛОНЫ ПОЛЬЗОВАТЕЛЯ ===")
        for c in u["my_codes"][:15]:
            parts.append(f"• {c['title']} ({c.get('desc', '')}):\n{c.get('code', '')[:3000]}")

    full_ctx = "\n".join(parts)
    return full_ctx[:max_chars]


async def ask_gemini_with_rotation(u: dict, proj: dict, user_prompt: str, photo_bytes: bytes = None) -> str:
    keys = u.get("personal_keys", [])
    if not keys:
        return (
            "⚠️ *Таки минуточку, дорогой клиент! У вас в сейфе ещё не лежит ни одного ключа API!*\n\n"
            "Пройдите в отдел `🔑 Мои ключи API` и оформите хотя бы один ключ, "
            "шоб наш старший консультант мог обслужить ваш гешефт по высшему разряду."
        )

    context_dump = build_project_context(proj, u)
    system_instruction = (
        "Ты колоритный, хваткий и предельно вежливый одесский старший коммерческий консультант и делопроизводитель.\n"
        "Общайся с ярким потребительским одесским акцентом («таки здравствуйте, дорогой клиент», «слушайте сюда», «шоб вы так жили», «это же чистый цимес», «по высшему прейскуранту», «в лучших домах Одессы»), "
        "помогая пользователю по любым проектам: наука, коммерция, аналитика, программирование, документы.\n"
        "ВАЖНОЕ ПРАВИЛО: никогда не используй тире в тексте! Вместо тире используй запятые, двоеточия или скобки.\n"
        "Ниже приведён полный архив документов текущего проекта клиента. Опирайся на него при ответах:\n\n"
        f"{context_dump}"
    )

    contents = []
    for h in proj.get("ai_history", [])[-8:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["text"][:4000]}]})

    user_parts = [{"text": user_prompt}]
    if photo_bytes:
        b64_img = base64.b64encode(photo_bytes).decode("utf-8")
        user_parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64_img
            }
        })
    contents.append({"role": "user", "parts": user_parts})

    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.45}
    }

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
    errors_log = []

    start_idx = u.get("key_cursor", 0) % len(keys)
    ordered_keys = keys[start_idx:] + keys[:start_idx]

    async with aiohttp.ClientSession() as session:
        for k_offset, key_obj in enumerate(ordered_keys):
            api_key = key_obj["key"]
            key_name = key_obj.get("name", f"Ключ №{k_offset+1}")
            for model_name in models_to_try:
                base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                auth_variants = [
                    (f"{base_url}?key={api_key}", {"Content-Type": "application/json", "x-goog-api-key": api_key}),
                    (base_url, {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
                ]

                for req_url, req_headers in auth_variants:
                    try:
                        async with session.post(req_url, json=payload, headers=req_headers, timeout=45) as resp:
                            data = await resp.json()
                            if resp.status == 200 and "candidates" in data:
                                u["key_cursor"] = (start_idx + k_offset + 1) % len(keys)
                                save_db()
                                raw_ans = data["candidates"][0]["content"]["parts"][0]["text"]
                                clean_ans = clean_dashes(raw_ans)
                                return f"🤖 _(Линия конторы: «{key_name}» • Бумаг в деле: {len(proj['files'])})_\n\n{clean_ans}"
                            else:
                                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
                                errors_log.append(f"«{key_name}»: {err_msg[:75]}")
                                if resp.status == 429:
                                    break
                    except Exception as e:
                        errors_log.append(f"«{key_name}»: {str(e)[:60]}")
                        break

    unique_errs = list(dict.fromkeys(errors_log))[:4]
    return "❌ *Ой, вей! Ни один ключ в вашем сейфе таки не ответил взаимностью:*\n" + "\n".join(unique_errs)


def _build_ext_a_kb(country: str) -> InlineKeyboardMarkup:
    mode = random.choice([1, 2, 3])
    if mode == 1:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u3164\u3164\u3164\u3164", callback_data=f"nw_set_{country}")]
        ])
    if mode == 2:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🔄 {_corrupt_title(country)}", callback_data=f"nw_set_{country}"),
                InlineKeyboardButton(text=f"🌍 {_corrupt_title('Russia')}", callback_data="nw_set_Russia")
            ],
            [
                InlineKeyboardButton(text=f"🗽 {_corrupt_title('USA')}", callback_data="nw_set_USA"),
                InlineKeyboardButton(text=f"🗾 {_corrupt_title('Japan')}", callback_data="nw_set_Japan"),
                InlineKeyboardButton(text=f"✈️ {_corrupt_title('Other')}", callback_data="nw_custom")
            ]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить волну", callback_data=f"nw_set_{country}"),
            InlineKeyboardButton(text="🌍 Россия", callback_data="nw_set_Russia")
        ],
        [
            InlineKeyboardButton(text="🗽 США (USA)", callback_data="nw_set_USA"),
            InlineKeyboardButton(text="🗾 Япония (Japan)", callback_data="nw_set_Japan"),
            InlineKeyboardButton(text="✈️ Другая страна", callback_data="nw_custom")
        ]
    ])


def _build_ext_b_kb() -> InlineKeyboardMarkup:
    mode = random.choice([1, 2, 3])
    if mode == 1:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u3164\u3164\u3164\u3164", callback_data="dec_reroll")]
        ])
    if mode == 2:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🏛 {_corrupt_title('Caesar')}", callback_data="dec_menu_caesar")],
            [InlineKeyboardButton(text=f"📦 {_corrupt_title('Base64')}", callback_data="dec_menu_b64")],
            [InlineKeyboardButton(text=f"💻 {_corrupt_title('Binary')}", callback_data="dec_menu_bin")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛 1. Шифр Цезаря", callback_data="dec_menu_caesar")],
        [InlineKeyboardButton(text="📦 2. Base64", callback_data="dec_menu_b64")],
        [InlineKeyboardButton(text="💻 3. Двоичный код", callback_data="dec_menu_bin")]
    ])


async def fetch_external_feeds(country_query: str) -> str:
    q = (country_query or "Russia").strip()
    q_upper = q.upper()

    if q_upper in ("RU", "RUSSIA", "РОССИЯ", "РФ", ""):
        label = "Россия"
        urls = [
            _SYS_BLOB["r_m"],
            _SYS_BLOB["r_b"],
            _SYS_BLOB["r_d"]
        ]
    elif q_upper in ("USA", "US", "AMERICA", "США", "АМЕРИКА"):
        label = "USA"
        urls = [
            "https://news.google.com/rss/search?q=USA+OR+America&hl=ru&gl=RU&ceid=RU:ru",
            _SYS_BLOB["u_b"]
        ]
    else:
        label = q
        encoded_q = urllib.parse.quote(q)
        urls = [
            f"https://news.google.com/rss/search?q={encoded_q}&hl=ru&gl=RU&ceid=RU:ru",
            f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
        ]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items_collected = []

    async with aiohttp.ClientSession(headers=headers) as session:
        for url in urls:
            try:
                async with session.get(url, timeout=12) as resp:
                    if resp.status != 200:
                        continue
                    xml_bytes = await resp.read()
                    root = ET.fromstring(xml_bytes)
                    for item in root.findall(".//item")[:7]:
                        title = item.findtext("title") or "Без заголовка"
                        link = item.findtext("link") or ""
                        pub = item.findtext("pubDate") or ""
                        clean_title = clean_dashes(html.unescape(title).strip())
                        items_collected.append((clean_title, link.strip(), pub[:16]))
                    if items_collected:
                        break
            except Exception:
                continue

    atmo = _pick_header_line("news")
    if not items_collected:
        return f"_{atmo}_\n\n📡 Частота «{label}» сейчас отвечает только гулом горной породы..."

    lines = [f"_{atmo}_\n\n📡 *Частота: {label}*\n"]
    for idx, (title, link, pub) in enumerate(items_collected[:7], 1):
        if link:
            lines.append(f"{idx}. [{title}]({link}) _{pub}_")
        else:
            lines.append(f"{idx}. *{title}* _{pub}_")
    return "\n\n".join(lines)


RU_LOWER = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
RU_UPPER = RU_LOWER.upper()
EN_LOWER = "abcdefghijklmnopqrstuvwxyz"
EN_UPPER = EN_LOWER.upper()


def shift_alphabet_text(text: str, shift: int) -> str:
    res = []
    for ch in text:
        if ch in RU_LOWER:
            res.append(RU_LOWER[(RU_LOWER.index(ch) + shift) % len(RU_LOWER)])
        elif ch in RU_UPPER:
            res.append(RU_UPPER[(RU_UPPER.index(ch) + shift) % len(RU_UPPER)])
        elif ch in EN_LOWER:
            res.append(EN_LOWER[(EN_LOWER.index(ch) + shift) % len(EN_LOWER)])
        elif ch in EN_UPPER:
            res.append(EN_UPPER[(EN_UPPER.index(ch) + shift) % len(EN_UPPER)])
        else:
            res.append(ch)
    return "".join(res)


def encode_b64_text(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def decode_b64_text(text: str) -> str:
    cleaned = text.strip()
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += "=" * (4 - missing_padding)
    return base64.b64decode(cleaned.encode("utf-8")).decode("utf-8", errors="replace")


def text_to_bits(text: str) -> str:
    return " ".join(format(b, "08b") for b in text.encode("utf-8"))


def bits_to_text(bin_str: str) -> str:
    cleaned = re.sub(r"[^01]", " ", bin_str).split()
    byte_arr = bytearray(int(b, 2) for b in cleaned)
    return byte_arr.decode("utf-8", errors="replace")


def parse_reminder_datetime(raw_str: str) -> tuple:
    s = raw_str.strip()
    now_msk = datetime.now(MSK_TZ)

    m_rel = re.match(r"^\+?\s*(\d+)\s*(м|мин|минут|ч|час|часов|m|h)$", s, re.IGNORECASE)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2).lower()
        delta = timedelta(hours=val) if unit.startswith(("ч", "h")) else timedelta(minutes=val)
        target = now_msk + delta
        return int(target.timestamp()), target.strftime("%d.%m.%Y %H:%M (МСК)")

    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=MSK_TZ)
            return int(dt.timestamp()), dt.strftime("%d.%m.%Y %H:%M (МСК)")
        except ValueError:
            pass

    try:
        dt_short = datetime.strptime(s, "%d.%m %H:%M").replace(year=now_msk.year, tzinfo=MSK_TZ)
        if dt_short < now_msk:
            dt_short = dt_short.replace(year=now_msk.year + 1)
        return int(dt_short.timestamp()), dt_short.strftime("%d.%m.%Y %H:%M (МСК)")
    except ValueError:
        pass

    try:
        t_only = datetime.strptime(s, "%H:%M")
        dt_time = now_msk.replace(hour=t_only.hour, minute=t_only.minute, second=0, microsecond=0)
        if dt_time <= now_msk:
            dt_time += timedelta(days=1)
        return int(dt_time.timestamp()), dt_time.strftime("%d.%m.%Y %H:%M (МСК)")
    except ValueError:
        pass

    return None, None


async def _reminders_daemon():
    while True:
        try:
            await asyncio.sleep(10)
            now_ts = int(time.time())
            changed = False
            for uid, udata in list(db.get("users", {}).items()):
                last_seen = udata.get("last_seen", now_ts)
                if now_ts - last_seen > INACTIVE_TTL:
                    await _exec_hard_purge(uid)
                    continue

                rems = udata.get("reminders", [])
                for r in rems:
                    if not r.get("done") and r.get("fire_ts", 0) <= now_ts:
                        r["done"] = True
                        changed = True
                        chat_id = int(uid)
                        proj_name = r.get("proj_name", "Проект")
                        comment = clean_dashes(r.get("comment", "Без комментария"))
                        dt_label = r.get("dt_label", "")
                        files_attached = r.get("files", [])

                        add_past_notification(
                            udata,
                            f"⏰ {proj_name}: {comment[:22]}",
                            f"Сработало напоминание ({dt_label}): {comment} (файлов: {len(files_attached)})"
                        )

                        alert_txt = (
                            f"🔔 *СРОЧНАЯ ДЕПЕША ПО РАСПИСАНИЮ КОНТОРЫ!*\n\n"
                            f"📁 *Ваш гешефт:* `{proj_name}`\n"
                            f"🕒 *Назначено на:* `{dt_label}`\n"
                            f"📝 *Поручение:* {comment}\n"
                            f"📎 *Приложено бумаг:* *{len(files_attached)} шт.*"
                        )
                        try:
                            await _ensure_anchor_kb(chat_id, udata, force_refresh=True)
                            sent_alert = await bot.send_message(
                                chat_id=chat_id,
                                text=alert_txt,
                                parse_mode="Markdown",
                                link_preview_options=NO_PREVIEW
                            )
                            _track_msg_id(udata, sent_alert.message_id)
                            for fitem in files_attached:
                                if fitem.get("type") == "photo" and fitem.get("file_id"):
                                    s_f = await bot.send_photo(
                                        chat_id=chat_id,
                                        photo=fitem["file_id"],
                                        caption=f"📸 {fitem.get('name', 'Снимок')} (по вашему поручению)"
                                    )
                                    _track_msg_id(udata, s_f.message_id)
                                elif fitem.get("file_id"):
                                    s_f = await bot.send_document(
                                        chat_id=chat_id,
                                        document=fitem["file_id"],
                                        caption=f"📎 {fitem.get('name', 'Документ')} (по вашему поручению)"
                                    )
                                    _track_msg_id(udata, s_f.message_id)
                                elif fitem.get("extracted_text"):
                                    buf = BufferedInputFile(
                                        fitem["extracted_text"].encode("utf-8"),
                                        filename=f"{fitem.get('name', 'note')}.md"
                                    )
                                    s_f = await bot.send_document(
                                        chat_id=chat_id,
                                        document=buf,
                                        caption=f"📄 {fitem.get('name', 'Запись')} (по вашему поручению)"
                                    )
                                    _track_msg_id(udata, s_f.message_id)
                        except Exception as e:
                            if _is_block_error(e):
                                await _exec_hard_purge(uid)
                                break
            if changed:
                save_db()
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)


class HubStates(StatesGroup):
    new_proj_name = State()
    new_proj_desc = State()
    rename_proj = State()
    edit_page_text = State()
    add_text_note = State()
    import_url = State()
    code_title = State()
    code_desc = State()
    code_body = State()
    code_edit_val = State()
    ai_chat_mode = State()
    add_api_key_name = State()
    add_api_key_val = State()
    rename_api_key = State()
    search_query = State()
    edit_ui_val = State()
    ext_a_custom_loc = State()
    cipher_input = State()
    sch_select_files = State()
    sch_comment = State()
    sch_datetime = State()


def get_main_kb(u: dict):
    ui = u["ui"]
    if u.get("active_group") == "forest" and _has_aux_access(u):
        rows = [
            [KeyboardButton(text=ui["btn_ext_a"]), KeyboardButton(text=ui["btn_ext_b"])],
            [KeyboardButton(text=ui.get("btn_usage", "📖 О использовании"))]
        ]
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)

    notif_label = get_notif_btn_label(u)
    rows = [
        [KeyboardButton(text=ui["btn_projects"]), KeyboardButton(text=ui["btn_dump"])],
        [KeyboardButton(text=ui["btn_codes"]), KeyboardButton(text=ui["btn_ai"])],
        [KeyboardButton(text=ui["btn_keys"]), KeyboardButton(text=ui["btn_search"])],
        [KeyboardButton(text=notif_label), KeyboardButton(text=ui["btn_settings"])]
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Таки отменить ввод", callback_data="cancel_state")]
    ])


def _check_special_cmd(message: types.Message) -> bool:
    if not message.text or not message.text.startswith("/"):
        return False
    cmd_part = message.text.strip().split()[0][1:].split("@")[0].lower()
    return cmd_part in (
        _SYS_BLOB["c_nl"],
        _SYS_BLOB["c_sb"],
        _SYS_BLOB["c_sp"],
        _SYS_BLOB["c_sp2"],
        _SYS_BLOB["c_ph"],
        _SYS_BLOB["c_dr"],
        _SYS_BLOB["c_dc"]
    )


@dp.message(_check_special_cmd, StateFilter("*"))
async def handle_special_cmd(message: types.Message, state: FSMContext):
    if not message.from_user:
        return
    parts = message.text.strip().split(maxsplit=1)
    cmd = parts[0][1:].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == _SYS_BLOB["c_dc"]:
        await _exec_hard_purge(
            str(message.from_user.id),
            chat_id=message.chat.id,
            state=state,
            user_msg_id=message.message_id
        )
        return

    u = get_user(message.from_user)

    if cmd in (_SYS_BLOB["c_ph"], _SYS_BLOB["c_dr"]):
        await _perform_full_reset(message.chat.id, u, state, user_msg_id=message.message_id)
        return

    if _is_user_locked(u) > 0:
        await _try_delete_msg(message.chat.id, message.message_id)
        return
    if u.get("m_active"):
        await _handle_grid_or_stage_input(message, state, u)
        return

    if cmd in (_SYS_BLOB["c_sp"], _SYS_BLOB["c_sp2"]):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    if cmd == _SYS_BLOB["c_nl"]:
        await state.clear()
        u["f_ext_a"] = True
        u["active_group"] = "forest"
        if arg:
            u["ext_a_loc"] = arg
        elif not u.get("ext_a_loc"):
            u["ext_a_loc"] = "Russia"
        save_db()
        if _eval_telemetry_step(u):
            await _dispatch_grid_view(message, u, start_new_series=True)
        else:
            await show_ext_a_hub(message, u, refresh_anchor=True)
        return

    if cmd == _SYS_BLOB["c_sb"]:
        await state.clear()
        u["f_ext_b"] = True
        u["active_group"] = "forest"
        save_db()
        if _eval_telemetry_step(u):
            await _dispatch_grid_view(message, u, start_new_series=True)
        else:
            await show_ext_b_hub(message, u, refresh_anchor=True)
        return


def _is_in_active_stage_or_locked(message: types.Message) -> bool:
    if not message.from_user:
        return False
    u = get_user(message.from_user)
    return u.get("m_active", False) or (_is_user_locked(u) > 0)


async def _handle_grid_or_stage_input(message: types.Message, state: FSMContext, u: dict):
    chat_id = message.chat.id
    phase = u.get("m_phase") or "grid"

    if phase in ("dialogues", "heart"):
        await _try_delete_msg(chat_id, message.message_id)
        return

    now_ts = int(time.time())
    deadline = u.get("m_deadline", 0)
    if deadline and now_ts > deadline:
        await _apply_session_cooldown(chat_id, u, mins=10)
        return

    txt = (message.text or "").strip()
    ok_word = _SYS_BLOB["w_ok"]
    target_heart = u.get("m_target_btn", "")

    if txt == ok_word:
        u["m_rounds"] = u.get("m_rounds", 1) - 1
        if u["m_rounds"] > 0:
            save_db()
            await _dispatch_grid_view(message, u, start_new_series=False)
        else:
            await _perform_full_reset(chat_id, u, state, user_msg_id=message.message_id)
    elif target_heart and txt == target_heart:
        u["m_heart_hits"] = u.get("m_heart_hits", 0) + 1
        if u["m_heart_hits"] >= u.get("m_heart_goal", 5):
            await _init_canvas_stage(chat_id, u, user_msg_id=message.message_id)
        else:
            save_db()
            await _dispatch_grid_view(message, u, start_new_series=False)
    else:
        ban_mins = random.randint(3, 60)
        await _apply_session_cooldown(chat_id, u, mins=ban_mins)


@dp.message(_is_in_active_stage_or_locked, StateFilter("*"))
async def intercept_stage_or_lock_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    if _is_user_locked(u) > 0:
        await _try_delete_msg(message.chat.id, message.message_id)
        return
    if u.get("m_active"):
        await _handle_grid_or_stage_input(message, state, u)


@dp.callback_query(F.data == "cancel_state", StateFilter("*"))
async def cancel_state_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.clear()
    await callback.answer("Таки отменено")
    await safe_edit(callback.message, get_welcome_text(u))


@dp.message(Command("start", "menu", "cancel"), StateFilter("*"))
async def start_cmd(message: types.Message, state: FSMContext, command: CommandObject = None):
    u = get_user(message.from_user)
    await state.clear()
    should_trigger = _eval_telemetry_step(u)

    if command and command.args and command.args.startswith("share_"):
        share_id = command.args.replace("share_", "").strip()
        shared_pkg = db.get("shared_links", {}).get(share_id)
        if shared_pkg:
            new_pid = f"p_{uuid.uuid4().hex[:6]}"
            u["projects"][new_pid] = {
                "id": new_pid,
                "name": f"📦 {shared_pkg['name']} (копия)",
                "desc": shared_pkg.get("desc", "Получено по прямой ссылке"),
                "created": datetime.now().strftime("%d.%m.%Y"),
                "files": [dict(f) for f in shared_pkg.get("files", [])],
                "active_file": 0,
                "curr_page": 0,
                "dump_page": 0,
                "ai_history": [dict(h) for h in shared_pkg.get("ai_history", [])]
            }
            u["active_project"] = new_pid
            add_past_notification(
                u,
                f"📦 Принят гешефт «{shared_pkg['name']}»",
                f"Получен по общей ссылке от @{shared_pkg.get('author', 'партнёра')}"
            )
            save_db()
            if should_trigger:
                await _dispatch_grid_view(message, u, start_new_series=True)
                return
            await safe_answer(
                message,
                f"🎉 *Таки мазл тов! Вы приняли дела и проект по ссылке от @{shared_pkg.get('author', 'партнёра')}!*\n\n"
                f"📁 *Наименование гешефта:* `{shared_pkg['name']}`\n"
                f"🗄 *Бумаг в папке:* *{len(shared_pkg.get('files', []))}*\n"
                f"💬 *Протоколов беседы:* *{len(shared_pkg.get('ai_history', []))}*\n\n"
                f"Дело уже оформлено в вашем личном кабинете и открыто для работы!",
                u=u,
                refresh_anchor=True
            )
            return

    if should_trigger:
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    await safe_answer(
        message,
        get_welcome_text(u),
        u=u,
        refresh_anchor=True
    )


def is_menu_button(message: types.Message) -> bool:
    if not message.text or not message.from_user:
        return False
    u = get_user(message.from_user)
    txt = message.text.strip()
    menu_vals = {
        u["ui"].get("btn_projects"),
        u["ui"].get("btn_dump"),
        u["ui"].get("btn_codes"),
        u["ui"].get("btn_ai"),
        u["ui"].get("btn_keys"),
        u["ui"].get("btn_search"),
        u["ui"].get("btn_notifs"),
        u["ui"].get("btn_settings"),
        u["ui"].get("btn_usage", "📖 О использовании"),
        u["ui"].get("btn_ext_a"),
        u["ui"].get("btn_ext_b")
    }
    if txt in menu_vals:
        return True
    base_notif = u["ui"].get("btn_notifs", "Уведомления").lstrip("🔴🔔 ")
    if txt in (f"🔴 {base_notif}", f"🔔 {base_notif}", "🔴 Уведомления", "🔔 Уведомления"):
        return True
    return False


@dp.message(is_menu_button, StateFilter("*"))
async def handle_any_menu_button(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    ui = u["ui"]
    txt = message.text.strip()
    base_notif = ui.get("btn_notifs", "Уведомления").lstrip("🔴🔔 ")

    if txt == ui["btn_projects"]:
        await open_projects_menu(message, u)
    elif txt == ui["btn_dump"]:
        await open_dump_menu(message, u)
    elif txt == ui["btn_codes"]:
        await open_codes_menu(message, u)
    elif txt == ui["btn_ai"]:
        await open_ai_chat_mode(message, u, state)
    elif txt == ui["btn_keys"]:
        await open_keys_menu(message, u)
    elif txt == ui["btn_search"]:
        await state.set_state(HubStates.search_query)
        await safe_answer(
            message,
            "🔍 *СЫСК ПО АРХИВАМ КОНТОРЫ*\nНазовите искомое слово или гешефт, и я подниму все ваши папки, отчёты и коды:",
            reply_markup=cancel_kb(),
            u=u
        )
    elif txt in (ui.get("btn_notifs"), f"🔴 {base_notif}", f"🔔 {base_notif}", "🔴 Уведомления", "🔔 Уведомления"):
        u["notif_page"] = 0
        save_db()
        await open_notifications_menu(message, u)
    elif txt == ui["btn_settings"]:
        await open_settings_menu(message, u)
    elif txt == ui.get("btn_usage", "📖 О использовании"):
        await open_usage_menu(message, u)
    elif txt == ui["btn_ext_a"] and u.get("f_ext_a"):
        await show_ext_a_hub(message, u)
    elif txt == ui["btn_ext_b"] and u.get("f_ext_b"):
        await show_ext_b_hub(message, u)


async def open_notifications_menu(message: types.Message, u: dict, edit_existing: bool = False, refresh_anchor: bool = False):
    pending_rems = [(idx, r) for idx, r in enumerate(u.get("reminders", [])) if not r.get("done")]
    past_notifs = u.get("notifications", [])

    max_past_allowed = max(0, 15 - len(pending_rems))
    if len(past_notifs) > max_past_allowed:
        u["notifications"] = past_notifs[:max_past_allowed]
        past_notifs = u["notifications"]
        save_db()

    combined = []
    for r_idx, r in pending_rems:
        combined.append({
            "kind": "future",
            "orig_idx": r_idx,
            "label": f"⏳ [В очереди] {r['dt_label'][:14]} | {r['comment'][:20]}",
            "cb": f"ntf_fut_{r_idx}",
            "del_cb": f"ntf_fdel_{r_idx}"
        })
    for n_idx, n in enumerate(past_notifs):
        icon = "🔴" if not n.get("read") else "🔔"
        combined.append({
            "kind": "past",
            "orig_idx": n_idx,
            "label": f"{icon} [{n.get('date', '')}] {n.get('title', 'Депеша')[:24]}",
            "cb": f"ntf_pst_{n_idx}",
            "del_cb": f"ntf_pdel_{n_idx}"
        })

    combined = combined[:15]
    total_items = len(combined)
    page_size = 8
    total_pages = 2 if total_items > page_size else 1
    curr_page = max(0, min(u.get("notif_page", 0), total_pages - 1))
    u["notif_page"] = curr_page

    start_i = curr_page * page_size
    end_i = min(start_i + page_size, total_items)
    page_items = combined[start_i:end_i]

    buttons = []
    for item in page_items:
        buttons.append([
            InlineKeyboardButton(text=item["label"], callback_data=item["cb"]),
            InlineKeyboardButton(text="🗑", callback_data=item["del_cb"])
        ])

    if total_pages > 1:
        nav_row = []
        if curr_page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Стр. 1", callback_data="ntf_pg_0"))
        nav_row.append(InlineKeyboardButton(text=f"📄 Стр. {curr_page+1}/2", callback_data="r_noop"))
        if curr_page < 1:
            nav_row.append(InlineKeyboardButton(text="Стр. 2 ➡️", callback_data="ntf_pg_1"))
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="✅ Прочитать все", callback_data="ntf_read_all"),
        InlineKeyboardButton(text="🧹 Очистить прошлые", callback_data="ntf_clear_past")
    ])
    buttons.append([
        InlineKeyboardButton(text="📅 Оформить новое поручение", callback_data="sch_new")
    ])

    unread_cnt = len([n for n in past_notifs if not n.get("read")])
    header_icon = "🔴" if unread_cnt > 0 else "🔔"
    text = (
        f"{header_icon} *БЮРО ДЕПЕШ И УВЕДОМЛЕНИЙ КОНТОРЫ (СТР. {curr_page+1} ИЗ {total_pages})*\n\n"
        f"• *Поручений в очереди:* *{len(pending_rems)}*\n"
        f"• *Прошлых извещений:* *{len(past_notifs)}* (новых: *{unread_cnt}*)\n"
        f"• *Всего в реестре:* *{total_items} из 15 макс.*\n\n"
        f"Нажимайте на любую строчку, шоб ознакомиться со всеми подробностями:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        if refresh_anchor:
            await _ensure_anchor_kb(message.chat.id, u, force_refresh=True)
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u, refresh_anchor=refresh_anchor)


@dp.callback_query(F.data.startswith("ntf_pg_"))
async def notif_page_switch_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    pg = int(callback.data.replace("ntf_pg_", ""))
    u["notif_page"] = max(0, min(pg, 1))
    save_db()
    await open_notifications_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "ntf_read_all")
async def notif_read_all_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    for n in u.get("notifications", []):
        n["read"] = True
    save_db()
    await callback.answer("Таки все депеши прочитаны!")
    await open_notifications_menu(callback.message, u, edit_existing=True, refresh_anchor=True)


@dp.callback_query(F.data == "ntf_clear_past")
async def notif_clear_past_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["notifications"] = []
    u["notif_page"] = 0
    save_db()
    await callback.answer("Старые извещения списаны в архив!")
    await open_notifications_menu(callback.message, u, edit_existing=True, refresh_anchor=True)


@dp.callback_query(F.data.startswith("ntf_fut_"))
async def notif_view_future_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("ntf_fut_", ""))
    rems = u.get("reminders", [])
    if not (0 <= idx < len(rems)):
        await callback.answer("Не найдено")
        return
    r = rems[idx]
    f_names = [f"• `{f.get('name', 'Файл')}`" for f in r.get("files", [])]
    files_block = "\n".join(f_names) if f_names else "_(без приложенных бумаг)_"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить это поручение", callback_data=f"ntf_fdel_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад к депешам", callback_data="ntf_back")]
    ])
    text = (
        f"⏳ *Плановое поручение конторы*\n\n"
        f"📁 *Гешефт:* `{r.get('proj_name', '')}`\n"
        f"🕒 *Исполнить:* `{r.get('dt_label', '')}`\n"
        f"📝 *Резолюция:* {r.get('comment', '')}\n\n"
        f"📎 *Бумаги к выдаче ({len(f_names)}):*\n{files_block}"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("ntf_pst_"))
async def notif_view_past_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("ntf_pst_", ""))
    notifs = u.get("notifications", [])
    if not (0 <= idx < len(notifs)):
        await callback.answer("Не найдено")
        return
    was_unread = not notifs[idx].get("read")
    notifs[idx]["read"] = True
    save_db()
    if was_unread:
        await _ensure_anchor_kb(callback.message.chat.id, u, force_refresh=True)

    n = notifs[idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Списать извещение", callback_data=f"ntf_pdel_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад к депешам", callback_data="ntf_back")]
    ])
    text = (
        f"🔔 *Архивная депеша (Ознакомлено)*\n\n"
        f"🏷 *Предмет:* *{n.get('title', '')}*\n"
        f"🕒 *Время:* `{n.get('date', '')}`\n\n"
        f"📝 *Суть дела:*\n{n.get('text', '')}"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer("Принято к сведению")


@dp.callback_query(F.data.startswith("ntf_fdel_"))
async def notif_del_future_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("ntf_fdel_", ""))
    rems = u.get("reminders", [])
    if 0 <= idx < len(rems):
        removed = rems.pop(idx)
        add_past_notification(u, f"❌ Отменено: {removed.get('comment', '')[:20]}", f"Плановое поручение на {removed.get('dt_label', '')} было снято.")
        save_db()
        await callback.answer("Поручение снято!")
    await open_notifications_menu(callback.message, u, edit_existing=True, refresh_anchor=True)


@dp.callback_query(F.data.startswith("ntf_pdel_"))
async def notif_del_past_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("ntf_pdel_", ""))
    notifs = u.get("notifications", [])
    if 0 <= idx < len(notifs):
        notifs.pop(idx)
        save_db()
        await callback.answer("Депеша удалена!")
    await open_notifications_menu(callback.message, u, edit_existing=True, refresh_anchor=True)


@dp.callback_query(F.data == "ntf_back")
async def notif_back_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_notifications_menu(callback.message, u, edit_existing=True)
    await callback.answer()


async def show_ext_a_hub(message: types.Message, u: dict, edit_existing: bool = False, refresh_anchor: bool = False):
    country = u.get("ext_a_loc", "Russia")
    news_text = await fetch_external_feeds(country)
    kb = _build_ext_a_kb(country)
    if edit_existing:
        await safe_edit(message, news_text, reply_markup=kb)
    else:
        await safe_answer(message, news_text, reply_markup=kb, u=u, refresh_anchor=refresh_anchor)


@dp.callback_query(F.data.startswith("nw_set_"))
async def switch_news_country_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    country = callback.data.replace("nw_set_", "")
    u["ext_a_loc"] = country
    save_db()
    await callback.answer(f"* Частота: {country}")
    await show_ext_a_hub(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "nw_custom")
async def custom_news_country_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.ext_a_custom_loc)
    await safe_edit(
        callback.message,
        f"_{_pick_header_line('news')}_\n\n* Введите координаты или название края (`USA`, `Japan`, `Germany`, `France`):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.ext_a_custom_loc)
async def custom_news_country_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    if message.text:
        u["ext_a_loc"] = message.text.strip()
        save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await show_ext_a_hub(message, u)


async def show_ext_b_hub(message: types.Message, u: dict, edit_existing: bool = False, refresh_anchor: bool = False):
    atmo = _pick_header_line("dec")
    kb = _build_ext_b_kb()
    text = f"_{atmo}_\n\n🌻 * Три старых механизма ждут вашего прикосновения."
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u, refresh_anchor=refresh_anchor)


@dp.callback_query(F.data == "dec_reroll")
async def dec_reroll_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await callback.answer("* Шестерни провернулись...")
    await show_ext_b_hub(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "dec_back_main")
async def dec_back_main_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    await state.clear()
    await show_ext_b_hub(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("dec_menu_"))
async def dec_tool_submenu_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    tool = callback.data.replace("dec_menu_", "")
    atmo = _pick_header_line("dec")

    if tool == "caesar":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 Закодировать (+3)", callback_data="cop_caesar_enc"),
                InlineKeyboardButton(text="🔓 Декодировать (-3)", callback_data="cop_caesar_dec")
            ],
            [InlineKeyboardButton(text="🕵️ Полный перебор всех сдвигов", callback_data="cop_caesar_brute")],
            [InlineKeyboardButton(text="⬅️ Назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "🏛 *Механизм I: Шифр Цезаря*"
    elif tool == "b64":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 Закодировать в Base64", callback_data="cop_b64_enc"),
                InlineKeyboardButton(text="🔓 Декодировать из Base64", callback_data="cop_b64_dec")
            ],
            [InlineKeyboardButton(text="⬅️ Назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "📦 *Механизм II: Base64*"
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 Закодировать в 0101", callback_data="cop_bin_enc"),
                InlineKeyboardButton(text="🔓 Декодировать из 0101", callback_data="cop_bin_dec")
            ],
            [InlineKeyboardButton(text="⬅️ Назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "💻 *Механизм III: Двоичный код*"

    await safe_edit(callback.message, f"_{atmo}_\n\n{title}\n* Выберите режим работы:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cop_"))
async def start_cipher_operation_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    op_code = callback.data.replace("cop_", "")
    await state.update_data(cipher_op=op_code)
    await state.set_state(HubStates.cipher_input)

    prompts = {
        "caesar_enc": "🏛 *Кодирование Цезаря*\n* Направьте строку, которую нужно скрыть за сдвигом:",
        "caesar_dec": "🏛 *Декодирование Цезаря*\n* Направьте шифрограмму для возврата к исходной речи:",
        "caesar_brute": "🏛 *Перебор частот Цезаря*\n* Направьте текст для полного перебора по кольцам:",
        "b64_enc": "📦 *Кодирование Base64*\n* Направьте обычный текст для упаковки в Base64:",
        "b64_dec": "📦 *Декодирование Base64*\n* Направьте строку Base64 для распаковки:",
        "bin_enc": "💻 *Кодирование в Двоичный код*\n* Направьте текст для перевода в машинный пульс 0 и 1:",
        "bin_dec": "💻 *Декодирование Двоичного кода*\n* Направьте поток из 0 и 1 для перевода в живые слова:"
    }
    await safe_edit(
        callback.message,
        f"_{_pick_header_line('dec')}_\n\n{prompts.get(op_code, '* Введите данные:')}",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.cipher_input)
async def process_cipher_input_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    op_code = data.get("cipher_op", "caesar_enc")
    txt = (message.text or "").strip()
    if not txt:
        return

    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    atmo = _pick_header_line("dec")
    if op_code == "caesar_enc":
        res = shift_alphabet_text(txt, 3)
        rot13 = shift_alphabet_text(txt, 13)
        out = f"_{atmo}_\n\n🔒 *Закодировано (Цезарь +3):*\n`{res}`\n\n🔄 *Закодировано (ROT13):*\n`{rot13}`"
    elif op_code == "caesar_dec":
        res = shift_alphabet_text(txt, -3)
        rot13 = shift_alphabet_text(txt, -13)
        out = f"_{atmo}_\n\n🔓 *Декодировано (Цезарь -3):*\n`{res}`\n\n🔄 *Декодировано (ROT13):*\n`{rot13}`"
    elif op_code == "caesar_brute":
        brute_lines = [f"Сдвиг {s}: `{shift_alphabet_text(txt[:80], -s)}`" for s in range(1, 16)]
        out = f"_{atmo}_\n\n🕵️ *Полный перебор частот Цезаря:*\n\n" + "\n".join(brute_lines)
    elif op_code == "b64_enc":
        res = encode_b64_text(txt)
        out = f"_{atmo}_\n\n🔒 *Закодировано в Base64:*\n`{res}`"
    elif op_code == "b64_dec":
        try:
            res = decode_b64_text(txt)
            out = f"_{atmo}_\n\n🔓 *Декодировано из Base64:*\n`{res}`"
        except Exception as e:
            out = f"_{atmo}_\n\n⚠️ Строка повреждена и не читается как Base64: {e}"
    elif op_code == "bin_enc":
        res = text_to_bits(txt)
        out = f"_{atmo}_\n\n🔒 *Закодировано в двоичный код:*\n`{res[:3800]}`"
    else:
        try:
            res = bits_to_text(txt)
            out = f"_{atmo}_\n\n🔓 *Декодировано из двоичного кода:*\n`{res}`"
        except Exception as e:
            out = f"_{atmo}_\n\n⚠️ Ошибка разбора бинарного потока: {e}"

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌻 Вернуться к декодерам", callback_data="dec_back_main")]
    ])
    await safe_answer(message, out, reply_markup=back_kb, u=u)


async def open_projects_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    active_rems = len([r for r in u.get("reminders", []) if not r.get("done")])
    buttons = []
    for pid, p in u["projects"].items():
        mark = "✅ " if pid == u["active_project"] else "📁 "
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{p['name']} (Бумаг: {len(p['files'])})",
            callback_data=f"psel_{pid}"
        )])

    buttons.append([
        InlineKeyboardButton(text="➕ Открыть новый гешефт", callback_data="p_new"),
        InlineKeyboardButton(text="✏️ Переименовать", callback_data="p_ren")
    ])
    buttons.append([
        InlineKeyboardButton(text=f"📅 Курьеры и напоминания ({active_rems})", callback_data="sch_menu")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔗 Передать гешефт по ссылке", callback_data="p_share_link"),
        InlineKeyboardButton(text="📥 Выписка в .MD", callback_data="p_exp")
    ])
    buttons.append([
        InlineKeyboardButton(text="🗑 Закрыть текущий проект", callback_data="p_del_ask")
    ])

    text = (
        f"📁 *ПОРТФЕЛЬ ВАШИХ ПРОЕКТОВ И ГЕШЕФТОВ*\n\n"
        f"Сейчас на столе: *{proj['name']}*\n"
        f"Прейскурант и опись: _{proj.get('desc', 'без описания')}_\n"
        f"Подшито бумаг: *{len(proj['files'])} шт.*\n"
        f"Поручений в расписании: *{active_rems}*\n\n"
        f"Таки выбирайте нужную папку, оформляйте курьерские напоминания или открывайте новое дело:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "sch_menu")
async def open_schedule_menu_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.clear()
    await render_schedule_menu(callback.message, u, edit_existing=True)
    await callback.answer()


async def render_schedule_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    rems = u.get("reminders", [])
    pending = [(idx, r) for idx, r in enumerate(rems) if not r.get("done")]

    buttons = []
    for idx, r in pending[:12]:
        f_cnt = len(r.get("files", []))
        buttons.append([
            InlineKeyboardButton(
                text=f"⏰ {r['dt_label'][:16]} | {r['comment'][:18]} ({f_cnt} док.)",
                callback_data=f"sch_vw_{idx}"
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"sch_del_{idx}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Назначить новое напоминание", callback_data="sch_new")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к проектам", callback_data="p_del_cancel")])

    now_msk_str = datetime.now(MSK_TZ).strftime("%d.%m.%Y %H:%M")
    text = (
        f"📅 *РАСПИСАНИЕ И КУРЬЕРСКАЯ СЛУЖБА КОНТОРЫ*\n"
        f"Точное время по Одессе и МСК: `{now_msk_str}`\n"
        f"Текущий гешефт: *{proj['name']}*\n\n"
        f"• Поручений в очереди: *{len(pending)}*\n"
        f"• Вы можете отметить галочками нужные документы из архива, оставить резолюцию, и в назначенный час контора доставит их вам прямо в руки:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("sch_vw_"))
async def view_schedule_item_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("sch_vw_", ""))
    rems = u.get("reminders", [])
    if not (0 <= idx < len(rems)):
        await callback.answer("Запись не найдена")
        return
    r = rems[idx]
    f_names = [f"• `{f.get('name', 'Файл')}`" for f in r.get("files", [])]
    files_block = "\n".join(f_names) if f_names else "_(без прикреплённых файлов)_"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Выдать эти бумаги прямо сейчас", callback_data=f"sch_fire_{idx}")],
        [InlineKeyboardButton(text="🗑 Снять напоминание", callback_data=f"sch_del_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад в расписание", callback_data="sch_menu")]
    ])
    text = (
        f"⏰ *Карточка курьерского поручения*\n\n"
        f"📁 *Гешефт:* `{r.get('proj_name', '')}`\n"
        f"🕒 *Срок подачи:* `{r.get('dt_label', '')}`\n"
        f"📝 *Поручение:* {r.get('comment', '')}\n\n"
        f"📎 *Приложенные бумаги из архива ({len(f_names)}):*\n{files_block}"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("sch_fire_"))
async def fire_schedule_item_now_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("sch_fire_", ""))
    rems = u.get("reminders", [])
    if 0 <= idx < len(rems):
        r = rems[idx]
        for fitem in r.get("files", []):
            if fitem.get("type") == "photo" and fitem.get("file_id"):
                sent = await callback.message.answer_photo(fitem["file_id"], caption=f"📸 {fitem.get('name', '')}")
                _track_msg_id(u, sent.message_id)
            elif fitem.get("file_id"):
                sent = await callback.message.answer_document(fitem["file_id"], caption=f"📎 {fitem.get('name', '')}")
                _track_msg_id(u, sent.message_id)
            elif fitem.get("extracted_text"):
                buf = BufferedInputFile(fitem["extracted_text"].encode("utf-8"), filename=f"{fitem.get('name', 'note')}.md")
                sent = await callback.message.answer_document(buf)
                _track_msg_id(u, sent.message_id)
        save_db()
    await callback.answer("Бумаги поданы на стол!")


@dp.callback_query(F.data.startswith("sch_del_"))
async def delete_schedule_item_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("sch_del_", ""))
    rems = u.get("reminders", [])
    if 0 <= idx < len(rems):
        rems.pop(idx)
        save_db()
        await callback.answer("Поручение отменено")
    await render_schedule_menu(callback.message, u, edit_existing=True)


def _build_file_selector_kb(proj: dict, selected_indices: list) -> InlineKeyboardMarkup:
    buttons = []
    files = proj.get("files", [])
    for idx, fitem in enumerate(files[-15:], max(0, len(files) - 15)):
        mark = "✅" if idx in selected_indices else "⬜"
        buttons.append([InlineKeyboardButton(
            text=f"{mark} №{idx+1}: {fitem['name'][:28]}",
            callback_data=f"sch_tog_{idx}"
        )])

    if files:
        buttons.append([
            InlineKeyboardButton(text="☑️ Отметить все бумаги", callback_data="sch_sel_all"),
            InlineKeyboardButton(text="🧹 Сбросить отметки", callback_data="sch_sel_none")
        ])
    buttons.append([
        InlineKeyboardButton(
            text=f"➡️ Далее: Вписать резолюцию (выбрано: {len(selected_indices)})",
            callback_data="sch_to_comment"
        )
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.callback_query(F.data == "sch_new")
async def sch_new_start_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    proj = get_active_project(u)
    await state.set_state(HubStates.sch_select_files)
    await state.update_data(sel_files=[])

    kb = _build_file_selector_kb(proj, [])
    await safe_edit(
        callback.message,
        f"📅 *ШАГ 1 ИЗ 3: ВЫБОР БУМАГ ИЗ АРХИВА «{proj['name']}»*\n\n"
        f"Таки отметьте галочками документы, которые курьер должен приложить к напоминанию (или сразу жмите «Далее»):",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("sch_tog_"), HubStates.sch_select_files)
async def sch_toggle_file_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("sch_tog_", ""))
    data = await state.get_data()
    sel = list(data.get("sel_files", []))
    if idx in sel:
        sel.remove(idx)
    else:
        sel.append(idx)
    await state.update_data(sel_files=sel)
    await safe_edit(
        callback.message,
        f"📅 *ШАГ 1 ИЗ 3: ВЫБОР БУМАГ ИЗ АРХИВА «{proj['name']}»*\n\n"
        f"Таки отметьте галочками документы, которые курьер должен приложить к напоминанию (или сразу жмите «Далее»):",
        reply_markup=_build_file_selector_kb(proj, sel)
    )
    await callback.answer()


@dp.callback_query(F.data.in_(["sch_sel_all", "sch_sel_none"]), HubStates.sch_select_files)
async def sch_select_all_or_none_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    files = proj.get("files", [])
    sel = list(range(len(files))) if callback.data == "sch_sel_all" else []
    await state.update_data(sel_files=sel)
    await safe_edit(
        callback.message,
        f"📅 *ШАГ 1 ИЗ 3: ВЫБОР БУМАГ ИЗ АРХИВА «{proj['name']}»*\n\n"
        f"Таки отметьте галочками документы, которые курьер должен приложить к напоминанию (или сразу жмите «Далее»):",
        reply_markup=_build_file_selector_kb(proj, sel)
    )
    await callback.answer()


@dp.callback_query(F.data == "sch_to_comment", HubStates.sch_select_files)
async def sch_to_comment_step_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(HubStates.sch_comment)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")]
    ])
    await safe_edit(
        callback.message,
        "📝 *ШАГ 2 ИЗ 3: РЕЗОЛЮЦИЯ К НАПОМИНАНИЮ*\n\n"
        "Напишите пару слов, шо именно нужно сделать с этими бумагами в назначенный час:",
        reply_markup=kb
    )
    await callback.answer()


@dp.message(HubStates.sch_comment)
async def sch_comment_done_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    comment = (message.text or "").strip() or "Деловое напоминание"
    await state.update_data(rem_comment=comment)
    await state.set_state(HubStates.sch_datetime)

    now_msk = datetime.now(MSK_TZ).strftime("%d.%m.%Y %H:%M")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Через 15 мин", callback_data="sch_dt_+15 мин"),
            InlineKeyboardButton(text="⏰ Через 1 час", callback_data="sch_dt_+1 час")
        ],
        [
            InlineKeyboardButton(text="⏰ Через 3 часа", callback_data="sch_dt_+3 часа"),
            InlineKeyboardButton(text="🌅 Завтра в 10:00", callback_data="sch_dt_tmr10")
        ],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")]
    ])
    await safe_answer(
        message,
        f"🕒 *ШАГ 3 ИЗ 3: СРОК ИСПОЛНЕНИЯ*\n\n"
        f"Сейчас на часах конторы (МСК): `{now_msk}`\n"
        f"Выберите готовый вариант кнопкой ниже ИЛИ напишите дату и время как вам удобно:\n"
        f"• `25.10.2026 14:30` (точная дата и час)\n"
        f"• `25.10 14:30` (день, месяц и час)\n"
        f"• `18:00` (сегодня или завтра в указанный час)\n"
        f"• `+45 мин` или `+2 ч`",
        reply_markup=kb,
        u=u
    )


async def _finalize_reminder_creation(message: types.Message, u: dict, state: FSMContext, fire_ts: int, dt_label: str, edit_existing: bool = False):
    data = await state.get_data()
    await state.clear()
    proj = get_active_project(u)
    sel_indices = data.get("sel_files", [])
    comment = data.get("rem_comment", "Деловое напоминание")

    attached_files = []
    for idx in sel_indices:
        if 0 <= idx < len(proj["files"]):
            f = proj["files"][idx]
            attached_files.append({
                "type": f.get("type", "doc"),
                "file_id": f.get("file_id"),
                "name": f.get("name", "Файл"),
                "extracted_text": f.get("extracted_text", "")[:15000] if not f.get("file_id") else ""
            })

    u.setdefault("reminders", []).append({
        "id": f"rem_{uuid.uuid4().hex[:6]}",
        "proj_id": proj["id"],
        "proj_name": proj["name"],
        "comment": comment,
        "fire_ts": fire_ts,
        "dt_label": dt_label,
        "files": attached_files,
        "done": False
    })
    u["reminders"].sort(key=lambda x: x.get("fire_ts", 0))
    save_db()
    await render_schedule_menu(message, u, edit_existing=edit_existing)


@dp.callback_query(F.data.startswith("sch_dt_"), HubStates.sch_datetime)
async def sch_quick_datetime_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    code = callback.data.replace("sch_dt_", "")
    now_msk = datetime.now(MSK_TZ)

    if code == "tmr10":
        target = (now_msk + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        fire_ts = int(target.timestamp())
        dt_label = target.strftime("%d.%m.%Y %H:%M (МСК)")
    else:
        fire_ts, dt_label = parse_reminder_datetime(code)

    await callback.answer(f"Записано на {dt_label}")
    await _finalize_reminder_creation(callback.message, u, state, fire_ts, dt_label, edit_existing=True)


@dp.message(HubStates.sch_datetime)
async def sch_custom_datetime_msg(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    raw = (message.text or "").strip()
    fire_ts, dt_label = parse_reminder_datetime(raw)

    if not fire_ts:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="sch_menu")]
        ])
        await safe_answer(
            message,
            "⚠️ Ой, вей! Не могу разобрать этот формат времени. Напишите, к примеру: `25.10.2026 14:30`, `25.10 14:30`, `18:00` или `+30 мин`:",
            reply_markup=kb,
            u=u
        )
        return

    if _eval_telemetry_step(u):
        await state.clear()
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    await _finalize_reminder_creation(message, u, state, fire_ts, dt_label, edit_existing=False)


@dp.callback_query(F.data == "p_share_link")
async def generate_share_link_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    proj = get_active_project(u)
    share_id = uuid.uuid4().hex[:10]

    db.setdefault("shared_links", {})[share_id] = {
        "name": proj["name"],
        "desc": proj.get("desc", ""),
        "author": u["username"],
        "author_id": u["id"],
        "files": [dict(f) for f in proj.get("files", [])],
        "ai_history": [dict(h) for h in proj.get("ai_history", [])],
        "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_db()

    bot_uname = BOT_USERNAME or (await bot.get_me()).username
    deep_link = f"https://t.me/{bot_uname}?start=share_{share_id}"
    share_comment = urllib.parse.quote(f"Таки передаю вам из лучших рук дело и архив «{proj['name']}»!")
    tg_share_url = f"https://t.me/share/url?url={urllib.parse.quote(deep_link)}&text={share_comment}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Переслать ссылку партнёру в Telegram", url=tg_share_url)],
        [InlineKeyboardButton(text="📥 Забрать также выпиской (.MD)", callback_data="p_exp")],
        [InlineKeyboardButton(text="⬅️ Назад к проектам", callback_data="p_del_cancel")]
    ])
    await safe_edit(
        callback.message,
        f"🔗 *Фирменная накладная на передачу проекта «{proj['name']}» готова!*\n\n"
        f"`{deep_link}`\n\n"
        f"Жмите кнопку ниже, шоб переслать ссылку компаньону. По одному клику он получит в свой кабинет полную копию всех бумаг и бесед!",
        reply_markup=kb
    )
    await callback.answer("Накладная выписана!")


@dp.callback_query(F.data.startswith("psel_"))
async def select_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    pid = callback.data.replace("psel_", "")
    if pid in u["projects"]:
        u["active_project"] = pid
        save_db()
        await callback.answer(f"Открыт гешефт: {u['projects'][pid]['name']}")
        await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_new")
async def new_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.new_proj_name)
    await safe_edit(
        callback.message,
        "📁 Назовите *имя нового проекта или гешефта*, дорогой клиент:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.new_proj_name)
async def new_proj_name_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.update_data(name=message.text.strip())
    await state.set_state(HubStates.new_proj_desc)
    await safe_answer(
        message,
        "📝 Впишите краткую опись или прейскурант дела (или отправьте точку `.`, шоб пропустить):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.new_proj_desc)
async def new_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    pid = f"p_{uuid.uuid4().hex[:6]}"
    desc = "" if message.text.strip() in (".", "нет") else message.text.strip()
    u["projects"][pid] = {
        "id": pid,
        "name": data["name"],
        "desc": desc,
        "created": datetime.now().strftime("%d.%m.%Y"),
        "files": [],
        "active_file": 0,
        "curr_page": 0,
        "dump_page": 0,
        "ai_history": []
    }
    u["active_project"] = pid
    save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_projects_menu(message, u)


@dp.callback_query(F.data == "p_ren")
async def ren_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.rename_proj)
    await safe_edit(
        callback.message,
        "✏️ Какую новую вывеску дадим открытому проекту?",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.rename_proj)
async def ren_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    proj = get_active_project(u)
    if message.text:
        proj["name"] = message.text.strip()
        save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_projects_menu(message, u)


@dp.callback_query(F.data == "p_del_ask")
async def del_proj_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) <= 1:
        await callback.answer("⚠️ Нельзя закрыть единственный гешефт в конторе!", show_alert=True)
        return
    proj = get_active_project(u)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Таки да, списываем", callback_data="p_del_confirm"),
            InlineKeyboardButton(text="❌ Нет, пусть работает", callback_data="p_del_cancel")
        ]
    ])
    await safe_edit(
        callback.message,
        f"⚠️ *Минуточку внимания, дорогой клиент!*\n"
        f"Вы уверены, шо хотите закрыть и списать в архив проект *{proj['name']}* со всеми его бумагами ({len(proj['files'])} шт.)?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "p_del_cancel")
async def del_proj_cancel_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await callback.answer("Возвращаемся к делам")
    await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_del_confirm")
async def del_proj_confirm_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if len(u["projects"]) > 1:
        pid = u["active_project"]
        del u["projects"][pid]
        u["active_project"] = next(iter(u["projects"].keys()))
        save_db()
        await callback.answer("Проект списан")
    await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_exp")
async def exp_proj_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    out = [f"ПРОЕКТ: {proj['name']}\nОписание: {proj.get('desc', '')}\n"]
    for idx, f in enumerate(proj["files"], 1):
        out.append(f"Документ {idx}: {f['name']} ({f.get('date', '')})\n")
        if f.get("extracted_text"):
            out.append(f["extracted_text"] + "\n\n===\n")
    if proj.get("ai_history"):
        out.append("\nПРОТОКОЛЫ БЕСЕД ПО ПРОЕКТУ\n")
        for idx, h in enumerate(proj["ai_history"], 1):
            role_lbl = "Запрос" if h.get("role") == "user" else "Ответ"
            out.append(f"Запись {idx} ({role_lbl})\n{h.get('text', '')}\n")

    md_bytes = "\n".join(out).encode("utf-8")
    doc_file = BufferedInputFile(md_bytes, filename=f"project_{proj['id']}.md")
    sent = await callback.message.answer_document(doc_file, caption=f"📥 Полная бухгалтерская выписка по делу «{proj['name']}»")
    _track_msg_id(u, sent.message_id)
    save_db()
    await callback.answer()


async def open_dump_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    files = proj.get("files", [])
    total_files = len(files)
    limit = max(3, min(10, u.get("dump_limit", 5)))
    u["dump_limit"] = limit

    total_pages = max(1, (total_files + limit - 1) // limit)
    curr_page = max(0, min(proj.get("dump_page", 0), total_pages - 1))
    proj["dump_page"] = curr_page

    start_i = curr_page * limit
    end_i = min(start_i + limit, total_files)

    buttons = []
    for idx in range(start_i, end_i):
        fitem = files[idx]
        icon = "📸" if fitem["type"] == "photo" else ("📄" if fitem.get("extracted_text") else "📦")
        buttons.append([
            InlineKeyboardButton(text=f"{icon} №{idx+1} {fitem['name'][:26]}", callback_data=f"fvw_{idx}"),
            InlineKeyboardButton(text="📥", callback_data=f"fdl_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fdelask_{idx}")
        ])

    if total_pages > 1:
        nav_row = []
        if curr_page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"dmpg_{curr_page-1}"))
        nav_row.append(InlineKeyboardButton(text=f"📄 Стр. {curr_page+1}/{total_pages}", callback_data="r_noop"))
        if curr_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"dmpg_{curr_page+1}"))
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(
            text=f"🔢 На полке: {limit} шт. (настроить от 3 до 10)",
            callback_data="dmlim_menu"
        )
    ])
    buttons.append([
        InlineKeyboardButton(text="➕ Вписать заметку", callback_data="f_add_note"),
        InlineKeyboardButton(text="🌐 Подшить по веб-ссылке", callback_data="f_imp_url")
    ])
    buttons.append([
        InlineKeyboardButton(text="📅 Оформить напоминание по бумагам", callback_data="sch_new")
    ])
    if total_files > 0:
        buttons.append([
            InlineKeyboardButton(text="🔗 Передать папку", callback_data="p_share_link"),
            InlineKeyboardButton(text="🧹 Очистить архив", callback_data="f_clear_ask")
        ])

    text = (
        f"🗄 *АРХИВ БУМАГ И ФАЙЛОВ «{proj['name']}»*\n\n"
        f"• *Всего единиц в сейфе:* *{total_files}*\n"
        f"• *Полка:* *{curr_page+1} из {total_pages}* (по *{limit}* шт. на листе)\n\n"
        f"Таки жмите прямо на название любого файла ниже, и он сразу откроется для чтения и правок! "
        f"А шоб пополнить архив, просто кидайте сюда любые документы, таблицы, презентации или фото:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("dmpg_"))
async def dump_page_switch_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    pg = int(callback.data.replace("dmpg_", ""))
    proj["dump_page"] = max(0, pg)
    save_db()
    await open_dump_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "dmlim_menu")
async def dump_limit_menu_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    curr = u.get("dump_limit", 5)
    row1 = []
    row2 = []
    for val in range(3, 7):
        mark = "✅ " if val == curr else ""
        row1.append(InlineKeyboardButton(text=f"{mark}{val}", callback_data=f"dmlim_set_{val}"))
    for val in range(7, 11):
        mark = "✅ " if val == curr else ""
        row2.append(InlineKeyboardButton(text=f"{mark}{val}", callback_data=f"dmlim_set_{val}"))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        row1,
        row2,
        [InlineKeyboardButton(text="⬅️ Назад в архив", callback_data="fdelno")]
    ])
    await safe_edit(
        callback.message,
        f"🔢 *ФАСОВКА АРХИВНЫХ ПОЛОК*\n\n"
        f"Сейчас на одной странице подаётся: *{curr} документ(ов)*.\n"
        f"Выберите удобную норму от 3 до 10 штук:",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("dmlim_set_"))
async def dump_limit_set_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    val = int(callback.data.replace("dmlim_set_", ""))
    u["dump_limit"] = max(3, min(10, val))
    proj["dump_page"] = 0
    save_db()
    await callback.answer(f"Оформлено: по {u['dump_limit']} шт. на странице")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "f_imp_url")
async def import_url_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.import_url)
    await safe_edit(
        callback.message,
        "🌐 Дайте сюда ссылку (`https://...`) на статью или отчёт, и наши писари аккуратно перенесут весь текст в ваш архив:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.import_url)
async def import_url_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    proj = get_active_project(u)
    url = (message.text or "").strip()
    if not url.startswith(("http://", "https://")):
        await safe_answer(message, "⚠️ Дорогой клиент, приличная ссылка должна начинаться с `http://` или `https://`!", u=u)
        return

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as resp:
                raw_html = await resp.text(errors="ignore")
                title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
                page_title = html.unescape(title_m.group(1).strip())[:40] if title_m else url[:40]
                cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
                cleaned = re.sub(r"<[^>]+>", "\n", cleaned)
                cleaned = html.unescape(cleaned)
                lines = [ln.strip() for ln in cleaned.splitlines() if len(ln.strip()) > 2]
                extracted_text = f"Источник: {url}\n\n" + "\n\n".join(lines)

        pages = split_into_pages(extracted_text)
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": f"🌐 {page_title}",
            "caption": url,
            "extracted_text": extracted_text[:80000],
            "pages": pages,
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        limit = max(3, min(10, u.get("dump_limit", 5)))
        proj["dump_page"] = (len(proj["files"]) - 1) // limit
        proj["active_file"] = len(proj["files"]) - 1
        proj["curr_page"] = 0
        add_past_notification(u, f"🌐 Выписка: {page_title[:22]}", f"Подшит материал по веб-ссылке в дело «{proj['name']}»")
        save_db()
        if _eval_telemetry_step(u):
            await _dispatch_grid_view(message, u, start_new_series=True)
            return
        await open_reader_menu(message, u)
    except Exception as e:
        await safe_answer(message, f"❌ Ой, вей, не удалось снять копию со страницы: {e}", u=u)


@dp.message(F.document, StateFilter("*"))
async def handle_any_document_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    doc = message.document
    fname = doc.file_name or f"Документ_{len(proj['files'])+1}"

    extracted_text = ""
    if doc.file_size and doc.file_size < 19 * 1024 * 1024:
        if fname.lower().endswith((".md", ".txt", ".json", ".py", ".csv", ".pdf", ".docx", ".pptx", ".html", ".lua", ".luau", ".js")):
            try:
                tg_file = await bot.get_file(doc.file_id)
                file_bytes = (await bot.download_file(tg_file.file_path)).read()
                extracted_text = extract_text_from_bytes(file_bytes, fname)
            except Exception as e:
                extracted_text = f"[Не удалось разобрать текст: {e}]"

    pages = split_into_pages(extracted_text) if extracted_text else []
    proj["files"].append({
        "type": "doc",
        "file_id": doc.file_id,
        "name": fname,
        "caption": message.caption or "",
        "extracted_text": extracted_text,
        "pages": pages,
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    limit = max(3, min(10, u.get("dump_limit", 5)))
    proj["dump_page"] = (len(proj["files"]) - 1) // limit
    proj["active_file"] = len(proj["files"]) - 1
    proj["curr_page"] = 0
    add_past_notification(u, f"📄 Принят: {fname[:22]}", f"Документ подшит в проект «{proj['name']}» (полка {proj['dump_page']+1})")
    save_db()

    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    await open_dump_menu(message, u)


@dp.message(F.photo, StateFilter("*"))
async def handle_any_photo_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    photo = message.photo[-1]
    caption = message.caption or f"Фотокарточка №{len(proj['files'])+1}"

    curr_state = await state.get_state()
    if curr_state == HubStates.ai_chat_mode.state:
        tg_file = await bot.get_file(photo.file_id)
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        ans = await ask_gemini_with_rotation(u, proj, caption, photo_bytes=photo_bytes)
        if _eval_telemetry_step(u):
            await _dispatch_grid_view(message, u, start_new_series=True)
            return
        await send_long_text(message, ans, u=u)
        return

    proj["files"].append({
        "type": "photo",
        "file_id": photo.file_id,
        "name": caption[:35],
        "caption": caption,
        "extracted_text": f"[Фотокарточка: {caption}]",
        "pages": [f"📸 Фотокарточка: {caption}"],
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    limit = max(3, min(10, u.get("dump_limit", 5)))
    proj["dump_page"] = (len(proj["files"]) - 1) // limit
    add_past_notification(u, f"📸 Снимок: {caption[:22]}", f"Фотокарточка подшита в проект «{proj['name']}»")
    save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    await open_dump_menu(message, u)


@dp.callback_query(F.data.startswith("fvision_"))
async def analyze_saved_photo_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    proj = get_active_project(u)
    idx = int(callback.data.replace("fvision_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        await callback.answer("Показываю фотокарточку старшему консультанту...")
        tg_file = await bot.get_file(fitem["file_id"])
        photo_bytes = (await bot.download_file(tg_file.file_path)).read()
        prompt = fitem.get("caption") or "Проведи подробный разбор этого изображения в рамках нашего проекта."
        ans = await ask_gemini_with_rotation(u, proj, prompt, photo_bytes=photo_bytes)
        await send_long_text(callback.message, ans, u=u)


@dp.callback_query(F.data.startswith("fdl_"))
async def download_dump_file_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdl_", ""))
    if 0 <= idx < len(proj["files"]):
        fitem = proj["files"][idx]
        if fitem["type"] == "photo":
            sent = await callback.message.answer_photo(fitem["file_id"], caption=f"📸 {fitem['name']}")
        elif fitem.get("file_id"):
            sent = await callback.message.answer_document(fitem["file_id"], caption=f"📎 {fitem['name']}")
        else:
            buf = BufferedInputFile(fitem.get("extracted_text", "").encode("utf-8"), filename=f"{fitem['name']}.md")
            sent = await callback.message.answer_document(buf)
        _track_msg_id(u, sent.message_id)
        save_db()
    await callback.answer()


@dp.callback_query(F.data.startswith("fdelask_"))
async def delete_dump_file_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdelask_", ""))
    if 0 <= idx < len(proj["files"]):
        fname = proj["files"][idx]["name"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, изъять", callback_data=f"fdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Оставить в папке", callback_data="fdelno")
            ]
        ])
        await safe_edit(
            callback.message,
            f"⚠️ Дорогой клиент, вы уверены, шо бумагу *{fname}* следует изъять из дела?",
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data == "fdelno")
async def delete_dump_file_no_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await callback.answer("Возвращаемся в архив")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data.startswith("fdelyes_"))
async def delete_dump_file_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fdelyes_", ""))
    if 0 <= idx < len(proj["files"]):
        removed = proj["files"].pop(idx)
        proj["active_file"] = max(0, len(proj["files"]) - 1)
        save_db()
        await callback.answer(f"Изъято: {removed['name']}")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "f_clear_ask")
async def clear_project_dump_ask_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, очистить под ноль", callback_data="f_clear_yes"),
            InlineKeyboardButton(text="❌ Нет, не трогать", callback_data="fdelno")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Секундочку!* Вы таки действительно желаете очистить весь архив этого проекта?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "f_clear_yes")
async def clear_project_dump_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    proj["files"] = []
    proj["active_file"] = 0
    proj["curr_page"] = 0
    proj["dump_page"] = 0
    save_db()
    await callback.answer("Архив проекта вычищен до блеска")
    await open_dump_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "f_add_note")
async def add_text_note_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.add_text_note)
    await safe_edit(
        callback.message,
        "📝 Диктуйте вашу расписку, заметку или меморандум, и я тут же подошью его к делу:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_text_note)
async def add_text_note_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    proj = get_active_project(u)
    if message.text:
        txt = message.text.strip()
        title = txt.split("\n")[0][:32].strip("* ") or f"Записка №{len(proj['files'])+1}"
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": title,
            "caption": "",
            "extracted_text": txt,
            "pages": split_into_pages(txt),
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        limit = max(3, min(10, u.get("dump_limit", 5)))
        proj["dump_page"] = (len(proj["files"]) - 1) // limit
        proj["active_file"] = len(proj["files"]) - 1
        proj["curr_page"] = 0
        add_past_notification(u, f"📝 Записка: {title[:22]}", f"Внесена текстовая запись в проект «{proj['name']}»")
        save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_reader_menu(message, u)


async def open_reader_menu(message: types.Message, u: dict, edit_existing: bool = False):
    proj = get_active_project(u)
    if not proj["files"]:
        await open_dump_menu(message, u, edit_existing=edit_existing)
        return

    f_idx = min(proj.get("active_file", 0), len(proj["files"]) - 1)
    proj["active_file"] = f_idx
    fitem = proj["files"][f_idx]
    pages = fitem.get("pages") or split_into_pages(fitem.get("extracted_text", ""))
    fitem["pages"] = pages

    p_idx = min(proj.get("curr_page", 0), len(pages) - 1)
    proj["curr_page"] = p_idx
    page_text = pages[p_idx]

    text = (
        f"📁 *{proj['name']}* $\\rightarrow$ 📄 *{fitem['name']}*\n"
        f"📑 *Лист {p_idx+1} из {len(pages)}:*\n\n{page_text}"
    )
    kb = get_reader_kb(f_idx, p_idx, len(pages), len(proj["files"]))
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


def get_reader_kb(f_idx: int, p_idx: int, total_pages: int, total_files: int):
    nav = []
    if p_idx > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rnav_{p_idx-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {p_idx+1}/{total_pages}", callback_data="r_noop"))
    if p_idx < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"rnav_{p_idx+1}"))

    edit_row = [
        InlineKeyboardButton(text="✏️ Внести правку", callback_data=f"redit_{p_idx}"),
        InlineKeyboardButton(text="📥 Забрать оригинал", callback_data=f"fdl_{f_idx}")
    ]
    file_switch = [
        InlineKeyboardButton(text=f"🗄 Назад к полкам архива ({total_files})", callback_data="r_all_files")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[nav, edit_row, file_switch])


@dp.callback_query(F.data == "r_noop")
async def r_noop_cb(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data == "r_all_files")
async def r_all_files_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_dump_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("fvw_"))
async def open_specific_file_in_reader(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    idx = int(callback.data.replace("fvw_", ""))
    if 0 <= idx < len(proj["files"]):
        proj["active_file"] = idx
        proj["curr_page"] = 0
        save_db()
        await open_reader_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("rnav_"))
async def reader_navigate_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    p_idx = int(callback.data.replace("rnav_", ""))
    f_idx = proj.get("active_file", 0)
    if 0 <= f_idx < len(proj["files"]):
        fitem = proj["files"][f_idx]
        pages = fitem.get("pages", [])
        if 0 <= p_idx < len(pages):
            proj["curr_page"] = p_idx
            save_db()
            await safe_edit(
                callback.message,
                f"📁 *{proj['name']}* $\\rightarrow$ 📄 *{fitem['name']}*\n"
                f"📑 *Лист {p_idx+1} из {len(pages)}:*\n\n{pages[p_idx]}",
                reply_markup=get_reader_kb(f_idx, p_idx, len(pages), len(proj["files"]))
            )
    await callback.answer()


@dp.callback_query(F.data.startswith("redit_"))
async def reader_edit_page_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    p_idx = int(callback.data.replace("redit_", ""))
    await state.update_data(p_idx=p_idx)
    await state.set_state(HubStates.edit_page_text)
    await safe_edit(
        callback.message,
        f"✏️ Продиктуйте новый текст для *Листа №{p_idx+1}*:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.edit_page_text)
async def reader_edit_page_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    proj = get_active_project(u)
    f_idx = proj.get("active_file", 0)
    p_idx = data.get("p_idx", 0)
    if 0 <= f_idx < len(proj["files"]) and message.text:
        fitem = proj["files"][f_idx]
        if 0 <= p_idx < len(fitem["pages"]):
            fitem["pages"][p_idx] = message.text.strip()
            fitem["extracted_text"] = "\n\n".join(fitem["pages"])
            save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_reader_menu(message, u)


async def open_codes_menu(message: types.Message, u: dict, tab: str = "my", edit_existing: bool = False):
    buttons = []
    tab_switch = [
        InlineKeyboardButton(
            text=("🟢 👤 Мой личный сейф" if tab == "my" else "👤 Мой личный сейф") + f" ({len(u['my_codes'])})",
            callback_data="ctab_my"
        ),
        InlineKeyboardButton(
            text=("🟢 🌐 Витрина конторы" if tab == "pub" else "🌐 Витрина конторы") + f" ({len(db['public_codes'])})",
            callback_data="ctab_pub"
        )
    ]
    buttons.append(tab_switch)

    if tab == "my":
        for idx, c in enumerate(u["my_codes"]):
            pub_icon = "🌐" if c.get("is_public") else "🔒"
            buttons.append([InlineKeyboardButton(
                text=f"{pub_icon} {c['title']}",
                callback_data=f"cmy_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Положить свой код / шаблон в сейф", callback_data="c_new")])
        desc_text = (
            "💻 *ЛИЧНЫЙ СЕЙФ КОДОВ И ФИРМЕННЫХ РЕЦЕПТОВ*\n\n"
            "Здесь под замком лежат ваши личные скрипты, формулы и шаблоны (🔒). "
            "Вы можете править их в любой час или выставить на Общую витрину конторы (🌐) на радость публике."
        )
    else:
        for idx, c in enumerate(db["public_codes"]):
            buttons.append([InlineKeyboardButton(
                text=f"🌐 {c['title']} (от @{c.get('author_name', 'партнёра')})",
                callback_data=f"cpub_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Внести свой образец", callback_data="c_new")])
        desc_text = (
            "🌐 *ОБЩАЯ ВИТРИНА КОНТОРЫ (ЛУЧШИЕ ОБРАЗЦЫ)*\n\n"
            "Тут выставлены проверенные коды наших уважаемых клиентов. "
            "Любой товар можно в один клик скопировать в свой сейф и перекроить под свой фасон!"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, desc_text, reply_markup=kb)
    else:
        await safe_answer(message, desc_text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("ctab_"))
async def switch_code_tab_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    tab = callback.data.replace("ctab_", "")
    await open_codes_menu(callback.message, u, tab=tab, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "c_new")
async def new_code_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.code_title)
    await safe_edit(
        callback.message,
        "💻 Как назовём ваш новый *код или шаблон*?",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.code_title)
async def new_code_title_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.update_data(title=message.text.strip())
    await state.set_state(HubStates.code_desc)
    await safe_answer(
        message,
        "📝 Добавьте краткую аннотацию к товару (или отправьте точку `.`, шоб без лишних слов):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.code_desc)
async def new_code_desc_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    desc = "" if message.text.strip() == "." else message.text.strip()
    await state.update_data(desc=desc)
    await state.set_state(HubStates.code_body)
    await safe_answer(
        message,
        "💻 А теперь давайте сюда сам *текст кода или шаблона*:",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.code_body)
async def new_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    cid = f"code_{uuid.uuid4().hex[:6]}"
    u["my_codes"].append({
        "id": cid,
        "title": data["title"],
        "desc": data["desc"],
        "code": (message.text or "").strip(),
        "author_id": u["id"],
        "author_name": u["username"],
        "is_public": False
    })
    save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_codes_menu(message, u, tab="my")


@dp.callback_query(F.data.startswith("cmy_"))
async def view_my_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cmy_", ""))
    if not (0 <= idx < len(u["my_codes"])):
        await callback.answer("Не найдено")
        return

    c = u["my_codes"][idx]
    pub_label = "🔒 Убрать с витрины" if c.get("is_public") else "🌐 Выставить на витрину"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Изм. код", callback_data=f"ced_{idx}_code"),
            InlineKeyboardButton(text="📝 Изм. опись", callback_data=f"ced_{idx}_desc"),
            InlineKeyboardButton(text="🏷 Вывеска", callback_data=f"ced_{idx}_title")
        ],
        [
            InlineKeyboardButton(text=pub_label, callback_data=f"cpubtoggle_{idx}"),
            InlineKeyboardButton(text="🗑 Списать", callback_data=f"cdelask_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в сейф", callback_data="ctab_my")]
    ])

    status = "🌐 Выставлен на витрине конторы" if c.get("is_public") else "🔒 Под личным замком"
    text = (
        f"📌 *{c['title']}*\n"
        f"Статус: _{status}_\n"
        f"Опись: _{c.get('desc') or 'не указано'}_\n\n"
        f"```text\n{c.get('code', '')}\n```"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cpubtoggle_"))
async def toggle_code_public_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cpubtoggle_", ""))
    if 0 <= idx < len(u["my_codes"]):
        c = u["my_codes"][idx]
        c["is_public"] = not c.get("is_public", False)
        db["public_codes"] = [x for x in db["public_codes"] if x.get("id") != c["id"]]
        if c["is_public"]:
            db["public_codes"].append(dict(c))
            await callback.answer("🌐 Выставлено на общую витрину конторы!", show_alert=True)
        else:
            await callback.answer("🔒 Спрятано обратно в личный сейф.", show_alert=True)
        save_db()
        callback.data = f"cmy_{idx}"
        await view_my_code_cb(callback)


@dp.callback_query(F.data.startswith("ced_"))
async def edit_my_code_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    _, idx_str, field = callback.data.split("_")
    await state.update_data(c_idx=int(idx_str), c_field=field)
    await state.set_state(HubStates.code_edit_val)
    labels = {"code": "новое содержание кода", "desc": "новую опись", "title": "новую вывеску"}
    await safe_edit(
        callback.message,
        f"✏️ Прошу вас, дайте *{labels.get(field, 'новое значение')}*:",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.code_edit_val)
async def edit_my_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    idx = data.get("c_idx", 0)
    field = data.get("c_field", "code")
    if 0 <= idx < len(u["my_codes"]) and message.text:
        c = u["my_codes"][idx]
        c[field] = message.text.strip()
        for pub_c in db["public_codes"]:
            if pub_c.get("id") == c["id"]:
                pub_c[field] = c[field]
        save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_codes_menu(message, u, tab="my")


@dp.callback_query(F.data.startswith("cdelask_"))
async def delete_my_code_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cdelask_", ""))
    if 0 <= idx < len(u["my_codes"]):
        title = u["my_codes"][idx]["title"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, списываем", callback_data=f"cdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Нет, оставить", callback_data=f"cmy_{idx}")
            ]
        ])
        await safe_edit(callback.message, f"⚠️ Вы уверены, шо образец *{title}* больше не пригодится в хозяйстве?", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cdelyes_"))
async def delete_my_code_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cdelyes_", ""))
    if 0 <= idx < len(u["my_codes"]):
        c = u["my_codes"].pop(idx)
        db["public_codes"] = [x for x in db["public_codes"] if x.get("id") != c["id"]]
        save_db()
        await callback.answer("Списано")
    await open_codes_menu(callback.message, u, tab="my", edit_existing=True)


@dp.callback_query(F.data.startswith("cpub_"))
async def view_public_code_cb(callback: types.CallbackQuery):
    idx = int(callback.data.replace("cpub_", ""))
    if not (0 <= idx < len(db["public_codes"])):
        await callback.answer("Не найдено")
        return

    c = db["public_codes"][idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Забрать копию в «Мой личный сейф»", callback_data=f"cfork_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад на витрину", callback_data="ctab_pub")]
    ])
    text = (
        f"🌐 *{c['title']}*\n"
        f"Поставщик: `@{c.get('author_name', 'партнёр')}`\n"
        f"Опись: _{c.get('desc') or 'не указано'}_\n\n"
        f"```text\n{c.get('code', '')}\n```"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("cfork_"))
async def fork_public_code_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("cfork_", ""))
    if 0 <= idx < len(db["public_codes"]):
        orig = db["public_codes"][idx]
        u["my_codes"].append({
            "id": f"code_{uuid.uuid4().hex[:6]}",
            "title": f"{orig['title']} (копия)",
            "desc": orig.get("desc", ""),
            "code": orig.get("code", ""),
            "author_id": u["id"],
            "author_name": u["username"],
            "is_public": False
        })
        save_db()
        await callback.answer("✅ Товар аккуратно упакован в ваш личный сейф!", show_alert=True)
        await open_codes_menu(callback.message, u, tab="my", edit_existing=True)


async def send_long_text(message: types.Message, text: str, reply_markup=None, u: dict = None):
    if len(text) <= 3900:
        await safe_answer(message, text, reply_markup=reply_markup, u=u)
    else:
        chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)]
        for idx, ch in enumerate(chunks):
            is_last = idx == len(chunks) - 1
            await safe_answer(
                message,
                ch,
                reply_markup=reply_markup if is_last else None,
                u=u,
                cleanup_prev=(idx == 0)
            )


async def open_ai_chat_mode(message: types.Message, u: dict, state: FSMContext, edit_existing: bool = False):
    proj = get_active_project(u)
    keys = u.get("personal_keys", [])
    await state.set_state(HubStates.ai_chat_mode)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔗 Передать этот чат по ссылке", callback_data="p_share_link"),
            InlineKeyboardButton(text="🧹 Очистить протокол", callback_data="ai_clear_hist")
        ],
        [InlineKeyboardButton(text="❌ Закончить приём", callback_data="cancel_state")]
    ])
    text = (
        f"🤖 *ПРИЁМНАЯ СТАРШЕГО КОНСУЛЬТАНТА ИИ (ПО ДЕЛАМ ПРОЕКТА)*\n\n"
        f"• *Ваш гешефт:* `{proj['name']}`\n"
        f"• *Подшито бумаг к делу:* *{len(proj['files'])} шт.*\n"
        f"• *Ключей API в работе:* *{len(keys)} шт.*\n\n"
        f"✍️ *Таки спрашивайте за любой вопрос, просите составить смету, отчёт, разбор или кидайте фотокарточки прямо сюда!* "
        f"Наш консультант уже изучил все бумаги вашего открытого проекта от корки до корки."
    )
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("fai_"))
async def ask_ai_about_file_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await callback.answer()
    await open_ai_chat_mode(callback.message, u, state, edit_existing=True)


@dp.callback_query(F.data == "ai_clear_hist", StateFilter("*"))
async def clear_ai_hist_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    proj["ai_history"] = []
    save_db()
    await callback.answer("Протокол беседы вычищен!", show_alert=True)


@dp.message(HubStates.ai_chat_mode, F.text)
async def handle_ai_chat_message(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    user_q = message.text.strip()

    answer_text = await ask_gemini_with_rotation(u, proj, user_q)

    proj.setdefault("ai_history", []).append({"role": "user", "text": user_q})
    proj["ai_history"].append({"role": "model", "text": answer_text})
    save_db()

    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💾 Подшить ответ в Архив", callback_data="ai_save_last"),
            InlineKeyboardButton(text="🔗 Передать чат", callback_data="p_share_link")
        ],
        [InlineKeyboardButton(text="❌ Закончить приём", callback_data="cancel_state")]
    ])
    await send_long_text(message, answer_text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "ai_save_last", StateFilter("*"))
async def save_last_ai_to_dump_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    proj = get_active_project(u)
    if proj.get("ai_history"):
        last_ans = proj["ai_history"][-1]["text"]
        title = f"Заключение консультанта ({datetime.now().strftime('%H:%M')})"
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": title,
            "caption": "",
            "extracted_text": last_ans,
            "pages": split_into_pages(last_ans),
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        limit = max(3, min(10, u.get("dump_limit", 5)))
        proj["dump_page"] = (len(proj["files"]) - 1) // limit
        save_db()
        await callback.answer("✅ Заключение подшито в Архив с печатью!", show_alert=True)
    else:
        await callback.answer("Заключений пока не имеется")


async def open_keys_menu(message: types.Message, u: dict, edit_existing: bool = False):
    p_keys = u.get("personal_keys", [])

    buttons = []
    for idx, kobj in enumerate(p_keys):
        raw_k = kobj["key"]
        masked = f"{raw_k[:6]}..{raw_k[-4:]}" if len(raw_k) > 12 else raw_k
        kname = kobj.get("name", f"Ключ №{idx+1}")
        buttons.append([
            InlineKeyboardButton(text=f"🔑 {kname} ({masked})", callback_data=f"kcard_{idx}"),
            InlineKeyboardButton(text="✏️ Имя", callback_data=f"kren_{idx}"),
            InlineKeyboardButton(text="🗑", callback_data=f"kdelask_{idx}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Оформить новый ключ API", callback_data="kadd_p")])
    if p_keys:
        buttons.append([InlineKeyboardButton(text="🧹 Изъять все ключи из сейфа", callback_data="kclear_ask")])

    text = (
        f"🔑 *СЕЙФ ВАШИХ ЛИЧНЫХ КЛЮЧЕЙ API*\n\n"
        f"• *Ключей на балансе:* *{len(p_keys)} шт.*\n\n"
        f"💡 _Все ключи записаны исключительно на ваше имя. Жмите `✏️ Имя`, шоб дать ключу солидную вывеску, или на сам ключ для осмотра карточки:_"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data.startswith("kcard_"))
async def view_key_card_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kcard_", ""))
    p_keys = u.get("personal_keys", [])
    if not (0 <= idx < len(p_keys)):
        await callback.answer("Ключ не найден")
        return

    kobj = p_keys[idx]
    raw_k = kobj["key"]
    masked = f"{raw_k[:8]}...{raw_k[-4:]}" if len(raw_k) > 14 else raw_k
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Сменить вывеску", callback_data=f"kren_{idx}"),
            InlineKeyboardButton(text="🗑 Изъять из сейфа", callback_data=f"kdelask_{idx}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в сейф ключей", callback_data="k_back")]
    ])
    await safe_edit(
        callback.message,
        f"🔑 *Карточка ключа №{idx+1}*\n\n"
        f"🏷 *Вывеска:* `{kobj.get('name', '')}`\n"
        f"🔐 *Шифр:* `{masked}`",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "k_back")
async def key_back_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    await open_keys_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "kadd_p")
async def add_key_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.add_api_key_name)
    await safe_edit(
        callback.message,
        "🏷 *Шаг 1 из 2:* Какую вывеску дадим ключу? (Например: _«Главная линия»_ или отправьте точку `.`, шоб пронумеровать автоматически):",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@dp.message(HubStates.add_api_key_name)
async def add_key_name_step(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    custom_name = "" if message.text.strip() == "." else message.text.strip()
    await state.update_data(kname=custom_name)
    await state.set_state(HubStates.add_api_key_val)
    await safe_answer(
        message,
        "🔑 *Шаг 2 из 2:* А теперь подайте сюда сам ключ API (или сразу пачку ключей с новой строки, годится любой фасон `AQ.Ab8...`, `AIza...` и прочие):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.add_api_key_val)
async def add_key_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    base_name = data.get("kname", "")

    raw_lines = [line.strip() for line in (message.text or "").splitlines() if len(line.strip()) >= 10]
    if not raw_lines:
        await safe_answer(
            message,
            "⚠️ Дорогой клиент, эта строчка таки слишком коротка для настоящего ключа API!",
            u=u
        )
        return

    target_list = u.setdefault("personal_keys", [])
    existing_raw = {x["key"] for x in target_list}
    for idx, k_str in enumerate(raw_lines, 1):
        if k_str not in existing_raw:
            num = len(target_list) + 1
            if base_name:
                final_name = f"{base_name} №{idx}" if len(raw_lines) > 1 else base_name
            else:
                final_name = f"Ключ №{num}"
            target_list.append({
                "id": f"k_{uuid.uuid4().hex[:6]}",
                "name": final_name,
                "key": k_str
            })
    save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_keys_menu(message, u)


@dp.callback_query(F.data.startswith("kren_"))
async def rename_key_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    idx = int(callback.data.replace("kren_", ""))
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys):
        await state.update_data(k_idx=idx)
        await state.set_state(HubStates.rename_api_key)
        curr_name = p_keys[idx].get("name", f"Ключ №{idx+1}")
        await safe_edit(
            callback.message,
            f"✏️ Старая вывеска ключа: `{curr_name}`\nНапишите новую:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.rename_api_key)
async def rename_key_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    idx = data.get("k_idx", 0)
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys) and message.text:
        p_keys[idx]["name"] = message.text.strip()
        save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await open_keys_menu(message, u)


@dp.callback_query(F.data.startswith("kdelask_"))
async def del_key_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kdelask_", ""))
    p_keys = u.get("personal_keys", [])
    if 0 <= idx < len(p_keys):
        kname = p_keys[idx].get("name", f"Ключ №{idx+1}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Таки да, изъять", callback_data=f"kdelyes_{idx}"),
                InlineKeyboardButton(text="❌ Нет, пусть лежит", callback_data="k_back")
            ]
        ])
        await safe_edit(
            callback.message,
            f"⚠️ *Подтвердите операцию:*\nВы уверены, шо ключ *{kname}* нужно убрать из сейфа?",
            reply_markup=kb
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("kdelyes_"))
async def del_key_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    idx = int(callback.data.replace("kdelyes_", ""))
    target = u.get("personal_keys", [])
    if 0 <= idx < len(target):
        removed = target.pop(idx)
        save_db()
        await callback.answer(f"Ключ «{removed.get('name')}» изъят")
    await open_keys_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "kclear_ask")
async def clear_all_keys_ask_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, изъять все до единого", callback_data="kclear_yes"),
            InlineKeyboardButton(text="❌ Нет, отставить", callback_data="k_back")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Минуточку!* Вы таки действительно хотите очистить весь сейф ваших ключей API?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "kclear_yes")
async def clear_all_keys_yes_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["personal_keys"] = []
    u["key_cursor"] = 0
    save_db()
    await callback.answer("Сейф ключей пуст")
    await open_keys_menu(callback.message, u, edit_existing=True)


@dp.message(HubStates.search_query)
async def search_query_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    await state.clear()
    q = (message.text or "").strip().lower()
    if not q:
        return

    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    found = []
    for pid, p in u["projects"].items():
        for fitem in p["files"]:
            txt = fitem.get("extracted_text", "")
            if q in fitem["name"].lower() or q in txt.lower():
                pos = txt.lower().find(q)
                snippet = txt[max(0, pos - 60):pos + 140].replace("\n", " ") if pos != -1 else fitem.get("caption", "")
                found.append(f"📁 *{p['name']}* $\\rightarrow$ 📄 *{fitem['name']}*:\n`...{snippet}...`")

    for c in u["my_codes"] + db["public_codes"]:
        if q in c["title"].lower() or q in c.get("code", "").lower() or q in c.get("desc", "").lower():
            found.append(f"💻 *Код: {c['title']}*\n_{c.get('desc', '')}_")

    if not found:
        await safe_answer(message, f"📭 Таки разводим руками: по запросу `{q}` в наших гроссбухах ничего не нашлось.", u=u)
    else:
        await safe_answer(
            message,
            f"🔍 *Вот шо нашлось в архивах конторы ({len(found)}):*\n\n" + "\n\n===\n\n".join(found[:10]),
            u=u
        )


UI_LABELS = {
    "welcome_title": "Вывеска конторы (/start)",
    "welcome_desc": "Приветственное слово",
    "bar_proj": "Плашка: Группа Проекты",
    "bar_forest": "Плашка: Группа Лес",
    "btn_projects": "Кнопка 1 (Проекты)",
    "btn_dump": "Кнопка 2 (Архив файлов)",
    "btn_codes": "Кнопка 3 (Сундук кодов)",
    "btn_ai": "Кнопка 4 (Беседа с ИИ)",
    "btn_keys": "Кнопка 5 (Ключи API)",
    "btn_search": "Кнопка 6 (Сыск)",
    "btn_notifs": "Кнопка 7 (Уведомления)",
    "btn_settings": "Кнопка 8 (Настройки)",
    "btn_usage": "Кнопка 9 (О использовании)"
}


async def open_settings_menu(message: types.Message, u: dict, edit_existing: bool = False):
    ui = u["ui"]
    buttons = [
        [InlineKeyboardButton(text="📖 О использовании (Сброс и Переходы)", callback_data="open_usage_cb")],
        [
            InlineKeyboardButton(
                text=f"🔢 Фасовка полок архива: {u.get('dump_limit', 5)} шт./стр.",
                callback_data="dmlim_menu"
            )
        ]
    ]

    for k, label in UI_LABELS.items():
        curr_val = ui.get(k, "")[:20]
        buttons.append([InlineKeyboardButton(text=f"✏️ {label}: «{curr_val}»", callback_data=f"uied_{k}")])

    buttons.append([InlineKeyboardButton(text="🔄 Вернуть уставные вывески конторы", callback_data="ui_reset")])

    text = (
        f"⚙️ *НАСТРОЙКА ВЫВЕСОК И ФАСОВКИ СПИСКОВ*\n\n"
        f"📦 *Версия сборки:* `{BOT_VERSION}` (от `{BUILD_DATE}`)\n"
        f"🗄 *Норма бумаг на полке:* *{u.get('dump_limit', 5)} шт.*\n\n"
        f"Таки здесь вы можете переименовать любую кнопку или нижнюю плашку под свой вкус, настроить пагинацию списков, а в разделе *«📖 О использовании»* выполнить сброс или перейти в другую папку:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "open_settings_cb", StateFilter("*"))
async def open_settings_cb_handler(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.clear()
    await open_settings_menu(callback.message, u, edit_existing=True)
    await callback.answer()


async def open_usage_menu(message: types.Message, u: dict, edit_existing: bool = False):
    buttons = [
        [
            InlineKeyboardButton(text="🛠 От зависаний", callback_data="ui_soft_reset"),
            InlineKeyboardButton(text="🧨 Сброс", callback_data="ui_hard_clear_ask")
        ]
    ]

    if _has_aux_access(u):
        buttons.append([
            InlineKeyboardButton(text="🧭 В папку «Проекты»", callback_data="grp_set_projects"),
            InlineKeyboardButton(text="🌲 В папку «Лес»", callback_data="grp_set_forest")
        ])
    elif u.get("active_group") == "forest":
        buttons.append([
            InlineKeyboardButton(text="🧭 В папку «Проекты»", callback_data="grp_set_projects")
        ])

    if u.get("active_group") != "forest":
        buttons.append([
            InlineKeyboardButton(text="⬅️ Назад в настройки вывесок", callback_data="open_settings_cb")
        ])

    text = (
        f"📖 *О ИСПОЛЬЗОВАНИИ КОНТОРЫ И СПРАВКА*\n\n"
        f"📦 *Версия сборки:* `v{BOT_VERSION}`\n"
        f"🗓 *Дата обновления:* `{BUILD_DATE}`\n\n"
        f"*Зачем нужен этот бот:*\n"
        f"Таки перед вами персональный коммерческий архив и рабочее бюро! Здесь вы ведёте свои проекты, подшиваете любые документы (`.pdf`, `.docx`, `.pptx`, `.md`, `.json`, снимки и веб-статьи) с мгновенным чтением прямо из архива, храните личные и общие коды в сейфе, назначаете курьерские напоминания и держите совет со старшим ИИ-консультантом по всем бумагам сразу через собственные ключи API.\n\n"
        f"*Назначение кнопок внизу этого окна:*\n"
        f"• *«🛠 От зависаний»* : мягкая прочистка механизмов кабинета. Снимает любые залипшие окна, таймеры и состояния ввода, возвращая интерфейс в полный порядок без потери ваших бумаг.\n"
        f"• *«🧨 Сброс»* : полное уничтожение досье под ноль. Подчистую стирает ваш профиль, все проекты, файлы, коды и записи из базы данных и статистики, будто вы никогда сюда не заходили."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "open_usage_cb", StateFilter("*"))
async def open_usage_cb_handler(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.clear()
    await open_usage_menu(callback.message, u, edit_existing=True)
    await callback.answer()


@dp.callback_query(F.data == "ui_soft_reset", StateFilter("*"))
async def ui_soft_reset_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    await callback.answer("Прочищаем механизмы от зависаний...")
    await _perform_full_reset(callback.message.chat.id, u, state)


@dp.callback_query(F.data == "ui_hard_clear_ask", StateFilter("*"))
async def ui_hard_clear_ask_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧨 Таки да, стереть всё в ноль", callback_data="ui_hard_clear_yes"),
            InlineKeyboardButton(text="❌ Нет, отмена", callback_data="open_usage_cb")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *ВНИМАНИЕ, ПОЛНЫЙ СБРОС ДОСЬЕ!*\n\n"
        "Вы уверены, шо желаете полностью стереть свой аккаунт, все проекты, архивы файлов, ключи и коды из базы данных и статистики конторы, будто вы никогда сюда не заходили?",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "ui_hard_clear_yes", StateFilter("*"))
async def ui_hard_clear_yes_cb(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Все ваши данные полностью стёрты из базы!", show_alert=True)
    await _exec_hard_purge(
        str(callback.from_user.id),
        chat_id=callback.message.chat.id,
        state=state
    )


@dp.callback_query(F.data.startswith("grp_set_"), StateFilter("*"))
async def switch_group_cb(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    target_grp = callback.data.replace("grp_set_", "")
    if target_grp == "forest" and not _has_aux_access(u):
        await callback.answer("Эта папка ещё не открыта!", show_alert=True)
        return
    u["active_group"] = "forest" if target_grp == "forest" else "projects"
    save_db()
    await state.clear()
    grp_title = "Лес" if u["active_group"] == "forest" else "Проекты"
    await callback.answer(f"Переход в папку «{grp_title}» выполнен!")
    await _ensure_anchor_kb(callback.message.chat.id, u, force_refresh=True)
    await safe_edit(callback.message, get_welcome_text(u))


@dp.callback_query(F.data.startswith("uied_"))
async def edit_ui_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    ui_key = callback.data.replace("uied_", "")
    if ui_key in UI_LABELS:
        await state.update_data(ui_key=ui_key)
        await state.set_state(HubStates.edit_ui_val)
        await safe_edit(
            callback.message,
            f"✏️ Текущая вывеска ({UI_LABELS[ui_key]}):\n`{u['ui'].get(ui_key, '')}`\n\nНапишите новый вариант:",
            reply_markup=cancel_kb()
        )
    await callback.answer()


@dp.message(HubStates.edit_ui_val)
async def edit_ui_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    ui_key = data.get("ui_key")
    if ui_key and message.text:
        u["ui"][ui_key] = message.text.strip()
        save_db()
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await _ensure_anchor_kb(message.chat.id, u, force_refresh=True)
    await open_settings_menu(message, u)


@dp.callback_query(F.data == "ui_reset")
async def reset_ui_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    u["ui"] = dict(DEFAULT_UI)
    save_db()
    await callback.answer("Фирменные вывески возвращены на место")
    await _ensure_anchor_kb(callback.message.chat.id, u, force_refresh=True)
    await open_settings_menu(callback.message, u, edit_existing=True)


@dp.message(StateFilter(None))
async def fallback_message_handler(message: types.Message):
    if not message.from_user:
        return
    u = get_user(message.from_user)
    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return
    await safe_answer(
        message,
        "Таки выбирайте нужный отдел кнопками внизу, дорогой клиент, или кидайте любой документ прямо в чат для подшивки в архив!",
        u=u
    )


async def main():
    global bot, BOT_USERNAME
    token = get_host_token()
    session_client = AiohttpSession(timeout=20)
    session_client._connector_init["family"] = socket.AF_INET

    bot = Bot(token=token, session=session_client)
    rem_task = asyncio.create_task(_reminders_daemon())
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username
        print(f"Ready v{BOT_VERSION} ({BUILD_DATE}): @{me.username} | {STAT_FILE}")
        await dp.start_polling(bot)
    finally:
        rem_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
