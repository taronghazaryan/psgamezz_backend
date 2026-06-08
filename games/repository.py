from .models import Game, Price

class GameRepository:
    @staticmethod
    def get_all_available():
        return (
            Game.objects
            .filter(is_available=True)
            .select_related()
            .prefetch_related(
                'prices__consoles',
                'categories',
                'publishers',
                'voice_acting',
                'subtitle',
                'images',
                'faqs'
            )
        )

    @staticmethod
    def get_by_id(game_id):
        return (
            Game.objects
            .filter(id=game_id)
            .select_related()
            .prefetch_related(
                'prices__consoles',
                'categories',
                'publishers',
                'voice_acting',
                'subtitle',
                'images',
                'faqs'
            )
            .first()
        )

    @staticmethod
    def get_price(game: Game, console, payment_type='without_activation'):
        return game.prices.filter(
            consoles=console,
            payment_type=payment_type,
            is_active=True
        ).first()


class PriceRepository:
    @staticmethod
    def get_price_by_id(price_id):
        try:
            return (
                Price.objects
                .filter(id=price_id, is_active=True)
                .select_related('game', 'consoles')
                .first()
            )
        except Exception as e:
            return None
