from datetime import datetime

from django.contrib import admin, messages
from django.http import HttpResponse
from django.urls import path
from django.shortcuts import render, redirect

import openpyxl
from decimal import Decimal

from .models import Game, Language, Categories, Faq, Publisher, Price, Image
from subscriptions.models import Consoles

from django.utils.safestring import mark_safe

from .repository import GameRepository
from .services import GameService


@admin.register(Consoles)
class ConsolesAdmin(admin.ModelAdmin):
    list_display = ['name']

@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']

@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = ['category']

@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ['publisher']

class FaqInline(admin.StackedInline):
    model = Faq
    extra = 1

class PriceInline(admin.StackedInline):
    model = Price
    extra = 1

class ImageInline(admin.TabularInline):
    model = Image
    extra = 1

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    change_list_template = "admin/games/game_changelist.html"
    list_display = (
        'title', 'get_prices',
        'get_consoles',
        'get_voice_acting', 'get_subtitles', 'get_sales_amount',
        'is_available', 'release_date'
    )
    list_filter = ['is_available', 'release_date']
    filter_horizontal = ['publishers']
    inlines = [PriceInline, ImageInline, FaqInline]
    search_fields = ['title', 'about']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основная информация', {
            'fields': ('title', 'about', 'main_image_url', 'categories', 'url_u', 'url_t',  'is_available')
        }),
        ('Дополнительное', {
            'fields': ('publishers', 'voice_acting', 'subtitle')
        }),
    )

    @admin.display(description="Консоли")
    def get_consoles(self, obj):
        return ", ".join({c.consoles.name for c in obj.prices.all() if c.is_active})

    @admin.display(description="Озвучки")
    def get_voice_acting(self, obj):
        return ", ".join([f"{c.consoles}({c.code})" for c in obj.voice_acting.all()])

    @admin.display(description="Субтитры")
    def get_subtitles(self, obj):
        return ", ".join([f"{l.consoles}({l.code})" for l in obj.subtitle.all()])

    @admin.display(description="Категории")
    def get_categories(self, obj):
        return ", ".join([c.category for c in obj.categories.all()])

    @admin.display(description="Издатель")
    def get_publishers(self, obj):
        return ", ".join([c.publisher for c in obj.publishers.all()])

    @admin.display(description="Цена")
    def get_prices(self, obj):
        return ", ".join([f"{c.consoles.name}-{c.price} ₽ ({c.payment_type}) " for c in obj.prices.all() if c.is_active])

    @admin.display(description="Цена со скидкой")
    def get_sales_amount(self, obj):
        result = []
        for price in obj.prices.all():
            if not price.is_active:
                continue

            if price.sale_amount and price.sale_unit == "price":
                final_price = price.price - price.sale_amount
                result.append(f"{price.consoles.name} – {final_price:.0f} ₽ ({price.payment_type})")

            elif price.sale_amount and price.sale_unit == "percent":
                final_price = price.price - ((price.price * price.sale_amount) / 100)
                result.append(f"{price.consoles.name} – {final_price:.0f} ₽ ({price.payment_type})")

            else:
                result.append(f"{price.payment_type}({price.consoles.name}-No sale)")

        return ", ".join(result)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("import-excel/", self.import_excel, name="game-import-excel"),
        ]
        return custom_urls + urls


    def import_excel(self, request):

        if request.method == "POST" and request.FILES.get("excel_file"):
            excel_file = request.FILES["excel_file"]
            try:
                wb = openpyxl.load_workbook(excel_file)
                sheet = wb.active

                for row in sheet.iter_rows(min_row=2, values_only=True):
                    title = row[0]
                    price_data = row[1]
                    image_url = row[2]
                    about = row[3]
                    if not title or not price_data:
                        continue


                    parts = price_data.split("::")
                    if len(parts) < 5:
                        continue

                    price1 = float(parts[0])
                    price2 = parts[1]
                    price2 = float(price2) if price2 else None
                    price3 = float(parts[2])
                    voice_text = parts[3]
                    date_str = parts[4]

                    voice_langs = []
                    subtitle_langs = []

                    if "|" in voice_text:
                        languages = voice_text.split(" | ")
                        for _ in languages:
                            if " - " not in _:
                                continue
                            console, lang = _.split(" - ")
                            lang_parts = lang.split("/")
                            voice_lang = lang_parts[0].strip() if len(lang_parts) > 0 else None
                            sub_lang = lang_parts[1].strip() if len(lang_parts) > 1 else None
                            if voice_lang:
                                voice_langs.append((console.strip(), voice_lang))
                            if sub_lang:
                                subtitle_langs.append((console.strip(), sub_lang))
                    elif "/" in voice_text:
                        voice, sub = voice_text.split("/")
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

                    try:
                        release_date = datetime.strptime(date_str.strip(), "%d.%m.%Y").date()
                    except Exception:
                        release_date = None

                    game, created = Game.objects.get_or_create(
                        title=title,
                        defaults={
                            'url_u': '/',
                            'url_t': '/',
                            'main_image_url': image_url or "https://example.com/default-image.jpg",
                            'about': about,
                            'is_available': True,
                            'release_date': release_date
                        }
                    )
                    if not created:
                        game.url_u = '/'
                        game.url_t = '/'
                        game.main_image_url = image_url or "https://example.com/default-image.jpg"
                        game.about = about
                        game.is_available = True
                        game.release_date = release_date
                        game.save()


                    for console_name, lang_name in voice_langs:
                        code = "en" if lang_name.lower().startswith("англ") else "ru" if lang_name.lower().startswith(
                            "рус") else lang_name[:2].lower()
                        console, _ = Consoles.objects.get_or_create(name=console_name)
                        lang_obj, _ = Language.objects.get_or_create(consoles=console, code=code, name=lang_name)
                        game.voice_acting.add(lang_obj)

                    for console_name, lang_name in subtitle_langs:
                        code = "en" if lang_name.lower().startswith("англ") else "ru" if lang_name.lower().startswith(
                            "рус") else lang_name[:2].lower()
                        console, _ = Consoles.objects.get_or_create(name=console_name)
                        lang_obj, _ = Language.objects.get_or_create(consoles=console, code=code, name=lang_name)
                        game.subtitle.add(lang_obj) 
                        

                    if price2 == 0:
                        ps5 = Consoles.objects.filter(name__icontains="PS5").first()
                        if ps5:
                            Price.objects.get_or_create(game=game, consoles=ps5, price=price1,
                                                 payment_type="without_activation", is_active=True)
                            Price.objects.get_or_create(game=game, consoles=ps5, price=price3,
                                                 payment_type="with_activation", is_active=True)
                    else:
                        ps4 = Consoles.objects.filter(name__icontains="PS4").first()
                        ps5 = Consoles.objects.filter(name__icontains="PS5").first()
                        if ps4:
                            Price.objects.get_or_create(game=game, consoles=ps4, price=price1,
                                                 payment_type="without_activation", is_active=True)
                            Price.objects.get_or_create(game=game, consoles=ps4, price=price2,
                                                 payment_type="with_activation", is_active=True)
                        if ps5:
                            Price.objects.get_or_create(game=game, consoles=ps5, price=price1,
                                                 payment_type="without_activation", is_active=True)
                            Price.objects.get_or_create(game=game, consoles=ps5, price=price3,
                                                 payment_type="with_activation", is_active=True)

                return HttpResponse("""
                    <script>
                        alert('Импорт завершён успешно!');
                        window.opener.location.reload(); 
                        window.close(); 
                    </script>
                """)
            except Exception as e:
                messages.error(request, f"Ошибка при импорте: {e}")
                print(e)
            return redirect("..")

        return render(request, "admin/import_excel.html")

