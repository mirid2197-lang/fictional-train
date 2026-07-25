import asyncio
import logging
import os
import traceback
from datetime import datetime, date
from typing import Optional, Union

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message,
    FSInputFile, InputMediaPhoto, CallbackQuery
)
from aiogram.enums import ParseMode, ContentType
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация бота
BOT_TOKEN = "8908089239:AAFmtv_81rNgFSpwR-aXPPeMKmqZmZd1AnY"
ADMIN_ID = 8071140258
PRIVATE_CHANNEL_LINK = "https://t.me/+1U-jYlcjtbo0ZDQy"
START_PHOTO_PATH = "Start.jpg"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Статистика
daily_complaints = {}
total_complaints = 0
bot_active = True
user_ids = set()

# Состояния FSM
class QuestionState(StatesGroup):
    waiting_for_question = State()
    waiting_for_response = State()
    waiting_for_announcement = State()

# Вспомогательные функции
async def safe_edit_message(
    message: Message,
    text: Optional[str] = None,
    caption: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    photo: Optional[Union[str, FSInputFile]] = None
) -> Optional[Message]:
    """
    Безопасное редактирование сообщения с автоматическим определением типа.
    """
    try:
        # Если передан путь к фото
        if photo and os.path.exists(str(photo) if isinstance(photo, str) else photo.path):
            media = FSInputFile(str(photo) if isinstance(photo, str) else photo.path)
            if message.photo:
                return await message.edit_media(
                    media=InputMediaPhoto(media=media, caption=caption),
                    reply_markup=reply_markup
                )
            else:
                # Удаляем текстовое сообщение и отправляем фото
                try:
                    await message.delete()
                except:
                    pass
                return await message.answer_photo(
                    photo=media,
                    caption=caption,
                    reply_markup=reply_markup
                )

        # Если сообщение содержит фото
        if message.photo:
            if caption is not None:
                return await message.edit_caption(
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                return await message.edit_reply_markup(reply_markup=reply_markup)

        # Если сообщение текстовое
        if message.text or message.caption:
            if text is not None:
                return await message.edit_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            elif caption is not None:
                return await message.edit_text(
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                return await message.edit_reply_markup(reply_markup=reply_markup)

        # Fallback: пробуем edit_text с caption
        if caption is not None:
            try:
                return await message.edit_text(
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except:
                pass

        return await message.edit_reply_markup(reply_markup=reply_markup)

    except TelegramBadRequest as e:
        error_msg = str(e)
        if "message is not modified" in error_msg.lower():
            logger.debug("Сообщение не изменено (одинаковый контент)")
            return message
        elif "message to edit not found" in error_msg.lower():
            logger.warning("Сообщение не найдено для редактирования")
            return None
        elif "there is no caption" in error_msg.lower():
            logger.debug("Нет подписи для редактирования, пробуем edit_text")
            try:
                return await message.edit_text(
                    text=caption or text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except:
                return None
        else:
            logger.error(f"Ошибка редактирования: {e}")
            try:
                # Создаем новое сообщение
                if message.photo and caption:
                    return await message.answer_photo(
                        photo=message.photo[-1].file_id,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                else:
                    return await message.answer(
                        text=caption or text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
            except:
                return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка редактирования: {e}")
        return None

async def safe_send_message(
    chat_id: int,
    text: Optional[str] = None,
    photo: Optional[Union[str, FSInputFile]] = None,
    caption: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    **kwargs
) -> Optional[Message]:
    """
    Безопасная отправка сообщения с обработкой ошибок.
    """
    try:
        if photo and os.path.exists(str(photo) if isinstance(photo, str) else photo.path):
            media = FSInputFile(str(photo) if isinstance(photo, str) else photo.path)
            return await bot.send_photo(
                chat_id=chat_id,
                photo=media,
                caption=caption or text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        elif text or caption:
            return await bot.send_message(
                chat_id=chat_id,
                text=text or caption,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        else:
            return await bot.send_message(
                chat_id=chat_id,
                text="Нет содержимого для отправки",
                reply_markup=reply_markup
            )
    except TelegramForbiddenError:
        logger.warning(f"Пользователь {chat_id} заблокировал бота")
        return None
    except Exception as e:
        if "not found" in str(e).lower() or "chat not found" in str(e).lower():
            logger.warning(f"Чат {chat_id} не найден")
            return None
        logger.error(f"Ошибка отправки сообщения: {e}")
        return None

async def forward_content_to_admin(user_message: Message, admin_id: int):
    """
    Пересылка любого типа контента администратору.
    """
    try:
        content_type = user_message.content_type

        if content_type == ContentType.TEXT:
            await bot.send_message(
                admin_id,
                f"💬 {user_message.text}"
            )
        elif content_type == ContentType.PHOTO:
            await bot.send_photo(
                admin_id,
                user_message.photo[-1].file_id,
                caption=f"🖼 Фото от пользователя\n{user_message.caption or ''}"
            )
        elif content_type == ContentType.VIDEO:
            await bot.send_video(
                admin_id,
                user_message.video.file_id,
                caption=f"🎥 Видео от пользователя\n{user_message.caption or ''}"
            )
        elif content_type == ContentType.VOICE:
            await bot.send_voice(admin_id, user_message.voice.file_id)
            await bot.send_message(admin_id, "🎤 Голосовое сообщение от пользователя")
        elif content_type == ContentType.AUDIO:
            await bot.send_audio(
                admin_id,
                user_message.audio.file_id,
                caption=f"🎵 Аудио от пользователя\n{user_message.caption or ''}"
            )
        elif content_type == ContentType.STICKER:
            await bot.send_sticker(admin_id, user_message.sticker.file_id)
            await bot.send_message(admin_id, "😀 Стикер от пользователя")
        elif content_type == ContentType.DOCUMENT:
            await bot.send_document(
                admin_id,
                user_message.document.file_id,
                caption=f"📄 Документ от пользователя\n{user_message.caption or ''}"
            )
        elif content_type == ContentType.ANIMATION:
            await bot.send_animation(
                admin_id,
                user_message.animation.file_id,
                caption=f"🎬 GIF от пользователя\n{user_message.caption or ''}"
            )
        elif content_type == ContentType.VIDEO_NOTE:
            await bot.send_video_note(admin_id, user_message.video_note.file_id)
            await bot.send_message(admin_id, "📹 Видеосообщение от пользователя")
        else:
            await bot.send_message(
                admin_id,
                f"📎 Получен тип контента: {content_type}"
            )
            # Пробуем переслать напрямую
            try:
                await bot.forward_message(admin_id, user_message.chat.id, user_message.message_id)
            except:
                await bot.send_message(admin_id, "Не удалось переслать сообщение")
    except Exception as e:
        logger.error(f"Ошибка пересылки контента админу: {e}")
        await bot.send_message(admin_id, f"❌ Ошибка пересылки сообщения: {e}")

async def send_content_to_user(
    admin_message: Message,
    user_id: int,
    reply_markup: Optional[InlineKeyboardMarkup] = None
):
    """
    Отправка любого типа контента от администратора пользователю.
    """
    try:
        content_type = admin_message.content_type

        if content_type == ContentType.TEXT:
            await bot.send_message(
                user_id,
                f"💬 <i>Ответ администратора:</i>\n\n{admin_message.text}",
                reply_markup=reply_markup
            )
        elif content_type == ContentType.PHOTO:
            await bot.send_photo(
                user_id,
                admin_message.photo[-1].file_id,
                caption=f"🖼 <i>Ответ администратора:</i>\n{admin_message.caption or ''}",
                reply_markup=reply_markup
            )
        elif content_type == ContentType.VIDEO:
            await bot.send_video(
                user_id,
                admin_message.video.file_id,
                caption=f"🎥 <i>Ответ администратора:</i>\n{admin_message.caption or ''}",
                reply_markup=reply_markup
            )
        elif content_type == ContentType.VOICE:
            await bot.send_voice(
                user_id,
                admin_message.voice.file_id,
                reply_markup=reply_markup
            )
            await bot.send_message(user_id, "🎤 Голосовой ответ от администратора")
        elif content_type == ContentType.AUDIO:
            await bot.send_audio(
                user_id,
                admin_message.audio.file_id,
                caption=f"🎵 <i>Ответ администратора:</i>\n{admin_message.caption or ''}",
                reply_markup=reply_markup
            )
        elif content_type == ContentType.STICKER:
            await bot.send_sticker(
                user_id,
                admin_message.sticker.file_id,
                reply_markup=reply_markup
            )
            await bot.send_message(user_id, "😀 Стикер от администратора")
        elif content_type == ContentType.DOCUMENT:
            await bot.send_document(
                user_id,
                admin_message.document.file_id,
                caption=f"📄 <i>Ответ администратора:</i>\n{admin_message.caption or ''}",
                reply_markup=reply_markup
            )
        elif content_type == ContentType.ANIMATION:
            await bot.send_animation(
                user_id,
                admin_message.animation.file_id,
                caption=f"🎬 <i>Ответ администратора:</i>\n{admin_message.caption or ''}",
                reply_markup=reply_markup
            )
        elif content_type == ContentType.VIDEO_NOTE:
            await bot.send_video_note(
                user_id,
                admin_message.video_note.file_id,
                reply_markup=reply_markup
            )
            await bot.send_message(user_id, "📹 Видеосообщение от администратора")
        else:
            await bot.send_message(
                user_id,
                f"📎 Ответ от администратора\nТип сообщения: {content_type}",
                reply_markup=reply_markup
            )
    except TelegramForbiddenError:
        logger.warning(f"Не удалось отправить ответ пользователю {user_id}: бот заблокирован")
    except Exception as e:
        logger.error(f"Ошибка отправки ответа пользователю {user_id}: {e}")

# Клавиатуры
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 ПРИВАТНЫЙ КАНАЛ", callback_data="private_channel")],
        [InlineKeyboardButton(text="📝 НАПИСАТЬ ВОПРОС", callback_data="write_question")],
        [InlineKeyboardButton(text="👨‍💻 АДМИНИСТРАТОР", callback_data="admin_panel")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_main")]
    ])

def get_admin_response_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"decline_{user_id}"),
            InlineKeyboardButton(text="✅ ПРИНЯТЬ", callback_data=f"accept_{user_id}")
        ]
    ])

def get_admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 СТАТИСТИКА ЗА ДЕНЬ", callback_data="daily_stats")],
        [InlineKeyboardButton(text="📈 ОБЩАЯ СТАТИСТИКА", callback_data="total_stats")],
        [InlineKeyboardButton(text="📢 СДЕЛАТЬ ОБЪЯВЛЕНИЕ", callback_data="make_announcement")],
        [InlineKeyboardButton(text="👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ", callback_data="users_list")],
        [InlineKeyboardButton(text="⏸ ПРИОСТАНОВИТЬ БОТА", callback_data="pause_bot")],
        [InlineKeyboardButton(text="▶️ ЗАПУСТИТЬ БОТА", callback_data="start_bot")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_main")]
    ])

# Тексты
WELCOME_TEXT = (
    "👤 <b>ДОБРО ПОЖАЛОВАТЬ В Николаевич God Team</b>\n\n"
    "📌 Здесь вы можете:\n"
    "• Написать жалобу или вопрос\n"
    "• Получить оперативный ответ\n"
    "• Подписаться на приватный канал\n\n"
    "👇 <i>Выберите действие ниже:</i>"
)

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    try:
        user_ids.add(message.from_user.id)

        if not bot_active and message.from_user.id != ADMIN_ID:
            await safe_send_message(
                message.chat.id,
                "⏸ Бот временно приостановлен. Попробуйте позже."
            )
            return

        if os.path.exists(START_PHOTO_PATH):
            await safe_send_message(
                message.chat.id,
                photo=START_PHOTO_PATH,
                caption=WELCOME_TEXT,
                reply_markup=get_main_keyboard()
            )
        else:
            await safe_send_message(
                message.chat.id,
                text=WELCOME_TEXT,
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}\n{traceback.format_exc()}")
        await safe_send_message(
            message.chat.id,
            "Произошла ошибка. Попробуйте позже или обратитесь к администратору.",
            reply_markup=get_main_keyboard()
        )

# Обработчик кнопки "Приватный канал"
@dp.callback_query(F.data == "private_channel")
async def show_private_channel(callback: CallbackQuery):
    try:
        text = (
            "🔒 <b>НАШ ПРИВАТНЫЙ КАНАЛ</b>\n\n"
            f"📎 Ссылка для доступа:\n"
            f"<code>{PRIVATE_CHANNEL_LINK}</code>\n\n"
            "🤫 <i>Эксклюзивный контент только для своих!</i>"
        )
        await safe_edit_message(
            callback.message,
            caption=text,
            reply_markup=get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в show_private_channel: {e}")
    finally:
        await callback.answer("🔒 Приватный канал")

# Обработчик кнопки "Написать вопрос"
@dp.callback_query(F.data == "write_question")
async def start_question(callback: CallbackQuery, state: FSMContext):
    try:
        if not bot_active:
            await callback.answer("⏸ Бот временно приостановлен", show_alert=True)
            return

        text = (
            "📝 <b>НАПИШИТЕ ВАШ ВОПРОС</b>\n\n"
            "Принимаются любые форматы:\n"
            "💬 Текстовые сообщения\n"
            "🖼 Фотографии\n"
            "🎥 Видео\n"
            "🎤 Голосовые сообщения\n"
            "😀 Стикеры\n\n"
            "<i>Опишите вашу проблему или задайте вопрос</i>"
        )
        await safe_edit_message(
            callback.message,
            caption=text,
            reply_markup=get_back_keyboard()
        )
        await state.set_state(QuestionState.waiting_for_question)
    except Exception as e:
        logger.error(f"Ошибка в start_question: {e}")
    finally:
        await callback.answer("📝 Напишите вопрос")

# Обработчик получения вопроса от пользователя
@dp.message(StateFilter(QuestionState.waiting_for_question))
async def receive_question(message: Message, state: FSMContext):
    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else f"{user.first_name} (ID: {user.id})"

        confirm_text = (
            "✅ <b>ВАШ ВОПРОС ОТПРАВЛЕН</b>\n\n"
            "📨 Сообщение доставлено команде Николаевич God team\n"
            "⏳ Ожидайте ответа в ближайшее время\n\n"
            "<i>Спасибо за обращение!</i>"
        )
        await safe_send_message(
            message.chat.id,
            text=confirm_text,
            reply_markup=get_back_keyboard()
        )

        await state.update_data(user_id=user.id)
        await state.clear()

        admin_text = (
            f"📨 <b>НОВОЕ ОБРАЩЕНИЕ</b>\n\n"
            f"👤 От: {username}\n"
            f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"🆔 User ID: <code>{user.id}</code>\n\n"
            f"📎 <i>Сообщение ниже:</i>"
        )
        await safe_send_message(
            ADMIN_ID,
            text=admin_text,
            reply_markup=get_admin_response_keyboard(user.id)
        )

        await forward_content_to_admin(message, ADMIN_ID)

        today = date.today()
        daily_complaints[today] = daily_complaints.get(today, 0) + 1
        global total_complaints
        total_complaints += 1

    except Exception as e:
        logger.error(f"Ошибка в receive_question: {e}\n{traceback.format_exc()}")
        await safe_send_message(
            message.chat.id,
            "Произошла ошибка при отправке вопроса. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
        await state.clear()

# Обработчик кнопки "Отклонить"
@dp.callback_query(F.data.startswith("decline_"))
async def decline_question(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split("_")[1])

        decline_text = (
            "❌ <b>ВАШЕ ОБРАЩЕНИЕ ОТКЛОНЕНО</b>\n\n"
            "Команда Николаевич God team отклонила ваш вопрос\n"
            "Возможно, он не соответствует правилам сообщества\n\n"
            "📝 Вы можете задать другой вопрос"
        )

        await safe_send_message(
            user_id,
            text=decline_text,
            reply_markup=get_back_keyboard()
        )

        # Отмечаем сообщение как отклоненное
        original_text = callback.message.text or callback.message.caption or ""
        await safe_edit_message(
            callback.message,
            text=original_text + "\n\n❌ <b>ОТКЛОНЕНО</b>"
        )
    except Exception as e:
        logger.error(f"Ошибка в decline_question: {e}")
    finally:
        await callback.answer("❌ Вопрос отклонен")

# Обработчик кнопки "Принять"
@dp.callback_query(F.data.startswith("accept_"))
async def accept_question(callback: CallbackQuery, state: FSMContext):
    try:
        user_id = int(callback.data.split("_")[1])
        await state.update_data(responding_to=user_id)
        await state.set_state(QuestionState.waiting_for_response)

        response_text = (
            "✅ <b>НАПИШИТЕ ОТВЕТ</b>\n\n"
            "Принимаются любые форматы сообщений\n"
            "Ответ будет отправлен пользователю"
        )

        await safe_edit_message(
            callback.message,
            text=response_text,
            reply_markup=get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в accept_question: {e}")
    finally:
        await callback.answer("✅ Принято")

# Обработчик ответа админа
@dp.message(StateFilter(QuestionState.waiting_for_response))
async def send_admin_response(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_id = data.get("responding_to")

        if not user_id:
            await safe_send_message(
                message.chat.id,
                "❌ Ошибка: не найден ID пользователя"
            )
            await state.clear()
            return

        notify_text = (
            "📨 <b>ОТВЕТ ОТ Николаевич God team</b>\n\n"
            "Вы получили ответ на ваш вопрос:"
        )
        await safe_send_message(user_id, text=notify_text)

        await send_content_to_user(message, user_id, reply_markup=get_back_keyboard())

        await safe_send_message(
            message.chat.id,
            "✅ Ответ успешно отправлен пользователю"
        )
    except Exception as e:
        logger.error(f"Ошибка в send_admin_response: {e}\n{traceback.format_exc()}")
        await safe_send_message(
            message.chat.id,
            "Произошла ошибка при отправке ответа."
        )
    finally:
        await state.clear()

# Обработчик кнопки "Админ"
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ У вас нет доступа к админ-панели", show_alert=True)
            return

        admin_text = (
            "👨‍💻 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            "Добро пожаловать в панель управления\n"
            f"🕐 Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y')}\n\n"
            "Выберите действие:"
        )

        await safe_edit_message(
            callback.message,
            caption=admin_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в admin_panel: {e}")
    finally:
        await callback.answer("👨‍💻 Админ-панель")

# Статистика за день
@dp.callback_query(F.data == "daily_stats")
async def show_daily_stats(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return

        today = date.today()
        count = daily_complaints.get(today, 0)

        stats_text = (
            "📊 <b>СТАТИСТИКА ЗА СЕГОДНЯ</b>\n\n"
            f"📅 Дата: {today.strftime('%d.%m.%Y')}\n"
            f"📝 Обработано вопросов: <b>{count}</b>\n\n"
            f"🕐 Текущее время: {datetime.now().strftime('%H:%M:%S')}"
        )

        await safe_edit_message(
            callback.message,
            caption=stats_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в show_daily_stats: {e}")
    finally:
        await callback.answer("📊 Статистика за день")

# Общая статистика
@dp.callback_query(F.data == "total_stats")
async def show_total_stats(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return

        avg_per_day = total_complaints // max(len(daily_complaints), 1)

        stats_text = (
            "📈 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
            f"👥 Всего пользователей: <b>{len(user_ids)}</b>\n"
            f"📝 Всего обращений: <b>{total_complaints}</b>\n"
            f"📅 Дней работы: <b>{len(daily_complaints)}</b>\n\n"
            f"📊 Среднее обращений в день: <b>{avg_per_day}</b>"
        )

        await safe_edit_message(
            callback.message,
            caption=stats_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в show_total_stats: {e}")
    finally:
        await callback.answer("📈 Общая статистика")

# Список пользователей
@dp.callback_query(F.data == "users_list")
async def show_users_list(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return

        users_sample = list(user_ids)[:20]
        users_list_str = "\n".join([f"• <code>{uid}</code>" for uid in users_sample])
        if len(user_ids) > 20:
            users_list_str += f"\n\n... и еще {len(user_ids) - 20}"

        users_text = (
            "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
            f"Всего пользователей: {len(user_ids)}\n\n"
            f"ID пользователей:\n{users_list_str}"
        )

        await safe_edit_message(
            callback.message,
            caption=users_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в show_users_list: {e}")
    finally:
        await callback.answer("👥 Список пользователей")

# Объявление
@dp.callback_query(F.data == "make_announcement")
async def start_announcement(callback: CallbackQuery, state: FSMContext):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return

        announcement_text = (
            "📢 <b>СОЗДАНИЕ ОБЪЯВЛЕНИЯ</b>\n\n"
            "Напишите текст объявления\n"
            "Оно будет отправлено всем пользователям бота\n\n"
            "<i>Поддерживается HTML-разметка</i>"
        )

        await safe_edit_message(
            callback.message,
            caption=announcement_text,
            reply_markup=get_back_keyboard()
        )
        await state.set_state(QuestionState.waiting_for_announcement)
    except Exception as e:
        logger.error(f"Ошибка в start_announcement: {e}")
    finally:
        await callback.answer("📢 Создание объявления")

# Отправка объявления
@dp.message(StateFilter(QuestionState.waiting_for_announcement))
async def send_announcement(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    success_count = 0
    error_count = 0

    try:
        users_copy = user_ids.copy()

        for user_id in users_copy:
            result = await safe_send_message(
                user_id,
                text=f"📢 <b>ОБЪЯВЛЕНИЕ ОТ Николаевич God team</b>\n\n{message.text}"
            )
            if result:
                success_count += 1
            else:
                error_count += 1

        result_text = (
            f"📢 <b>РЕЗУЛЬТАТ РАССЫЛКИ</b>\n\n"
            f"✅ Успешно отправлено: {success_count}\n"
            f"❌ Ошибок: {error_count}\n"
            f"👥 Всего пользователей: {len(user_ids)}"
        )

        await safe_send_message(
            message.chat.id,
            text=result_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в send_announcement: {e}\n{traceback.format_exc()}")
        await safe_send_message(
            message.chat.id,
            "Произошла ошибка при рассылке.",
            reply_markup=get_admin_panel_keyboard()
        )
    finally:
        await state.clear()

# Приостановка бота
@dp.callback_query(F.data == "pause_bot")
async def pause_bot(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return

        global bot_active
        bot_active = False

        pause_text = (
            "⏸ <b>БОТ ПРИОСТАНОВЛЕН</b>\n\n"
            "Пользователи не смогут отправлять вопросы\n"
            "Для возобновления работы нажмите «Запустить бота»"
        )

        await safe_edit_message(
            callback.message,
            caption=pause_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в pause_bot: {e}")
    finally:
        await callback.answer("⏸ Бот приостановлен")

# Запуск бота
@dp.callback_query(F.data == "start_bot")
async def start_bot_callback(callback: CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID:
            await callback.answer("⛔ Нет доступа", show_alert=True)
            return

        global bot_active
        bot_active = True

        start_text = (
            "▶️ <b>БОТ ЗАПУЩЕН</b>\n\n"
            "Бот снова принимает обращения\n"
            "Все функции работают в обычном режиме"
        )

        await safe_edit_message(
            callback.message,
            caption=start_text,
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в start_bot_callback: {e}")
    finally:
        await callback.answer("▶️ Бот запущен")

# Кнопка "Назад"
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()

        if os.path.exists(START_PHOTO_PATH):
            await safe_edit_message(
                callback.message,
                caption=WELCOME_TEXT,
                reply_markup=get_main_keyboard(),
                photo=START_PHOTO_PATH
            )
        else:
            await safe_edit_message(
                callback.message,
                text=WELCOME_TEXT,
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка в back_to_main: {e}")
        # Пробуем отправить новое сообщение
        if os.path.exists(START_PHOTO_PATH):
            await safe_send_message(
                callback.message.chat.id,
                photo=START_PHOTO_PATH,
                caption=WELCOME_TEXT,
                reply_markup=get_main_keyboard()
            )
        else:
            await safe_send_message(
                callback.message.chat.id,
                text=WELCOME_TEXT,
                reply_markup=get_main_keyboard()
            )
    finally:
        await callback.answer("◀️ Главное меню")

# Обработчик всех остальных сообщений (для случаев, когда состояние не установлено)
@dp.message()
async def handle_unknown_messages(message: Message):
    if message.content_type == ContentType.NEW_CHAT_MEMBERS:
        return
    if message.content_type == ContentType.LEFT_CHAT_MEMBER:
        return

    await safe_send_message(
        message.chat.id,
        "Используйте команду /start для начала работы с ботом.",
        reply_markup=get_main_keyboard()
    )

# Запуск бота
async def main():
    logger.info("🤖 Бот Николаевич God team запускается...")
    logger.info(f"👨‍💻 ID администратора: {ADMIN_ID}")
    logger.info(f"📸 Стартовое фото: {'Загружено' if os.path.exists(START_PHOTO_PATH) else 'Не найдено'}")

    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}\n{traceback.format_exc()}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
