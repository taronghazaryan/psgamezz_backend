import uuid

from django.utils.text import slugify

from django.db import models

from subscriptions.models import Consoles


class Game(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500, blank=False, null=False, verbose_name="Название", db_index=True)
    url_u = models.CharField(max_length=255, blank=True, null=False, verbose_name="URL_U")
    url_t = models.CharField(max_length=255, blank=True, null=False, verbose_name="URL_T")
    slug = models.SlugField(max_length=60, unique=True, blank=True, verbose_name="Slug")
    main_image_url = models.CharField(max_length=1000, blank=False, null=False, verbose_name="Главное изображение(URL)")
    voice_acting = models.ManyToManyField(
        'Language',
        blank=True,
        related_name='voice_acting_games',
        verbose_name="Озвучки"
    )
    subtitle = models.ManyToManyField(
        'Language',
        blank=True,
        related_name='subtitle_games',
        verbose_name="Субтитры"
    )
    categories = models.ManyToManyField(
        'Categories',
        related_name='category_games',
        verbose_name="Категория",
        blank=True,
    )

    publishers = models.ManyToManyField(
        'Publisher',
        blank=True,
        related_name='publisher_game',
        verbose_name="Издатель")
    about = models.TextField(blank=True, null=True, verbose_name="Описание")
    is_available = models.BooleanField(default=True, verbose_name="Доступен")
    release_date = models.DateField(blank=True, null=True, verbose_name="Дата выпуска")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            n = 1
            while Game.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title}"

    class Meta:
        verbose_name = "Игра"
        verbose_name_plural = "Игры"


class Image(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='images')
    image_url = models.CharField(max_length=255, blank=False, null=False, verbose_name="URL изображения")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.image_url}"

    class Meta:
        verbose_name = "Изображения"
        verbose_name_plural = "Изображение"


class Language(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=50)
    consoles = models.ForeignKey(Consoles, on_delete=models.CASCADE, verbose_name="Консоли")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.consoles} ({self.code})"

    class Meta:
        verbose_name = "Язык"
        verbose_name_plural = "Языки"


class Faq(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='faqs')
    question = models.TextField(blank=True, null=False, verbose_name="Вопрос")
    answer = models.TextField(blank=True, null=True, verbose_name="Ответ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.question} ({self.answer})"

    class Meta:
        verbose_name = "FAQ"
        verbose_name_plural = "FAQ"


class Categories(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=50 ,blank=True, null=True, verbose_name="Категория")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.category}"

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"


class Publisher(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publisher = models.CharField(max_length=50 ,blank=True, null=True, verbose_name="Издатель")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return f"{self.publisher}"

    class Meta:
        verbose_name = "Издатель"
        verbose_name_plural = "Издатели"


class Price(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='prices')
    payment_type = models.CharField(max_length=70, default='without_activation',
                                 blank=True,
                                 choices=[
                                     ('with_activation', 'С активацией'),
                                     ('without_activation', 'Без активаций'),
                                 ],
                                 verbose_name="Тип активации")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    is_active = models.BooleanField(default=True, blank=False, null=False, verbose_name="Активен")
    consoles = models.ForeignKey(Consoles, on_delete=models.CASCADE, verbose_name="Консоли")
    sale_unit = models.CharField(max_length=70, default='percent',
                                 blank=True, null=True,
                                 choices=[
                                     ('price', 'Рубли'),
                                     ('percent', 'Проценты'),
                                 ],
                                 verbose_name="Единица")
    sale_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                      verbose_name="Сума или Процент")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    @property
    def discounted_price(self):
        if self.sale_amount is None:
            return self.price

        if self.sale_unit == 'percent':
            discount = (self.price * self.sale_amount) / 100
            return self.price - discount

        elif self.sale_unit == 'price':
            return self.price - self.sale_amount
        else:
            return self.price

    def __str__(self):
        return f"{self.payment_type} | {self.consoles} | {self.price} ₽"

    class Meta:
        verbose_name = "Цена"
        verbose_name_plural = "Цены"
        unique_together = ('game', 'consoles', 'payment_type')

