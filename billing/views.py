import hashlib
import time
import requests

from urllib.parse import urlencode

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.response import Response
from rest_framework.views import APIView

from .services import RobokassaService, logger
from subscriptions.models import Consoles, SubscriptionService, SubscriptionPeriod, Subscription
from subscriptions.serializers import ConsolesSerializer, ServiceSerializer, PeriodSerializer, SubscriptionSerializer
from subscriptions.services import SubscriptionPurchaseService
from games.services import GamePurchaseService


class InitiatePayment(APIView):
    def post(self, request):
        logger.info(f"=== НАЧАЛО ИНИЦИАЦИИ ПЛАТЕЖА ===")
        logger.info(f"User: {request.user.username} (ID: {request.user.id})")
        logger.info(f"Request data: {request.data}")

        try:
            username = request.data.get("username", request.user.username)
            email = request.data.get("email", None)
            items_data = request.data.get("items")

            if not items_data:
                logger.error("Missing required parameters")
                return Response({'error': 'Не все обязательные параметры указаны'}, status=400)

            items_for_payment = []

            for item in items_data:
                if item["product_type"] == "subscription_service":
                    sub_items = SubscriptionPurchaseService.prepare_subscription_purchase_items(item)

                    items_for_payment.extend(sub_items)
                elif item["product_type"] == "game":
                    game_items = GamePurchaseService.prepare_game_purchase_items(item)
                    items_for_payment.extend(game_items)
                else:
                    logger.warning(f"Unknown product_type: {item['product_type']}")

            if not items_for_payment:
                return Response({'error': 'Нет корректных товаров для оплаты'}, status=400)

            payment = RobokassaService.create_payment(
                username=username,
                email=email,
                items=items_for_payment
            )
            logger.info(f"Created payment: ID={payment.id}, invoice={payment.invoice_id}, amount={payment.amount}")

            payment_url = RobokassaService.get_payment_url(payment, items_for_payment)
            logger.info(f"Generated payment URL, length: {len(payment_url)}")

            response_data = {'payment_url': payment_url, 'invoice_id': payment.invoice_id}
            logger.info(f"Returning response: {response_data}")
            logger.info(f"=== КОНЕЦ ИНИЦИАЦИИ ПЛАТЕЖА ===")
            return Response(response_data)

        except Exception as e:
            logger.error(f"Error during payment initiation: {str(e)}")
            logger.exception(e)
            logger.info(f"=== ОШИБКА ИНИЦИАЦИИ ПЛАТЕЖА ===")
            return Response({'error': str(e)}, status=500)


