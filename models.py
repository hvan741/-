import decimal

from django.conf import settings
from django.db import models
from django.db.models import OuterRef, Count, Subquery, Prefetch
from django.db.models import Sum

from coupons.api.service import calculate_coupon_items_discount
from handbooks.enums import PaymentTypeEnum
from orders import ADDRESS_MAPPING
from snippets.enums import PaymentStatusEnum
from snippets.models import LastModMixin, BasicModel, BaseManager
from snippets.models.abstract import BaseQuerySet
from snippets.utils.passwords import generate_alt_id


class OrderQuerySet(BaseQuerySet):
    def get_list(self, user):
        order_item = OrderItem.objects.filter(
            order=OuterRef('pk')
        ).values_list('quantity', flat=True)[:1]
        return self.filter(
            user=user
        ).select_related(
            'status'
        ).prefetch_related(
            Prefetch(
                'items',
                queryset=OrderItem.objects.select_related('card')
            ),
        ).annotate(total_count=Count(Subquery(order_item))).order_by('-created')

    def get_retrieve(self, user):
        return self.get_list(user=user).select_related('delivery_type')


class Order(LastModMixin, BasicModel):
    """Заказ """

    user = models.ForeignKey(
        'users.User', related_name='orders', verbose_name='Пользователь',
        on_delete=models.SET_NULL, blank=True, null=True
    )
    region = models.ForeignKey(
        'handbooks.Region', related_name='orders', verbose_name='Регион', blank=True, null=True,
        on_delete=models.SET_NULL
    )
    self_delivery_point = models.ForeignKey(
        'handbooks.SelfDeliveryPoint', related_name='orders', verbose_name='Собственный пункт самовывоза',
        blank=True, null=True, on_delete=models.SET_NULL
    )
    delivery_point = models.ForeignKey(
        'handbooks.DeliveryListPoint', related_name='orders', verbose_name='Пункт доставки',
        blank=True, null=True, on_delete=models.SET_NULL
    )
    delivery_type = models.ForeignKey(
        'handbooks.DeliveryType', verbose_name='Тип доставки', related_name='orders', null=True,
        on_delete=models.SET_NULL
    )
    payment_type = models.ForeignKey(
        'handbooks.PaymentType', verbose_name='Тип оплаты', related_name='orders', null=True,
        on_delete=models.SET_NULL
    )
    coupon = models.ForeignKey(
        'coupons.Coupon', related_name='orders', verbose_name='Промокод',
        on_delete=models.SET_NULL, blank=True, null=True
    )
    coupon_entry = models.OneToOneField(
        'coupons.CouponEntry', related_name='order_duplicate',
        verbose_name='Использование промокода', on_delete=models.SET_NULL, blank=True, null=True
    )
    status = models.ForeignKey(
        'handbooks.OrderStatus', verbose_name='Статус', related_name='orders',
        on_delete=models.CASCADE
    )

    order_number = models.CharField('Номер заказа', max_length=12, unique=True)
    alt_id = models.CharField('Alt ID', max_length=30, default=generate_alt_id, unique=True)
    yookassa_id = models.CharField('ID в ЮKassa', max_length=40, unique=True, null=True, blank=True)
    first_name = models.CharField('Имя', max_length=255)
    last_name = models.CharField('Фамилия', max_length=255, blank=True, null=True)
    phone = models.CharField('Телефон', max_length=30)
    email = models.EmailField('Email', max_length=254, blank=True, null=True)
    comment = models.TextField('Комментарий', max_length=4096, blank=True, null=True)

    locality = models.CharField('Населенный пункт', blank=True, null=True, max_length=255)
    postcode = models.CharField('Почтовый индекс', max_length=6, blank=True, null=True)
    street = models.CharField('Улица', max_length=150, blank=True, null=True)
    building = models.CharField('Корпус', max_length=20, blank=True, null=True)
    housing = models.CharField('Дом', max_length=20, blank=True, null=True)
    apartment = models.CharField('Квартира', max_length=20, blank=True, null=True)

    is_fast_order = models.BooleanField('Быстрый заказ', default=False)
    coupon_amount = models.DecimalField(
        'Скидка по промокоду', max_digits=11, decimal_places=2, blank=True, null=True
    )
    retailcrm_id = models.IntegerField('ID в RetailCRM', blank=True, null=True)
    retail_crm_log = models.TextField('Лог RetailCRM', blank=True, null=True)

    congratulation = models.TextField('Поздравление', blank=True, null=True)

    items_amount = models.DecimalField(
        'Стоимость товара', max_digits=11, decimal_places=2, blank=True, default=0
    )
    bonus_amount = models.DecimalField(
        'Бонусы', max_digits=11, decimal_places=2, blank=True, null=True
    )
    delivery_amount = models.DecimalField(
        'Стоимость доставки', max_digits=11, decimal_places=2, blank=True, null=True
    )
    delivery_date = models.DateField('Дата доставки', blank=True, null=True)
    delivery_time = models.CharField('Время доставки', max_length=50, blank=True, null=True)
    discount_amount = models.DecimalField(
        'Скидки', max_digits=11, decimal_places=2, blank=True, null=True
    )
    total_amount = models.DecimalField(
        'Общая стоимость', max_digits=11, decimal_places=2, blank=True, default=0
    )
    comission = models.DecimalField(
        'Комиссия', max_digits=11, decimal_places=2, blank=True, default=0
    )
    last_payment_attempt = models.DateTimeField(
        'Последняя попытка оплаты', blank=True, null=True
    )
    payment_status = models.SmallIntegerField(
        'Статус оплаты', default=PaymentStatusEnum.default, choices=PaymentStatusEnum.get_choices()
    )
    payment_gateway_order_id = models.CharField(
        'Идентификатор оплаты шлюза', blank=True, null=True, max_length=64
    )
    income = models.DecimalField(
        'Полученная сумма', max_digits=11, decimal_places=2, blank=True, null=True
    )
    payment_error_code = models.CharField(
        'Код ошибки оплаты', max_length=20, blank=True, null=True
    )
    payment_error_message = models.TextField('Текст ошибки оплаты', blank=True, null=True)

    utm_source = models.CharField(
        'UTM Source', max_length=255, blank=True, null=True, db_index=True
    )
    utm_medium = models.CharField(
        'UTM Medium', max_length=255, blank=True, null=True, db_index=True
    )
    utm_campaign = models.CharField(
        'UTM Campaign', max_length=255, blank=True, null=True, db_index=True
    )
    utm_content = models.CharField(
        'UTM Content', max_length=255, blank=True, null=True, db_index=True
    )
    utm_term = models.CharField(
        'UTM Term', max_length=255, blank=True, null=True, db_index=True
    )
    utm_placement = models.CharField(
        'UTM Placement', max_length=255, blank=True, null=True, db_index=True
    )

    fast_order_email_fields = (
        'order_number', 'email', 'first_name', 'phone', 'items_amount', 'total_amount'
    )
    full_order_email_fields = (
        'order_number', 'user', 'first_name', 'last_name', 'phone', 'email', 'comment', 'region',
        'locality', 'postcode', 'street', 'building', 'housing', 'apartment', 'delivery_type',
        'payment_type', 'coupon', 'congratulation',
        'items_amount', 'delivery_amount', 'discount_amount', 'total_amount'
    )

    objects = BaseManager.from_queryset(OrderQuerySet)()
    
    class Meta:
        ordering = ('-created',)
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self):
        return self.order_number

    def get_payment_id(self):
        return '%s%s' % ('test-' if settings.DEBUG else '', self.order_number)

    def save(self, *args, **kwargs):
        self.update_totals()
        return super(Order, self).save(*args, **kwargs)

    def update_totals(self):
        if self.pk:
            items = self.items.all()
            self.items_amount = sum([
                x.price * x.quantity for x in items if x.price and x.quantity
            ])

            if self.coupon_id:
                self.coupon_amount = min(
                    calculate_coupon_items_discount(self.coupon, items),
                    self.items_amount
                )
            else:
                self.coupon_amount = decimal.Decimal('0')

            self.discount_amount = self.coupon_amount
            self.comission = self.items_amount * decimal.Decimal(self.payment_type.comission_percent) / 100
            self.total_amount = self.items_amount + self.comission \
                                + decimal.Decimal(
                self.delivery_amount if self.delivery_amount else 0) \
                                - decimal.Decimal(self.discount_amount or 0) \
            - decimal.Decimal(self.bonus_amount or 0)

    @property
    def address_full(self):
        parts = []
        for k, v in ADDRESS_MAPPING.items():
            if getattr(self, k):
                parts.append('%s%s' % (('%s ' % v if v else ''), getattr(self, k)))
        return ', '.join(parts)

    @property
    def is_prepayed(self):
        return self.payment_type.payment_kind in PaymentTypeEnum.online_types

    def get_full_name(self):
        res = ' '.join(filter(lambda x: x, [self.first_name, self.last_name]))
        if not res and self.user_id:
            return self.user.get_full_name()

        return res

    @property
    def total_quantity(self):
        total = self.items.aggregate(Sum('quantity'))
        return total['quantity__sum'] if total.get('quantity__sum') else 0

    @property
    def admin_url(self):
        return "/%s/%s/%s/change/" % (self._meta.app_label, self._meta.model_name, self.id)


