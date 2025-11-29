import logging
import os
import asyncio
import io
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, BufferedInputFile
import qrcode
from PIL import Image
from pyzbar.pyzbar import decode
from dotenv import load_dotenv

load_dotenv()

# Konfiguratsiya
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi! .env faylida kiriting.")

# Logging sozlash
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("qr_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot inicializatsiya
storage = MemoryStorage()
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Temp papka yaratish
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(exist_ok=True)

# Fayllarni avtomatik o'chirish uchun
FILE_LIFETIME = timedelta(minutes=5)  # 5 daqiqadan keyin o'chirish
cleanup_tasks = {}


class QRStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_image = State()


# ============= Yordamchi funksiyalar =============

async def cleanup_file(file_path: Path, delay: int = 300):
    """Faylni kechiktirib o'chirish (300 sekund = 5 daqiqa)"""
    try:
        await asyncio.sleep(delay)
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Fayl o'chirildi: {file_path}")
    except Exception as e:
        logger.error(f"Faylni o'chirishda xato: {e}")


def generate_qr_code(text: str, size: int = 10, border: int = 2) -> io.BytesIO:
    """Matndan QR kod generatsiya qilish"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=size,
            border=border,
        )
        qr.add_data(text)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # BytesIO'ga saqlash (xotirada)
        bio = io.BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        return bio
    except Exception as e:
        logger.error(f"QR kod yaratishda xato: {e}")
        raise


async def decode_qr_from_image(image_path: Path) -> str:
    """Rasmdan QR kodni o'qish"""
    try:
        img = Image.open(image_path)
        decoded_objects = decode(img)
        
        if not decoded_objects:
            return None
        
        # Birinchi topilgan QR kodni qaytarish
        text = decoded_objects[0].data.decode('utf-8')
        return text
    except Exception as e:
        logger.error(f"QR kodni o'qishda xato: {e}")
        return None


def get_user_stats(user_id: int) -> dict:
    """Foydalanuvchi statistikasi (sodda versiya)"""
    return {
        "user_id": user_id,
        "timestamp": datetime.now().isoformat()
    }


# ============= Bot handlarlari =============

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Start buyrug'i"""
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="📝 Matn → QR kod"),
                types.KeyboardButton(text="📷 QR kod → Matn")
            ],
            [
                types.KeyboardButton(text="ℹ️ Ma'lumot"),
                types.KeyboardButton(text="📊 Statistika")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Funksiyani tanlang"
    )
    
    await message.answer(
        "🤖 <b>QR Code Bot'ga xush kelibsiz!</b>\n\n"
        "Men quyidagi funksiyalarni bajaraman:\n"
        "📝 Matndan QR kod yaratish\n"
        "📷 QR koddan matnni o'qish\n\n"
        "Kerakli funksiyani tanlang 👇",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    logger.info(f"User {message.from_user.id} botni boshladi")


@dp.message(F.text == "📝 Matn → QR kod")
async def text_to_qr_start(message: types.Message, state: FSMContext):
    """Matndan QR kod yaratish - boshlash"""
    await state.set_state(QRStates.waiting_for_text)
    
    cancel_kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "📝 <b>QR kodga aylantirmoqchi bo'lgan matningizni yuboring:</b>\n\n"
        "Masalan:\n"
        "• URL: https://example.com\n"
        "• Matn: Salom dunyo!\n"
        "• Telefon: +998901234567\n"
        "• Wi-Fi: WIFI:T:WPA;S:MyNetwork;P:password;;\n\n"
        "<i>Maksimal uzunlik: 2000 belgi</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )


@dp.message(QRStates.waiting_for_text, F.text)
async def text_to_qr_process(message: types.Message, state: FSMContext):
    """Matndan QR kod yaratish - qayta ishlash"""
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await cmd_start(message)
        return
    
    text = message.text.strip()
    
    # Uzunlikni tekshirish
    if len(text) > 2000:
        await message.answer(
            "❌ Matn juda uzun! Maksimal 2000 belgi.\n"
            "Iltimos, qisqaroq matn yuboring."
        )
        return
    
    # Loading xabari
    loading_msg = await message.answer("⏳ QR kod yaratilmoqda...")
    
    try:
        # QR kod yaratish
        qr_bytes = generate_qr_code(text)
        
        # Telegram'ga yuborish (xotiradan)
        qr_file = BufferedInputFile(qr_bytes.read(), filename="qr_code.png")
        
        await message.answer_photo(
            photo=qr_file,
            caption=f"✅ <b>QR kod tayyor!</b>\n\n"
                    f"📊 Belgilar soni: {len(text)}\n"
                    f"⏰ Yaratilgan vaqt: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="HTML"
        )
        
        # Loading xabarini o'chirish
        await loading_msg.delete()
        
        # Statistika
        logger.info(f"User {message.from_user.id} QR kod yaratdi (uzunlik: {len(text)})")
        
        # State'ni tozalash
        await state.clear()
        
        # Asosiy menyuga qaytish
        await cmd_start(message)
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            "❌ QR kod yaratishda xatolik yuz berdi.\n"
            "Iltimos, qayta urinib ko'ring."
        )
        logger.error(f"QR yaratishda xato: {e}")
        await state.clear()


