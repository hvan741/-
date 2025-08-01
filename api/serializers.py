from rest_framework import serializers

from catalog.api.serializers import ProductSerializer, ProductOfferCardListSerializer
from catalog.models import ProductOfferCard
from coupons.api.service import find_coupon
from handbooks.enums import PaymentTypeEnum
from handbooks.models import DeliveryType, PaymentType, Region
from orders import models
from snippets.enums import PaymentStatusEnum
from snippets.api.serializers import fields
from vars.models import SiteConfig


class FastOrderSerializer(serializers.ModelSerializer):
    """Быстрый заказ"""

    theme = serializers.CharField(required=False, allow_null=True)

    class Meta:
        model = models.Order
        fields = ('email', 'first_name', 'phone', 'theme')


class NewOrderSerializer(serializers.ModelSerializer):
    """Создание заказа"""

    coupon = serializers.CharField(required=False, allow_null=True)
    delivery_type = serializers.IntegerField(required=True)
    is_subscribe = serializers.BooleanField(label='Подписаться', required=False, initial=True)
    orders_issue_point = serializers.IntegerField(required=False, allow_null=True)
    delivery_amount = serializers.DecimalField(max_digits=11, decimal_places=2, required=False, allow_null=True)
    payment_type = serializers.IntegerField(required=True)
    delivery_date = serializers.DateField(required=False, allow_null=True)
    delivery_time = serializers.CharField(required=False, allow_null=True)
    utm_campaign = serializers.CharField(required=False, allow_null=True)
    utm_content = serializers.CharField(required=False, allow_null=True)
    utm_medium = serializers.CharField(required=False, allow_null=True)
    utm_placement = serializers.CharField(required=False, allow_null=True)
    utm_source = serializers.CharField(required=False, allow_null=True)
    utm_term = serializers.CharField(required=False, allow_null=True)
    bonuses = serializers.DecimalField(allow_null=True, max_digits=10, decimal_places=2, write_only=True, required=False)

    class Meta:
        model = models.Order
        fields = (
            'apartment',
            'building',
            'comment',
            'congratulation',
            'coupon',
            'delivery_amount',
            'delivery_date',
            'delivery_point',
            'delivery_time',
            'delivery_type',
            'email',
            'first_name',
            'housing',
            'is_subscribe',
            'last_name',
            'locality',
            'orders_issue_point',
            'payment_type',
            'phone',
            'postcode',
            'region',
            'self_delivery_point',
            'street',
            'utm_campaign',
            'utm_content',
            'utm_medium',
            'utm_placement',
            'utm_source',
            'utm_term',
            'bonuses'
        )

    def validate_coupon(self, value):
        user = self.context['user']
        items_amount = self.context['items_amount']

        coupon = None
        if value:
            coupon, message = find_coupon(value, user=user, items_amount=items_amount)
            if not coupon and message:
                raise serializers.ValidationError(message)

        return coupon

    @staticmethod
    def validate_delivery_type(value):
        try:
            value = DeliveryType.objects.published().get(pk=value)
        except DeliveryType.DoesNotExist:
            raise serializers.ValidationError(
                'Способ доставки не найден среди доступных вариантов'
            )

        return value

    @staticmethod
    def validate_payment_type(value):
        try:
            value = PaymentType.objects.published().get(pk=value)
        except PaymentType.DoesNotExist:
            raise serializers.ValidationError(
                'Способ оплаты не найден среди доступных способов оплаты'
            )

        return value


