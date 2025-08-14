from decimal import Decimal
from django.db import transaction
import uuid

from decimal import Decimal

from .models import Payment
from .repository import PaymentRepository, PaymentItemRepository
import hashlib
import sys
import time
import os
import json

from urllib.parse import urlencode
from django.conf import settings
# from django.core.mail import send_mail

import logging
from datetime import datetime

from games.repository import GameRepository
from subscriptions.repository import (SubscriptionServiceRepository, SubscriptionPeriodRepository,
                                      SubscriptionRepository, ConsolesRepository, SubscriptionRepository)

from games.services import GameService

from subscriptions.services import SubscriptionServiceManager

from subscriptions.models import SubscriptionService, SubscriptionPeriod, Consoles
from games.models import Game, Price


log_dir = os.path.expanduser('~/robokassa_logs')
os.makedirs(log_dir, exist_ok=True)

file_handler = logging.FileHandler(os.path.join(log_dir, f'robokassa_debug_{datetime.now().strftime("%Y%m%d")}.log'))
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logger = logging.getLogger('robokassa')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False


class PaymentService:
    @staticmethod
    @transaction.atomic
    def create_payment_with_items(username, email, invoice_id, description, items_data):
        total_amount = sum(Decimal(item["price"]) * item["quantity"] for item in items_data)
        serialized_items = PaymentService.serialize_items_data(items_data)
        payment = PaymentRepository.create_payment(
            username=username,
            email=email,
            invoice_id=invoice_id,
            amount=total_amount,
            description=description,
            extra_field={
                "items_data": serialized_items
            },
            status='pending'
        )

        payment_items = []
        for item in items_data:
            product_type = item["product_type"]
            extra = item.get("extra", {})
            payment_item_data = {
                "payment": payment,
                "product_type": product_type,
                "price": item["price"],
                "quantity": item["quantity"],
                "selected_level": extra.get("selected_level")
            }

            if product_type == "game":
                payment_item_data["game"] = item["product"]
                payment_item_data["subscription_service"] = None
            elif product_type == "subscription_service":
                payment_item_data["subscription_service"] = item["product"]
                payment_item_data["subscription_period"] = extra.get("subscription_period")
                payment_item_data["game"] = None

            payment_items.append(payment_item_data)
        PaymentItemRepository.bulk_create_items(payment_items)
        return payment

    @staticmethod
    def mark_payment_as_success(invoice_id: str):
        return PaymentRepository.update_payment_status(invoice_id, status='success')

    @staticmethod
    def mark_payment_as_failed(invoice_id: str):
        return PaymentRepository.update_payment_status(invoice_id, status='failed')

    @staticmethod
    def get_payment_details(invoice_id: str):
        return PaymentRepository.get_payment_by_invoice(invoice_id)

    @staticmethod
    def serialize_items_data(items_data):
        cleaned = []

        for item in items_data:
            def serialize_value(val):
                if hasattr(val, "id"):
                    return str(val.id)
                elif isinstance(val, uuid.UUID):
                    return str(val)
                elif isinstance(val, Decimal):
                    return str(val)  # или float(val), если нужна арифметика
                elif isinstance(val, (str, int, float, bool, list, dict)) or val is None:
                    return val
                else:
                    return str(val)

            new_item = {
                "product_type": item["product_type"],
                "product_id": serialize_value(item.get("product")),
                "price": serialize_value(item["price"]),
                "quantity": serialize_value(item["quantity"]),
                "extra": {}
            }

            extra = item.get("extra", {})
            for key, value in extra.items():
                new_item["extra"][key] = serialize_value(value)

            cleaned.append(new_item)

        return cleaned


class PaymentItemService:
    @staticmethod
    def get_payment_details(payment_id: str):
        return PaymentItemRepository.get_items_by_payment(payment_id)



