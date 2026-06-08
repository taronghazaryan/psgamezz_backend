from .models import (
    Consoles,
    SubscriptionService,
    SubscriptionPeriod,
    Subscription, SeoMetric
)
from django.db.models import QuerySet
from typing import Optional
import uuid


class ConsolesRepository:
    @staticmethod
    def get_all() -> QuerySet:
        return Consoles.objects.all()

    @staticmethod
    def get_by_id(console_id: uuid.UUID) -> Optional[Consoles]:
        return Consoles.objects.filter(id=console_id).first()


class SubscriptionServiceRepository:
    @staticmethod
    def get_all_available() -> QuerySet:
        return SubscriptionService.objects.filter(is_available=True)

    @staticmethod
    def get_by_id(service_id: uuid.UUID) -> Optional[SubscriptionService]:
        return SubscriptionService.objects.filter(id=service_id).first()

    @staticmethod
    def get_by_service(service, console_type, level = None) -> Optional[SubscriptionService]:
        return SubscriptionService.objects.filter(service, console_type, level).first()


class SubscriptionPeriodRepository:
    @staticmethod
    def get_by_id(period_id: uuid.UUID) -> Optional[SubscriptionPeriod]:
        return SubscriptionPeriod.objects.filter(id=period_id).first()

    @staticmethod
    def get_periods_for_service(service: SubscriptionService) -> QuerySet:
        return service.periods.all()


class SubscriptionRepository:
    @staticmethod
    def create(subscription_service: SubscriptionService, subscription_period: SubscriptionPeriod, email: str) -> Subscription:
        return Subscription.objects.create(
            subscription_service=subscription_service,
            subscription_period=subscription_period,
            email=email
        )

    @staticmethod
    def get_user_subscriptions(email: str) -> QuerySet:
        return Subscription.objects.filter(email=email)

    @staticmethod
    def deactivate(subscription: Subscription):
        subscription.is_active = False
        subscription.save()


class SeoMetricRepository:
    @staticmethod
    def get_seo_metric():
        return SeoMetric.objects.first()