@dp.message(F.text == "📷 QR kod → Matn")
async def qr_to_text_start(message: types.Message, state: FSMContext):
    """QR koddan matn o'qish - boshlash"""
    await state.set_state(QRStates.waiting_for_image)
    
    cancel_kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "📷 <b>QR kod rasmini yuboring:</b>\n\n"
        "• Rasmni to'g'ridan-to'g'ri yuboring (compress qilmang)\n"
        "• Yoki file sifatida yuboring\n"
        "• QR kod aniq ko'rinishi kerak\n\n"
        "<i>Qo'llab-quvvatlanadigan formatlar: JPG, PNG</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )


@dp.message(QRStates.waiting_for_image, F.photo | F.document)
async def qr_to_text_process(message: types.Message, state: FSMContext):
    """QR koddan matn o'qish - qayta ishlash"""
    # Loading xabari
    loading_msg = await message.answer("⏳ QR kod o'qilmoqda...")
    
    try:
        # Rasmni yuklab olish
        if message.photo:
            file_id = message.photo[-1].file_id  # Eng katta o'lchamni olish
        elif message.document:
            if not message.document.mime_type.startswith('image/'):
                await loading_msg.delete()
                await message.answer("❌ Faqat rasm fayllarini yuboring!")
                return
            file_id = message.document.file_id
        else:
            await loading_msg.delete()
            await message.answer("❌ Iltimos, rasm yuboring!")
            return
        
        # Faylni yuklab olish
        file = await bot.get_file(file_id)
        
        # Unique fayl nomi
        temp_path = TEMP_DIR / f"qr_{message.from_user.id}_{datetime.now().timestamp()}.png"
        
        # Faylni saqlash
        await bot.download_file(file.file_path, temp_path)
        
        # QR kodni o'qish
        decoded_text = await decode_qr_from_image(temp_path)
        
        # Faylni darhol o'chirish
        if temp_path.exists():
            temp_path.unlink()
        
        await loading_msg.delete()
        
        if decoded_text:
            # Matnni formatlash
            text_preview = decoded_text[:500]  # Birinchi 500 belgini ko'rsatish
            if len(decoded_text) > 500:
                text_preview += "\n\n<i>... (jami {} belgi)</i>".format(len(decoded_text))
            
            await message.answer(
                f"✅ <b>QR kod muvaffaqiyatli o'qildi!</b>\n\n"
                f"📝 <b>Matn:</b>\n<code>{text_preview}</code>\n\n"
                f"📊 Belgilar soni: {len(decoded_text)}\n"
                f"⏰ O'qilgan vaqt: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode="HTML"
            )
            
            # Agar matn juda uzun bo'lsa, file sifatida yuborish
            if len(decoded_text) > 4000:
                text_file = io.BytesIO(decoded_text.encode('utf-8'))
                text_file.name = "qr_text.txt"
                await message.answer_document(
                    document=BufferedInputFile(text_file.read(), filename="qr_text.txt"),
                    caption="📄 To'liq matn fayl ko'rinishida"
                )
            
            logger.info(f"User {message.from_user.id} QR kodni o'qidi (uzunlik: {len(decoded_text)})")
        else:
            await message.answer(
                "❌ <b>QR kod topilmadi!</b>\n\n"
                "Iltimos:\n"
                "• Aniq rasm yuboring\n"
                "• QR kod to'liq ko'rinishini tekshiring\n"
                "• Yaxshi yorug'likda suratga oling",
                parse_mode="HTML"
            )
        
        # State'ni tozalash
        await state.clear()
        
        # Asosiy menyuga qaytish
        await cmd_start(message)
        
    except Exception as e:
        await loading_msg.delete()
        
        # Temp faylni o'chirish
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        
        await message.answer(
            "❌ QR kodni o'qishda xatolik yuz berdi.\n"
            "Iltimos, boshqa rasm yuboring."
        )
        logger.error(f"QR o'qishda xato: {e}")
        await state.clear()


@dp.message(StateFilter(QRStates.waiting_for_text, QRStates.waiting_for_image), F.text == "❌ Bekor qilish")
async def cancel_operation(message: types.Message, state: FSMContext):
    """Operatsiyani bekor qilish"""
    await state.clear()
    await message.answer("❌ Operatsiya bekor qilindi")
    await cmd_start(message)


