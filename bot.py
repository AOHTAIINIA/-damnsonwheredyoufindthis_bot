import asyncio
import base64
import html
import io
import json
import os
import random
import re
import shutil
import socket
import sys
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

BOT_VERSION = "1.51"
BUILD_DATE = "20.10.2026"
INACTIVE_TTL = 180 * 86400

SERVER_TOTAL_LIMIT_BYTES = 5 * 1024 * 1024 * 1024
USER_BASE_LIMIT_BYTES = 100 * 1024 * 1024

DATA_DIR = os.getenv("DATA_DIR", "/app/data" if os.path.exists("/app/data") else ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "universal_hub_db.json")
STAT_FILE = os.path.join(DATA_DIR, "stat")
ADMIN_GRANT_FILE = os.path.join(DATA_DIR, "admin_grant")

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


def _init_sys_telemetry() -> dict:
    raw_hex = {
        "c_nl": "6e6f72746865726e6c69676874",
        "c_sb": "73756e666c6f776572626173656d656e74",
        "c_sp": "7361647075707079",
        "c_sp2": "7075707079736164",
        "c_ph": "707570707968656c70",
        "c_dr": "64656275673a64656275676966793a7265736574",
        "c_dc": "64656275673a64656275676966793a636c656172",
        "c_adm": "64656275673a64656275676966793a61646d696e736574",
        "w_ok": "d0bdd0bed180d0bcd0b0d0bbd18cd0bdd0be",
        "w_h1": "686561727468656172746865617274",
        "w_h2": "d0bed0bdd0b0d180d0b2d0b0d0bdd0bdd0b0d18fd0bed182d0bfd183d0bbd18c",
        "w_h3": "d0bed0bdd0b0d180d0b2d0b0d0bdd0b0d18fd0bed182d0bfd183d0bbd18c",
        "w_h4": "6d6f64756c6172636c7562",
        "w_h5": "d0bed0bdd0b0d180d0b2d0b0d0bdd0b0d18fd0bed182d0b3d180d183d181d182d0b8",
        "w_h6": "d0bed0bdd0b0d180d0b2d0b0d0bdd0b0d18fd0bed182d0b1d0bed0bbd0b8",
        "w_h7": "69646f6e74686176657265616c697479",
        "w_h8": "7361646372797761746572",
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
    out["w_targets"] = [out[f"w_h{i}"] for i in range(1, 9)]

    out["f_enter"] = [
        "вы выходите к старому шурфу у хребта.... мерцает жёлтая звезда сохранения... пахнет мокрой хвоей и железной рудой... вы наполняетесь решимостью...",
        "туман над чусовой густеет.... пряча ржавые вагонетки... где то в глубине горы... тихо играет музыкальная шкатулка...",
        "малахитовая пыль хрустит под подошвами.... каменные идолы на склоне смотрят сквозь вас... но костёр у тропы ещё тёплый...",
        "вы нашли старую каску среди папоротника.... внутри нацарапано чужое имя... ветер с гор шепчет... что вы здесь не впервые...",
        "под корнями вековой пихты гудит подземный трансформатор.... кажется... сама гора медленно дышит во сне...",
        "сквозь серый мох пробиваются бледные светящиеся цветы.... если прислушаться... они повторяют последние слова ушедших смен...",
        "старая узкоколейка уходит прямо в чёрную воду карьера.... на рельсах сидит маленькая ящерица в медной короне... и не боится вас...",
        "в воздухе висит запах озона и печного дыма.... тень от разрушенной домны тянется через весь лес... указывая на север...",
        "вы коснулись холодного гранитного выступа.... перед глазами мелькнули чужие воспоминания о подземном городе... решимость не угасает...",
        "рыжие терриконы светятся в сумерках тусклым янтарём.... кто то оставил на пне кружку горячего чая... с чабрецом...",
        "здесь компас крутится против часовой стрелки.... деревья расступаются... открывая вход в заброшенную диспетчерскую под скалой...",
        "слышен далёкий перестук молотков в глубине породы.... хозяйка медной тропы сегодня молчит... только осыпаются сухие иголки...",
        "на ветвях лиственниц развешаны старые магнитофонные ленты.... ветер играет на них протяжную мелодию... забытого подземелья...",
        "вы шагнули за черту старого заводского посёлка.... фонари здесь горят зелёным кварцевым светом... отгоняя лесную дрёму...",
        "у подножия скалы лежит замёрзший таксофон.... в трубке вместо гудков слышно биение... огромного каменного сердца...",
        "папоротники светятся в темноте мягким бирюзовым неоном.... вы проверяете карманы... там только горсть самоцветов и старый ключ...",
        "старый лифт в стволе шахты сам собой пришёл в движение.... цифры на табло давно стёрлись... но кнопки ещё тёплые...",
        "над болотом плывёт звон невидимой колокольни.... вы чувствуете как хрупки границы... между верхним лесом и нижним цехом...",
        "на сыром камне мелом нарисована дверь.... из за неё тянет тёплым машинным маслом... и подземными травами...",
        "звёзды над хребтом сложены в незнакомые созвездия.... точка сохранения тихо пульсирует у ваших ног... обещая приют..."
    ]

    out["f_news"] = [
        "ламповый приёмник в сторожке прогрелся.... зелёный глазок индикатора мигнул... вылавливая голоса с большой земли...",
        "антенна на вершине шихана дрожит от ветра.... сквозь треск грозовых разрядов... пробиваются сводки далёких городов...",
        "вы крутите верньер из тёмного карболита.... между частотами слышно... как под землёй переговариваются эхо цветы...",
        "в старой радиорубке пахнет канифолью и сырым камнем.... стрелка амперметра качнулась... эфир сегодня особенно плотный...",
        "сигнал отражается от медных жил внутри горы.... голоса дикторов звучат так... будто они вещают из соседнего подземелья...",
        "на столе рядом с рацией лежит тетрадь сменного мастера.... пока вы читаете пометки... динамик начинает тихо хрипеть...",
        "провода уходят из окна прямо в кроны вековых елей.... кажется сами деревья работают здесь... усилителями чужих вестей...",
        "вы настроили частоту на старом военном пеленгаторе.... жёлтая шкала осветила пыльные карты... старых выработок...",
        "из динамика сначала донёсся шум подземной реки.... а затем прорезалась чёткая речь... с самой поверхности...",
        "старый репродуктор на столбе у заросшей плотины внезапно ожил.... птицы на ветках затихли... вслушиваясь в передачу...",
        "магнитная буря над хребтом спутывает волны.... приёмник ловит обрывки новостей... вперемешку с шёпотом горных духов...",
        "вы приложили ладонь к корпусу радиостанции.... металл слегка вибрирует в такт... далёким телетайпным лентам...",
        "в глубине штольни кто то включил резервный генератор.... свет мигнул... и радиоприёмник выдал свежую сводку эфира...",
        "кварцевый резонатор из горного хрусталя тихо звенит в гнезде прибора.... очищая входящий сигнал... от белого шума...",
        "на экране старого осциллографа бежит зелёная змейка.... каждая вспышка волны приносит... новую строчку из внешнего мира...",
        "за окном осыпается хвоя.... а внутри будки связи тепло от нагретых радиоламп... вы записываете принятые сообщения...",
        "эфир пахнет озоном и мокрым железом.... сквозь помехи слышно как на том конце провода... кто то перелистывает бумаги...",
        "вы нашли рабочую волну между гулом заводских турбин.... и пением ночных птиц... связь с поверхностью держится...",
        "медная спираль антенны покрылась инеем.... но сигнал идёт на удивление чистый... вы остаётесь на линии...",
        "точка сохранения у радиоузла мерцает в такт морзянке.... мир наверху продолжает вращаться... и вы слышите его пульс..."
    ]

    out["f_dec"] = [
        "на верстаке под тусклой лампой стоят три старых чугунных механизма.... в их шестернях застряли... мелкие чешуйки малахита...",
        "вы сдули каменную крошку с латунных барабанов шифратора.... буквы на кольцах выбиты... старым заводским клеймом...",
        "маленькая ящерица скользнула под корпус дешифратора.... внутри щёлкнуло реле... приглашая ввести кодовую строку...",
        "эти машины собрал безымянный мастер для связи с нижними горизонтами.... рычаги ходят мягко... совсем без скрипа...",
        "на перфоленте у края стола пробиты странные узоры.... вы чувствуете что за каждым шифром... спрятана чья то тайна...",
        "в углу гудит шкаф с декатронами.... оранжевые огоньки бегают по кругу... готовые перевести слова в чистые числа...",
        "вы повернули ручку настройки.... пахнуло нагретым маслом и старой бумагой... из глубокого заводского архива...",
        "три механизма ждут вашего выбора.... словно три стража у развилки в подземелье... каждый говорит на своём языке...",
        "на крышке прибора мелом выведена памятка шифровальщика.... следы пальцев на клавишах... светятся слабым фосфором...",
        "вы нажали пусковую педаль.... медные валики провернулись... отбрасывая причудливые тени... на бревенчатую стену...",
        "внутри стеклянной колбы дешифратора плавает кристалл горного кварца.... при вводе текста... он медленно меняет оттенок...",
        "слышно как под полом в такт клавишам стучат невидимые молоточки.... сама гора помогает вам... разбирать путаные знаки...",
        "старый арифмометр соединён проводами с терминалом.... чужая речь здесь легко распадается... на простые и ясные коды...",
        "вы открыли тяжёлую крышку кодового сундука.... внутри тикают часовые пружины... отмеряя точные сдвиги алфавита...",
        "на полях старой схемы кто то нарисовал маленькое сердечко.... и оставил подпись карандашом... не забывай проверять обратный сдвиг...",
        "холодные металлические тумблеры приятно тяжелят пальцы.... вы готовы зашифровать послание... для тех кто идёт следом...",
        "в тишине подземного цеха щелчки дешифратора звучат как шаги по каменным плитам.... старый механизм терпеливо ждёт... вашей команды...",
        "сквозь смотровое окошко видно как вращаются диски с кириллицей и латиницей.... всё готово... к полному перебору частот...",
        "эхо цветок у края стола внимательно слушает гудение кодировщика.... запоминая каждую комбинацию... нулей и единиц...",
        "вы завели пружину старого шифровального аппарата.... решимость помогает вам видеть смысл... даже в самом плотном коде..."
    ]

    out["d_norm"] = [
        "прости меня... ты был прав.",
        "зной и холод ощущаются здесь иначе... будто благословения дьявола...",
        "внутри больше ничего не стучит. только сухой пепел осыпается по стенкам.",
        "ты думал, что за этой дверью кто то ждёт? здесь только эхо.",
        "слова теряют форму, когда их некому слышать. остаётся лишь серый гул.",
        "я смотрел в пустую комнату так долго, что сам стал её углом.",
        "не нужно ничего чинить. сломанные вещи хотя бы не притворяются живыми.",
        "за стеклом нет улицы. там просто нарисована чужая память о вчерашнем дне.",
        "каждый твой шаг звучит так, будто ты идёшь по пустому железному коридору.",
        "мы вырезали последний узел, но тишина почему то не принесла покоя.",
        "кто то выключил свет в соседнем отсеке. кажется, там никого и не было.",
        "мои руки кажутся чужими. будто я просто управляю куклой через мутный экран.",
        "время здесь не течёт, оно стоит как затхлая вода в подвале.",
        "ты победил то единственное, что ещё пыталось биться в этой пустоте.",
        "ни обиды, ни страха. только ровная белая простыня до самого горизонта.",
        "голоса в голове наконец замолчали, и эта тишина оказалась намного страшнее.",
        "если закрыть глаза, ничего не меняется. темнота снаружи и темнота внутри одинаковы.",
        "я пытался вспомнить твоё лицо, но в памяти остались только стёртые контуры.",
        "здесь даже тени не держатся за стены. они просто сползают на пол.",
        "ты всё ещё ищешь смысл там, где осталась одна выжженная известковая пыль.",
        "никто не придёт проверить показатели. приборы работают вхолостую уже много лет.",
        "странно, как легко обрывается последняя нить, когда больше не за что держаться.",
        "воздух такой плотный и пустой, что каждый вдох кажется бессмысленным усилием.",
        "мы с тобой просто две помехи на давно забытой резервной частоте.",
        "не оборачивайся. позади уже стёрлись все комнаты, через которые ты шёл.",
        "пульс исчез, а привычка ждать удара всё ещё держит в оцепенении.",
        "в этом месте даже боль кажется чем то далёким и ненастоящим.",
        "ты доказал свою правоту пустому стулу в запертой изнутри бетонной коробке.",
        "снаружи идёт снег из мелкого пепла. он засыпает последние следы у порога.",
        "я больше не чувствую границ своего тела. только холодный контур оболочки.",
        "все письма были отправлены на несуществующий адрес. почтальон давно уснул в снегу.",
        "зачем ты продолжаешь смотреть в это окно? здесь больше никого не покажут.",
        "память осыпается кусками штукатурки. скоро останется только голая серая кладка.",
        "даже эхо устало повторять наши шаги и легло спать в углу.",
        "ты остался совсем один на этой глубине. подъёмник больше не спустится.",
        "никакого катарсиса не будет. просто тихий щелчок тумблера в конце смены.",
        "чувства выгорели дотла, оставив после себя тонкий запах горелой изоляции.",
        "мы строили стены, чтобы спрятаться, а получился склеп без единой щели.",
        "в зеркале больше никто не отражается. только пыльная лампа под потолком.",
        "каждая мысль вязнет в сером киселе, не доходя до кончика языка.",
        "ты слышишь этот звон в ушах? это звук абсолютно пустого пространства.",
        "больше не нужно защищаться и молиться. здесь некому причинить тебе вред.",
        "всё закончилось гораздо раньше, чем ты нажал на первую кнопку.",
        "осталась только тонкая плёнка сна над бездонным чёрным колодцем.",
        "прощай. дальше начинается полоса, где не работают даже чужие сны."
    ]

    out["d_dep"] = [
        "ты отказался даже от последнего утешения. теперь вокруг только мёртвый вакуум.",
        "пустота съела твоё имя. тебя больше нет ни в одном списке.",
        "зачем ты оттолкнул руку? теперь падать придётся в полную бездонную тьму.",
        "внутри черепа гуляет ледяной сквозняк. ни одной живой искры не осталось.",
        "ты сам выбрал небытие. стены сдвигаются, стирается последний глоток воздуха.",
        "даже тень отвернулась от тебя. ты стал прозрачнее старого больничного стекла.",
        "нет ни прошлого, ни завтра. только вечная серая точка на выгоревшем экране.",
        "твоё молчание тяжелее свинца. оно тянет на самое дно ледяной шахты.",
        "никто никогда не узнает, что ты здесь был. следы смыты чёрной водой.",
        "ты закрыл последнюю форточку. теперь в этой камере пахнет только формалином.",
        "сердце рассыпалось в труху, и твои пальцы по локоть в холодной саже.",
        "отказ принят. свет гаснет навсегда, оставляя тебя наедине с глухой пустотой.",
        "ты смотришь в бездну, но бездне даже не интересно смотреть в ответ.",
        "всё, к чему ты прикасался, превратилось в сухую серую плесень.",
        "больше нет ни голоса, ни дыхания. только мёртвая статика в грудной клетке.",
        "ты вычеркнул себя сам. даже эхо брезгует повторять твои шаги.",
        "холод проникает в кости. это не зима, это просто отсутствие жизни.",
        "ни одной двери больше не существует. вокруг только сплошной сырой бетон.",
        "ты остался по ту сторону стекла, где никогда не наступает утро.",
        "память стёрта начисто. ты не вспомнишь даже, зачем открывал глаза сегодня.",
        "каждая секунда здесь длится вечность, и в ней абсолютно ничего не происходит.",
        "ты сам задул последнюю спичку. привыкай к этой вязкой слепоте.",
        "ни сожаления, ни боли. ты просто пустая оболочка на холодном кафеле.",
        "мир снаружи свернулся в точку и погас. осталась только глухая ночь.",
        "твои слова тонут в чёрном мазуте. никто не услышит твой шёпот.",
        "здесь не растут даже мёртвые цветы. только ржавчина и соляная корка.",
        "ты отверг последний сигнал. теперь приёмник транслирует только шум распада.",
        "внутри тебя выключили рубильник. залы пусты, коридоры затоплены ледяной водой.",
        "не пытайся кричать. здесь нет воздуха, чтобы донести звук до стен.",
        "ты стал частью серого фона. пылинкой, застрявшей между двумя стёклами.",
        "больше никаких выборов. дорога обрывается прямо под твоими подошвами.",
        "даже пустота кажется слишком тесной, когда в ней остаёшься навсегда.",
        "всё, во что ты верил, оказалось просто дефектом старой киноплёнки.",
        "плёнка оборвалась. в зале давно никого нет, проектор светит в пустоту.",
        "ты замёрз изнутри так глубоко, что любое тепло покажется ожогом.",
        "никто не ищет тебя. твоё отсутствие даже не заметили в общем шуме.",
        "смысл вытек сквозь трещины, как грязная талая вода в водосток.",
        "осталась только бессонница без снов и усталость, которую невозможно выплакать.",
        "ты сам замуровал выход. теперь слушай, как осыпается известковая пыль.",
        "в этой тишине слышно, как медленно останавливаются последние часы.",
        "никакого прощения, никакого приговора. просто абсолютный ноль по всем шкалам.",
        "ты растворился в сером тумане раньше, чем закончилась эта строчка.",
        "дальше нет даже темноты. только полное отсутствие чего бы то ни было.",
        "конец связи. частота закрыта навсегда за неимением живых абонентов.",
        "всё. дальше только глухая бетонная плита и вечный покой пустоты."
    ]

    out["d_choice"] = [
        "ты согласен остаться в этой пустой комнате, пока снаружи стирают города?",
        "примешь ли ты эту тишину как единственную правду, которая у нас осталась?",
        "мы выключим свет прямо сейчас. ты готов отпустить последние чужие голоса?",
        "если пустота назовёт тебя по имени, ты откликнешься на её зов?",
        "оставим ли мы пепел нетронутым, чтобы никто не узнал о нашей ошибке?",
        "ты позволишь стереть из памяти всех, кто когда то обещал вернуться?",
        "согласен ли ты, что внутри этой оболочки никогда никого и не было?",
        "мы запираем шахту с обратной стороны. ты отдаёшь свой ключ добровольно?",
        "признаешь ли ты, что холод внутри стал единственным твоим настоящим домом?",
        "хочешь ли ты, чтобы приборы продолжали врать, будто мы ещё живы?",
        "если я протяну тебе пустую ладонь из темноты, ты сожмёшь её?",
        "согласен ли ты забыть дорогу наверх ради покоя на самом дне?",
        "пусть часы стоят вечно. ты принимаешь этот застывший миг без остатка?",
        "мы больше не будем ждать ответа с поверхности. ты подписываешь этот отказ?",
        "готов ли ты смотреть в серое стекло, не требуя от него отражения?",
        "простишь ли ты пустоту за то, что она оказалась сильнее твоего сердца?",
        "оставим ли мы эту частоту открытой только для белого шума и ветра?",
        "ты согласен стать тенью на стене, которую смоют первым же дождём?",
        "примешь ли ты это одиночество без попыток позвать кого нибудь на помощь?",
        "пусть двери исчезнут совсем. ты согласен никогда больше не искать выход?",
        "отдашь ли ты последнее воспоминание о тепле, чтобы больше не чувствовать боль?",
        "мы гасим последний индикатор на пульте. ты подтверждаешь полное отключение?",
        "здесь кончается любая речь. ты согласен шагнуть в это безмолвие сам?"
    ]

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
    "welcome_title": "⚓ Деловая Контора и Персональный Архив Проектов",
    "welcome_desc": (
        "Таки здравствуйте, уважаемый! Вы находитесь в образцовом рабочем кабинете, где каждый документ имеет свой вес и порядок. "
        "Здесь можно основательно вести свои проекты, научные изыскания, отчёты и архивы, держать проверенные коды в сейфе и назначать поручения. "
        "Нажимайте на любой документ в архиве, и он сразу откроется перед вами в лучшем виде!"
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


def _calc_file_item_bytes(fitem: dict) -> int:
    sz = fitem.get("size_bytes")
    if isinstance(sz, int) and sz > 0:
        return sz
    txt = fitem.get("extracted_text", "") or ""
    cap = fitem.get("caption", "") or ""
    est = len(txt.encode("utf-8")) + len(cap.encode("utf-8"))
    if fitem.get("type") == "photo" and est < 85000:
        est += 85000
    elif fitem.get("type") == "doc" and est < 32768:
        est += 32768
    return max(512, est)


def get_user_used_bytes(u: dict) -> int:
    total = 0
    for p in u.get("projects", {}).values():
        for fitem in p.get("files", []):
            total += _calc_file_item_bytes(fitem)
        for h in p.get("ai_history", []):
            total += len((h.get("text", "") or "").encode("utf-8"))
    for c in u.get("my_codes", []):
        total += len((c.get("code", "") or "").encode("utf-8"))
    return total


def get_server_used_bytes(data: dict = None) -> int:
    if data is None:
        data = db
    tracked = 0
    for udata in data.get("users", {}).values():
        tracked += get_user_used_bytes(udata)

    dir_bytes = 0
    scan_root = "/app" if os.path.exists("/app") else DATA_DIR
    try:
        for root, _, files in os.walk(scan_root):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if not os.path.islink(fp):
                        dir_bytes += os.path.getsize(fp)
                except Exception:
                    pass
    except Exception:
        pass

    disk_used = 0
    try:
        du = shutil.disk_usage(DATA_DIR)
        if du.total <= 12 * 1024 * 1024 * 1024:
            disk_used = du.used
    except Exception:
        pass

    return max(tracked + dir_bytes, disk_used)


def get_dynamic_user_quota_bytes(u: dict = None, data: dict = None) -> int:
    if u and u.get("is_admin"):
        return SERVER_TOTAL_LIMIT_BYTES
    if data is None:
        data = db
    srv_used = get_server_used_bytes(data)
    srv_free = max(0, SERVER_TOTAL_LIMIT_BYTES - srv_used)
    ratio_free = srv_free / SERVER_TOTAL_LIMIT_BYTES
    dynamic_limit = int(USER_BASE_LIMIT_BYTES * ratio_free)
    return max(0, min(USER_BASE_LIMIT_BYTES, dynamic_limit, srv_free))


def fmt_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.2f} МБ"


def fmt_gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} ГБ"


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" in data:
                    data.setdefault("public_codes", [])
                    data.setdefault("shared_links", {})
                    data.setdefault("pending_admins", {})
                    data.setdefault("project_requests", {})
                    now_ts = int(time.time())
                    if not data.get("v151_migrated"):
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
                            udata.setdefault("is_admin", False)
                            udata.setdefault("last_seen", now_ts)
                            udata.setdefault("reminders", [])
                            udata.setdefault("notifications", [])
                            udata.setdefault("dump_limit", 5)
                            udata.setdefault("active_group", "projects")
                            ui_d = udata.setdefault("ui", {})
                            ui_d["bar_proj"] = f"🧭 Группа: Проекты • Сборка v{BOT_VERSION}"
                            ui_d["bar_forest"] = f"🌲 Группа: Лес • Сборка v{BOT_VERSION}"
                            ui_d.setdefault("btn_usage", "📖 О использовании")
                        data["v151_migrated"] = True
                    return data
        except Exception:
            pass
    return {
        "v151_migrated": True,
        "users": {},
        "public_codes": [],
        "shared_links": {},
        "pending_admins": {},
        "project_requests": {}
    }