class OrderItem(LastModMixin, BasicModel):
    """Элементы заказа"""

    order = models.ForeignKey(
        'orders.Order', related_name='items', on_delete=models.CASCADE, verbose_name='Заказ'
    )
    offer = models.ForeignKey(
        'catalog.ProductOffer', verbose_name='Предложение', related_name='order_items',
        on_delete=models.SET_NULL, null=True
    )
    card = models.ForeignKey(
        'catalog.ProductOfferCard', verbose_name='Карточка товара', related_name='order_items',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    quantity = models.PositiveIntegerField('Количество', default=1)
    price = models.DecimalField(
        'Цена за единицу', max_digits=11, decimal_places=2, blank=True, default=0
    )
    size = models.CharField('Размер', max_length=100, blank=True)

    class Meta:
        ordering = ('created',)
        verbose_name = 'Позиция в заказе'
        verbose_name_plural = 'Позиции заказа'

    def __str__(self):
        return str('Заказ #{order_id} - {product} ({quantity} {price} ').format(
            order_id=self.order.order_number,
            product=self.offer,
            quantity=self.quantity,
            price=self.price
        )

    @property
    def total_amount(self):
        return self.quantity * self.price


class OrderStatusLog(LastModMixin, BasicModel):
    """Статусы заказа"""

    order = models.ForeignKey(
        'orders.Order', related_name='statuses', on_delete=models.CASCADE, verbose_name='Заказ'
    )
    status = models.ForeignKey(
        'handbooks.OrderStatus', verbose_name='Статус', related_name='order_statuses',
        on_delete=models.CASCADE
    )
    comment = models.TextField('Комментарий', max_length=4096, blank=True, null=True)
    send_email = models.BooleanField('Отправить email', default=True)
    is_email_sent = models.BooleanField('Отправлен email', default=False)

    class Meta:
        ordering = ('created',)
        verbose_name = 'Статус заказа'
        verbose_name_plural = 'Статусы заказа'

    def __str__(self):
        return f'{self.order} - {self.status}'

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.order.status_id != self.status_id:
                self.order.status = self.status
                self.order.save()

            # if self.order.email and self.send_email and not self.status.is_default:
            #     send_email(
            #         'order_status_customer',
            #         [self.order.email],
            #         _('Изменение статуса Вашего заказа на сайте %s') % self.order.site.domain,
            #         params={
            #             'site_url': settings.SITE_URL,
            #             'order': self.order,
            #             'status': self,
            #             'status_verbose': self.status.title
            #         },
            #         raise_error=False
            #     )
            #     self.is_email_sent = True

        return super(OrderStatusLog, self).save(*args, **kwargs)
