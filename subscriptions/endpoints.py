from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ConsoleTypeViewSet, SubscriptionServiceViewSet, GetSeo


app_name = "subscriptions"

router = DefaultRouter()
router.register(r'console-types', ConsoleTypeViewSet, basename='console_type')
router.register(r'subscription-services', SubscriptionServiceViewSet, basename='subscription_services')

router_urls = [
    path('api/', include(router.urls)),
]

urlpatterns = []

sub_authorized_endpoints = [
    path('api/metric', GetSeo.as_view(), name='metric')
]

urlpatterns.extend(router_urls)
urlpatterns.extend(sub_authorized_endpoints)
