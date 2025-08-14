from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import GameDetail, AllGames


app_name = "games"

urlpatterns = []

games_authorized_endpoints = [
    path("api/games/", AllGames.as_view(), name="all_games"),
    path("api/games/<str:game_id>", GameDetail.as_view(), name="game_detail"),
]

urlpatterns.extend(games_authorized_endpoints)