class CompareLoginsTest(APIView):
    def get(self, request):
        logger.info("=== ТЕСТ СРАВНЕНИЯ ЛОГИНОВ ===")

        try:
            inv_id = str(int(time.time()) % 100000)
            out_sum = "10.00"
            description = "Тест логинов"
            test_password = settings.ROBOKASSA_TEST_PASSWORD1

            login1 = "PSGAMEZZ.RU"
            signature_value1 = f"{login1}:{out_sum}:{inv_id}:{test_password}"
            signature1 = hashlib.md5(signature_value1.encode('utf-8')).hexdigest().lower()

            login2 = "Psgamezz"
            signature_value2 = f"{login2}:{out_sum}:{inv_id}:{test_password}"
            signature2 = hashlib.md5(signature_value2.encode('utf-8')).hexdigest().lower()

            base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'

            params1 = {
                'MerchantLogin': login1,
                'OutSum': out_sum,
                'InvId': inv_id,
                'Description': description,
                'SignatureValue': signature1,
                'IsTest': 1,
                'Culture': 'ru',
            }
            url1 = f"{base_url}?{urlencode(params1)}"

            params2 = {
                'MerchantLogin': login2,
                'OutSum': out_sum,
                'InvId': inv_id,
                'Description': description,
                'SignatureValue': signature2,
                'IsTest': 1,
                'Culture': 'ru',
            }
            url2 = f"{base_url}?{urlencode(params2)}"

            logger.info(f"Тестирование URL с логином 1 (PSGAMEZZ.RU): {url1}")
            try:
                response1 = requests.get(url1, allow_redirects=False)
                status1 = response1.status_code
                logger.info(f"Статус ответа для логина 1: {status1}")

                if status1 == 302:
                    redirect1 = response1.headers.get('Location', '')
                    logger.info(f"URL с логином 1 принят, редирект на: {redirect1}")
                    result1 = "Успешно (редирект)"
                else:
                    if "ошибки: 23" in response1.text:
                        result1 = "Ошибка 23 (неверный формат параметров)"
                    elif "ошибки: 29" in response1.text:
                        result1 = "Ошибка 29 (неверный параметр Signature)"
                    else:
                        result1 = f"Ошибка (статус {status1})"
            except Exception as e:
                logger.error(f"Ошибка при тестировании URL с логином 1: {str(e)}")
                result1 = f"Ошибка запроса: {str(e)}"

            logger.info(f"Тестирование URL с логином 2 (Psgamezz): {url2}")
            try:
                response2 = requests.get(url2, allow_redirects=False)
                status2 = response2.status_code
                logger.info(f"Статус ответа для логина 2: {status2}")

                if status2 == 302:
                    redirect2 = response2.headers.get('Location', '')
                    logger.info(f"URL с логином 2 принят, редирект на: {redirect2}")
                    result2 = "Успешно (редирект)"
                else:
                    if "ошибки: 23" in response2.text:
                        result2 = "Ошибка 23 (неверный формат параметров)"
                    elif "ошибки: 29" in response2.text:
                        result2 = "Ошибка 29 (неверный параметр Signature)"
                    else:
                        result2 = f"Ошибка (статус {status2})"
            except Exception as e:
                logger.error(f"Ошибка при тестировании URL с логином 2: {str(e)}")
                result2 = f"Ошибка запроса: {str(e)}"

            logger.info(f"Результат сравнения логинов:")
            logger.info(f"Логин 1 (PSGAMEZZ.RU): {result1}")
            logger.info(f"Логин 2 (Psgamezz): {result2}")
            logger.info(f"=== КОНЕЦ ТЕСТА СРАВНЕНИЯ ЛОГИНОВ ===")

            return Response({
                'login1': login1,
                'login1_signature': signature_value1,
                'login1_url': url1,
                'login1_result': result1,

                'login2': login2,
                'login2_signature': signature_value2,
                'login2_url': url2,
                'login2_result': result2,

                'conclusion': "Используйте тот вариант логина, который дал лучший результат."
            })

        except Exception as e:
            logger.error(f"Ошибка в тесте сравнения логинов: {str(e)}")
            return Response({'error': str(e)}, status=500)


class TestMinimalConnection(APIView):
    def get(self, request):
        logger.info("=== МИНИМАЛЬНЫЙ ТЕСТ СВЯЗИ С РОБОКАССОЙ ===")

        try:
            url = "https://auth.robokassa.ru/Merchant/Index.aspx"
            logger.info(f"Тестирование базового URL: {url}")

            response = requests.get(url)
            logger.info(f"Ответ от сервера: {response.status_code}")

            return Response({
                'status': 'success',
                'message': f"Соединение с Робокассой установлено, статус: {response.status_code}",
                'can_connect': True
            })
        except Exception as e:
            logger.error(f"Ошибка при тестировании связи с Робокассой: {str(e)}")
            return Response({
                'status': 'error',
                'message': f"Ошибка при подключении к Робокассе: {str(e)}",
                'can_connect': False
            }, status=500)


