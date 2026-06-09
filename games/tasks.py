import io
import uuid
from datetime import datetime
from hashlib import md5
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.utils.text import slugify

from .models import Game, Language, Price
from subscriptions.models import Consoles


import gspread
from google.oauth2.service_account import Credentials

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


SERVICE_ACCOUNT_FILE = "/app/credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

gc = gspread.authorize(credentials)

SPREADSHEET_ID = "1sSZS8ZAudzQ5ir1rgvBByzG7FeWfzAFAbT1XZPwSaDQ"


def generate_unique_slug(title):
    base_slug = slugify(title)
    return f"{base_slug}-{uuid.uuid4().hex[:6]}"


@shared_task
def import_excel_task(file_bytes):
    import openpyxl

    # python-slugify умеет транслитерировать кириллицу (Англ->angl, Рус->rus),
    # как и тот шаг, что раскладывал картинки. Django-вский slugify так не умеет.
    try:
        from slugify import slugify as slugify_unicode
    except ImportError:
        slugify_unicode = None
        logger.warning(
            "python-slugify не установлен — пути к картинкам не будут восстановлены, "
            "ставится default-image.png. Добавь python-slugify в requirements."
        )

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    sheet = wb.active

    consoles_cache = {c.name: c for c in Consoles.objects.all()}
    languages_cache = {(l.consoles_id, l.code): l for l in Language.objects.all()}

    prices_to_create = []
    voice_relations = []
    subtitle_relations = []
    processed_count = 0
    skipped_count = 0

    for row in sheet.iter_rows(min_row=2, values_only=True):
        title = row[0]
        price_data = row[1]
        image_url = row[2]
        about = row[3]
        artic = row[4]
        if not title or not price_data:
            continue

        try:
            parts = price_data.split("::")
            if len(parts) < 5:
                logger.warning("Пропущена строка (мало полей цены): %r", title)
                skipped_count += 1
                continue

            try:
                price1 = float(parts[0])
                price2 = float(parts[1]) if parts[1] else None
                price3 = float(parts[2])
            except (ValueError, TypeError):
                logger.warning("Пропущена строка с некорректной ценой: %r", title)
                skipped_count += 1
                continue
            voice_text = parts[3]
            date_str = parts[4]

            try:
                release_date = datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
            except Exception:
                release_date = None

            try:
                game, created = Game.objects.get_or_create(
                    title=title,
                    defaults={
                        "slug": f"{slugify(title)}-{uuid.uuid4().hex[:6]}",
                        "articule": artic,
                        "url_u": "/",
                        "url_t": "/",
                        "about": about,
                        "is_available": True,
                        "release_date": release_date,
                    },
                )
            except IntegrityError:
                game, created = Game.objects.get_or_create(
                    title=title,
                    defaults={
                        "slug": f"{slugify(title)}-{uuid.uuid4().hex[:6]}",
                        "articule": artic,
                        "url_u": "/",
                        "url_t": "/",
                        "about": about,
                        "is_available": True,
                        "release_date": release_date,
                    },
                )
            image_url = (image_url or "").strip()

            if image_url.startswith("media/"):
                game.main_image_url.name = image_url[len("media/") :]
            elif image_url and slugify_unicode is not None:
                # В файле картинка хранится сырой строкой "Название__...__дата.png".
                # Реальные файлы разложены как
                #   <translit(название)>/main_image/<translit(строки)>.png
                folder = slugify_unicode(title)
                fname = slugify_unicode(image_url.rsplit(".", 1)[0]) + ".png"
                candidate = f"{folder}/main_image/{fname}"
                if default_storage.exists(candidate):
                    game.main_image_url.name = candidate
                else:
                    game.main_image_url.name = "default-image.png"
            else:
                game.main_image_url.name = "default-image.png"
            game.save()

            if not created:
                game.about = about
                game.articule = artic
                game.is_available = True
                game.release_date = release_date
                game.save()

            voice_langs = []
            subtitle_langs = []

            if "|" in voice_text:
                languages = voice_text.split(" | ")
                for _ in languages:
                    if " - " not in _:
                        continue
                    console_name, lang = _.split(" - ", 1)
                    lang_parts = lang.split("/")
                    voice_lang = lang_parts[0].strip() if len(lang_parts) > 0 else None
                    sub_lang = lang_parts[1].strip() if len(lang_parts) > 1 else None
                    if voice_lang:
                        voice_langs.append((console_name.strip(), voice_lang))
                    if sub_lang:
                        subtitle_langs.append((console_name.strip(), sub_lang))
            elif "/" in voice_text:
                voice, _, sub = voice_text.partition("/")
                voice = voice.strip()
                sub = sub.strip()
                if price2 == 0:
                    if voice:
                        voice_langs.append(("PS5", voice))
                    if sub:
                        subtitle_langs.append(("PS5", sub))
                else:
                    for console_name in ["PS4", "PS5"]:
                        if voice:
                            voice_langs.append((console_name, voice))
                        if sub:
                            subtitle_langs.append((console_name, sub))
            else:
                lang = voice_text.strip()
                if price2 == 0:
                    voice_langs.append(("PS5", lang))
                else:
                    for console_name in ["PS4", "PS5"]:
                        voice_langs.append((console_name, lang))

            for console_name, lang_name in voice_langs:
                console = consoles_cache.get(console_name)
                if not console:
                    console = Consoles.objects.create(name=console_name)
                    consoles_cache[console_name] = console

                code = (
                    "en"
                    if lang_name.lower().startswith("англ")
                    else (
                        "ru"
                        if lang_name.lower().startswith("рус")
                        else lang_name[:2].lower()
                    )
                )
                lang_obj = languages_cache.get((console.id, code))
                if not lang_obj:
                    lang_obj = Language.objects.create(
                        consoles=console, code=code, name=lang_name
                    )
                    languages_cache[(console.id, code)] = lang_obj
                voice_relations.append((game, lang_obj))

            for console_name, lang_name in subtitle_langs:
                console = consoles_cache.get(console_name)
                if not console:
                    console = Consoles.objects.create(name=console_name)
                    consoles_cache[console_name] = console

                code = (
                    "en"
                    if lang_name.lower().startswith("англ")
                    else (
                        "ru"
                        if lang_name.lower().startswith("рус")
                        else lang_name[:2].lower()
                    )
                )
                lang_obj = languages_cache.get((console.id, code))
                if not lang_obj:
                    lang_obj = Language.objects.create(
                        consoles=console, code=code, name=lang_name
                    )
                    languages_cache[(console.id, code)] = lang_obj
                subtitle_relations.append((game, lang_obj))

            ps4 = consoles_cache.get("PS4")
            ps5 = consoles_cache.get("PS5")

            if price2 == 0:
                if ps5:
                    prices_to_create.append(
                        Price(
                            game=game,
                            consoles=ps5,
                            price=price1,
                            payment_type="without_activation",
                            is_active=True,
                        )
                    )
                    prices_to_create.append(
                        Price(
                            game=game,
                            consoles=ps5,
                            price=price3,
                            payment_type="with_activation",
                            is_active=True,
                        )
                    )
            else:
                for console in [ps4, ps5]:
                    if console:
                        prices_to_create.append(
                            Price(
                                game=game,
                                consoles=console,
                                price=price1,
                                payment_type="without_activation",
                                is_active=True,
                            )
                        )
                        prices_to_create.append(
                            Price(
                                game=game,
                                consoles=console,
                                price=price2 if console.name == "PS4" else price3,
                                payment_type="with_activation",
                                is_active=True,
                            )
                        )

            processed_count += 1

        except Exception as e:
            logger.warning("Пропущена проблемная строка %r: %s", title, e, exc_info=True)
            skipped_count += 1
            continue

    if prices_to_create:
        Price.objects.bulk_create(prices_to_create)

    for game_obj, lang_obj in voice_relations:
        game_obj.voice_acting.add(lang_obj)
    for game_obj, lang_obj in subtitle_relations:
        game_obj.subtitle.add(lang_obj)

    logger.info(
        "Импорт завершён: обработано %s, пропущено %s",
        processed_count,
        skipped_count,
    )
    return f"Импорт завершён: обработано {processed_count}, пропущено {skipped_count}"


