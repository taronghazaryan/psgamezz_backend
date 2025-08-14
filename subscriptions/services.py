from .repository import (
    SubscriptionServiceRepository,
    SubscriptionPeriodRepository,
    SubscriptionRepository, ConsolesRepository, SeoMetricRepository
)
from .models import SubscriptionService, SubscriptionPeriod, Subscription, Consoles
from typing import Optional
import uuid


class SubscriptionServiceManager:
    @staticmethod
    def list_available_services():
        return SubscriptionServiceRepository.get_all_available()

    @staticmethod
    def get_service_detail(service_id: uuid.UUID) -> Optional[SubscriptionService]:
        return SubscriptionServiceRepository.get_by_id(service_id)

    @staticmethod
    def get_periods_for_service(service_id: uuid.UUID):
        service = SubscriptionServiceRepository.get_by_id(service_id)
        if not service:
            return []
        return SubscriptionPeriodRepository.get_periods_for_service(service)

    @staticmethod
    def get_period_for_service(period_id: uuid.UUID):
        return SubscriptionPeriodRepository.get_by_id(period_id)

    @staticmethod
    def get_console(console_id: uuid.UUID):
        return ConsolesRepository.get_by_id(console_id)

    @staticmethod
    def create_subscription(email: str, service_id: uuid.UUID, period_id: uuid.UUID) -> Subscription:
        service = SubscriptionServiceRepository.get_by_id(service_id)
        if not service or not service.is_available:
            raise ValueError("Подписка недоступна")

        period = SubscriptionPeriodRepository.get_by_id(period_id)
        if not period or period.subscription_service != service:
            raise ValueError("Неверный период подписки")

        return SubscriptionRepository.create(
            subscription_service=service,
            subscription_period=period,
            email=email
        )

    @staticmethod
    def get_user_subscriptions(email: str):
        return SubscriptionRepository.get_user_subscriptions(email)

    @staticmethod
    def deactivate_subscription(subscription_id: uuid.UUID):
        subscription = Subscription.objects.filter(id=subscription_id).first()
        if not subscription:
            raise ValueError("Подписка не найдена")
        SubscriptionRepository.deactivate(subscription)



class SubscriptionPurchaseService:
    @staticmethod
    def prepare_subscription_purchase_items(subscription_data: dict) -> list:
        try:
            service = SubscriptionServiceRepository.get_by_id(subscription_data['service_id'])
            period = SubscriptionPeriod.objects.get(
                id=subscription_data['period_id'],
                subscription_service=service
            )
            console = ConsolesRepository.get_by_id(subscription_data['console_id'])

            if service.level:
                if subscription_data.get('level') not in dict(service.CHOICES_LEVEL):
                    raise ValueError("Неверный уровень подписки")

            return [{
                "product_type": "subscription_service",
                "product": service,
                "price": period.price,
                "quantity": subscription_data.get('quantity', 1),
                "extra": {
                    "subscription_period": period,
                    "console": console,
                    "selected_level": subscription_data.get('level')
                }
            }]


        except SubscriptionService.DoesNotExist:
            raise ValueError("Подписка не найдена или недоступна")
        except SubscriptionPeriod.DoesNotExist:
            raise ValueError("Выбранный период недействителен для этой подписки")
        except Consoles.DoesNotExist:
            raise ValueError("Консоль не найдена")


class SeoMetricService:
    @staticmethod
    def get_seo():
        return SeoMetricRepository.get_seo_metric()