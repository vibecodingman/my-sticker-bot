import asyncio
import io
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile, InputSticker, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from PIL import Image
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class PackCreation(StatesGroup):
    choosing_name = State()

user_photos = {}

main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ Готово, создать стикерпак")]],
    resize_keyboard=True
)

def resize_image_for_sticker(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    
    width, height = img.size
    if width > height:
        new_width = 512
        new_height = int(height * (512 / width))
    else:
        new_height = 512
        new_width = int(width * (512 / height))
        
    new_width = max(1, new_width)
    new_height = max(1, new_height)
    
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    output = io.BytesIO()
    # Сохраняем в WEBP с качеством 90% — вес уменьшится до 30-50 КБ
    img.save(output, format="WEBP", quality=90)
    return output.getvalue()

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_photos[message.from_user.id] = []
    await message.answer(
        "👋 Привет! Отправь мне те фотографии (сжатые или файлом), из которых хочешь получить стикеры.\n"
        "Когда закончишь, нажми на кнопку «Готово, создать стикерпак», чтобы выбрать название!\n"
        "Если возникнут какие-то проблемы, то пиши сюда 👉 @CryGarant",
        reply_markup=main_kb
    )

@dp.message(F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def collect_images(message: Message):
    user_id = message.from_user.id
    if user_id not in user_photos:
        user_photos[user_id] = []
    try:
        file_id = message.photo[-1].file_id if message.photo else message.document.file_id
        file_io = io.BytesIO()
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, file_io)
        sticker_bytes = resize_image_for_sticker(file_io.getvalue())
        user_photos[user_id].append(sticker_bytes)
        await message.answer(f"📸 Фото добавлено. Всего в будущем паке: {len(user_photos[user_id])}")
    except Exception as e:
        await message.answer(f"❌ Ошибка при сохранении фото: {e}")

@dp.message(F.text == "✅ Готово, создать стикерпак")
async def request_pack_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    photos = user_photos.get(user_id, [])
    if not photos:
        await message.answer("⚠️ Сначала отправьте мне хотя бы одну фотографию!")
        return
    await state.set_state(PackCreation.choosing_name)
    await message.answer("📝 Введите желаемое отображаемое название для вашего стикерпака:", reply_markup=ReplyKeyboardRemove())

@dp.message(PackCreation.choosing_name)
async def process_pack_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    photos = user_photos.get(user_id, [])
    pack_title = f"{message.text} by @{BOT_USERNAME}" 
    await message.answer("⏳ Начинаю создание вашего стикерпака, проявите терпение... ")
    pack_name = f"pack_{user_id}_{int(asyncio.get_event_loop().time())}_by_{BOT_USERNAME}"
    try:
        input_stickers = []
        for i, img_bytes in enumerate(photos):
            sticker_file = BufferedInputFile(img_bytes, filename=f"sticker_{i}.png")
            uploaded_file = await bot.upload_sticker_file(user_id=user_id, sticker=sticker_file, sticker_format="static")
            input_stickers.append(InputSticker(sticker=uploaded_file.file_id, format="static", emoji_list=["✨"]))
        await bot.create_new_sticker_set(user_id=user_id, name=pack_name, title=pack_title, stickers=input_stickers, sticker_format="static")
        user_photos[user_id] = []
        await state.clear()
        await message.answer(f"🎉 Стикерпак «{pack_title}» успешно создан!\n🔗 Ссылка: t.me/addstickers/{pack_name}", reply_markup=main_kb)
    except Exception as e:
        await message.answer(f"❌ Ошибка создания пака: {e}\nПопробуйте написать другое название.", reply_markup=main_kb)
        await state.clear()

# Микро веб-сервер для прохождения проверки Render
async def handle_web(request):
    return web.Response(text="Bot is running!")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    # Читаем порт, который выдает Render (по умолчанию 10000)
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    # Запускаем веб-сервер и бота одновременно
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