class TestPaymentWithBoth(APIView):
    def get(self, request):
        logger.info("=== ТЕСТ СОЗДАНИЯ ПЛАТЕЖА С ОБОИМИ ЛОГИНАМИ ===")

        try:
            class TestPayment:
                def __init__(self):
                    self.invoice_id = str(int(time.time()) % 100000)
                    self.username = "johndoe"
                    self.email = "johndoe@test.com"
                    self.amount = "10.00"
                    self.description = "Тестовый платеж"
                    self.subscription_service = type('obj', (object,), {'id': 1})
                    self.subscription_period = type('obj', (object,), {'id': 1})
                    self.console_type = type('obj', (object,), {'id': 1})

            test_payment = TestPayment()

            url1 = RobokassaService.get_payment_url(test_payment, merchant_login="PSWIN.RU", items_data=[])
            url2 = RobokassaService.get_payment_url(test_payment, merchant_login="PSWIN.RU", items_data=[])
            logger.info(f"URL с логином PSGAMEZZ.RU: {url1}")
            logger.info(f"URL с логином Psgamezz: {url2}")

            try:
                response1 = requests.get(url1, allow_redirects=False)
                status1 = response1.status_code
                if status1 == 302:
                    result1 = "Успешно (редирект)"
                else:
                    result1 = f"Ошибка (статус {status1})"
            except Exception as e:
                result1 = f"Ошибка запроса: {str(e)}"

            try:
                response2 = requests.get(url2, allow_redirects=False)
                status2 = response2.status_code
                if status2 == 302:
                    result2 = "Успешно (редирект)"
                else:
                    result2 = f"Ошибка (статус {status2})"
            except Exception as e:
                result2 = f"Ошибка запроса: {str(e)}"

            logger.info(f"Результат для логина PSGAMEZZ.RU: {result1}")
            logger.info(f"Результат для логина Psgamezz: {result2}")
            logger.info(f"=== КОНЕЦ ТЕСТА СОЗДАНИЯ ПЛАТЕЖА ===")

            return Response({
                'payment_id': test_payment.invoice_id,
                'amount': test_payment.amount,
                'description': test_payment.description,
                'url1': url1,
                'result1': result1,
                'url2': url2,
                'result2': result2
            })
        except Exception as e:
            logger.error(f"Ошибка в тесте создания платежа: {str(e)}")
            return Response({'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class PaymentResult(APIView):
    def post(self, request):
        logger.info(f"=== ПОЛУЧЕНО УВЕДОМЛЕНИЕ ОТ РОБОКАССЫ ===")

        if request.method == 'POST':
            data = request.POST.dict()
        else:
            data = request.GET.dict()

        logger.info(f"Request method: {request.method}")
        logger.info(f"Request data: {data}")
        logger.info(f"Request headers: {dict(request.headers)}")

        if not RobokassaService.check_signature(data):
            logger.error("Invalid signature from Robokassa")
            return Response("Неверная подпись", status=400)

        success, message = RobokassaService.process_payment(data)

        if success:
            logger.info("Payment processed successfully")
            logger.info(f"=== КОНЕЦ ОБРАБОТКИ УВЕДОМЛЕНИЯ ===")
            return Response("OK")
        else:
            logger.error(f"Payment processing failed: {message}")
            logger.info(f"=== ОШИБКА ОБРАБОТКИ УВЕДОМЛЕНИЯ ===")
            return Response(message, status=400)


class TestRobokassa(APIView):
    def get(self, request):
        """
        Тестовый эндпоинт для проверки Робокассы с минимальными параметрами
        """
        logger.info("=== ТЕСТОВЫЙ ЗАПРОС К РОБОКАССЕ ===")

        try:
            merchant_login = settings.ROBOKASSA_MERCHANT_LOGIN
            password = settings.ROBOKASSA_TEST_PASSWORD1 if settings.ROBOKASSA_TEST_MODE else settings.ROBOKASSA_PASSWORD1

            invoice_id = str(int(time.time()) % 100000)
            amount = "10.00"
            description = "Тестовый платеж"

            logger.info(f"MerchantLogin: {merchant_login}")
            logger.info(f"OutSum: {amount}")
            logger.info(f"InvId: {invoice_id}")
            logger.info(f"Password: {password[:3]}...{password[-3:]}")

            signature_value = f"{merchant_login}:{amount}:{invoice_id}:{password}"
            logger.info(f"Signature string: {signature_value}")

            signature = hashlib.md5(signature_value.encode('utf-8')).hexdigest().lower()
            logger.info(f"MD5 hash: {signature}")

            params = {
                'MerchantLogin': merchant_login,
                'OutSum': amount,
                'InvId': invoice_id,
                'Description': description,
                'SignatureValue': signature,
                'IsTest': 1,
                'Culture': 'ru',
            }

            logger.info(f"All params: {params}")

            base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'
            final_url = f"{base_url}?{urlencode(params)}"

            logger.info(f"Final URL: {final_url}")

            try:
                response = requests.get(final_url, allow_redirects=False)
                status = response.status_code
                logger.info(f"Test request status: {status}")
                if status == 302:
                    test_result = "Успешно (редирект)"
                    redirect_url = response.headers.get('Location', '')
                    logger.info(f"Redirect URL: {redirect_url}")
                else:
                    test_result = f"Ошибка (статус {status})"
                    if "ошибки: " in response.text:
                        error_code = response.text.split("ошибки: ")[1].split(" ")[0]
                        test_result = f"Ошибка {error_code}"
            except Exception as e:
                test_result = f"Ошибка запроса: {str(e)}"
                logger.error(f"Error testing URL: {str(e)}")

            logger.info(f"Test result: {test_result}")
            logger.info("=== КОНЕЦ ТЕСТОВОГО ЗАПРОСА ===")

            return Response({
                'test_url': final_url,
                'params': params,
                'signature_string': signature_value,
                'test_result': test_result
            })
        except Exception as e:
            logger.error(f"Error during test: {str(e)}")
            logger.exception(e)
            return Response({'error': str(e)}, status=500)