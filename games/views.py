from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import JsonResponse

from .serializers import GameSerializer, GameDetailSerializer
from .services import GameService
from .repository import GameRepository
from .tasks import update_prices_bulk


class GameDetail(APIView):
    def get(self, request, game_id):
        try:
            game_id = game_id
            if not game_id:
                return Response(
                    {"error": "game_id is required field"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            service = GameService(GameRepository())
            game = service.get_game_detail(game_id)
            if not game:
                return Response(
                    {"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND
                )
            serializer = GameDetailSerializer(game)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": f"something went wrong! {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GamePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class AllGames(ListAPIView):
    serializer_class = GameSerializer
    pagination_class = GamePagination

    def get_queryset(self):
        service = GameService(GameRepository())
        queryset = service.list_available_games()

        # фильтры
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(categories__category=category)

        min_price = self.request.query_params.get("min_price")
        if min_price:
            queryset = queryset.filter(price__gte=min_price)

        max_price = self.request.query_params.get("max_price")
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        has_discount = self.request.query_params.get("has_discount")
        if has_discount == "true":
            queryset = queryset.filter(prices__sale_amount__gt=0).distinct()

        title = self.request.query_params.get("title")
        if title:
            queryset = queryset.filter(title__icontains=title)

        slug = self.request.query_params.get("slug")
        if slug:
            queryset = queryset.filter(slug__exact=slug)

        return queryset


def update_prices_view(request):
    result = update_prices_bulk()
    updated_games = result["updated_games"]
    disabled_games = result["disabled_games"]
    new_games = result["new_games"]
    message = (
        f"игр обновлено: {updated_games}, "
        f"новых игр создано: {new_games}, "
        f"игр деактивировано: {disabled_games}"
    )

    return JsonResponse({"status": "completed", "message": message})
