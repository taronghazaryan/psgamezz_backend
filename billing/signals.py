from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import PaymentItems

@receiver([post_save, post_delete], sender=PaymentItems)
def update_payment_amount(sender, instance, **kwargs):
    payment = instance.payment
    total = sum(item.discounted_price * item.quantity for item in payment.items.all())
    payment.amount = total
    payment.save(update_fields=['amount'])
