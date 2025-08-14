from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Consoles, SubscriptionService
from .serializers import ConsolesSerializer, ServiceSerializer, PeriodSerializer, SubscriptionSerializer, \
    SeoMetricSerializer

from .services import SeoMetricService

class ConsoleTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Consoles.objects.all()
    serializer_class = ConsolesSerializer
    permission_classes = [AllowAny]


class SubscriptionServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionService.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]


class GetSeo(APIView):
    def get(self, request):
        seo_data = SeoMetricService.get_seo()
        if seo_data:
            serializer = SeoMetricSerializer(seo_data)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({'code': ''})
            
