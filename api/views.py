from http import HTTPStatus

from django.conf import settings
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from carts import MIN_AVAILABILITY
from carts.api.service import get_cart, get_cart_items_amount, get_cart_items, checkout_cart, \
    remove_cart_item
from catalog.api.service import get_product_amount
from coupons.api.service import find_coupon, apply_coupon
from handbooks.models import OrderStatus
from orders import models
from orders.api import serializers
from orders.api.service import calc_amounts, update_user_data, update_user_address_data
from orders.utils import generate_order_number
from snippets.api.response import error_response, success_response, validation_error_response
from snippets.api.views import PublicViewMixin
from snippets.enums import StatusEnum
from snippets.utils.email import send_email, send_trigger_email
from vars.models import SiteConfig, MenuItem
from users.models import Bonus


class OrderView(APIView):
    """Заказ"""

    serializer_class = serializers.NewOrderSerializer

    def post(self, request, **kwargs):
        user = request.user if request.user.is_authenticated else None
        cart = get_cart(request, user=user)[0]
        cart_items = get_cart_items(cart, sort_by_created=False, select_related_package_type=False)
        items_amount = get_cart_items_amount(cart_items) if cart else None

        serializer = self.serializer_class(
            data=request.data,
            context={
                'cart': cart,
                'items_amount': items_amount,
                'request': request,
                'user': user,
                'view': self
            }
        )

        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        total_cartitems_count = len(cart_items)
        if not total_cartitems_count:
            return error_response('Ваша корзина пуста.', code='cart_issue')

        with transaction.atomic():
            # acquired_amounts = acquire_amounts(cart_items)

            removed_cartitems_count = 0
            decreased_cartitems_count = 0

            for cart_item in cart_items:
                amount = get_product_amount(cart_item.offer_id)
                if amount < MIN_AVAILABILITY:
                    remove_cart_item(cart, cart_item.id)
                    removed_cartitems_count += 1
                elif cart_item.quantity > amount:
                    cart_item.quantity = amount
                    cart_item.save()
                    decreased_cartitems_count += 1

            if removed_cartitems_count > 0:
                if total_cartitems_count == 1:
                    msg = 'Товар закончился'
                elif removed_cartitems_count == total_cartitems_count:
                    msg = 'Все товары из корзины закончились'
                else:
                    msg = 'Некоторые товары из корзины закончились'
                return error_response(msg, code='cart_issue')

            if decreased_cartitems_count:
                return error_response(
                    'Количество товара на складе недостаточно для оформления заказа и было '
                    'уменьшено до доступного количества. '
                    'Вы можете оформить заказ с новым количеством товара.'
                    , code='cart_issue'
                )

            data = serializer.validated_data.copy()
            bonuses = None
            if 'bonuses' in data :
                bonuses = data.pop('bonuses')
            is_subscribe = data.pop('is_subscribe', False)
            status = OrderStatus.objects.filter(is_default=True).first()

            order_obj = models.Order(**data)
            order_obj.user = user
            order_obj.is_fast_order = False
            order_obj.order_number = generate_order_number()
            order_obj.status = status
            order_obj.bonus_amount = bonuses
            order_obj.save()

            if bonuses is not None:
                Bonus.objects.create(user=user, amount=bonuses, order=order_obj)

            update_user_data(user, order_obj)
            update_user_address_data(user, order_obj)

            if status:
                models.OrderStatusLog.objects.create(
                    order=order_obj, status=status, send_email=False
                )

            order_items = []
            for cart_item in cart_items:
                order_item_obj = models.OrderItem.objects.create(
                    order=order_obj,
                    offer=cart_item.offer,
                    card=cart_item.card,
                    size=cart_item.size,
                    quantity=cart_item.quantity,
                    price=cart_item.price,
                )
                order_items.append(order_item_obj)

            # update total amount
            calc_result = calc_amounts(cart_items, items_amount, serializer.validated_data)

            order_obj.delivery_amount = calc_result['delivery_amount']
            order_obj.discount_amount = calc_result['discount_amount']
            order_obj.items_amount = calc_result['items_amount']
            order_obj.total_amount = calc_result['total_amount'] 
            
            if serializer.validated_data.get('coupon') and calc_result.get('coupon_amount'):
                apply_coupon(
                    order_obj,
                    serializer.validated_data.get('coupon'),
                    calc_result['coupon_amount']
                )
            # if is_subscribe and order_obj.email:
            #     Subscription.objects.get_or_create(email=order_obj.email)
            order_obj.save()

        if order_obj.email:
            send_email(
                'order_customer',
                [order_obj.email],
                'Заказ №%s на сайте %s успешно оформлен' % (
                    order_obj.order_number, settings.SITE_NAME
                ),
                params={
                    'order': order_obj,
                    'order_items': order_items,
                    'site_name': settings.SITE_NAME,
                    'media_url': settings.MEDIA_URL,
                    'site_url': settings.SITE_URL,
                    'config': SiteConfig.get_solo(),
                },
                raise_error=False
            )

        # send_trigger_email(
        #     'Новый развернутый заказ №%s' % order_obj.order_number, request=request, obj=order_obj,
        #     fields=order_obj.full_order_email_fields, raise_error=False
        # )

        return success_response({
            'order_number': order_obj.order_number,
            'alt_id': order_obj.alt_id
        })