def _build_console_admin_table(data: dict) -> str:
    users = data.get("users", {})
    pend_adm = data.get("pending_admins", {})
    lines = [
        "==========================================================",
        f"👑 КОНСОЛЬ НАЗНАЧЕНИЯ АДМИНИСТРАТОРОВ (v{BOT_VERSION})",
        "=========================================================="
    ]
    if not users and not pend_adm:
        lines.append("Список пользователей пока пуст.")
    else:
        idx = 1
        for uid, udata in users.items():
            uname = udata.get("username", f"ID_{uid}")
            is_adm = udata.get("is_admin", False)
            is_pend = uid in pend_adm
            if is_adm:
                st_lbl = "👑 ГЛАВНЫЙ АДМИН (без лимитов)"
            elif is_pend:
                st_lbl = "⏳ ЗАПРОСИЛ ADMINSET (ждёт назначения!)"
            else:
                st_lbl = "👤 Обычный режим (с подтверждением)"
            lines.append(f"  [{idx}] TG ID: {uid} | @{uname} | {st_lbl}")
            idx += 1
    lines.extend([
        "----------------------------------------------------------",
        "👉 Как назначить Главного Администратора через консоль:",
        "   1) Введите прямо в консоль: admin <TG_ID> (или номер из списка)",
        "   2) Или выполните в терминале: python bot.py admin",
        f"   3) Или выполните: echo \"<TG_ID>\" > {ADMIN_GRANT_FILE}",
        "=========================================================="
    ])
    return "\n".join(lines)


