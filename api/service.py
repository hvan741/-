import traceback
from decimal import Decimal

import retailcrm
from carts.api.service import get_cart_items_amount
from coupons.api.service import (
    calculate_coupon_delivery_discount,
    calculate_coupon_items_discount,
)
from coupons.enums import ItemsPercentagePriceTypeEnum
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from handbooks.api.service import get_order_statuses_codes
from handbooks.enums import DeliveryCalcPriceMethodEnum, PaymentTypeEnum
from handbooks.models import DeliveryRegion
from integrations.api.alpha import check_alpha_order_status
from integrations.api.payselection import PayselectionAPI, PayselectionRusAPI
from integrations.api.podeli.error import BnlpStatusError
from integrations.api.podeli_api import PodeliAPI
from integrations.api.yookassa import YookassaAPI
from integrations.services import create_retail_user
from orders import models
from orders.models import Order
from users.models import UserAddress

from snippets.enums import PaymentStatusEnum
from snippets.forms.validators import valid_email


def accept_payment(order):
    """Accept payment"""
    order.payment_status = PaymentStatusEnum.PAID
    order.save()

    return order


def calc_delivery_amount(delivery_type, region=None):
    if not delivery_type:
        return None

    if delivery_type.calc_price_method == DeliveryCalcPriceMethodEnum.ALWAYS_FREE:
        return Decimal(0)

    if delivery_type.calc_price_method == DeliveryCalcPriceMethodEnum.FIXED_PRICE:
        return delivery_type.price

    if not region:
        return None

    try:
        delivery_region = DeliveryRegion.objects.published().filter(
            delivery_type=delivery_type
        ).get(region=region)
    except (DeliveryRegion.DoesNotExist, DeliveryRegion.MultipleObjectsReturned):
        return None

    return delivery_region.price if not delivery_type.is_price_from else 0


def calc_amounts(cart_items, items_amount, validated_data):
    coupon_amount = Decimal(0)
    discount_amount = Decimal(0)
    delivery_amount = Decimal(validated_data.get('delivery_amount', 0))

    # delivery_type = validated_data.get('delivery_type')
    # region = validated_data.get('region')
    # if delivery_type:
    #     delivery_amount = float(calc_delivery_amount(delivery_type, region=region) or .0)

    coupon = validated_data.get('coupon')
    bonuses = validated_data.get('bonuses')
    coupon_delivery_amount = Decimal(0)

    if coupon and items_amount:
        amount_for_coupon = items_amount
        if coupon.items_percentage_price_type == ItemsPercentagePriceTypeEnum.PRICE:
            amount_for_coupon = get_cart_items_amount(cart_items, base_price=True)

        discount_amount = Decimal(calculate_coupon_items_discount(coupon, cart_items) or 0)

        coupon_delivery_amount = Decimal(0)
        if delivery_amount:
            coupon_delivery_amount = Decimal(calculate_coupon_delivery_discount(
                coupon,
                amount_for_coupon,
                delivery_amount
            ) or 0)
            delivery_amount -= coupon_delivery_amount
        coupon_amount = discount_amount

    total_amount = Decimal(items_amount) + delivery_amount - (discount_amount or 0) - (bonuses or 0)
    discount_amount += coupon_delivery_amount

    return {
        'coupon_amount': coupon_amount,
        'delivery_amount': delivery_amount,
        'discount_amount': discount_amount,
        'items_amount': items_amount,
        'total_amount': total_amount
    }


def check_order_statuses_from_retailcrm(orders_retailcrm_ids, retailcrm_client=None,
                                        statuses_codes=None):
    if retailcrm_client is None:
        retailcrm_client = retailcrm.v5(settings.RETAIL_CRM_URL, settings.RETAIL_CRM_API_KEY)

    if statuses_codes is None:
        statuses_codes = get_order_statuses_codes()

    response = retailcrm_client.orders_statuses(ids=list(orders_retailcrm_ids), external_ids=[])
    result = response.get_response()
    print(result)

    for order in result['orders']:
        if order['status'] not in statuses_codes:
            print(
                f'Continue, status {order["status"]} was not found for order {order["externalId"]}'
            )
            continue

        status = statuses_codes[order['status']]

        try:
            if 'externalId' in order:
                order_obj = models.Order.objects.get(pk=int(order['externalId']))
            elif 'id' in order:
                order_obj = models.Order.objects.get(retailcrm_id=int(order['id']))
        except (models.Order.DoesNotExist, ValueError):
            continue

        if order_obj.status_id != status.id:
            models.OrderStatusLog.objects.create(order=order_obj, status=status, send_email=True)
            print(f'Order {order_obj}: {status}')


def is_free_delivery(items_amount, deivery_region, delivery_type):
    """Является ли доставка бесплатной по объему покупки (если включен такой режим)"""

    if delivery_type.is_price_from:
        return False

    limit = deivery_region.free_delivery
    if limit and items_amount >= limit:
        return True

    return False


