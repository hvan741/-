from django.contrib import admin
from handbooks.models import OrderStatus

from orders import models
from orders.filters import OrderStatusFilter, OrderRetailCRMFilter
from orders.utils import generate_order_number


class OrderItemInline(admin.TabularInline):
    """Позиции в заказе"""

    extra = 0
    fields = ('offer', 'offer_sku', 'color', 'size', 'quantity', 'price', 'created', 'updated')
    model = models.OrderItem
    raw_id_fields = ('offer',)
    readonly_fields = ('created', 'updated', 'price', 'quantity', 'size', 'color', 'offer_sku')
    suit_classes = 'suit-tab suit-tab-items'

    @admin.display(description='Цвет')
    def color(self, obj):
        return obj.offer.color_value

    @admin.display(description='Артикул')
    def offer_sku(self, obj):
        return obj.offer.sku


class OrderStatusLogInline(admin.TabularInline):
    """Статусы заказа"""
    extra = 0
    fields = models.OrderStatusLog().collect_fields()
    model = models.OrderStatusLog
    readonly_fields = list(fields)
    suit_classes = 'suit-tab suit-tab-retail'

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    """Заказы"""

    date_hierarchy = 'created'
    fieldsets = (
        (None, {
            'classes': ('suit-tab', 'suit-tab-general'),
            'fields': (
                'order_number', 'user', 'first_name', 'last_name', 'phone',
                'email', 'comment', 'utm_source', 'utm_medium', 'utm_campaign',
                'utm_content', 'utm_term', 'status', 'created', 'updated',
            )
        }),
        (None, {
            'classes': ('suit-tab', 'suit-tab-delivery'),
            'fields': (
                'delivery_type', 'region', 'locality', 'street', 'building',
                'housing', 'apartment', 'delivery_point', 'self_delivery_point'
                # 'delivery_date',
                # 'delivery_time'
            )
        }),
        (None, {
            'classes': ('suit-tab', 'suit-tab-payment'),
            'fields': (
                'payment_type', 'payment_status',
                'payment_gateway_order_id', 'income', 'payment_error_code', 'payment_error_message'
            )
        }),
        (None, {
            'classes': ('suit-tab', 'suit-tab-bonuses'),
            'fields': ('coupon', 'coupon_entry')
        }),
        (None, {
            'classes': ('suit-tab', 'suit-tab-totals'),
            'fields': (
                'items_amount', 'coupon_amount', 'delivery_amount',
                'discount_amount', 'comission', 'bonus_amount', 'total_amount'
            )
        }),
        (None, {
            'classes': ('suit-tab', 'suit-tab-retail'),
            'fields': (
                'retailcrm_id', 'retail_crm_log'
            )
        })
    )
    inlines = (OrderItemInline, )
    list_display = (
        'order_number', 'user', 'first_name', 'last_name', 'phone', 'total_amount',
        'delivery_type', 'payment_type', 'payment_status', 'status', 'created'
    )
    list_filter = (
        OrderStatusFilter, 'created', 'delivery_type', 'payment_type', 
        'payment_status', OrderRetailCRMFilter, 'utm_source', 'utm_medium', 'utm_campaign',
    )
    list_max_show_all = 10000
    list_per_page = 50
    list_select_related = True
    raw_id_fields = (
        'coupon', 'coupon_entry', 'user', 'self_delivery_point', 'delivery_point', 'status'
    )
    readonly_fields = (
        'alt_id', 'created', 'order_number', 'income', 'items_amount', 'payment_status',
        'payment_gateway_order_id', 'payment_error_code', 'payment_error_message', 'retailcrm_id',
        'total_amount', 'updated', 'retail_crm_log', 'utm_campaign', 'utm_content', 'utm_medium',
        'utm_source', 'utm_term', 'comission'
    )
    search_fields = (
        '=id',  'order_number', 'first_name', 'last_name', 'phone', 'email', 'comment',
        'user__username', 'user__first_name', 'user__last_name', 'user__phone', 'region__title',
        'locality', 'postcode', 'street', 'building', 'housing', 'apartment',
        'total_amount', 'delivery_type__title', 'payment_type__title', 'coupon__passphrase',
        'retailcrm_id', 'utm_campaign', 'utm_content', 'utm_medium', 'utm_source', 'utm_term',
    )

    suit_form_tabs = (
        ('general', 'Основное'),
        ('items', 'Товары'),
        ('delivery', 'Доставка'),
        ('payment', 'Оплата'),
        ('bonuses', 'Бонусы'),
        ('totals', 'Суммы'),
        ('retail', 'Retail CRM')
    )
    def save_model(self, request, obj, form, change):
        if not obj.status_id:
            try:
                default_status = OrderStatus.objects.get(is_default=True)
                obj.status = default_status
            except (OrderStatus.DoesNotExist, OrderStatus.MultipleObjectsReturned):
                pass

        if not obj.order_number:
            obj.order_number = generate_order_number()

        return super(OrderAdmin, self).save_model(request, obj, form, change)