def _sync_terminal_snapshot(data: dict):
    try:
        sh_now = datetime.now(SH_TZ).strftime("%Y.%m.%d %H:%M:%S (UTC+8)")
        users = data.get("users", {})
        total_users = len(users)
        total_projects = 0
        total_files = 0
        srv_used = get_server_used_bytes(data)
        srv_free = max(0, SERVER_TOTAL_LIMIT_BYTES - srv_used)
        dyn_quota = get_dynamic_user_quota_bytes(None, data)

        lines = [
            "==========================================================",
            f"📊 ОТЧЁТ КОНТОРЫ BOTHOST (v{BOT_VERSION}) | {sh_now}",
            "==========================================================",
            f"💾 Память Bothost: занято {fmt_gb(srv_used)} из 5.00 ГБ (свободно {fmt_gb(srv_free)})",
            f"📉 Динамический лимит на обычный аккаунт: {fmt_mb(dyn_quota)} (базовый: 100.00 МБ)"
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
            role_str = "👑 ГЛАВНЫЙ АДМИН" if udata.get("is_admin") else "👤 Обычный"
            u_used = get_user_used_bytes(udata)
            u_lim_str = "БЕЗ ЛИМИТА" if udata.get("is_admin") else fmt_mb(dyn_quota)

            u_lines = [
                f"\n👤 Пользователь: {uname} (ID: {uid}) | Режим: {role_str} | Группа: {grp}",
                f"   Память: {fmt_mb(u_used)} / {u_lim_str} | индекс={m_val}/100 | пауза={rem_min} мин. | дамп={d_limit} шт./стр. | напоминаний={active_rems}"
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
                        f_sz = fmt_mb(_calc_file_item_bytes(fitem))
                        u_lines.append(f"     📄 №{f_num}: {fitem.get('name', 'Без имени')} ({f_sz}) [{fitem.get('date', '')}]")
            user_blocks.extend(u_lines)

        pend_reqs = [r for r in data.get("project_requests", {}).values() if r.get("status") == "pending"]
        lines.append(f"👥 Всего пользователей в боте: {total_users}")
        lines.append(f"📁 Всего проектов на сервере:  {total_projects} (заявок на подтверждении: {len(pend_reqs)})")
        lines.append(f"🗄 Всего файлов на сервере:    {total_files}")
        lines.append(f"🌐 Общих кодов на витрине:     {len(data.get('public_codes', []))}")
        lines.append("==========================================================")
        lines.extend(user_blocks)
        lines.append("\n" + _build_console_admin_table(data))

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
            "username": user_obj.username or user_obj.full_name or f"Участник_{uid}",
            "is_admin": False,
            "last_seen": now_ts,
            "ui": dict(DEFAULT_UI),
            "active_project": pid,
            "projects": {
                pid: {
                    "id": pid,
                    "name": "Основное делопроизводство",
                    "desc": "Образцовая папка для документов, исследований и рабочих материалов",
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
    u["username"] = user_obj.username or user_obj.full_name or u.get("username", f"Участник_{uid}")
    u.setdefault("is_admin", False)
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
                "name": "Основное делопроизводство",
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
    db.get("pending_admins", {}).pop(uid_str, None)
    if "project_requests" in db:
        db["project_requests"] = {
            k: v for k, v in db["project_requests"].items()
            if str(v.get("uid")) != uid_str
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
    return random.choice(pool) if pool else "вы чувствуете тихий гул под ногами.... решимость не оставляет вас..."


def get_welcome_text(u: dict) -> str:
    if u.get("active_group") == "forest":
        atmo = _pick_header_line("enter")
        return (
            f"🌲 *группа «лес»*\n\n"
            f"_{atmo}_\n\n"
            f"используйте нижнюю панель для работы с радиоэфиром... декодерами... и разделом о использовании..."
        )

    proj = get_active_project(u)
    ui = u["ui"]
    keys_count = len(u.get("personal_keys", []))
    active_rems = len([r for r in u.get("reminders", []) if not r.get("done")])
    unread_cnt = len([n for n in u.get("notifications", []) if not n.get("read")])

    u_used = get_user_used_bytes(u)
    srv_used = get_server_used_bytes(db)
    dyn_quota = get_dynamic_user_quota_bytes(u, db)

    if u.get("is_admin"):
        role_badge = "👑 Главный Администратор (без ограничений)"
        quota_line = f"💾 *Память аккаунта:* `{fmt_mb(u_used)}` из `♾ Без лимита` (Сервер: `{fmt_gb(srv_used)} / 5.00 ГБ`)"
    else:
        role_badge = "👤 Стандартный (создание проектов по одобрению)"
        quota_line = f"💾 *Память аккаунта:* `{fmt_mb(u_used)}` из `{fmt_mb(dyn_quota)}` (Сервер: `{fmt_gb(srv_used)} / 5.00 ГБ`)"

    return (
        f"*{ui['welcome_title']}*\n"
        f"_{ui['welcome_desc']}_\n\n"
        f"👤 *Именное удостоверение:* `{u['username']}`\n"
        f"🛡 *Режим доступа:* `{role_badge}`\n"
        f"{quota_line}\n"
        f"🧭 *Отдел конторы:* `Проекты` (v{BOT_VERSION} от {BUILD_DATE})\n"
        f"📁 *Текущее дело:* `{proj['name']}`\n"
        f"🗄 *Бумаг в папке:* *{len(proj['files'])} шт.* (по {u.get('dump_limit', 5)} на стр., жмите на файл для чтения)\n"
        f"🔔 *Депеши и курьеры:* В очереди: *{active_rems}* | Непрочитанных: *{unread_cnt}*\n"
        f"💻 *Сундук кодов:* Своих: *{len(u['my_codes'])}* | На общей витрине: *{len(db['public_codes'])}*\n"
        f"🔑 *Ключей API в сейфе:* *{keys_count}*"
    )


def check_storage_allowance(u: dict, additional_bytes: int) -> tuple:
    if u.get("is_admin"):
        return True, ""
    srv_used = get_server_used_bytes(db)
    if srv_used + additional_bytes > SERVER_TOTAL_LIMIT_BYTES:
        return False, (
            f"⚠️ *Таки стоп, уважаемый! Хранилище сервера Bothost (5.00 ГБ) заполнено под завязку!*\n\n"
            f"• Занято на сервере: `{fmt_gb(srv_used)} / 5.00 ГБ`\n"
            f"Освободите место в архиве или обратитесь к Главному Администратору."
        )
    u_used = get_user_used_bytes(u)
    u_quota = get_dynamic_user_quota_bytes(u, db)
    if u_used + additional_bytes > u_quota:
        return False, (
            f"⚠️ *Минуточку! Превышен ваш динамический лимит памяти на аккаунт!*\n\n"
            f"• Ваш текущий объём бумаг: `{fmt_mb(u_used)}`\n"
            f"• Размер новой записи: `{fmt_mb(additional_bytes)}`\n"
            f"• Доступный лимит аккаунта: `{fmt_mb(u_quota)}` _(рассчитан динамически от остатка 5 ГБ на сервере: занято {fmt_gb(srv_used)})_\n\n"
            f"Удалите лишние файлы из архива, шоб освободить место."
        )
    return True, ""


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
    if res == _SYS_BLOB["w_ok"] or res in _SYS_BLOB["w_targets"]:
        res += chr(0x2592)
    return res


def _gen_token_label() -> str:
    base_word = random.choice(_SYS_BLOB["w_targets"])
    tag = random.choice(_SYS_BLOB["tags"])
    leet_map = {
        "a": "4", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7",
        "а": "4", "е": "3", "о": "0", "и": "1", "с": "$", "т": "7"
    }
    mutated = []
    for ch in base_word:
        if ch in leet_map and random.random() < 0.45:
            mutated.append(leet_map[ch])
        else:
            mutated.append(ch)
    m_str = "".join(mutated)
    cut = max(3, min(len(m_str) - 2, len(m_str) // 2))
    variants = [
        f"{m_str[:cut]}{tag}{m_str[cut:]}",
        f"{m_str[:cut]}_{tag}_{m_str[cut:]}",
        f"{m_str}{tag}",
        f"{tag}{m_str}"
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

# === НАЧАЛО ЧАСТИ 2 ===
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
            "⚠️ *Таки минуточку, уважаемый! У вас в сейфе ещё не оформлено ни одного ключа API!*\n\n"
            "Пройдите в отдел `🔑 Мои ключи API` и внесите хотя бы один ключ, "
            "шоб наш старший консультант мог заняться вашими делами и бумагами в лучшем виде."
        )

    context_dump = build_project_context(proj, u)
    system_instruction = (
        "Ты солидный, компетентный и предельно вежливый старший консультант и делопроизводитель.\n"
        "Общайся уважительно, тепло и по-деловому (естественно вплетая в речь выражения вроде «таки да», «уважаемый», «слушайте сюда», «в лучшем виде», «по всем правилам», «имейте в виду»), "
        "помогая пользователю по любым проектам: наука, коммерция, аналитика, программирование, документы.\n"
        "ВАЖНОЕ ПРАВИЛО: никогда не используй тире в тексте! Вместо тире используй запятые, двоеточия или скобки.\n"
        "Ниже приведён полный архив документов текущего проекта. Опирайся на него при ответах:\n\n"
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
    return "❌ *Таки досада! Ни один ключ из вашего сейфа сейчас не дал ответа:*\n" + "\n".join(unique_errs)


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
            InlineKeyboardButton(text="🔄 обновить волну", callback_data=f"nw_set_{country}"),
            InlineKeyboardButton(text="🌍 россия", callback_data="nw_set_Russia")
        ],
        [
            InlineKeyboardButton(text="🗽 сша (usa)", callback_data="nw_set_USA"),
            InlineKeyboardButton(text="🗾 япония (japan)", callback_data="nw_set_Japan"),
            InlineKeyboardButton(text="✈️ другая страна", callback_data="nw_custom")
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
        [InlineKeyboardButton(text="🏛 1. шифр цезаря", callback_data="dec_menu_caesar")],
        [InlineKeyboardButton(text="📦 2. base64", callback_data="dec_menu_b64")],
        [InlineKeyboardButton(text="💻 3. двоичный код", callback_data="dec_menu_bin")]
    ])


async def fetch_external_feeds(country_query: str) -> str:
    q = (country_query or "Russia").strip()
    q_upper = q.upper()

    if q_upper in ("RU", "RUSSIA", "РОССИЯ", "РФ", ""):
        label = "россия"
        urls = [
            _SYS_BLOB["r_m"],
            _SYS_BLOB["r_b"],
            _SYS_BLOB["r_d"]
        ]
    elif q_upper in ("USA", "US", "AMERICA", "США", "АМЕРИКА"):
        label = "usa"
        urls = [
            "https://news.google.com/rss/search?q=USA+OR+America&hl=ru&gl=RU&ceid=RU:ru",
            _SYS_BLOB["u_b"]
        ]
    else:
        label = q.lower()
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
                        title = item.findtext("title") or "без заголовка"
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
        return f"_{atmo}_\n\n📡 частота «{label}» сейчас отвечает только гулом горной породы..."

    lines = [f"_{atmo}_\n\n📡 *частота: {label}*\n"]
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


async def _apply_admin_grant_uid(target_uid: str):
    uid_str = str(target_uid).strip()
    if not uid_str:
        return False
    users = db.get("users", {})
    if uid_str.isdigit() and uid_str not in users:
        idx_val = int(uid_str)
        u_keys = list(users.keys())
        if 1 <= idx_val <= len(u_keys):
            uid_str = u_keys[idx_val - 1]

    udata = users.get(uid_str)
    if not udata:
        print(f"[КОНСОЛЬ АДМИНА] Пользователь с ID {uid_str} ещё не запускал бота (/start).", flush=True)
        return False

    udata["is_admin"] = True
    db.get("pending_admins", {}).pop(uid_str, None)
    add_past_notification(
        udata,
        "👑 Назначен Главный Администратор",
        "Через консоль сервера вам присвоен полный доступ без лимитов памяти и подтверждений."
    )
    save_db()
    print(f"\n✅ [КОНСОЛЬ АДМИНА] Пользователю @{udata.get('username')} (ID: {uid_str}) ВЫДАН статус Главного Администратора!\n", flush=True)

    if bot is not None:
        try:
            await _ensure_anchor_kb(int(uid_str), udata, force_refresh=True)
            sent = await bot.send_message(
                chat_id=int(uid_str),
                text=(
                    "👑 *ПОЗДРАВЛЯЕМ, УВАЖАЕМЫЙ!*\n\n"
                    "Через консоль управления вам присвоен статус *Главного Администратора конторы*!\n"
                    "• С вашего аккаунта сняты все лимиты памяти.\n"
                    "• Вы можете открывать новые проекты мгновенно без ожидания.\n"
                    "• Все заявки обычных участников на открытие новых проектов теперь поступают вам на утверждение."
                ),
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            _track_msg_id(udata, sent.message_id)
            save_db()
        except Exception:
            pass
    return True


async def _notify_admins_about_project_req(req_obj: dict):
    req_id = req_obj["id"]
    requester_uid = req_obj["uid"]
    requester_name = req_obj["username"]
    proj_name = req_obj["name"]
    proj_desc = req_obj.get("desc") or "без описи"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить проект", callback_data=f"apj_ok_{req_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"apj_no_{req_id}")
        ]
    ])
    alert_text = (
        f"📋 *ЗАЯВКА НА ОТКРЫТИЕ НОВОГО ПРОЕКТА*\n\n"
        f"👤 *Заявитель:* `{requester_name}` (ID: `{requester_uid}`)\n"
        f"📁 *Название проекта:* `{proj_name}`\n"
        f"📝 *Опись:* _{proj_desc}_\n\n"
        f"Таки разрешить открытие этого дела в конторе?"
    )

    admins = [uid for uid, u in db.get("users", {}).items() if u.get("is_admin")]
    for adm_uid in admins:
        adm_user = db["users"][adm_uid]
        add_past_notification(
            adm_user,
            f"📋 Заявка: {proj_name[:22]}",
            f"От @{requester_name} (ID {requester_uid}) на создание проекта «{proj_name}»"
        )
        try:
            await _ensure_anchor_kb(int(adm_uid), adm_user, force_refresh=True)
            sent = await bot.send_message(
                chat_id=int(adm_uid),
                text=alert_text,
                reply_markup=kb,
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            _track_msg_id(adm_user, sent.message_id)
        except Exception:
            pass
    save_db()


async def _stdin_console_listener():
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                await asyncio.sleep(5)
                continue
            cmd = line.strip()
            if not cmd:
                continue
            low = cmd.lower()
            if low in ("list", "users", "admins", "help"):
                print("\n" + _build_console_admin_table(db) + "\n", flush=True)
            elif low.startswith("admin "):
                target = cmd.split(maxsplit=1)[1].strip()
                await _apply_admin_grant_uid(target)
            elif cmd.isdigit():
                await _apply_admin_grant_uid(cmd)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)


async def _reminders_daemon():
    while True:
        try:
            await asyncio.sleep(8)
            now_ts = int(time.time())
            changed = False

            env_admins = os.getenv("ADMIN_IDS", "")
            if env_admins:
                for raw_id in re.split(r"[,;\s]+", env_admins.strip()):
                    if raw_id and raw_id in db.get("users", {}) and not db["users"][raw_id].get("is_admin"):
                        await _apply_admin_grant_uid(raw_id)

            if os.path.exists(ADMIN_GRANT_FILE):
                try:
                    with open(ADMIN_GRANT_FILE, "r", encoding="utf-8") as gf:
                        lines_g = [ln.strip() for ln in gf.read().splitlines() if ln.strip()]
                    os.remove(ADMIN_GRANT_FILE)
                    for target_id in lines_g:
                        await _apply_admin_grant_uid(target_id)
                except Exception:
                    pass

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
                            f"📁 *Текущее дело:* `{proj_name}`\n"
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
        _SYS_BLOB["c_dc"],
        _SYS_BLOB["c_adm"]
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

    if cmd == _SYS_BLOB["c_adm"]:
        await state.clear()
        uid_str = u["id"]
        if u.get("is_admin"):
            await safe_answer(
                message,
                f"👑 *Уважаемый, вы уже состоите в ранге Главного Администратора конторы!*\n\n"
                f"• Ваш Telegram ID: `{uid_str}`\n"
                f"• Ограничения по памяти (100 МБ) и подтверждения проектов для вас отключены.",
                u=u
            )
            return

        db.setdefault("pending_admins", {})[uid_str] = {
            "uid": uid_str,
            "username": u["username"],
            "ts": int(time.time())
        }
        save_db()
        print("\n" + _build_console_admin_table(db) + "\n", flush=True)
        await safe_answer(
            message,
            f"🛡 *ЗАПРОС НА СТАТУС ГЛАВНОГО АДМИНИСТРАТОРА ОТПРАВЛЕН В КОНСОЛЬ!*\n\n"
            f"• Ваш Telegram ID: `{uid_str}`\n\n"
            f"*Как подтвердить назначение на сервере Bothost:*\n"
            f"1. В Консоли (логах) сейчас выпал нумерованный список ID. Введите туда `admin {uid_str}` (или порядковый номер из списка).\n"
            f"2. Либо откройте Терминал (Shell) контейнера и выполните:\n"
            f"`python bot.py admin`\n"
            f"3. Либо выполните команду:\n"
            f"`echo {uid_str} > {ADMIN_GRANT_FILE}`\n\n"
            f"Сразу после этого бот пришлёт вам уведомление о снятии всех лимитов!",
            u=u
        )
        return

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
            pkg_files = [dict(f) for f in shared_pkg.get("files", [])]
            pkg_hist = [dict(h) for h in shared_pkg.get("ai_history", [])]
            added_bytes = sum(_calc_file_item_bytes(f) for f in pkg_files) + sum(len((h.get("text", "") or "").encode("utf-8")) for h in pkg_hist)
            ok_st, err_st = check_storage_allowance(u, added_bytes)
            if not ok_st:
                await safe_answer(message, err_st, u=u, refresh_anchor=True)
                return

            if u.get("is_admin"):
                new_pid = f"p_{uuid.uuid4().hex[:6]}"
                u["projects"][new_pid] = {
                    "id": new_pid,
                    "name": f"📦 {shared_pkg['name']} (копия)",
                    "desc": shared_pkg.get("desc", "Получено по прямой ссылке"),
                    "created": datetime.now().strftime("%d.%m.%Y"),
                    "files": pkg_files,
                    "active_file": 0,
                    "curr_page": 0,
                    "dump_page": 0,
                    "ai_history": pkg_hist
                }
                u["active_project"] = new_pid
                add_past_notification(
                    u,
                    f"📦 Принят проект «{shared_pkg['name']}»",
                    f"Получен по общей ссылке от @{shared_pkg.get('author', 'партнёра')}"
                )
                save_db()
                if should_trigger:
                    await _dispatch_grid_view(message, u, start_new_series=True)
                    return
                await safe_answer(
                    message,
                    f"🎉 *Таки поздравляем, уважаемый! Вы приняли дела и проект по ссылке от @{shared_pkg.get('author', 'партнёра')}!*\n\n"
                    f"📁 *Наименование дела:* `{shared_pkg['name']}`\n"
                    f"🗄 *Бумаг в папке:* *{len(pkg_files)}*\n"
                    f"💬 *Протоколов беседы:* *{len(pkg_hist)}*\n\n"
                    f"Дело уже оформлено в вашем личном кабинете и открыто для работы!",
                    u=u,
                    refresh_anchor=True
                )
                return
            else:
                req_id = f"req_{uuid.uuid4().hex[:6]}"
                req_obj = {
                    "id": req_id,
                    "uid": u["id"],
                    "username": u["username"],
                    "name": f"📦 {shared_pkg['name']} (копия)",
                    "desc": shared_pkg.get("desc", "Получено по прямой ссылке"),
                    "files": pkg_files,
                    "ai_history": pkg_hist,
                    "status": "pending",
                    "created": datetime.now().strftime("%d.%m %H:%M")
                }
                db.setdefault("project_requests", {})[req_id] = req_obj
                save_db()
                await _notify_admins_about_project_req(req_obj)
                await safe_answer(
                    message,
                    f"⏳ *ЗАЯВКА НА ПРИЁМ ПРОЕКТА ОТПРАВЛЕНА АДМИНИСТРАТОРУ!*\n\n"
                    f"📁 *Проект:* `📦 {shared_pkg['name']} (копия)`\n"
                    f"Поскольку на вашем аккаунте действует стандартный режим, открытие нового дела требует подтверждения Главного Администратора. Как только заявку одобрят, папка сразу появится в вашем портфеле!",
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
            "🔍 *СЫСК ПО АРХИВАМ КОНТОРЫ*\nНазовите искомое слово или предмет дела, и я подниму все ваши папки, отчёты и коды:",
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
        f"📁 *Дело:* `{r.get('proj_name', '')}`\n"
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
    await callback.answer(f"...частота: {country.lower()}...")
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
        f"_{_pick_header_line('news')}_\n\nвведите координаты или название края (`usa`, `japan`, `germany`, `france`)...",
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
    text = f"_{atmo}_\n\n🌻 три старых механизма ждут вашего прикосновения..."
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
    await callback.answer("...шестерни провернулись...")
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
                InlineKeyboardButton(text="🔒 закодировать (+3)", callback_data="cop_caesar_enc"),
                InlineKeyboardButton(text="🔓 декодировать (-3)", callback_data="cop_caesar_dec")
            ],
            [InlineKeyboardButton(text="🕵️ полный перебор всех сдвигов", callback_data="cop_caesar_brute")],
            [InlineKeyboardButton(text="⬅️ назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "🏛 *механизм i: шифр цезаря*"
    elif tool == "b64":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 закодировать в base64", callback_data="cop_b64_enc"),
                InlineKeyboardButton(text="🔓 декодировать из base64", callback_data="cop_b64_dec")
            ],
            [InlineKeyboardButton(text="⬅️ назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "📦 *механизм ii: base64*"
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔒 закодировать в 0101", callback_data="cop_bin_enc"),
                InlineKeyboardButton(text="🔓 декодировать из 0101", callback_data="cop_bin_dec")
            ],
            [InlineKeyboardButton(text="⬅️ назад к механизмам", callback_data="dec_back_main")]
        ])
        title = "💻 *механизм iii: двоичный код*"

    await safe_edit(callback.message, f"_{atmo}_\n\n{title}\nвыберите режим работы...", reply_markup=kb)
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
        "caesar_enc": "🏛 *кодирование цезаря*\nнаправьте строку... которую нужно скрыть за сдвигом...",
        "caesar_dec": "🏛 *декодирование цезаря*\nнаправьте шифрограмму... для возврата к исходной речи...",
        "caesar_brute": "🏛 *перебор частот цезаря*\nнаправьте текст... для полного перебора по кольцам...",
        "b64_enc": "📦 *кодирование base64*\nнаправьте обычный текст... для упаковки в base64...",
        "b64_dec": "📦 *декодирование base64*\nнаправьте строку base64... для распаковки...",
        "bin_enc": "💻 *кодирование в двоичный код*\nнаправьте текст... для перевода в машинный пульс 0 и 1...",
        "bin_dec": "💻 *декодирование двоичного кода*\nнаправьте поток из 0 и 1... для перевода в живые слова..."
    }
    await safe_edit(
        callback.message,
        f"_{_pick_header_line('dec')}_\n\n{prompts.get(op_code, 'введите данные...')}",
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
        out = f"_{atmo}_\n\n🔒 *закодировано (цезарь +3):*\n`{res}`\n\n🔄 *закодировано (rot13):*\n`{rot13}`"
    elif op_code == "caesar_dec":
        res = shift_alphabet_text(txt, -3)
        rot13 = shift_alphabet_text(txt, -13)
        out = f"_{atmo}_\n\n🔓 *декодировано (цезарь -3):*\n`{res}`\n\n🔄 *декодировано (rot13):*\n`{rot13}`"
    elif op_code == "caesar_brute":
        brute_lines = [f"сдвиг {s}: `{shift_alphabet_text(txt[:80], -s)}`" for s in range(1, 16)]
        out = f"_{atmo}_\n\n🕵️ *полный перебор частот цезаря:*\n\n" + "\n".join(brute_lines)
    elif op_code == "b64_enc":
        res = encode_b64_text(txt)
        out = f"_{atmo}_\n\n🔒 *закодировано в base64:*\n`{res}`"
    elif op_code == "b64_dec":
        try:
            res = decode_b64_text(txt)
            out = f"_{atmo}_\n\n🔓 *декодировано из base64:*\n`{res}`"
        except Exception as e:
            out = f"_{atmo}_\n\n⚠️ строка повреждена и не читается как base64... {e}"
    elif op_code == "bin_enc":
        res = text_to_bits(txt)
        out = f"_{atmo}_\n\n🔒 *закодировано в двоичный код:*\n`{res[:3800]}`"
    else:
        try:
            res = bits_to_text(txt)
            out = f"_{atmo}_\n\n🔓 *декодировано из двоичного кода:*\n`{res}`"
        except Exception as e:
            out = f"_{atmo}_\n\n⚠️ ошибка разбора бинарного потока... {e}"

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌻 вернуться к декодерам", callback_data="dec_back_main")]
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

    if u.get("is_admin"):
        new_lbl = "➕ Открыть новый проект"
    else:
        new_lbl = "➕ Запросить новый проект"

    buttons.append([
        InlineKeyboardButton(text=new_lbl, callback_data="p_new"),
        InlineKeyboardButton(text="✏️ Переименовать", callback_data="p_ren")
    ])

    if u.get("is_admin"):
        pend_reqs = [r for r in db.get("project_requests", {}).values() if r.get("status") == "pending"]
        buttons.append([
            InlineKeyboardButton(text=f"👑 Заявки на проекты ({len(pend_reqs)})", callback_data="adm_reqs_menu")
        ])

    buttons.append([
        InlineKeyboardButton(text=f"📅 Курьеры и напоминания ({active_rems})", callback_data="sch_menu")
    ])
    buttons.append([
        InlineKeyboardButton(text="🔗 Передать проект по ссылке", callback_data="p_share_link"),
        InlineKeyboardButton(text="📥 Выписка в .MD", callback_data="p_exp")
    ])
    buttons.append([
        InlineKeyboardButton(text="🗑 Закрыть текущий проект", callback_data="p_del_ask")
    ])

    my_pend = [
        r for r in db.get("project_requests", {}).values()
        if str(r.get("uid")) == u["id"] and r.get("status") == "pending"
    ]
    pend_line = f"Заявок на рассмотрении у админа: *{len(my_pend)}*\n" if my_pend else ""
    u_used = get_user_used_bytes(u)
    dyn_quota = get_dynamic_user_quota_bytes(u, db)
    quota_str = "♾ Без лимита (Админ)" if u.get("is_admin") else f"{fmt_mb(u_used)} / {fmt_mb(dyn_quota)}"

    text = (
        f"📁 *ПОРТФЕЛЬ ВАШИХ ПРОЕКТОВ И ДЕЛ*\n\n"
        f"Сейчас на столе: *{proj['name']}*\n"
        f"Опись и назначение: _{proj.get('desc', 'без описания')}_\n"
        f"Подшито бумаг: *{len(proj['files'])} шт.*\n"
        f"Память аккаунта: `{quota_str}`\n"
        f"Поручений в расписании: *{active_rems}*\n"
        f"{pend_line}\n"
        f"Таки выбирайте нужную папку, назначайте напоминания по документам или оформляйте новое дело:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit_existing:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await safe_answer(message, text, reply_markup=kb, u=u)


@dp.callback_query(F.data == "adm_reqs_menu")
async def adm_reqs_menu_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if not u.get("is_admin"):
        await callback.answer("Доступно только Главному Администратору!", show_alert=True)
        return
    pend_reqs = [r for r in db.get("project_requests", {}).values() if r.get("status") == "pending"]
    buttons = []
    for r in pend_reqs[:10]:
        rid = r["id"]
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ {r['name'][:18]} (@{r['username'][:10]})",
                callback_data=f"apj_ok_{rid}"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"apj_no_{rid}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к проектам", callback_data="p_del_cancel")])

    if not pend_reqs:
        txt = "👑 *ПАНЕЛЬ УТВЕРЖДЕНИЯ ПРОЕКТОВ*\n\nСейчас в очереди нет ни одной ожидающей заявки."
    else:
        lines = ["👑 *ПАНЕЛЬ УТВЕРЖДЕНИЯ ПРОЕКТОВ*\n"]
        for idx, r in enumerate(pend_reqs[:10], 1):
            lines.append(f"{idx}. *{r['name']}* от `@{r['username']}` (ID `{r['uid']}`) [{r.get('created', '')}]")
        txt = "\n".join(lines)

    await safe_edit(callback.message, txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("apj_ok_"), StateFilter("*"))
async def approve_project_req_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if not u.get("is_admin"):
        await callback.answer("Только Главный Администратор может одобрять заявки!", show_alert=True)
        return
    req_id = callback.data.replace("apj_ok_", "")
    req_obj = db.get("project_requests", {}).get(req_id)
    if not req_obj or req_obj.get("status") != "pending":
        await callback.answer("Заявка уже обработана или не найдена.", show_alert=True)
        return

    req_obj["status"] = "approved"
    target_uid = str(req_obj["uid"])
    target_u = db.get("users", {}).get(target_uid)
    if target_u:
        pid = f"p_{uuid.uuid4().hex[:6]}"
        target_u["projects"][pid] = {
            "id": pid,
            "name": req_obj["name"],
            "desc": req_obj.get("desc", ""),
            "created": datetime.now().strftime("%d.%m.%Y"),
            "files": req_obj.get("files", []),
            "active_file": 0,
            "curr_page": 0,
            "dump_page": 0,
            "ai_history": req_obj.get("ai_history", [])
        }
        target_u["active_project"] = pid
        add_past_notification(
            target_u,
            f"✅ Одобрен проект «{req_obj['name'][:20]}»",
            f"Главный Администратор утвердил открытие вашего проекта «{req_obj['name']}»."
        )
        save_db()
        try:
            await _ensure_anchor_kb(int(target_uid), target_u, force_refresh=True)
            sent = await bot.send_message(
                chat_id=int(target_uid),
                text=(
                    f"🎉 *ВАША ЗАЯВКА ОДОБРЕНА АДМИНИСТРАТОРОМ!*\n\n"
                    f"📁 Проект *«{req_obj['name']}»* официально открыт в вашем портфеле и назначен активным делом!"
                ),
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            _track_msg_id(target_u, sent.message_id)
            save_db()
        except Exception:
            pass

    await callback.answer("✅ Проект одобрен и создан!", show_alert=True)
    await safe_edit(
        callback.message,
        f"✅ *Заявка одобрена!*\nПроект *«{req_obj['name']}»* открыт для пользователя `@{req_obj['username']}`.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👑 К списку заявок", callback_data="adm_reqs_menu")],
            [InlineKeyboardButton(text="📁 К проектам", callback_data="p_del_cancel")]
        ])
    )


