from collections import defaultdict

from .repository import GameRepository, PriceRepository

from .models import Price, Game


class GameService:
    def __init__(self, repository: GameRepository):
        self.repository = repository

    def list_available_games(self):
        return self.repository.get_all_available()

    def get_game_detail(self, game_id):
        return self.repository.get_by_id(game_id)

    @staticmethod
    def get_prices(game):
        return {
            "with_activation": [
                {"id": c.id, c.consoles.name: c.price, "sale_amount": c.sale_amount if c.sale_amount else 0}
                for c in game.prices.all()
                if c.payment_type == "with_activation" and c.is_active
            ],
            "without_activation": [
                {"id": c.id, c.consoles.name: c.price, "sale_amount": c.sale_amount if c.sale_amount else 0}
                for c in game.prices.all()
                if c.payment_type == "without_activation" and c.is_active
            ]
        }

    @staticmethod
    def get_consoles(game):
        return {c.consoles.name for c in game.prices.all() if c.is_active}

    @staticmethod
    def get_categories(game):
        return [cat.category for cat in game.categories.all()]

    @staticmethod
    def get_publishers(game):
        return [pub.publisher for pub in game.publishers.all()]

    @staticmethod
    def get_voice_acting(game):
        result = defaultdict(list)
        for lang in game.voice_acting.all():
            console_name = lang.consoles.name if lang.consoles else "unknown"
            result[console_name].append(lang.code)
        return dict(result)

    @staticmethod
    def get_subtitle(game):
        result = defaultdict(list)
        for lang in game.subtitle.all():
            console_name = lang.consoles.name if lang.consoles else "unknown"
            result[console_name].append(lang.code)
        return dict(result)

    @staticmethod
    def get_images(game):
        return {image.image_url for image in game.images.all()}


class GamePurchaseService:
    @staticmethod
    def prepare_game_purchase_items(game_data):

        try:
            price = PriceRepository.get_price_by_id(game_data['price_id'])
            if price is None:
                raise Price.DoesNotExist("Цена не найдена или неактивна")

            game = price.game
            if not game.is_available:
                raise ValueError("Игра временно недоступна для покупки")

            return [{
                "product_type": "game",
                "product": game,
                "price": price.discounted_price,
                "quantity": game_data.get('quantity', 1),
                "extra": {
                    "price_object": price,
                    "payment_type": price.payment_type,
                    "console": price.consoles
                }
            }]


        except Price.DoesNotExist:
            raise ValueError("Указанная комбинация игры, типа оплаты и консоли не найдена")
        except Game.DoesNotExist:
            raise ValueError("Игра не найдена")
