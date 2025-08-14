from .models import Payment, PaymentItems


class PaymentRepository:
    @staticmethod
    def create_payment(**kwargs):
        return Payment.objects.create(**kwargs)

    @staticmethod
    def get_payment_by_invoice(invoice_id: str):
        return Payment.objects.prefetch_related('items').filter(invoice_id=invoice_id).first()

    @staticmethod
    def update_payment_status(invoice_id: str, status: str):
        return Payment.objects.filter(invoice_id=invoice_id).update(status=status)


class PaymentItemRepository:
    @staticmethod
    def create_item(**kwargs):
        return PaymentItems.objects.create(**kwargs)

    @staticmethod
    def bulk_create_items(items_data):
        allowed_fields = {
            'payment', 'product_type', 'game',
            'subscription_service', 'price', 'quantity', 'level'
        }

        cleaned_items = []
        for data in items_data:
            filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
            cleaned_items.append(PaymentItems(**filtered_data))

        PaymentItems.objects.bulk_create(cleaned_items)

    @staticmethod
    def get_items_by_payment(payment_id):
        return PaymentItems.objects.filter(payment_id=payment_id)
