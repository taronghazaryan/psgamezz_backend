from django.contrib import admin

from .models import Payment, PaymentItems


class ItemsInLine(admin.TabularInline):
    model = PaymentItems
    extra = 1


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['invoice_id', 'username', 'email', 'amount', 'status', "get_items", 'created_at']
    inlines = [ItemsInLine]
    list_filter = ['status', 'username']
    search_fields = ['invoice_id', 'username', 'description']
    readonly_fields = ['invoice_id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основная информация', {
            'fields': ('invoice_id', 'username', 'amount', 'description', 'status')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    @admin.display(description="Элементы")
    def get_items(self, obj):
        items = []
        for c in obj.items.all():
            if c.product_type == 'game' and c.game:
                items.append(f"{c.game.title}(game)")
            elif c.product_type == 'subscription_service' and c.subscription_service:
                items.append(f"{c.subscription_service.title}(subscription_service)")
            else:
                items.append(f"Неизвестный товар ({c.product_type})")
        return ", ".join(items)


