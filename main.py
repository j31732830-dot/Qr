import os
import cv2
import qrcode
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import json


TOKEN = "8499904012:AAFBj0PE3gM-0U0-cCcQA7IPmTCKXk2CGmY"

# AIROGRAM 3.7+ to‘g‘ri yozilishi
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- TEMP PAPKA ----------
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# ---------- STATISTIKA ----------
STATS_FILE = "stats.json"


def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"users": [], "qr_created": 0, "qr_scanned": 0}
    return json.load(open(STATS_FILE, "r"))


def save_stats(data):
    json.dump(data, open(STATS_FILE, "w"), indent=4)


def add_user(user_id):
    data = load_stats()
    if user_id not in data["users"]:
        data["users"].append(user_id)
    save_stats(data)


def inc_created():
    data = load_stats()
    data["qr_created"] += 1
    save_stats(data)


def inc_scanned():
    data = load_stats()
    data["qr_scanned"] += 1
    save_stats(data)


# ---------- MENYU ----------
def menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Matn → QR kod", callback_data="make_qr"),
            InlineKeyboardButton(text="📷 QR kod → Matn", callback_data="read_qr")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Ma'lumot", callback_data="info"),
            InlineKeyboardButton(text="📊 Statistika", callback_data="stats")
        ]
    ])


# ---------- START ----------
@dp.message(F.text == "/start")
async def start(msg: Message):
    add_user(msg.from_user.id)
    await msg.answer("<b>Funktsiyani tanlang:</b>", reply_markup=menu_keyboard())


# =============== CALLBACK HANDLER ==================
@dp.callback_query(F.data == "make_qr")
async def cb_make_qr(call):
    await call.message.answer("📝 <b>QR kod yaratish uchun matn yuboring.</b>")
    await call.answer()


@dp.callback_query(F.data == "read_qr")
async def cb_read_qr(call):
    await call.message.answer("📷 <b>QR kod rasmini yuboring.</b>")
    await call.answer()


@dp.callback_query(F.data == "info")
async def cb_info(call):
    await call.message.answer(
        "<b>ℹ️ QR Bot haqida:</b>\n"
        "— Matndan QR kod yaratadi\n"
        "— QR kod rasmini matnga o‘giradi\n"
        "— Statistika yuritadi\n"
        "\nBot ishlab chiqaruvchi: <b>JamoStar Dev</b>"
    )
    await call.answer()


@dp.callback_query(F.data == "stats")
async def cb_stats(call):
    stats = load_stats()
    await call.message.answer(
        "<b>📊 Statistika:</b>\n\n"
        f"👤 Foydalanuvchilar: <b>{len(stats['users'])}</b>\n"
        f"📝 Yaratilgan QR: <b>{stats['qr_created']}</b>\n"
        f"📷 O‘qilgan QR: <b>{stats['qr_scanned']}</b>"
    )
    await call.answer()


# =============== MATN → QR ===============
@dp.message(F.text & ~F.via_bot)
async def create_qr(msg: Message):
    text = msg.text.strip()
    file_path = f"{TEMP_DIR}/qr_{msg.from_user.id}.png"

    img = qrcode.make(text)
    img.save(file_path)

    inc_created()

    await msg.answer_photo(
        photo=open(file_path, "rb"),
        caption=f"✅ <b>QR kod yaratildi!</b>\n\nMatn:\n<code>{text}</code>",
        reply_markup=menu_keyboard()
    )

    # Rasmni o‘chiramiz
    if os.path.exists(file_path):
        os.remove(file_path)


# =============== QR → MATN ===============
@dp.message(F.photo)
async def read_qr(msg: Message):

    # 1) rasmni yuklab olish
    file = await msg.photo[-1].download(destination_dir=TEMP_DIR)
    img_path = file.name

    # 2) QR-ni o‘qish
    img = cv2.imread(img_path)
    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    # 3) Agar topilmasa
    if not data:
        await msg.answer("❌ QR kod topilmadi!", reply_markup=menu_keyboard())
        os.remove(img_path)
        return

    inc_scanned()

    await msg.answer(
        f"🔍 <b>QR kod o‘qildi!</b>\n\n📄 Matn:\n<code>{data}</code>",
        reply_markup=menu_keyboard()
    )

    # 4) Ish tugagach rasmni o‘chiramiz
    if os.path.exists(img_path):
        os.remove(img_path)


# =============== ISHGA TUSHIRISH ===============
async def main():
    print("🚀 Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
