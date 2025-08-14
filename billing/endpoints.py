from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt

from .views import (
    InitiatePayment, TestPaymentWithBoth,
    TestMinimalConnection, CompareLoginsTest,
    TestRobokassa, PaymentResult
)

app_name = "billing"

urlpatterns = []

billing_authorized_endpoints = [
    path('api/payment/initiate/', InitiatePayment.as_view(), name='initiate_payment'),

    path('api/payment/test-robokassa/', TestRobokassa.as_view(), name='payment_test_robokassa'),
    path('api/payment/compare-logins/', CompareLoginsTest.as_view(), name='payment_compare_logins_test'),
    path('api/payment/test-connection/', TestMinimalConnection.as_view(), name='payment_test_minimal_connection'),
    path('api/payment/test-both-logins/', TestPaymentWithBoth.as_view(), name='payment_test_payment_with_both_logins'),
]

billing_public_urls = [
    path('api/payment/result/', PaymentResult.as_view(), name='payment_result'),
]

urlpatterns.extend(billing_authorized_endpoints)
urlpatterns.extend(billing_public_urls)