def update_prices_bulk():
    try:
        logger.info("Начало обновления цен")

        # --- Кэшируем игры, консоли, языки ---
        all_games = list(Game.objects.all())
        # Поиск по артикулу; пустые артикулы пропускаем, чтобы не схлопывать
        # разные игры в один ключ "None"/"" (иначе ломается и поиск, и деактивация).
        games_by_art = {}
        for g in all_games:
            art = str(g.articule).strip() if g.articule is not None else ""
            if art:
                games_by_art.setdefault(art, g)
        consoles_cache = {c.name: c for c in Consoles.objects.all()}
        languages_cache = {(l.consoles_id, l.code): l for l in Language.objects.all()}

        ps4 = consoles_cache.get("PS4")
        ps5 = consoles_cache.get("PS5")

        # --- Кэш ВСЕХ цен (не только активных): иначе bulk_create словит
        #     IntegrityError по unique_together, если в базе есть неактивный дубль ---
        prices_cache = {
            (p.game_id, p.consoles_id, p.payment_type): p
            for p in Price.objects.all()
        }

        # --- Читаем таблицу Google Sheets ---
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1

        col_A = worksheet.col_values(1)   # Название
        col_B = worksheet.col_values(2)   # цена без активации
        col_C = worksheet.col_values(3)   # PS4 с активацией (0 = нет PS4)
        col_D = worksheet.col_values(4)   # PS5 с активацией
        col_E = worksheet.col_values(5)   # Описание
        col_G = worksheet.col_values(7)   # озвучка/субтитры
        col_J = worksheet.col_values(10)  # артикул

        # col_values() обрезает столбец по последней непустой ячейке, поэтому колонки
        # бывают разной длины. Длину берём по названию, а ячейки читаем безопасно —
        # это убирает риск IndexError по col_D/col_E/col_G.
        def cell(col, idx):
            return col[idx] if idx < len(col) else ""

        data_len = len(col_A)
        logger.info(f"Обработаем {max(data_len - 1, 0)} строк(и) данных (без заголовка)")

        # --- Списки для bulk ---
        prices_to_update = []
        prices_to_create = []
        games_to_update = []
        new_games_count = 0
        skipped_count = 0
        games_in_table_ids = set()
        # (game_id, console_id) — какие консоли реально поддержаны в таблице.
        # По ним в конце удалим цены вариантов, которых больше нет.
        supported_console_keys = set()
        voice_relations = []
        subtitle_relations = []

        for i in range(1, data_len):
            title = cell(col_A, i)
            if not title or not title.strip():
                continue

            try:
                game_art = str(cell(col_J, i)).strip()
                game = games_by_art.get(game_art) if game_art else None
                created_new_game = False

                # --- Если игры нет, создаём ---
                if not game:
                    desc = cell(col_E, i)
                    artic = cell(col_J, i)
                    voice_text = cell(col_G, i)

                    game, created = Game.objects.get_or_create(
                        title=title,
                        defaults={
                            "slug": f"{slugify(title)}-{uuid.uuid4().hex[:6]}",
                            "articule": artic,
                            "url_u": "/",
                            "url_t": "/",
                            "about": desc,
                            "is_available": True,
                            "release_date": None,
                        },
                    )

                    game.main_image_url.name = "default-image.png"
                    game.save()

                    # запоминаем новую игру в кэшах, чтобы повтор артикула не дублировал
                    all_games.append(game)
                    if game_art:
                        games_by_art.setdefault(game_art, game)

                    # --- Обработка озвучки и субтитров ---
                    voice_langs = []
                    subtitle_langs = []

                    if voice_text and voice_text.strip():
                        if "|" in voice_text:
                            languages = voice_text.split(" | ")
                            for _ in languages:
                                if " - " not in _:
                                    continue
                                console_name, lang = _.split(" - ", 1)
                                lang_parts = lang.split("/")
                                voice_lang = (
                                    lang_parts[0].strip() if len(lang_parts) > 0 else None
                                )
                                sub_lang = (
                                    lang_parts[1].strip() if len(lang_parts) > 1 else None
                                )
                                if voice_lang:
                                    voice_langs.append((console_name.strip(), voice_lang))
                                if sub_lang:
                                    subtitle_langs.append((console_name.strip(), sub_lang))
                        elif "/" in voice_text:
                            voice, _, sub = voice_text.partition("/")
                            voice = voice.strip()
                            sub = sub.strip()
                            if voice:
                                voice_langs.append(("PS5", voice))
                            if sub:
                                subtitle_langs.append(("PS5", sub))
                        else:
                            lang = voice_text.strip()
                            if lang:
                                voice_langs.append(("PS5", lang))

                    for console_name, lang_name in voice_langs:
                        console = consoles_cache.get(console_name)
                        if not console:
                            console = Consoles.objects.create(name=console_name)
                            consoles_cache[console_name] = console
                        code = (
                            "en"
                            if lang_name.lower().startswith("англ")
                            else "ru"
                            if lang_name.lower().startswith("рус")
                            else lang_name[:2].lower()
                        )
                        lang_obj = languages_cache.get((console.id, code))
                        if not lang_obj:
                            lang_obj = Language.objects.create(
                                consoles=console, code=code, name=lang_name
                            )
                            languages_cache[(console.id, code)] = lang_obj
                        voice_relations.append((game, lang_obj))

                    for console_name, lang_name in subtitle_langs:
                        console = consoles_cache.get(console_name)
                        if not console:
                            console = Consoles.objects.create(name=console_name)
                            consoles_cache[console_name] = console
                        code = (
                            "en"
                            if lang_name.lower().startswith("англ")
                            else "ru"
                            if lang_name.lower().startswith("рус")
                            else lang_name[:2].lower()
                        )
                        lang_obj = languages_cache.get((console.id, code))
                        if not lang_obj:
                            lang_obj = Language.objects.create(
                                consoles=console, code=code, name=lang_name
                            )
                            languages_cache[(console.id, code)] = lang_obj
                        subtitle_relations.append((game, lang_obj))

                    new_games_count += 1
                    created_new_game = True

                games_in_table_ids.add(game.id)

                # --- Обновляем is_available ---
                if not created_new_game and not game.is_available:
                    game.is_available = True
                    games_to_update.append(game)

                # --- Обновление цен для PS5 ---
                if ps5:
                    supported_console_keys.add((game.id, ps5.id))
                    for payment_type, col_value in [
                        ("with_activation", cell(col_D, i)),
                        ("without_activation", cell(col_B, i)),
                    ]:
                        try:
                            price_val = float(col_value)
                        except (ValueError, TypeError):
                            continue
                        key = (game.id, ps5.id, payment_type)
                        price = prices_cache.get(key)
                        if price is not None:
                            price.price = price_val
                            price.is_active = True
                            prices_to_update.append(price)
                        else:
                            prices_to_create.append(
                                Price(
                                    game=game,
                                    consoles=ps5,
                                    price=price_val,
                                    payment_type=payment_type,
                                    is_active=True,
                                )
                            )

                # --- Обновление цен для PS4 (только если PS4-цена задана и != 0) ---
                c_val = str(cell(col_C, i)).strip()
                if ps4 and c_val not in ("0", "0.0", ""):
                    supported_console_keys.add((game.id, ps4.id))
                    for payment_type, col_value in [
                        ("with_activation", cell(col_C, i)),
                        ("without_activation", cell(col_B, i)),
                    ]:
                        try:
                            price_val = float(col_value)
                        except (ValueError, TypeError):
                            continue
                        key = (game.id, ps4.id, payment_type)
                        price = prices_cache.get(key)
                        if price is not None:
                            price.price = price_val
                            price.is_active = True
                            prices_to_update.append(price)
                        else:
                            prices_to_create.append(
                                Price(
                                    game=game,
                                    consoles=ps4,
                                    price=price_val,
                                    payment_type=payment_type,
                                    is_active=True,
                                )
                            )

            except Exception as e:
                logger.warning(
                    "Пропущена проблемная строка %r: %s", title, e, exc_info=True
                )
                skipped_count += 1
                continue

        # --- Bulk операции ---
        if prices_to_update:
            Price.objects.bulk_update(prices_to_update, ["price", "is_active"])
        if prices_to_create:
            Price.objects.bulk_create(prices_to_create)
        if games_to_update:
            Game.objects.bulk_update(games_to_update, ["is_available"])

        # --- Удаляем цены вариантов (консолей), которых больше нет в таблице ---
        #     Напр. игра стала PS5-only (col_C = 0) → её PS4-цены удаляются.
        #     Трогаем только игры, присутствующие в таблице.
        price_ids_to_delete = [
            p.id
            for (gid, cid, _pt), p in prices_cache.items()
            if gid in games_in_table_ids and (gid, cid) not in supported_console_keys
        ]
        deleted_prices_count = 0
        if price_ids_to_delete:
            deleted_prices_count = Price.objects.filter(
                id__in=price_ids_to_delete
            ).delete()[0]

        # --- Деактивируем игры, которых нет в таблице (по id, не по артикулу) ---
        games_not_in_table = [g for g in all_games if g.id not in games_in_table_ids]
        if games_not_in_table:
            for g in games_not_in_table:
                g.is_available = False
            Game.objects.bulk_update(games_not_in_table, ["is_available"])

        # --- Добавляем озвучку и субтитры ---
        for game_obj, lang_obj in voice_relations:
            game_obj.voice_acting.add(lang_obj)
        for game_obj, lang_obj in subtitle_relations:
            game_obj.subtitle.add(lang_obj)

        # --- Итоговые значения ---
        updated_games_count = len(games_to_update)
        disabled_games_count = len(games_not_in_table)
        total_new_games = new_games_count

        logger.info(
            f"Обновление цен завершено: "
            f"игр обновлено: {updated_games_count}, "
            f"игр деактивировано: {disabled_games_count}, "
            f"новых игр создано: {total_new_games}, "
            f"цен удалено (неподдерж. варианты): {deleted_prices_count}, "
            f"строк пропущено: {skipped_count}"
        )

        return {
            "updated_games": updated_games_count,
            "disabled_games": disabled_games_count,
            "new_games": total_new_games,
            "deleted_prices": deleted_prices_count,
            "skipped_rows": skipped_count,
        }

    except Exception as e:
        logger.error(f"Ошибка при обновлении цен: {e}", exc_info=True)
        raise