class RobokassaService:
    @staticmethod
    def generate_invoice_id():
        invoice_id = str(int(time.time()) % 100000)
        logger.debug(f"Сгенерирован InvId: {invoice_id}")
        return invoice_id

    @staticmethod
    def get_payment_url(payment, items_data, merchant_login=None):
        logger.info(f"=== НАЧАЛО СОЗДАНИЯ ПЛАТЕЖНОГО URL ===")

        if merchant_login is None:
            merchant_login = settings.ROBOKASSA_MERCHANT_LOGIN

        password = settings.ROBOKASSA_TEST_PASSWORD1 if settings.ROBOKASSA_TEST_MODE else settings.ROBOKASSA_PASSWORD1

        invoice_id = payment.invoice_id
        amount = payment.amount
        description = payment.description

        logger.info(f"MerchantLogin: {merchant_login}")
        logger.info(f"OutSum (raw): {amount} (type: {type(amount)})")
        logger.info(f"InvId: {invoice_id}")
        logger.info(f"Password1: {password[:3]}...{password[-3:]}")
        logger.info(f"Description: {description}")
        logger.info(f"Using test mode: {settings.ROBOKASSA_TEST_MODE}")

        amount_str = f"{float(amount):.2f}".replace(',', '.')
        logger.info(f"Formatted OutSum: {amount_str}")

        base_signature = f"{merchant_login}:{amount_str}:{invoice_id}:{password}"
        logger.info(f"Base signature string: {base_signature}")

        shp_params = {
            'Shp_username': payment.username,
            'Shp_payment_id': str(payment.id),
        }

        sorted_shp_params = sorted(shp_params.items())

        signature_value = base_signature
        for key, value in sorted_shp_params:
            signature_value += f":{key}={value}"

        logger.info(f"Full signature string: {signature_value}")

        signature = hashlib.md5(signature_value.encode('utf-8')).hexdigest().lower()
        logger.info(f"MD5 hash: {signature}")

        email = getattr(payment, "email", None)
        result_url = settings.ROBOKASSA_RESULT_URL
        success_url = settings.ROBOKASSA_SUCCESS_URL
        fail_url = settings.ROBOKASSA_FAIL_URL

        rec_items = []
        for item in items_data:
            template = {
                "name": '',
                "quantity": 0,
                "sum": '',
                "payment_method": "full_payment",
                "payment_object": "service",
                "tax": "none"
            }
            if item["product_type"] == "subscription_service":
                service = item["product"]
                extra = item["extra"]
                if extra["selected_level"]:
                    rec_description = (
                        f"{service.title} на {extra['subscription_period'].months} мес., "
                        f" Вариант подписки={extra['selected_level']}, "
                        f" Консоль={extra['console'].name}"
                    )
                    template["name"] = rec_description
                    template["sum"] = f"{extra['subscription_period'].price * item['quantity']:.2f}"
                    template["quantity"] = item["quantity"]
                    rec_items.append(template)
                else:
                    rec_description = (
                        f"{service.title} на {extra['subscription_period'].months} мес., "
                        f" Консоль={extra['console'].name}"
                    )
                    template["name"] = rec_description
                    template["sum"] = f"{extra['subscription_period'].price * item['quantity']:.2f}"
                    template["quantity"] = item["quantity"]
                    rec_items.append(template)
            elif item["product_type"] == "game":
                game = item["product"]
                extra = item["extra"]
                rec_description = (
                    f"{game.title}, "
                    f" Консоль={extra['console'].name}, "
                    f" {'С активацией' if extra['price_object'].payment_type == 'with_activation' else 'Без активаций'} "
                )
                template["name"] = rec_description
                template["sum"] = f"{extra['price_object'].discounted_price * item['quantity']:.2f}"
                template["quantity"] = item["quantity"]
                rec_items.append(template)

        receipt = {
            "sno": "osn",
            "items": rec_items
        }

        receipt_json = json.dumps(receipt, ensure_ascii=False)
        base_signature = f"{merchant_login}:{amount_str}:{invoice_id}:{receipt_json}:{password}"

        sorted_shp_params = sorted(shp_params.items())
        for key, value in sorted_shp_params:
            base_signature += f":{key}={value}"

        logger.info(f"Full signature string: {base_signature}")

        signature = hashlib.md5(base_signature.encode('utf-8')).hexdigest().lower()

        params = {
            'MerchantLogin': merchant_login,
            'OutSum': amount_str,
            'InvId': invoice_id,
            'Description': description,
            'SignatureValue': signature,
            'ResultURL': result_url,
            'SuccessURL': success_url,
            'FailURL': fail_url,
            'IsTest': 1 if settings.ROBOKASSA_TEST_MODE else 0,
            'Culture': 'ru',
        }

        if email:
            params['Email'] = email
            params['Receipt'] = receipt_json

        params.update(shp_params)

        logger.debug(f"All request params: {params}")

        base_url = 'https://auth.robokassa.ru/Merchant/Index.aspx'
        final_url = f"{base_url}?{urlencode(params)}"
        logger.info(f"Final URL: {final_url}")
        logger.info(f"URL length: {len(final_url)} chars")
        logger.info(f"=== КОНЕЦ СОЗДАНИЯ ПЛАТЕЖНОГО URL ===")

        try:
            log_path = os.path.join(log_dir, 'payment_urls.log')
            with open(log_path, 'a') as f:
                f.write(f"\n\nTime: {datetime.now()}\n")
                f.write(f"MerchantLogin: {merchant_login}\n")
                f.write(f"Payment ID: {payment.invoice_id}\n")
                f.write(f"Amount: {amount_str}\n")
                f.write(f"Signature String: {signature_value}\n")
                f.write(f"Signature: {signature}\n")
                f.write(f"URL: {final_url}\n")
            logger.debug(f"Данные платежа записаны в {log_path}")
        except Exception as e:
            logger.error(f"Error writing to log file: {e}")

        return final_url

    @staticmethod
    def check_signature(request_data):
        logger.info(f"=== ПРОВЕРКА ПОДПИСИ ОТ РОБОКАССЫ ===")
        if settings.ROBOKASSA_TEST_MODE:
            password = settings.ROBOKASSA_TEST_PASSWORD2
        else:
            password = settings.ROBOKASSA_PASSWORD2

        out_sum = request_data.get('OutSum')
        inv_id = request_data.get('InvId')
        received_signature = request_data.get('SignatureValue')

        logger.info(f"Verifying signature. OutSum: {out_sum}, InvId: {inv_id}")
        logger.info(f"Received signature: {received_signature}")
        logger.info(f"Using password2: {password[:3]}...{password[-3:]}")

        if not all([out_sum, inv_id, received_signature]):
            logger.error("Missing required parameters for signature verification")
            return False

        shp_params = {}
        for key, value in request_data.items():
            if key.startswith('Shp_'):
                shp_params[key] = value

        logger.info(f"Received Shp params: {shp_params}")

        signature_string = f"{out_sum}:{inv_id}:{password}"
        base_signature = signature_string
        logger.info(f"Base signature string for checking: {base_signature}")

        sorted_shp_params = sorted(shp_params.items())
        for key, value in sorted_shp_params:
            signature_string += f":{key}={value}"

        logger.info(f"Full signature string for checking: {signature_string}")

        calculated_signature = hashlib.md5(signature_string.encode('utf-8')).hexdigest().lower()
        logger.info(f"Calculated signature: {calculated_signature}")
        logger.info(f"Received signature: {received_signature.lower()}")

        result = calculated_signature == received_signature.lower()
        logger.info(f"Signature match: {result}")
        logger.info(f"=== КОНЕЦ ПРОВЕРКИ ПОДПИСИ ===")

        return result

    @staticmethod
    def process_payment(payment_data):
        logger.info(f"=== ОБРАБОТКА ПЛАТЕЖА ===")
        try:
            logger.info(f"Processing payment. Data: {payment_data}")

            inv_id = payment_data.get('InvId')
            out_sum = payment_data.get('OutSum')

            username = payment_data.get('Shp_username')
            payment_id = payment_data.get('Shp_payment_id')
            try:
                payment = PaymentService.get_payment_details(payment_id)
                logger.info(f"Found payment in DB: {payment}")
            except Payment.DoesNotExist:
                logger.error(f"Error - Payment with ID {inv_id} not found in database")
                return False, "Платеж не найден"
            data = payment.extra_field
            for item in data["items_data"]:
                if item["product_type"] == "subscription_service":
                    subscription_service_id = item["product_id"]
                    subscription_period_id = item["extra"]["subscription_period_id"]
                    console_id = item["extra"]["console_id"]
                    logger.info(
                        f"Username: {username}, Service ID: {subscription_service_id}, Period_ID: {subscription_period_id}-, Console ID: {console_id}")
                    subscription = SubscriptionServiceManager.get_user_subscriptions(payment.email)
                    if not subscription:
                        logger.info(f"Creating new subscription")
                        try:
                            subscription = SubscriptionServiceManager.create_subscription(
                                subscription_service_id=subscription_service_id,
                                subscription_period_id=subscription_period_id,
                                is_active=False,
                                email=payment.email
                            )
                            logger.info(f"Subscription created: {subscription}")

                        except Exception as e:
                            logger.error(f"Error creating subscription: {e}")
                            return False, f"Ошибка при создании подписки: {str(e)}"
                    else:
                        logger.info(f"Activating existing subscription: {payment.subscription}")
                        subscription.is_active = True
                        subscription.save()
                else:
                    continue

            logger.info(f"Payment ID: {inv_id}, Amount: {out_sum}")

            payment_amount = float(payment.amount)
            received_amount = float(out_sum)

            logger.info(f"Payment amount in DB: {payment_amount}, Received amount: {received_amount}")

            if payment_amount != received_amount:
                logger.warning(f"Amount mismatch. DB: {payment_amount}, Received: {received_amount}")
                payment.status = 'failed'
                payment.save()
                return False, "Сумма платежа не соответствует"

            logger.info(f"Updating payment status to 'success'")
            payment.status = 'success'
            payment.save()

            logger.info(f"Payment processing completed successfully")
            logger.info(f"=== КОНЕЦ ОБРАБОТКИ ПЛАТЕЖА ===")
            return True, "Платеж успешно обработан"

        except Payment.DoesNotExist:
            logger.error(f"Error - Payment not found")
            return False, "Платеж не найден"
        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            return False, f"Ошибка при обработке платежа: {str(e)}"

    @staticmethod
    def create_payment(username, email, items):
        logger.info(f"=== СОЗДАНИЕ ПЛАТЕЖА ===")
        invoice_id = RobokassaService.generate_invoice_id()
        description = RobokassaService.build_description(items)

        try:
            payment = PaymentService.create_payment_with_items(
                username=username,
                email=email,
                description=description,
                invoice_id=invoice_id,
                items_data=items,
            )
            logger.info(f"Payment created: {payment}")
            logger.info(f"=== КОНЕЦ СОЗДАНИЯ ПЛАТЕЖА ===")
            return payment
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            logger.info(f"=== ОШИБКА СОЗДАНИЯ ПЛАТЕЖА ===")
            raise

    @staticmethod
    def build_description(items):
        descriptions = []
        for item in items:
            if item["product_type"] == "game":
                game = item["product"]
                descriptions.append(f"Игра: {game.title}")

            elif item["product_type"] == "subscription_service":
                sub = item["product"].title
                extra = item["extra"]
                period = extra["subscription_period"]
                level = extra["selected_level"]
                console = extra["console"].name if extra["console"] else ""
                descriptions.append(
                    f"Подписка: {sub} на {period.months} мес. {level} {console}".strip()
                )

        return "; ".join(descriptions)