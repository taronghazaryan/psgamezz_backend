from .tasks import import_excel_task
from django.contrib import admin, messages
from django.core.files import File
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
    list_display = ["name"]


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ["code", "name"]


@admin.register(Categories)
class CategoriesAdmin(admin.ModelAdmin):
    list_display = ["category"]


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ["publisher"]


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
        "title",
        "get_prices",
        "get_consoles",
        "get_voice_acting",
        "get_subtitles",
        "get_sales_amount",
        "is_available",
        "release_date",
        "articule",
    )
    list_filter = ["is_available", "release_date"]
    filter_horizontal = ["publishers"]
    inlines = [PriceInline, ImageInline, FaqInline]
    search_fields = ["title", "about", "articule"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "title",
                    "about",
                    "main_image_url",
                    "categories",
                    "url_u",
                    "url_t",
                    "is_available",
                    "articule",
                )
            },
        ),
        ("Дополнительное", {"fields": ("publishers", "voice_acting", "subtitle")}),
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
        return ", ".join(
            [
                f"{c.consoles.name}-{c.price} ₽ ({c.payment_type}) "
                for c in obj.prices.all()
                if c.is_active
            ]
        )

    @admin.display(description="Цена со скидкой")
    def get_sales_amount(self, obj):
        result = []
        for price in obj.prices.all():
            if not price.is_active:
                continue

            if price.sale_amount and price.sale_unit == "price":
                final_price = price.price - price.sale_amount
                result.append(
                    f"{price.consoles.name} – {final_price:.0f} ₽ ({price.payment_type})"
                )

            elif price.sale_amount and price.sale_unit == "percent":
                final_price = price.price - ((price.price * price.sale_amount) / 100)
                result.append(
                    f"{price.consoles.name} – {final_price:.0f} ₽ ({price.payment_type})"
                )

            else:
                result.append(f"{price.consoles.name}(No sale)")

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
            # Запуск Celery задачи
            import_excel_task.delay(excel_file.read())
            messages.success(
                request, "Импорт запущен, результаты можно проверить позже."
            )
            return redirect("..")  # вернуться в список игр
        return render(request, "admin/import_excel.html")

    @staticmethod
    def extract_direct_url(yandex_url):
        import requests
        from bs4 import BeautifulSoup

        try:
            response = requests.get(yandex_url)
            soup = BeautifulSoup(response.text, "html.parser")

            og_image = soup.find("meta", property="og:image")
            if og_image:
                return og_image.get("content")

            img_tag = soup.find("img", class_="content__image-preview")
            if img_tag:
                return img_tag.get("src")

            return ""
        except Exception as e:
            print(f"Ошибка при парсинге: {e}")
            return ""