def update_payment_status(order: Order):
    """Updates payment status"""

    with transaction.atomic():
        is_podeli = order.payment_type.payment_kind == PaymentTypeEnum.PODELI
        is_payselection = order.payment_type.payment_kind == PaymentTypeEnum.PAYSELECTION
        is_payselection_rus = order.payment_type.payment_kind == PaymentTypeEnum.PAYSELECTION_RUS
        is_yookassa = order.payment_type.payment_kind == PaymentTypeEnum.YOOKASSA
        if order.total_amount == 0:
            result = {'OrderStatus': 2}
        else:
            if is_podeli:
                api = PodeliAPI()
                try:
                    api.commit(order)
                except BnlpStatusError:
                    traceback.print_exc()

                result = api.check_order(order)
            elif is_payselection:
                api = PayselectionAPI()
                result = api.check_order(order)
            elif is_payselection_rus:
                api = PayselectionRusAPI()
                result = api.check_order(order)
            elif is_yookassa:
                api = YookassaAPI()
                result = api.check_order(order)
            else:
                result = check_alpha_order_status(order)
        if result.get('errorCode') or result.get('errorMessage'):
            order.payment_error_code = result.get('errorCode')
            order.payment_error_message = result.get('errorMessage')
            order.save()

        if is_podeli and result.get('OrderStatus') in [
            PaymentStatusEnum.PAID,
            PaymentStatusEnum.PAID_PARTIALLY
        ]:
            order.income = Decimal(str(result.get('depositAmount', 0) / 100))
            if order.income:
                order.save()
            if order.payment_status != PaymentStatusEnum.PAID:
                accept_payment(order)
        else:
            is_paid = result.get('OrderStatus', 0) == PaymentStatusEnum.PAID
            if is_paid and not order.income:
                order.income = Decimal(str(result.get('depositAmount', 0) / 100))
                if order.income:
                    order.save()

            if is_paid and order.payment_status != PaymentStatusEnum.PAID:
                accept_payment(order)

    return order


def get_address(order):
    address = {
        'index': order.postcode,
        'text': order.address_full
    }
    if order.region_id:
        address['region'] = order.region.title

    if order.locality:
        address['city'] = order.locality

    if order.street:
        address['street'] = order.street

    if order.housing:
        address['building'] = order.housing

    if order.building:
        address['house'] = order.building

    if order.apartment:
        address['flat'] = order.apartment

    return address


def update_retail_user(order: Order, client) -> bool:
    """Обновляет данные пользователя в системе ReatilCRM"""
    user = order.user
    address = get_address(order)
    customer_data = {
        "externalId": user.id,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "address": address,
        "createdAt": timezone.localtime(user.created).strftime("%Y-%m-%d %H:%M:%S"),
        "site": settings.RETAIL_CRM_SITE_CODE,
    }

    if user.birth_date:
        customer_data["birthday"] = user.birth_date.strftime("%Y-%m-%d")

    print("Обновляем пользователя")
    response = client.customer_edit(customer_data, site=settings.RETAIL_CRM_SITE_CODE)
    result = response.get_response()
    print(result)
    if result.get("success") is False:
        order.retail_crm_log = (
            f"Отправлено при обновлении пользователя:\n"
            f"{customer_data}\n\nОтвет:\n{result}"
        )
        order.save()
        return False

    return True


def get_delivery_data(order) -> dict:

    # Если выбран способ доставки курьером
    if not order.delivery_point and not order.self_delivery_point:
        address = get_address(order)
        return {
            'address': address,
            'cost': float(order.delivery_amount) if order.delivery_amount else .0,
        }

    delivery_data = {
        'address': {},
        'cost': float(order.delivery_amount) if order.delivery_amount else .0,
    }

    # Если выбран способ доставки из пункта выдачи
    if order.delivery_point:
        delivery_data['code'] = order.delivery_point.code
        delivery_point_address = order.delivery_point.address
        address = {
            'text': delivery_point_address
        }
        delivery_data['address'] = address
        delivery_data['pickuppointAddress'] = delivery_point_address

    # Если выбран способ доставки самовывоз
    if order.self_delivery_point:
        self_delivery_point_address = order.self_delivery_point.address
        address = {
            'text': self_delivery_point_address
        }
        delivery_data['address'] = address

    return delivery_data


def get_order_items(order) -> list:
    items = []
    for item in order.items.select_related('offer').iterator():
        item_data = {
            'initialPrice': float(item.price),
            'createdAt': item.created.strftime('%Y-%m-%d %H:%M:%S'),
            'quantity': item.quantity,
            'properties': [
                {
                    'name': 'Размер',
                    'value': item.size
                },
                {
                    'name': 'Цвет',
                    'value': item.offer.color_value.value
                }
            ],
            'offer': {
                'externalId': item.offer_id,
                'xmlId': f'{item.offer.product.uuid}#{item.offer.uuid}'
            }
        }
        items.append(item_data)

    return items


