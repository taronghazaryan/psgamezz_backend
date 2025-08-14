import uuid

from django.db import models


class Consoles(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=30, verbose_name='Название')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тип консоли"
        verbose_name_plural = "Типы консолей"


class SubscriptionService(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=100, verbose_name="Название")
    consoles = models.ManyToManyField(Consoles, related_name="subscriptions", verbose_name="Консоли")
    CHOICES_LEVEL = (
        ('Essential', 'Essential'),
        ('Extra', 'Extra'),
        ('Deluxe', 'Deluxe'),
    )
    level = models.CharField(max_length=70, blank=True, null=True, choices=CHOICES_LEVEL, verbose_name="Уровень подписки")
    image = models.FileField(upload_to='subscription_images/', blank=True, null=True, verbose_name="Изображение")
    is_available = models.BooleanField(default=True, verbose_name="Доступна ли подписка")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.title} - {self.level}"

    class Meta:
        verbose_name = "Сервис подписки"
        verbose_name_plural = "Сервисы подписок"


class SubscriptionPeriod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    months = models.IntegerField(verbose_name="Количество месяцев")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    subscription_service = models.ForeignKey(SubscriptionService, on_delete=models.CASCADE, related_name="periods", verbose_name="Сервис подписки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.months} - {self.price}"

    class Meta:
        verbose_name = "Период подписки"
        verbose_name_plural = "Периоды подписки"


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription_service = models.ForeignKey(SubscriptionService, on_delete=models.CASCADE,
                                             related_name="services", verbose_name="Сервис подписки")
    subscription_period = models.ForeignKey(SubscriptionPeriod, on_delete=models.CASCADE,
                                            related_name="periods", verbose_name="Период подписки")
    email = models.EmailField(max_length=40, blank=False, null=False, verbose_name="Почта")
    start_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата начала")
    is_active = models.BooleanField(default=False, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.id} - {self.subscription_service.name} - {self.subscription_service.subscription_period.months} месяцев"

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"


class SeoMetric(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.TextField(blank=True, null=True, verbose_name="Код Яндекс Метрики")

    class Meta:
        verbose_name = "SEO Метрика"
        verbose_name_plural = "SEO Метрики"