class OrderCalcPriceSerializer(serializers.ModelSerializer):
    """Стоимость заказа"""
    coupon = serializers.CharField(required=False, allow_null=True)
    delivery_type = serializers.IntegerField(required=False, allow_null=True)
    payment_type = serializers.IntegerField(required=False, allow_null=True)
    region = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = models.Order
        fields = ('coupon', 'delivery_type', 'payment_type', 'region')

    def validate_coupon(self, value):
        coupon = None
        if value:
            user = self.context['user']
            items_amount = self.context['items_amount']
            coupon, message = find_coupon(value, user=user, items_amount=items_amount)
            if not coupon and message:
                raise serializers.ValidationError(message)

        return coupon

    @staticmethod
    def validate_delivery_type(value):
        if value:
            try:
                value = DeliveryType.objects.published().get(pk=value)
            except DeliveryType.DoesNotExist:
                raise serializers.ValidationError(
                    'Способ доставки не найден среди доступных вариантов'
                )

        return value

    @staticmethod
    def validate_payment_type(value):
        if value:
            try:
                value = PaymentType.objects.published().get(pk=value)
            except PaymentType.DoesNotExist:
                raise serializers.ValidationError(
                    'Способ оплаты не найден среди доступных вариантов'
                )

        return value

    @staticmethod
    def validate_region(value):
        if value:
            try:
                value = Region.objects.published().get(pk=value)
            except Region.DoesNotExist:
                raise serializers.ValidationError(
                    'Регион не найден среди доступных вариантов'
                )

        return value


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = models.OrderItem
        fields = ('product', 'quantity', 'price')


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    is_online_pay = serializers.SerializerMethodField()
    is_paid = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = models.Order
        fields = (
            'alt_id', 'created', 'id', 'is_online_pay', 'is_paid',
            'items_count', 'order_number', 'status', 'total_amount'
        )

    @staticmethod
    def get_items_count(obj):
        if hasattr(obj, 'items_count'):
            return obj.items_count

        return obj.items.count()

    @staticmethod
    def get_is_online_pay(obj):
        if not obj.payment_type_id:
            return False
        return obj.payment_type.payment_kind in PaymentTypeEnum.online_types

    @staticmethod
    def get_is_paid(obj):
        return obj.payment_status == PaymentStatusEnum.PAID

    @staticmethod
    def get_status(obj):
        return obj.status.title


class OrderSerializer(OrderListSerializer):
    delivery_type = serializers.StringRelatedField()
    items = serializers.SerializerMethodField()
    payment_type = serializers.StringRelatedField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = models.Order
        fields = (
            'alt_id',
            'created',
            'delivery_amount',
            'delivery_type',
            'id',
            'is_online_pay',
            'is_paid',
            'items',
            'items_amount',
            'order_number',
            'payment_type',
            'status',
            'total_amount',
        )

    @staticmethod
    def get_items(obj):
        items = obj.items.all()
        return OrderItemSerializer(items, many=True).data


class OrderSimpleSerializer(serializers.ModelSerializer):
    coupon = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    class Meta:
        model = models.Order
        fields = (
            'alt_id',
            'coupon',
            'delivery_amount',
            'is_fast_order',
            'items',
            'items_amount',
            'order_number',
            'total_amount',
        )

    @staticmethod
    def get_coupon(obj):
        if obj.coupon_id:
            return obj.coupon.passphrase

    @staticmethod
    def get_items(obj):
        items = obj.items.all()
        # return OrderItemSimpleSerializer(items, many=True).data


class OrderItemsHistorySerializer(serializers.ModelSerializer):
    """Позиции заказа"""
    image = fields.ImageField(source='card.image')
    slug = serializers.SerializerMethodField()

    class Meta:
        model = models.OrderItem
        fields = (
            'id',
            'image',
            'offer',
            'price',
            'quantity',
            'size',
            'slug'
        )

    def get_slug(self, obj):
        return obj.card.slug


class OrderHistorySerializer(serializers.ModelSerializer):
    """История заказов"""
    total_count = serializers.IntegerField()
    items = serializers.SerializerMethodField()
    status = serializers.SlugRelatedField(slug_field='title', read_only=True)

    class Meta:
        model = models.Order
        fields = (
            'alt_id',
            'delivery_date',
            'order_number',
            'status',
            'total_amount',
            'total_count',
            'items',
        )

    def get_items(self, obj):
        return OrderItemsHistorySerializer(obj.items, many=True).data


class OrderHistoryRetrieveSerializer(serializers.ModelSerializer):
    """История заказов"""
    total_count = serializers.IntegerField()
    items = serializers.SerializerMethodField()
    delivery_price = serializers.SlugRelatedField(slug_field='delivery_type.price', read_only=True)
    status = serializers.SlugRelatedField(slug_field='title', read_only=True)

    class Meta:
        model = models.Order
        fields = (
            'alt_id',
            'delivery_date',
            'delivery_price',
            'order_number',
            'status',
            'total_amount',
            'total_count',
            'items',
        )

    def get_items(self, obj):
        return OrderItemsHistorySerializer(obj.items, many=True).data
