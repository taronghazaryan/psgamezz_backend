from rest_framework import serializers

from .models import (Game)
from .services import GameService


class GameSerializer(serializers.ModelSerializer):
    consoles = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    publishers = serializers.SerializerMethodField()
    prices = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    voice_acting = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "id", "title", "slug", "prices",
            "consoles", "categories", "publishers", "voice_acting",  "subtitle",
            "about", "main_image_url", "images", "release_date", "updated_at"
        ]

    def get_prices(self, obj):
        return GameService.get_prices(obj)

    def get_images(self, obj):
        return GameService.get_images(obj)

    def get_consoles(self, obj):
        return GameService.get_consoles(obj)

    def get_categories(self, obj):
        return GameService.get_categories(obj)

    def get_publishers(self, obj):
        return GameService.get_publishers(obj)

    def get_voice_acting(self, obj):
        return GameService.get_voice_acting(obj)

    def get_subtitle(self, obj):
        return GameService.get_subtitle(obj)


class GameDetailSerializer(serializers.ModelSerializer):
    consoles = serializers.SerializerMethodField()
    voice_acting = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    publishers = serializers.SerializerMethodField()
    prices = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "id", "title", "slug", "prices", "consoles",
            "about", "voice_acting",  "subtitle",
            "categories", "publishers", "main_image_url", "images", "release_date"
        ]

    def get_prices(self, obj):
        return GameService.get_prices(obj)

    def get_images(self, obj):
        return GameService.get_images(obj)

    def get_consoles(self, obj):
        return GameService.get_consoles(obj)

    def get_categories(self, obj):
        return GameService.get_categories(obj)

    def get_publishers(self, obj):
        return GameService.get_publishers(obj)

    def get_voice_acting(self, obj):
        return GameService.get_voice_acting(obj)

    def get_subtitle(self, obj):
        return GameService.get_subtitle(obj)