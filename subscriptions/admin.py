from django.contrib import admin
from .models import SubscriptionService, SubscriptionPeriod, Subscription, SeoMetric


class SubscriptionPeriodInline(admin.TabularInline):
    model = SubscriptionPeriod
    extra = 1


@admin.register(SubscriptionService)
class SubscriptionServiceAdmin(admin.ModelAdmin):
    list_display = ['title', 'level', 'is_available', 'get_periods_and_prices']
    inlines = [SubscriptionPeriodInline]
    filter_horizontal = ['consoles']

    @admin.display(description="Периоды и цены")
    def get_periods_and_prices(self, obj):
        return ", ".join([f"{p.months} мес — {p.price}₽" for p in obj.periods.all()])

    @admin.display(description="Консоли")
    def get_consoles(self, obj):
        return ", ".join([c.name for c in obj.consoles.all()])


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['email', 'subscription_service', 'subscription_period', 'start_date', 'is_active']
    list_filter = ['id', 'is_active', 'subscription_service']
    search_fields = ['id']


@admin.register(SeoMetric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ['id','code']