@dp.message(F.text == "ℹ️ Ma'lumot")
async def info_command(message: types.Message):
    """Ma'lumot"""
    await message.answer(
        "ℹ️ <b>QR Code Bot haqida</b>\n\n"
        "🤖 <b>Versiya:</b> 1.0.0\n"
        "⚡️ <b>Funksiyalar:</b>\n"
        "• Matndan QR kod yaratish\n"
        "• QR koddan matnni o'qish\n"
        "• Tez va xavfsiz ishlash\n"
        "• Avtomatik fayl tozalash\n\n"
        "🔒 <b>Maxfiylik:</b>\n"
        "Barcha fayllar 5 daqiqadan keyin avtomatik o'chiriladi\n\n"
        "💡 <b>Maslahat:</b>\n"
        "• URL'larni to'g'ri kiriting\n"
        "• Aniq rasmlar yuboring\n"
        "• Wi-Fi ma'lumotlarini formatlang\n\n"
        "📧 <b>Aloqa:</b> @YourUsername",
        parse_mode="HTML"
    )


@dp.message(F.text == "📊 Statistika")
async def stats_command(message: types.Message):
    """Statistika"""
    user_id = message.from_user.id
    username = message.from_user.username or "Noma'lum"
    
    # Temp papkadagi fayllar soni
    temp_files = len(list(TEMP_DIR.glob("*")))
    
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👤 <b>Foydalanuvchi ID:</b> <code>{user_id}</code>\n"
        f"📝 <b>Username:</b> @{username}\n"
        f"📁 <b>Temp fayllar:</b> {temp_files} ta\n"
        f"⏰ <b>Vaqt:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"<i>Barcha fayllar 5 daqiqadan keyin avtomatik o'chiriladi</i>",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Yordam"""
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "<b>Buyruqlar:</b>\n"
        "/start - Botni boshlash\n"
        "/help - Yordam\n\n"
        "<b>Funksiyalar:</b>\n"
        "📝 <b>Matn → QR kod:</b>\n"
        "Istalgan matnni QR kodga aylantirish\n\n"
        "📷 <b>QR kod → Matn:</b>\n"
        "QR kod rasmidan matnni o'qish\n\n"
        "<b>Qo'llab-quvvatlanadigan formatlar:</b>\n"
        "• Oddiy matn\n"
        "• URL linklar\n"
        "• Telefon raqamlar\n"
        "• Wi-Fi ma'lumotlari\n"
        "• Email manzillar\n"
        "• Va boshqalar...\n\n"
        "<b>Maksimal uzunlik:</b> 2000 belgi",
        parse_mode="HTML"
    )


@dp.message()
async def unknown_message(message: types.Message, state: FSMContext):
    """Noma'lum xabar"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer(
            "❓ Noma'lum buyruq.\n"
            "/start buyrug'ini yuboring yoki quyidagi tugmalardan birini bosing.",
            reply_markup=types.ReplyKeyboardMarkup(
                keyboard=[
                    [
                        types.KeyboardButton(text="📝 Matn → QR kod"),
                        types.KeyboardButton(text="📷 QR kod → Matn")
                    ]
                ],
                resize_keyboard=True
            )
        )


# ============= Cleanup funksiyasi =============

async def periodic_cleanup():
    """Davriy ravishda temp papkani tozalash"""
    while True:
        try:
            await asyncio.sleep(300)  # Har 5 daqiqada
            
            current_time = datetime.now()
            deleted_count = 0
            
            for file_path in TEMP_DIR.glob("*"):
                if file_path.is_file():
                    # Fayl yaratilgan vaqtni tekshirish
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    if current_time - file_time > FILE_LIFETIME:
                        file_path.unlink()
                        deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"Cleanup: {deleted_count} ta fayl o'chirildi")
                
        except Exception as e:
            logger.error(f"Cleanup xatosi: {e}")


# ============= Asosiy funksiya =============

async def on_startup():
    """Bot ishga tushganda"""
    logger.info("Bot ishga tushdi")
    
    # Cleanup task'ni boshlash
    asyncio.create_task(periodic_cleanup())
    
    # Eski fayllarni darhol tozalash
    for file_path in TEMP_DIR.glob("*"):
        if file_path.is_file():
            file_path.unlink()
    logger.info("Eski fayllar tozalandi")


async def on_shutdown():
    """Bot to'xtaganda"""
    logger.info("Bot to'xtayapti")
    
    # Barcha temp fayllarni o'chirish
    for file_path in TEMP_DIR.glob("*"):
        if file_path.is_file():
            file_path.unlink()
    logger.info("Barcha temp fayllar o'chirildi")


async def main():
    """Asosiy funksiya"""
    try:
        await on_startup()
        logger.info("Polling boshlandi...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot to'xtatildi (Ctrl+C)")
    except Exception as e:
        logger.error(f"Kritik xato: {e}")