class OrderFastView(PublicViewMixin, APIView):
    """Быстрое оформление заказа"""

    serializer_class = serializers.FastOrderSerializer

    def post(self, request, **kwargs):
        user = request.user if request.user.is_authenticated else None
        cart = get_cart(request, user=user)[0]
        items_amount = get_cart_items_amount(cart) if cart else None

        serializer = self.serializer_class(
            data=request.data,
            context={
                'cart': cart,
                'items_amount': items_amount,
                'request': request,
                'user': user,
                'view': self
            }
        )

        if not serializer.is_valid():
            return validation_error_response(serializer.errors)

        cart = get_cart(request, user)[0]
        cart_items = get_cart_items(cart, sort_by_created=False)

        total_cartitems_count = len(cart_items)
        if not total_cartitems_count:
            return error_response('Ваша корзина пуста.', code='cart_issue')

        with transaction.atomic():
            # acquired_amounts = acquire_amounts(cart_items)

            removed_cartitems_count = 0
            decreased_cartitems_count = 0

            for cart_item in cart_items:
                amount = get_product_amount(cart_item.product)
                if amount < MIN_AVAILABILITY:
                    remove_cart_item(cart, cart_item.id)
                    removed_cartitems_count += 1
                elif cart_item.quantity > amount:
                    cart_item.quantity = amount
                    cart_item.save()
                    decreased_cartitems_count += 1

            if removed_cartitems_count > 0:
                if total_cartitems_count == 1:
                    msg = _('Товар закончился')
                elif removed_cartitems_count == total_cartitems_count:
                    msg = _('Все товары из корзины закончились')
                else:
                    msg = _('Некоторые товары из корзины закончились')
                return error_response(msg, code='cart_issue')

            if decreased_cartitems_count:
                return error_response(
                    _(
                        'Количество товара на складе недостаточно для оформления заказа и было '
                        'уменьшено до доступного количества. '
                        'Вы можете оформить заказ с новым количеством товара.'
                    ), code='cart_issue'
                )

            status = OrderStatus.objects.filter(is_default=True).first()
            data = serializer.validated_data.copy()
            order_obj = models.Order(**data)
            order_obj.user = user
            order_obj.is_fast_order = True
            order_obj.order_number = generate_order_number()
            order_obj.status = status
            order_obj.save()

            if status:
                models.OrderStatusLog.objects.create(
                    order=order_obj, status=status, send_email=False
                )

            order_items = []
            for cart_item in cart_items:
                order_item_obj = models.OrderItem.objects.create(
                    order=order_obj,
                    offer=cart_item.offer,
                    card=cart_item.card,
                    size=cart_item.size,
                    quantity=cart_item.quantity,
                    price=cart_item.price,
                )
                order_items.append(order_item_obj)

            # update total amount
            calc_result = calc_amounts(cart_items, items_amount, serializer.validated_data)

            order_obj.delivery_amount = calc_result['delivery_amount']
            order_obj.discount_amount = calc_result['discount_amount']
            order_obj.items_amount = calc_result['items_amount']
            order_obj.total_amount = calc_result['total_amount']

            order_obj.save()

        if order_obj.email:
            send_email(
                'fast_order_customer',
                [order_obj.email],
                'Быстрый заказ №%s на сайте %s успешно оформлен' % (
                    order_obj.order_number, settings.SITE_NAME
                ),
                params={
                    'order': order_obj,
                    'order_items': order_items,
                    'config': SiteConfig.get_solo(),
                    'socials': MenuItem.objects.published()
                .filter(menu__slug='SOCIALS', menu__status=StatusEnum.PUBLIC)
                },
                raise_error=False
            )

        send_trigger_email(
            'Новый быстрый заказ №%s' % order_obj.order_number, request=request, obj=order_obj,
            fields=order_obj.fast_order_email_fields, raise_error=False
        )

        return success_response({
            'order_number': order_obj.order_number,
            'alt_id': order_obj.alt_id
        })


class OrderApplyCouponView(PublicViewMixin, APIView):
    """Применение купона"""

    def post(self, request, **kwargs):
        coupon_passphrase = request.data.get('coupon')
        delivery = request.data.get('delivery')
        if not coupon_passphrase:
            return Response({'message': 'Не указан промокод'}, status=HTTPStatus.BAD_REQUEST)

        user = request.user if request.user.is_authenticated else None
        cart = get_cart(request, user=user)[0]
        cart_items = get_cart_items(cart, sort_by_created=False)

        items_amount = get_cart_items_amount(cart_items) if cart else None
        coupon, message = find_coupon(
            coupon_passphrase, delivery=delivery, user=user, items_amount=items_amount,
            cart_items=cart_items
        )
        if not coupon and message:
            return Response({'message': message}, status=HTTPStatus.BAD_REQUEST)

        return success_response('Промокод применен')


class OrderCalcPriceView(PublicViewMixin, APIView):
    """Калькулятор стоимости заказа"""

    serializer_class = serializers.OrderCalcPriceSerializer

    def post(self, request, **kwargs):
        user = request.user if request.user.is_authenticated else None
        cart = get_cart(request, user=user)[0]
        cart_items = get_cart_items(cart, sort_by_created=False)
        items_amount = get_cart_items_amount(cart_items) if cart else None

        serializer = self.serializer_class(
            data=request.data,
            context={
                'cart': cart,
                'items_amount': items_amount,
                'request': request,
                'user': user,
                'view': self
            }
        )

        if serializer.is_valid():
            result = calc_amounts(cart_items, items_amount, serializer.validated_data)

            return Response({'discount_amount': result['discount_amount']})

        return validation_error_response(serializer.errors)


class OrderHistoryView(ReadOnlyModelViewSet):
    """История заказов"""

    lookup_field = 'order_number'

    def get_queryset(self):
        user = self.request.user
        qs = {
            'list': models.Order.objects.get_list(user=user),
            'retrieve': models.Order.objects.get_retrieve(user=user)
        }
        return qs[self.action]

    def get_serializer_class(self):
        serializer_classes = {
            'list': serializers.OrderHistorySerializer,
            'retrieve': serializers.OrderHistoryRetrieveSerializer
        }
        return serializer_classes[self.action]