def get_order_data(order) -> dict:
    delivery_data = get_delivery_data(order)

    order_data = {
        'number': order.order_number,
        # 'externalId': order.id,
        'createdAt': timezone.localtime(order.created).strftime('%Y-%m-%d %H:%M:%S'),
        'discountAmount': float(order.discount_amount) if order.discount_amount else .0,
        'firstName': order.first_name,
        'phone': order.phone,
        'status': 'new',
        'items': [],
        'delivery': delivery_data,
        'payments': [],
        'orderType': 'eshop-individual',
        'site': settings.RETAIL_CRM_SITE_CODE
    }

    if order.payment_type:
        payment_data = {
            'id': order.id,
            'status': 'paid'
            if order.payment_type.payment_kind in PaymentTypeEnum.online_types
               and order.payment_status is PaymentStatusEnum.PAID else 'not-paid',
            'type': order.payment_type.retail_code or '',
            'amount': float(order.total_amount)
        }

        # TODO: remove name comparison add integration_payment: bool field to PaymentType model
        # TODO: and check by "if order.payment_type.integration_payment:"
        if order.payment_type.retail_code == 'alfabank-r-milnali-api':
            payment_data.pop('status')

        if order.payment_type.payment_kind in PaymentTypeEnum.online_types \
                and order.payment_gateway_order_id:
            payment_data['externalId'] = order.payment_gateway_order_id

        if order.payment_type.payment_kind in PaymentTypeEnum.online_types \
                and order.last_payment_attempt:
            payment_data['paidAt'] = timezone.localtime(
                order.last_payment_attempt
            ).strftime('%Y-%m-%d %H:%M:%S')

        order_data['payments'].append(payment_data)

    order_data['items'] = get_order_items(order)

    if order.last_name:
        order_data['lastName'] = order.last_name

    order_data['customFields'] = {}

    if order.coupon_id:
        order_data['customFields']['coupon'] = order.coupon.passphrase

    if order.email:
        order_data['email'] = order.email.lower()

    if order.comment:
        order_data['customerComment'] = order.comment

    if order.user_id:
        order_data['customer'] = {
            'externalId': order.user_id,
            'id': order.user.retailcrm_id
        }

    if order.utm_source:
        order_data['source'] = {
            'source': order.utm_source or '',
            'medium': order.utm_medium or '',
            'campaign': order.utm_campaign or '',
            'keyword': order.utm_term or '',
            'content': order.utm_content or ''
        }

    return order_data


def upload_order_to_retailcrm(order, retailcrm_client=None):
    print(f'Order {order}... ', end='')
    if retailcrm_client is None:
        retailcrm_client = retailcrm.v5(
            settings.RETAIL_CRM_URL,
            settings.RETAIL_CRM_API_KEY
        )

    with transaction.atomic():

        need_update = False 
        try:
            if order.user.id:
                user = retailcrm_client.customer(uid=order.user.id).get_response()
                if not user['success']:
                    create_retail_user(order.user)
                else:
                    need_update = bool(('firstName' not in user['customer']) or not user['customer']['firstName'])

            if need_update:
                is_updated = update_retail_user(order, client=retailcrm_client)
                if not is_updated:
                    order.retail_crm_log = 'Ошибка обновления пользователя в RetailCRM'
                    order.save()
                    return False
        except Exception as e:
            order.retail_crm_log = f'Ошибка создания или обновления пользователя в RetailCRM: {traceback.format_exc()}'
            order.save()
            return False

        order_data = get_order_data(order)

        print('Sending\n', order_data)

        response = retailcrm_client.order_create(
            order_data,
            site=settings.RETAIL_CRM_SITE_CODE,
        )
        result = response.get_response()
        print('Result\n', result)

        if result.get('id'):
            order.retailcrm_id = result.get('id')

        order.retail_crm_log = f'Отправлено:\n{order_data}\n\nОтвет:\n{result}'
        order.save()

    print('done')
    return bool(result.get('success'))


def update_user_data(user, order: Order) -> None:

    if not user.first_name:
        user.first_name = order.first_name

    if not user.last_name and order.last_name:
        user.last_name = order.last_name

    if not user.email:
        user.email = order.email

    user.save()


def update_user_address_data(user, order: Order) -> None:
    """Обновление данных адреса доставки пользователя"""

    user_address: UserAddress = UserAddress.objects.filter(user=user)
    if user_address:
        user_address = user_address[0]
    else:
        user_address = UserAddress(user=user)

    user_address.city = order.locality
    user_address.street = order.street
    user_address.building = order.housing
    user_address.housing = order.building
    user_address.region = order.region.id
    user_address.delivery_type = order.delivery_type.id
    user_address.payment_type = order.payment_type.id
    user_address.apartment = order.apartment
    user_address.comment = order.comment
    user_address.save()
