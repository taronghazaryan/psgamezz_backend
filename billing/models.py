import uuid

from django.db import models

from games.models import Game
from subscriptions.models import SubscriptionService


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=30, verbose_name="Пользователь")
    email = models.EmailField(max_length=40, blank=True, null=False, verbose_name="Почта")
    invoice_id = models.CharField(max_length=100, default=uuid.uuid4, unique=True, verbose_name="ID счета")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сумма")
    status = models.CharField(max_length=20, default='pending', verbose_name="Статус", choices=[
        ('pending', 'Ожидает оплаты'),
        ('success', 'Оплачен'),
        ('failed', 'Ошибка оплаты'),
    ])
    description = models.CharField(max_length=255, verbose_name="Описание")
    extra_field = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    @property
    def total_amount(self):
        return sum(item.price * item.quantity for item in self.items.all())

    def __str__(self):
        return f"Платеж {self.invoice_id} - {self.status}"

    class Meta:
        verbose_name = "Платеж"
        verbose_name_plural = "Платежи"


class PaymentItems(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='items', verbose_name="Платеж")
    product_type  = models.CharField(max_length=20, default='game', verbose_name="Тип продукта", choices=[
        ('game', 'Игра'),
        ('subscription_service', 'Сервис подписки'),
    ])
    game = models.ForeignKey(Game, on_delete=models.CASCADE, blank=True, null=True, related_name='game_payment', verbose_name="Игра")
    subscription_service = models.ForeignKey(SubscriptionService, on_delete=models.CASCADE, blank=True, null=True, related_name='subscription_payment', verbose_name="Подписка")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Сума")
    quantity = models.IntegerField(verbose_name="Количество")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.product_type == 'game' and not self.game:
            raise ValidationError("Поле 'game' обязательно для product_type='game'")
        if self.product_type == 'subscription_service' and not self.subscription_service:
            raise ValidationError("Поле 'subscription_service' обязательно для product_type='subscription service'")

        if self.game and self.subscription_service:
            raise ValidationError("Нельзя одновременно указать и игру, и подписку")

    def get_total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_type} | {self.quantity} * {self.price} | {self.get_total_price()}"

    class Meta:
        verbose_name = "Элемент платежа"
        verbose_name_plural = "Элементы платежа"
