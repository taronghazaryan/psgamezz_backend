from rest_framework import serializers

from .models import (Payment,
                     PaymentItems)
from subscriptions.serializers import ServiceSerializer
from games.serializers import GameSerializer


class PaymentItemSerializer(serializers.ModelSerializer):
    game = GameSerializer(read_only=True)
    subscription_service = ServiceSerializer(read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = PaymentItems
        fields = [
            'id', 'payment', 'product_type', 'game',
            'subscription_service', 'total_price',
            'quantity'
        ]


    def get_total_price(self, obj):
        return obj.get_total_price()


class PaymentSerializer(serializers.ModelSerializer):
    items = PaymentItemSerializer(read_only=True)
    total_amount = serializers.DecimalField(source='total_amount', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'username', 'email', 'invoice_id',
            'amount', 'status', 'description',
            'created_at', 'updated_at',
            'items', 'total_amount'
        ]