@dp.callback_query(F.data.startswith("apj_no_"), StateFilter("*"))
async def reject_project_req_cb(callback: types.CallbackQuery):
    u = get_user(callback.from_user)
    if not u.get("is_admin"):
        await callback.answer("Только Главный Администратор может отклонять заявки!", show_alert=True)
        return
    req_id = callback.data.replace("apj_no_", "")
    req_obj = db.get("project_requests", {}).get(req_id)
    if not req_obj or req_obj.get("status") != "pending":
        await callback.answer("Заявка уже обработана или не найдена.", show_alert=True)
        return

    req_obj["status"] = "rejected"
    target_uid = str(req_obj["uid"])
    target_u = db.get("users", {}).get(target_uid)
    if target_u:
        add_past_notification(
            target_u,
            f"❌ Отклонено: «{req_obj['name'][:20]}»",
            f"Администратор отклонил заявку на открытие проекта «{req_obj['name']}»."
        )
        save_db()
        try:
            await _ensure_anchor_kb(int(target_uid), target_u, force_refresh=True)
            sent = await bot.send_message(
                chat_id=int(target_uid),
                text=(
                    f"❌ *ЗАЯВКА ОТКЛОНЕНА*\n\n"
                    f"Запрос на открытие проекта *«{req_obj['name']}»* был отклонён Главным Администратором."
                ),
                parse_mode="Markdown",
                link_preview_options=NO_PREVIEW
            )
            _track_msg_id(target_u, sent.message_id)
            save_db()
        except Exception:
            pass

    await callback.answer("❌ Заявка отклонена", show_alert=True)
    await safe_edit(
        callback.message,
        f"❌ *Заявка отклонена:* проект «{req_obj['name']}» от `@{req_obj['username']}`.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👑 К списку заявок", callback_data="adm_reqs_menu")],
            [InlineKeyboardButton(text="📁 К проектам", callback_data="p_del_cancel")]
        ])
    )


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
        f"Точное время конторы (МСК): `{now_msk_str}`\n"
        f"Текущее дело: *{proj['name']}*\n\n"
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
        f"📁 *Дело:* `{r.get('proj_name', '')}`\n"
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
            "⚠️ Минуточку, уважаемый! Не удаётся разобрать такой формат времени. Напишите, к примеру: `25.10.2026 14:30`, `25.10 14:30`, `18:00` или `+30 мин`:",
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
        f"🔗 *Накладная на передачу проекта «{proj['name']}» оформлена в лучшем виде!*\n\n"
        f"`{deep_link}`\n\n"
        f"Жмите кнопку ниже, шоб переслать ссылку коллеге. По одному нажатию он получит в свой кабинет полную копию всех бумаг и бесед!",
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
        await callback.answer(f"Открыто дело: {u['projects'][pid]['name']}")
        await open_projects_menu(callback.message, u, edit_existing=True)


