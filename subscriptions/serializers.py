from .models import (Consoles,
                     SubscriptionService,
                     SubscriptionPeriod,
                     Subscription, SeoMetric, )

from rest_framework import serializers


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPeriod
        fields = ['id', 'months', 'price']


class ConsolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consoles
        fields = ['id', 'name']


class ServiceSerializer(serializers.ModelSerializer):
    periods = PeriodSerializer(many=True, read_only=True)

    class Meta:
        model = SubscriptionService
        fields = ['id', 'title', 'consoles', 'level', 'periods', 'image']


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['id', 'subscription_service', 'subscription_period',
                  'start_date', 'is_active', 'console_type']
        read_only_fields = ['start_date']


class SeoMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeoMetric
        fields = ['code']
