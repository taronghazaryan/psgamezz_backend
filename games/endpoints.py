from django.urls import path

from .views import GameDetail, AllGames, update_prices_view


app_name = "games"

urlpatterns = []

games_authorized_endpoints = [
    path("api/games/", AllGames.as_view(), name="all_games"),
    path("api/games/<str:game_id>", GameDetail.as_view(), name="game_detail"),
]

games_public_endpoints = [
    path('update-prices/', update_prices_view, name='update-prices'),
]
urlpatterns.extend(games_public_endpoints)
urlpatterns.extend(games_authorized_endpoints)