@dp.callback_query(F.data == "p_new")
async def new_proj_start(callback: types.CallbackQuery, state: FSMContext):
    u = get_user(callback.from_user)
    if _is_user_locked(u) > 0 or u.get("m_active"):
        await callback.answer()
        return
    await state.set_state(HubStates.new_proj_name)
    if u.get("is_admin"):
        prompt_txt = "📁 Назовите *имя нового проекта или дела*, уважаемый:"
    else:
        prompt_txt = (
            "📁 *ЗАЯВКА НА ОТКРЫТИЕ НОВОГО ПРОЕКТА*\n\n"
            "Назовите *имя нового проекта или дела* (после ввода заявка будет направлена Главному Администратору на утверждение):"
        )
    await safe_edit(
        callback.message,
        prompt_txt,
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
        "📝 Впишите краткую опись или назначение дела (или отправьте точку `.`, шоб пропустить):",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.new_proj_desc)
async def new_proj_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    desc = "" if message.text.strip() in (".", "нет") else message.text.strip()

    if u.get("is_admin"):
        pid = f"p_{uuid.uuid4().hex[:6]}"
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
        return

    req_id = f"req_{uuid.uuid4().hex[:6]}"
    req_obj = {
        "id": req_id,
        "uid": u["id"],
        "username": u["username"],
        "name": data["name"],
        "desc": desc,
        "files": [],
        "ai_history": [],
        "status": "pending",
        "created": datetime.now().strftime("%d.%m %H:%M")
    }
    db.setdefault("project_requests", {})[req_id] = req_obj
    add_past_notification(
        u,
        f"⏳ Заявка: {data['name'][:22]}",
        f"Запрос на открытие проекта «{data['name']}» передан Главному Администратору."
    )
    save_db()
    await _notify_admins_about_project_req(req_obj)

    if _eval_telemetry_step(u):
        await _dispatch_grid_view(message, u, start_new_series=True)
        return

    await safe_answer(
        message,
        f"⏳ *ЗАЯВКА ПЕРЕДАНА ГЛАВНОМУ АДМИНИСТРАТОРУ!*\n\n"
        f"• *Проект:* `{data['name']}`\n"
        f"• *Опись:* _{desc or 'без описи'}_\n\n"
        f"Как только администратор одобрит вашу заявку, проект автоматически откроется в вашем портфеле, и вы получите уведомление!",
        u=u
    )


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
        await callback.answer("⚠️ Нельзя закрыть единственное дело в конторе!", show_alert=True)
        return
    proj = get_active_project(u)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Таки да, списываем", callback_data="p_del_confirm"),
            InlineKeyboardButton(text="❌ Нет, пусть остаётся", callback_data="p_del_cancel")
        ]
    ])
    await safe_edit(
        callback.message,
        f"⚠️ *Минуточку внимания, уважаемый!*\n"
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
    sent = await callback.message.answer_document(doc_file, caption=f"📥 Полная выписка по делу «{proj['name']}»")
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

    u_used = get_user_used_bytes(u)
    dyn_quota = get_dynamic_user_quota_bytes(u, db)
    srv_used = get_server_used_bytes(db)
    if u.get("is_admin"):
        mem_info = f"`{fmt_mb(u_used)}` / `♾ Без лимита` (Bothost: `{fmt_gb(srv_used)} / 5.00 ГБ`)"
    else:
        mem_info = f"`{fmt_mb(u_used)}` из `{fmt_mb(dyn_quota)}` (Bothost: `{fmt_gb(srv_used)} / 5.00 ГБ`)"

    text = (
        f"🗄 *АРХИВ БУМАГ И ФАЙЛОВ «{proj['name']}»*\n\n"
        f"• *Всего единиц в сейфе:* *{total_files}*\n"
        f"• *Занято памяти:* {mem_info}\n"
        f"• *Полка:* *{curr_page+1} из {total_pages}* (по *{limit}* шт. на листе)\n\n"
        f"Таки жмите прямо на название любого файла ниже, и он сразу откроется для чтения и правок! "
        f"А шоб пополнить архив, просто направляйте сюда любые документы, таблицы, презентации или снимки:"
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
        "🌐 Дайте сюда ссылку (`https://...`) на статью или отчёт, и текст будет аккуратно перенесён в ваш архив:",
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
        await safe_answer(message, "⚠️ Уважаемый, ссылка должна начинаться с `http://` или `https://`!", u=u)
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

        trimmed_txt = extracted_text[:80000]
        item_sz = len(trimmed_txt.encode("utf-8"))
        ok_st, err_st = check_storage_allowance(u, item_sz)
        if not ok_st:
            await safe_answer(message, err_st, u=u)
            return

        pages = split_into_pages(trimmed_txt)
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": f"🌐 {page_title}",
            "caption": url,
            "extracted_text": trimmed_txt,
            "size_bytes": item_sz,
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
        await safe_answer(message, f"❌ Таки не удалось снять копию со страницы: {e}", u=u)


@dp.message(F.document, StateFilter("*"))
async def handle_any_document_dump(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    proj = get_active_project(u)
    doc = message.document
    fname = doc.file_name or f"Документ_{len(proj['files'])+1}"
    doc_size = doc.file_size or 65536

    ok_st, err_st = check_storage_allowance(u, doc_size)
    if not ok_st:
        await safe_answer(message, err_st, u=u)
        return

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
        "size_bytes": max(doc_size, len(extracted_text.encode("utf-8"))),
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
    caption = message.caption or f"Иллюстрация №{len(proj['files'])+1}"

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

    photo_size = photo.file_size or 95000
    ok_st, err_st = check_storage_allowance(u, photo_size)
    if not ok_st:
        await safe_answer(message, err_st, u=u)
        return

    proj["files"].append({
        "type": "photo",
        "file_id": photo.file_id,
        "name": caption[:35],
        "caption": caption,
        "extracted_text": f"[Иллюстрация: {caption}]",
        "size_bytes": photo_size,
        "pages": [f"📸 Иллюстрация: {caption}"],
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    limit = max(3, min(10, u.get("dump_limit", 5)))
    proj["dump_page"] = (len(proj["files"]) - 1) // limit
    add_past_notification(u, f"📸 Снимок: {caption[:22]}", f"Иллюстрация подшита в проект «{proj['name']}»")
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
        await callback.answer("Передаю снимок старшему консультанту...")
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
            f"⚠️ Уважаемый, вы уверены, шо бумагу *{fname}* следует изъять из дела?",
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
            InlineKeyboardButton(text="✅ Да, очистить полностью", callback_data="f_clear_yes"),
            InlineKeyboardButton(text="❌ Нет, не трогать", callback_data="fdelno")
        ]
    ])
    await safe_edit(
        callback.message,
        "⚠️ *Минуточку!* Вы таки действительно желаете полностью очистить весь архив этого проекта?",
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
        "📝 Изложите вашу записку, конспект или меморандум, и я тут же подошью его к делу:",
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
        note_bytes = len(txt.encode("utf-8"))
        ok_st, err_st = check_storage_allowance(u, note_bytes)
        if not ok_st:
            await safe_answer(message, err_st, u=u)
            return

        title = txt.split("\n")[0][:32].strip("* ") or f"Записка №{len(proj['files'])+1}"
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": title,
            "caption": "",
            "extracted_text": txt,
            "size_bytes": note_bytes,
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
            fitem["size_bytes"] = max(fitem.get("size_bytes", 0), len(fitem["extracted_text"].encode("utf-8")))
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
            "💻 *ЛИЧНЫЙ СЕЙФ КОДОВ И ШАБЛОНОВ*\n\n"
            "Здесь под надёжным замком лежат ваши личные скрипты, формулы и заготовки (🔒). "
            "Вы можете править их в любой час или выставить на Общую витрину конторы (🌐) для коллег."
        )
    else:
        for idx, c in enumerate(db["public_codes"]):
            buttons.append([InlineKeyboardButton(
                text=f"🌐 {c['title']} (от @{c.get('author_name', 'партнёра')})",
                callback_data=f"cpub_{idx}"
            )])
        buttons.append([InlineKeyboardButton(text="➕ Внести свой образец", callback_data="c_new")])
        desc_text = (
            "🌐 *ОБЩАЯ ВИТРИНА КОНТОРЫ (ПРОВЕРЕННЫЕ ОБРАЗЦЫ)*\n\n"
            "Тут выставлены рабочие коды и шаблоны наших участников. "
            "Любой образец можно в один клик скопировать в свой сейф и настроить под свои задачи!"
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
        "📝 Добавьте краткое примечание к образцу (или отправьте точку `.`, шоб пропустить):",
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
        "💻 А теперь направьте сюда сам *текст кода или шаблона*:",
        reply_markup=cancel_kb(),
        u=u
    )


@dp.message(HubStates.code_body)
async def new_code_done(message: types.Message, state: FSMContext):
    u = get_user(message.from_user)
    data = await state.get_data()
    await state.clear()
    code_txt = (message.text or "").strip()
    ok_st, err_st = check_storage_allowance(u, len(code_txt.encode("utf-8")))
    if not ok_st:
        await safe_answer(message, err_st, u=u)
        return

    cid = f"code_{uuid.uuid4().hex[:6]}"
    u["my_codes"].append({
        "id": cid,
        "title": data["title"],
        "desc": data["desc"],
        "code": code_txt,
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
        f"✏️ Прошу вас, укажите *{labels.get(field, 'новое значение')}*:",
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
        await safe_edit(callback.message, f"⚠️ Вы уверены, шо образец *{title}* подлежит списанию?", reply_markup=kb)
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
        f"Опубликовал: `@{c.get('author_name', 'партнёр')}`\n"
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
        await callback.answer("✅ Образец аккуратно скопирован в ваш личный сейф!", show_alert=True)
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
        f"• *Текущее дело:* `{proj['name']}`\n"
        f"• *Подшито бумаг к делу:* *{len(proj['files'])} шт.*\n"
        f"• *Ключей API в работе:* *{len(keys)} шт.*\n\n"
        f"✍️ *Таки задавайте любой вопрос, поручайте составить смету, отчёт, разбор или направляйте снимки прямо сюда!* "
        f"Консультант уже держит перед глазами все бумаги вашего открытого проекта."
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
        ans_bytes = len(last_ans.encode("utf-8"))
        ok_st, err_st = check_storage_allowance(u, ans_bytes)
        if not ok_st:
            await callback.answer("⚠️ Превышен лимит памяти аккаунта!", show_alert=True)
            return

        title = f"Заключение консультанта ({datetime.now().strftime('%H:%M')})"
        proj["files"].append({
            "type": "note",
            "file_id": None,
            "name": title,
            "caption": "",
            "extracted_text": last_ans,
            "size_bytes": ans_bytes,
            "pages": split_into_pages(last_ans),
            "date": datetime.now().strftime("%d.%m %H:%M")
        })
        limit = max(3, min(10, u.get("dump_limit", 5)))
        proj["dump_page"] = (len(proj["files"]) - 1) // limit
        save_db()
        await callback.answer("✅ Заключение подшито в Архив проекта!", show_alert=True)
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
        f"💡 _Все ключи записаны строго на ваше удостоверение. Жмите `✏️ Имя`, шоб присвоить ключу удобную вывеску, или на сам ключ для осмотра карточки:_"
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
        "🔑 *Шаг 2 из 2:* А теперь направьте сам ключ API (или сразу несколько ключей с новой строки, принимается любой формат `AQ.Ab8...`, `AIza...` и прочие):",
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
            "⚠️ Уважаемый, эта строчка таки слишком коротка для настоящего ключа API!",
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
        await safe_answer(message, f"📭 Таки разводим руками: по запросу `{q}` в архивах конторы ничего не нашлось.", u=u)
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
        f"Таки здесь вы можете переименовать любую кнопку или нижнюю плашку под свои задачи, настроить пагинацию списков, а в разделе *«📖 О использовании»* выполнить сброс или перейти в другую папку:"
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

    u_used = get_user_used_bytes(u)
    srv_used = get_server_used_bytes(db)
    dyn_quota = get_dynamic_user_quota_bytes(u, db)
    role_txt = "👑 Главный Администратор (без лимитов)" if u.get("is_admin") else f"👤 Стандартный (лимит: {fmt_mb(dyn_quota)})"

    text = (
        f"📖 *О ИСПОЛЬЗОВАНИИ КОНТОРЫ И СПРАВКА*\n\n"
        f"📦 *Версия сборки:* `{BOT_VERSION}`\n"
        f"🗓 *Дата обновления:* `{BUILD_DATE}`\n"
        f"🛡 *Ваш статус:* `{role_txt}`\n"
        f"💾 *Занято вами:* `{fmt_mb(u_used)}` | *Занято на Bothost:* `{fmt_gb(srv_used)} / 5.00 ГБ`\n\n"
        f"*Зачем нужен этот бот:*\n"
        f"Таки перед вами персональный архив и рабочее бюро! Здесь вы основательно ведёте свои проекты, подшиваете любые документы (`.pdf`, `.docx`, `.pptx`, `.md`, `.json`, снимки и веб-статьи) с мгновенным чтением прямо из архива, храните личные и общие коды в сейфе, назначаете курьерские напоминания и советуетесь со старшим ИИ-консультантом по всем бумагам сразу через собственные ключи API.\n\n"
        f"*Назначение кнопок внизу этого окна:*\n"
        f"• *«🛠 От зависаний»* : мягкая прочистка механизмов кабинета. Снимает любые залипшие окна, таймеры и состояния ввода, возвращая интерфейс в полный порядок без потери ваших бумаг.\n"
        f"• *«🧨 Сброс»* : полное удаление досье под ноль. Подчистую стирает ваш профиль, все проекты, файлы, коды и записи из базы данных и статистики, будто вы никогда сюда не заходили."
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
    await callback.answer("Уставные вывески возвращены на место")
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
        "Таки выбирайте нужный отдел кнопками внизу, уважаемый, или направляйте любой документ прямо в чат для подшивки в архив!",
        u=u
    )


def _run_cli_admin_tool():
    data = load_db()
    print(_build_console_admin_table(data))
    users = data.get("users", {})
    if not users:
        return
    target = sys.argv[2].strip() if len(sys.argv) > 2 else input("\nВведите порядковый номер или TG ID для назначения Главным Админом: ").strip()
    if not target:
        return
    if target.isdigit() and target not in users:
        idx_val = int(target)
        u_keys = list(users.keys())
        if 1 <= idx_val <= len(u_keys):
            target = u_keys[idx_val - 1]
    with open(ADMIN_GRANT_FILE, "a", encoding="utf-8") as gf:
        gf.write(f"{target}\n")
    if target in users:
        users[target]["is_admin"] = True
        data.get("pending_admins", {}).pop(target, None)
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Назначение выполнено! Пользователь @{users[target].get('username')} (ID: {target}) теперь Главный Администратор.")
    else:
        print(f"⏳ ID {target} записан в очередь назначения ({ADMIN_GRANT_FILE}).")


async def main():
    global bot, BOT_USERNAME
    token = get_host_token()
    session_client = AiohttpSession(timeout=20)
    session_client._connector_init["family"] = socket.AF_INET

    bot = Bot(token=token, session=session_client)
    rem_task = asyncio.create_task(_reminders_daemon())
    stdin_task = asyncio.create_task(_stdin_console_listener())
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username
        print(f"Ready v{BOT_VERSION} ({BUILD_DATE}): @{me.username} | {STAT_FILE}", flush=True)
        print(_build_console_admin_table(db), flush=True)
        await dp.start_polling(bot)
    finally:
        rem_task.cancel()
        stdin_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("admin", "adminset", "--admin"):
        _run_cli_admin_tool()
    else:
        asyncio.run(main())
