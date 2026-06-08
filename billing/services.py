from decimal import Decimal
from django.db import transaction
import uuid
import requests

import json
import time
import base64
import hashlib
import hmac
import requests

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Payment
from .repository import PaymentRepository, PaymentItemRepository
import hashlib
import sys
import time
import os

from urllib.parse import urlencode
from django.conf import settings

# from django.core.mail import send_mail

import logging
from datetime import datetime

from games.repository import GameRepository
from subscriptions.repository import (
    SubscriptionServiceRepository,
    SubscriptionPeriodRepository,
    SubscriptionRepository,
    ConsolesRepository,
    SubscriptionRepository,
)

from games.services import GameService

from subscriptions.services import SubscriptionServiceManager

from subscriptions.models import SubscriptionService, SubscriptionPeriod, Consoles
from games.models import Game, Price


log_dir = os.path.expanduser("~/robokassa_logs")
os.makedirs(log_dir, exist_ok=True)

file_handler = logging.FileHandler(
    os.path.join(log_dir, f'robokassa_debug_{datetime.now().strftime("%Y%m%d")}.log')
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)

logger = logging.getLogger("robokassa")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(round(obj, 2))
        return super().default(obj)


class PaymentService:
    @staticmethod
    @transaction.atomic
    def create_payment_with_items(username, email, invoice_id, description, items_data):
        total_amount = sum(
            Decimal(item["price"]) * item["quantity"] for item in items_data
        )
        serialized_items = PaymentService.serialize_items_data(items_data)
        payment = PaymentRepository.create_payment(
            username=username,
            email=email,
            invoice_id=invoice_id,
            amount=total_amount,
            description=description,
            extra_field={"items_data": serialized_items},
            status="pending",
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
                "selected_level": extra.get("selected_level"),
            }

            if product_type == "game":
                payment_item_data["game"] = item["product"]
                payment_item_data["subscription_service"] = None
            elif product_type == "subscription_service":
                payment_item_data["subscription_service"] = item["product"]
                payment_item_data["subscription_period"] = extra.get(
                    "subscription_period"
                )
                payment_item_data["game"] = None

            payment_items.append(payment_item_data)
        PaymentItemRepository.bulk_create_items(payment_items)
        return payment

    @staticmethod
    def mark_payment_as_success(invoice_id: str):
        return PaymentRepository.update_payment_status(invoice_id, status="success")

    @staticmethod
    def mark_payment_as_failed(invoice_id: str):
        return PaymentRepository.update_payment_status(invoice_id, status="failed")

    @staticmethod
    def get_payment_details(invoice_id: str):
        return PaymentRepository.get_payment_by_invoice(invoice_id)

    @staticmethod
    def get_payment_by_pk(payment_id):
        return PaymentRepository.get_payment_by_id(payment_id)

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
                    return str(val)
                elif (
                    isinstance(val, (str, int, float, bool, list, dict)) or val is None
                ):
                    return val
                else:
                    return str(val)

            new_item = {
                "product_type": item["product_type"],
                "product_id": serialize_value(item.get("product")),
                "price": serialize_value(item["price"]),
                "quantity": serialize_value(item["quantity"]),
                "extra": {},
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
        invoice_id = int(time.time()) % 100000
        logger.debug(f"Сгенерирован InvId: {invoice_id}")
        return invoice_id

    @staticmethod
    def base64url_encode(data: str):
        encoded = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")

    @staticmethod
    def md5_signature(message: str, secret: str):
        key = secret.encode("utf-8")
        msg = message.encode("utf-8")
        hmac_digest = hmac.new(key, msg, hashlib.md5).digest()
        return base64.b64encode(hmac_digest).decode("utf-8").rstrip("=")

    @staticmethod
    def get_payment_url(payment, items_data, merchant_login=None):
        if merchant_login is None:
            merchant_login = settings.ROBOKASSA_MERCHANT_LOGIN

        password = settings.ROBOKASSA_PASSWORD1
        invoice_id = payment.invoice_id
        amount = Decimal(payment.amount)
        email = str(payment.email)
        description = payment.description or "Оплата"

        invoice_items = []
        for item in items_data:
            template = {
                "Name": "",
                "Quantity": 0,
                "Cost": Decimal(0),
                "Tax": "none",
                "PaymentMethod": "full_payment",
                "PaymentObject": "commodity",
            }

            if item["product_type"] == "subscription_service":
                service = item["product"]
                extra = item["extra"]
                rec_description = (
                    f"{service.title} на {extra['subscription_period'].months} мес."
                )
                if extra.get("selected_level"):
                    rec_description += f", Вариант подписки={extra['selected_level']}"
                rec_description += f", Консоль={extra['console'].name}"

                template["Name"] = rec_description
                template["Cost"] = Decimal(extra["subscription_period"].price)
                template["Quantity"] = item["quantity"]
                invoice_items.append(template)

            elif item["product_type"] == "game":
                game = item["product"]
                extra = item["extra"]
                rec_description = f"{game.title}, Консоль={extra['console'].name}"
                rec_description += (
                    " С активацией"
                    if extra["price_object"].payment_type == "with_activation"
                    else " Без активаций"
                )
                template["Name"] = rec_description
                template["Cost"] = Decimal(extra["price_object"].discounted_price)
                template["Quantity"] = item["quantity"]
                invoice_items.append(template)

        header = {"typ": "JWT", "alg": "MD5"}
        payload = {
            "MerchantLogin": merchant_login,
            "InvoiceType": "OneTime",
            "Culture": "ru",
            "InvId": invoice_id,
            "OutSum": amount,
            "Description": description,
            "MerchantComments": "no comment",
            "Email": email,
            "UserFields": {
                "shp_username": payment.username,
                "shp_Email": payment.email,
                "shp_payment_id": str(payment.id),
            },
            "InvoiceItems": invoice_items,
        }

        header_b64 = RobokassaService.base64url_encode(
            json.dumps(header, ensure_ascii=False)
        )
        payload_b64 = RobokassaService.base64url_encode(
            json.dumps(payload, ensure_ascii=False, cls=DecimalEncoder)
        )
        signature = RobokassaService.md5_signature(
            f"{header_b64}.{payload_b64}", f"{merchant_login}:{password}"
        )
        jwt_token = f"{header_b64}.{payload_b64}.{signature}"

        response = requests.post(
            settings.ROBO_API,
            json=jwt_token,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            result = response.json()
            return result["url"]
        else:
            raise Exception(
                f"Robokassa API error: {response.status_code} {response.text}"
            )

    @staticmethod
    def check_signature(request_data):
        logger.info(f"=== ПРОВЕРКА ПОДПИСИ ОТ РОБОКАССЫ ===")
        if settings.ROBOKASSA_TEST_MODE:
            password = settings.ROBOKASSA_TEST_PASSWORD2
        else:
            password = settings.ROBOKASSA_PASSWORD2

        out_sum = request_data.get("OutSum")
        inv_id = request_data.get("InvId")
        received_signature = request_data.get("SignatureValue")

        logger.info(f"Verifying signature. OutSum: {out_sum}, InvId: {inv_id}")
        logger.info(f"Received signature: {received_signature}")
        logger.info(f"Using password2: {password[:3]}...{password[-3:]}")

        if not all([out_sum, inv_id, received_signature]):
            logger.error("Missing required parameters for signature verification")
            return False

        shp_params = {}
        for key, value in request_data.items():
            if key.lower().startswith("shp_"):
                shp_params[key] = value

        logger.info(f"Received Shp params: {shp_params}")

        signature_string = f"{out_sum}:{inv_id}:{password}"
        base_signature = signature_string
        logger.info(f"Base signature string for checking: {base_signature}")

        sorted_shp_params = sorted(shp_params.items())
        for key, value in sorted_shp_params:
            signature_string += f":{key}={value}"

        logger.info(f"Full signature string for checking: {signature_string}")

        calculated_signature = (
            hashlib.md5(signature_string.encode("utf-8")).hexdigest().lower()
        )
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

            inv_id = payment_data.get("InvId")
            out_sum = payment_data.get("OutSum")

            username = payment_data.get("shp_username")
            payment_id = payment_data.get("shp_payment_id")
            try:
                payment = PaymentService.get_payment_details(inv_id)
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
                        f"Username: {username}, Service ID: {subscription_service_id}, Period_ID: {subscription_period_id}-, Console ID: {console_id}"
                    )
                    subscription = SubscriptionServiceManager.get_user_subscriptions(
                        payment.email
                    )
                    if not subscription:
                        logger.info(f"Creating new subscription")
                        try:
                            subscription = SubscriptionServiceManager.create_subscription(
                                subscription_service_id=subscription_service_id,
                                subscription_period_id=subscription_period_id,
                                is_active=False,
                                email=payment.email,
                            )
                            logger.info(f"Subscription created: {subscription}")

                        except Exception as e:
                            logger.error(f"Error creating subscription: {e}")
                            return False, f"Ошибка при создании подписки: {str(e)}"
                    else:
                        logger.info(
                            f"Activating existing subscription: {payment.subscription}"
                        )
                        subscription.is_active = True
                        subscription.save()
                else:
                    continue

            logger.info(f"Payment ID: {inv_id}, Amount: {out_sum}")

            payment_amount = float(payment.amount)
            received_amount = float(out_sum)

            logger.info(
                f"Payment amount in DB: {payment_amount}, Received amount: {received_amount}"
            )

            if payment_amount != received_amount:
                logger.warning(
                    f"Amount mismatch. DB: {payment_amount}, Received: {received_amount}"
                )
                payment.status = "failed"
                payment.save()
                return False, "Сумма платежа не соответствует"

            logger.info(f"Updating payment status to 'success'")
            payment.status = "success"
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
        count_games = sum(1 for item in items if item["product_type"] == "game")
        count_subscriptions = sum(
            1 for item in items if item["product_type"] == "subscription_service"
        )

        parts = []
        if count_games:
            parts.append(f"Установка цифровых версий игр: {count_games}")
        if count_subscriptions:
            parts.append(f"Подписка(и): {count_subscriptions}")

        return "; ".join(parts)

        return f"Установка цифровых версий игр: {count_games}; Подписка(и): {count_subscriptions}"


class PaymentItemService:
    @staticmethod
    def get_payment_details(payment_id: str):
        return PaymentItemRepository.get_items_by_payment(payment_id)


class RobokassaService:
    @staticmethod
    def generate_invoice_id():
        invoice_id = int(time.time()) % 100000
        logger.debug(f"Сгенерирован InvId: {invoice_id}")
        return invoice_id

    @staticmethod
    def base64url_encode(data: str):
        encoded = base64.urlsafe_b64encode(data.encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")

    @staticmethod
    def md5_signature(message: str, secret: str):
        key = secret.encode("utf-8")
        msg = message.encode("utf-8")
        hmac_digest = hmac.new(key, msg, hashlib.md5).digest()
        return base64.b64encode(hmac_digest).decode("utf-8").rstrip("=")

    @staticmethod
    def get_payment_url(payment, items_data, merchant_login=None):
        if merchant_login is None:
            merchant_login = settings.ROBOKASSA_MERCHANT_LOGIN

        password = settings.ROBOKASSA_PASSWORD1
        invoice_id = payment.invoice_id
        amount = Decimal(payment.amount)
        email = str(payment.email)
        description = payment.description or "Оплата"

        invoice_items = []
        for item in items_data:
            template = {
                "Name": "",
                "Quantity": 0,
                "Cost": Decimal(0),
                "Tax": "none",
                "PaymentMethod": "full_payment",
                "PaymentObject": "commodity",
            }

            if item["product_type"] == "subscription_service":
                service = item["product"]
                extra = item["extra"]
                rec_description = (
                    f"{service.title} на {extra['subscription_period'].months} мес."
                )
                if extra.get("selected_level"):
                    rec_description += f", Вариант подписки={extra['selected_level']}"
                rec_description += f", Консоль={extra['console'].name}"

                template["Name"] = rec_description
                template["Cost"] = Decimal(extra["subscription_period"].price)
                template["Quantity"] = item["quantity"]
                invoice_items.append(template)

            elif item["product_type"] == "game":
                game = item["product"]
                extra = item["extra"]
                rec_description = f"{game.title}, Консоль={extra['console'].name}"
                rec_description += (
                    " С активацией"
                    if extra["price_object"].payment_type == "with_activation"
                    else " Без активаций"
                )
                template["Name"] = rec_description
                template["Cost"] = Decimal(extra["price_object"].discounted_price)
                template["Quantity"] = item["quantity"]
                invoice_items.append(template)

        header = {"typ": "JWT", "alg": "MD5"}
        payload = {
            "MerchantLogin": merchant_login,
            "InvoiceType": "OneTime",
            "Culture": "ru",
            "InvId": invoice_id,
            "OutSum": amount,
            "Description": description,
            "MerchantComments": "no comment",
            "Email": email,
            "UserFields": {
                "shp_username": payment.username,
                "shp_Email": payment.email,
                "shp_payment_id": str(payment.id),
            },
            "InvoiceItems": invoice_items,
        }

        header_b64 = RobokassaService.base64url_encode(
            json.dumps(header, ensure_ascii=False)
        )
        payload_b64 = RobokassaService.base64url_encode(
            json.dumps(payload, ensure_ascii=False, cls=DecimalEncoder)
        )
        signature = RobokassaService.md5_signature(
            f"{header_b64}.{payload_b64}", f"{merchant_login}:{password}"
        )
        jwt_token = f"{header_b64}.{payload_b64}.{signature}"

        response = requests.post(
            settings.ROBO_API,
            json=jwt_token,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            result = response.json()
            return result["url"]
        else:
            raise Exception(
                f"Robokassa API error: {response.status_code} {response.text}"
            )

    @staticmethod
    def check_signature(request_data):
        logger.info(f"=== ПРОВЕРКА ПОДПИСИ ОТ РОБОКАССЫ ===")
        if settings.ROBOKASSA_TEST_MODE:
            password = settings.ROBOKASSA_TEST_PASSWORD2
        else:
            password = settings.ROBOKASSA_PASSWORD2

        out_sum = request_data.get("OutSum")
        inv_id = request_data.get("InvId")
        received_signature = request_data.get("SignatureValue")

        logger.info(f"Verifying signature. OutSum: {out_sum}, InvId: {inv_id}")
        logger.info(f"Received signature: {received_signature}")
        logger.info(f"Using password2: {password[:3]}...{password[-3:]}")

        if not all([out_sum, inv_id, received_signature]):
            logger.error("Missing required parameters for signature verification")
            return False

        shp_params = {}
        for key, value in request_data.items():
            if key.lower().startswith("shp_"):
                shp_params[key] = value

        logger.info(f"Received Shp params: {shp_params}")

        signature_string = f"{out_sum}:{inv_id}:{password}"
        base_signature = signature_string
        logger.info(f"Base signature string for checking: {base_signature}")

        sorted_shp_params = sorted(shp_params.items())
        for key, value in sorted_shp_params:
            signature_string += f":{key}={value}"

        logger.info(f"Full signature string for checking: {signature_string}")

        calculated_signature = (
            hashlib.md5(signature_string.encode("utf-8")).hexdigest().lower()
        )
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

            inv_id = payment_data.get("InvId")
            out_sum = payment_data.get("OutSum")

            username = payment_data.get("shp_username")
            payment_id = payment_data.get("shp_payment_id")
            try:
                payment = PaymentService.get_payment_details(inv_id)
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
                        f"Username: {username}, Service ID: {subscription_service_id}, Period_ID: {subscription_period_id}-, Console ID: {console_id}"
                    )
                    subscription = SubscriptionServiceManager.get_user_subscriptions(
                        payment.email
                    )
                    if not subscription:
                        logger.info(f"Creating new subscription")
                        try:
                            subscription = SubscriptionServiceManager.create_subscription(
                                subscription_service_id=subscription_service_id,
                                subscription_period_id=subscription_period_id,
                                is_active=False,
                                email=payment.email,
                            )
                            logger.info(f"Subscription created: {subscription}")

                        except Exception as e:
                            logger.error(f"Error creating subscription: {e}")
                            return False, f"Ошибка при создании подписки: {str(e)}"
                    else:
                        logger.info(
                            f"Activating existing subscription: {payment.subscription}"
                        )
                        subscription.is_active = True
                        subscription.save()
                else:
                    continue

            logger.info(f"Payment ID: {inv_id}, Amount: {out_sum}")

            payment_amount = float(payment.amount)
            received_amount = float(out_sum)

            logger.info(
                f"Payment amount in DB: {payment_amount}, Received amount: {received_amount}"
            )

            if payment_amount != received_amount:
                logger.warning(
                    f"Amount mismatch. DB: {payment_amount}, Received: {received_amount}"
                )
                payment.status = "failed"
                payment.save()
                return False, "Сумма платежа не соответствует"

            logger.info(f"Updating payment status to 'success'")
            payment.status = "success"
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
        count_games = sum(1 for item in items if item["product_type"] == "game")
        count_subscriptions = sum(
            1 for item in items if item["product_type"] == "subscription_service"
        )

        parts = []
        if count_games:
            parts.append(f"Установка цифровых версий игр: {count_games}")
        if count_subscriptions:
            parts.append(f"Подписка(и): {count_subscriptions}")

        return "; ".join(parts)

        return f"Установка цифровых версий игр: {count_games}; Подписка(и): {count_subscriptions}"


class PallyService:
    @staticmethod
    def generate_invoice_id():
        invoice_id = int(time.time()) % 100000
        logger.debug(f"Сгенерирован InvId: {invoice_id}")
        return invoice_id

    @staticmethod
    def build_description(items):
        count_games = sum(1 for item in items if item["product_type"] == "game")
        count_subscriptions = sum(
            1 for item in items if item["product_type"] == "subscription_service"
        )

        parts = []
        if count_games:
            parts.append(f"Установка цифровых версий игр: {count_games}")
        if count_subscriptions:
            parts.append(f"Подписка(и): {count_subscriptions}")

        return "; ".join(parts)

    @staticmethod
    def create_payment(username, email, items):
        logger.info(f"=== СОЗДАНИЕ ПЛАТЕЖА ===")
        invoice_id = PallyService.generate_invoice_id()
        description = PallyService.build_description(items)

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
    def get_payment_url(payment, items_data, merchant_login=None):
        api_key = settings.P_API_KEY
        shp_id = settings.P_SHP_ID
        invoice_id = payment.invoice_id
        amount = Decimal(payment.amount)
        description = payment.description or "Оплата"
        email = str(payment.email)

        invoice_items = []
        for item in items_data:
            template = {
                "name": "",
                "quantity": 0,
                "price": Decimal(0),
                "category": "Digital",
                "extra": {"phone": None},
            }

            if item["product_type"] == "subscription_service":
                service = item["product"]
                extra = item["extra"]
                rec_description = (
                    f"{service.title} на {extra['subscription_period'].months} мес."
                )
                if extra.get("selected_level"):
                    rec_description += f", Вариант подписки={extra['selected_level']}"
                rec_description += f", Консоль={extra['console'].name}"

                template["name"] = rec_description
                template["price"] = Decimal(extra["subscription_period"].price)
                template["quantity"] = item["quantity"]
                invoice_items.append(template)

            elif item["product_type"] == "game":
                game = item["product"]
                extra = item["extra"]
                rec_description = f"{game.title}, Консоль={extra['console'].name}"
                rec_description += (
                    " С активацией"
                    if extra["price_object"].payment_type == "with_activation"
                    else " Без активаций"
                )
                template["name"] = rec_description
                template["price"] = Decimal(extra["price_object"].discounted_price)
                template["quantity"] = item["quantity"]
                invoice_items.append(template)

        form_data = {
            "amount": amount,
            "shop_id": shp_id,
            "order_id": invoice_id,
            "description": description,
            "type": "normal",
            "locale": "ru",
            "custom": email,
            "currency_in": "RUB",
            "items": invoice_items,
        }

        for i, item in enumerate(invoice_items):
            form_data[f"items[{i}][name]"] = item["name"]
            form_data[f"items[{i}][price]"] = str(item["price"])
            form_data[f"items[{i}][quantity]"] = str(item["quantity"])
            form_data[f"items[{i}][category]"] = item.get("category", "Digital")
            for extra_key, extra_val in item.get("extra", {}).items():
                if extra_val is not None:
                    form_data[f"items[{i}][extra][{extra_key}]"] = str(extra_val)

        API_URL = "https://pal24.pro/api/v1/bill/create"
        response = requests.post(
            url=API_URL, data=form_data, headers={"Authorization": f"Bearer {api_key}"}
        )

        if response.status_code == 200:
            result = response.json()
            return result["link_page_url"]
        else:
            raise Exception(
                f"PayPalych API error: {response.status_code} {response.text}"
            )

    @staticmethod
    def process_payment(payment_data):
        logger.info(f"=== ОБРАБОТКА ПЛАТЕЖА ===")
        try:
            logger.info(f"Processing payment. Data: {payment_data}")

            inv_id = payment_data.get("InvId")
            status = payment_data.get("Status")
            out_sum = payment_data.get("OutSum")
            err_code = payment_data.get("ErrorCode") or None
            email = payment_data.get("custom")
            signature = payment_data.get("SignatureValue")

            try:
                payment = PaymentService.get_payment_details(inv_id)
                logger.info(f"Found payment in DB: {payment}")
            except Payment.DoesNotExist:
                logger.error(f"Error - Payment with ID {inv_id} not found in database")
                return False, "Платеж не найден"
            data = payment.extra_field
            logger.info(f"Extra from DB. Data: {data}")
            for item in data["items_data"]:
                if item["product_type"] == "subscription_service":
                    subscription_service_id = item["product_id"]
                    subscription_period_id = item["extra"]["subscription_period"]
                    console_id = item["extra"]["console"]
                    logger.info(
                        f" Service ID: {subscription_service_id}, Period_ID: {subscription_period_id}-, Console ID: {console_id}"
                    )

                    logger.info(f"Creating new subscription")
                    try:
                        subscription = SubscriptionServiceManager.create_subscription(
                            service_id=subscription_service_id,
                            period_id=subscription_period_id,
                            email=payment.email,
                        )
                        logger.info(f"Subscription created: {subscription}")
                        subscription.is_active = True
                        subscription.save()
                    except Exception as e:
                        logger.error(f"Error creating subscription: {e}")
                        return False, f"Ошибка при создании подписки: {str(e)}"
                else:
                    continue

            logger.info(f"Payment ID: {inv_id}, Amount: {out_sum}")

            payment_amount = float(payment.amount)
            received_amount = float(out_sum)

            logger.info(
                f"Payment amount in DB: {payment_amount}, Received amount: {received_amount}"
            )
            raw = f"{out_sum}:{inv_id}:{settings.P_API_KEY}"
            my_signature = hashlib.md5(raw.encode()).hexdigest().upper()

            if my_signature != signature.upper() or status == "FAIL":
                logger.warning(
                    f"The payment was declined by the payment system: ERRCODE - {err_code}"
                )
                payment.status = "failed"
                payment.save()
                return False, "Получен отказ от платёжной системы."

            logger.info(f"Updating payment status to 'success'")
            payment.status = "success"
            EmailService.send(email, inv_id)
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


class EmailService:
    @staticmethod
    def send(email, inv_id):
        context = {"email": email, "inv_id": inv_id}

        html_message = render_to_string("billing/verify_email.html", context)
        plain_message = strip_tags(html_message)
        email_from = settings.EMAIL_HOST_USER
        email_to = [email]

        mail = EmailMultiAlternatives(
            subject=f"PsGamezz — ваш заказ {inv_id}",
            body=plain_message,
            from_email=email_from,
            to=email_to,
        )

        mail.attach_alternative(html_message, "text/html")

        mail.send(fail_silently=False)
