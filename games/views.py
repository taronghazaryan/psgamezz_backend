from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import GameSerializer, GameDetailSerializer
from .services import GameService
from .repository import GameRepository


class GameDetail(APIView):
    def get(self, request, game_id):
        try:
            game_id = game_id
            if not game_id:
                return Response({"error": "game_id is required field"}, status=status.HTTP_400_BAD_REQUEST)
            service = GameService(GameRepository())
            game = service.get_game_detail(game_id)
            if not game:
                return Response({"error": "Game not found"}, status=status.HTTP_404_NOT_FOUND)
            serializer = GameDetailSerializer(game)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": f"something went wrong! {e}"}, status=status.HTTP_400_BAD_REQUEST)


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
            queryset = queryset.exclude(sale_amount__isnull=True).exclude(sale_amount=0)

        title = self.request.query_params.get("title")
        if title:
            queryset = queryset.filter(title__icontains=title)

        return queryset

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            return Response({"error": f"games not found {e}"}, status=status.HTTP_404_NOT_FOUND)