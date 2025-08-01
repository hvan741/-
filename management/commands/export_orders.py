import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from catalog.models import ProductOffer
from snippets.enums import PaymentStatusEnum

from ... import models


class Command(BaseCommand):
    """Экспорт заказов в json"""

    def handle(self, *args, **options):
        orders = models.Order.objects.prefetch_related('items').select_related(
            'status', 'region', 'delivery_type', 'courier_delivery_time_slot',
            'self_delivery_point', 'payment_type', 'coupon', 'coupon_entry'
        )

        with open(os.path.join(settings.SITE_ROOT, 'import_data', 'orders.csv'), 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'id', 'user_id', 'order_number', 'status', 'first_name', 'last_name', 'phone',
                'email', 'comment', 'region', 'locality', 'created', 'postcode', 'street',
                'building', 'housing', 'apartment', 'pickup_point_operator',
                'pickup_point_address', 'pickup_point_id', 'delivery_type',
                'courier_delivery_date', 'courier_delivery_time_slot', 'self_delivery_point',
                'payment_type', 'is_fast_order', 'coupon', 'coupon_applied', 'items_amount',
                'coupon_amount', 'delivery_amount', 'discount_amount', 'total_amount',
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
                'utm_placement', 'last_payment_attempt', 'payment_status', 'payment_income',
                'retailcrm_id', 'item_product_id', 'item_size', 'offer_id', 'quantity',
                'product_base_price', 'base_price', 'price'
            ])

            for order in orders:
                order_data = [
                    order.id,
                    order.user_id or '',
                    order.order_number or '',
                    order.status.title if order.status_id else '',
                    order.first_name or '',
                    order.last_name or '',
                    order.phone or '',
                    order.email or '',
                    order.comment or '',
                    order.region.title if order.region_id else '',
                    order.locality or '',
                    order.created.strftime('%Y-%m-%d'),
                    order.postcode or '',
                    order.street or '',
                    order.building or '',
                    order.housing or '',
                    order.apartment or '',
                    order.pickup_point_operator.title if order.pickup_point_operator else '',
                    order.pickup_point_address or '',
                    order.pickup_point_id or '',
                    order.delivery_type.title if order.delivery_type_id else '',
                    order.courier_delivery_date.strftime('%Y-%m-%d')
                    if order.courier_delivery_date else '',
                    order.courier_delivery_time_slot.title
                    if order.courier_delivery_time_slot_id else '',
                    order.self_delivery_point.title
                    if order.self_delivery_point_id else '',
                    order.payment_type.title if order.payment_type_id else '',
                    order.is_fast_order,
                    order.coupon.passphrase.upper() if order.coupon_id else '',
                    order.coupon_entry.created.strftime('%Y-%m-%d')
                    if order.coupon_entry_id else '',
                    float(order.items_amount or 0),
                    float(order.coupon_amount or 0),
                    float(order.delivery_amount or 0),
                    float(order.discount_amount or 0),
                    float(order.total_amount or 0),
                    order.utm_source or '',
                    order.utm_medium or '',
                    order.utm_campaign or '',
                    order.utm_content or '',
                    order.utm_term or '',
                    order.utm_placement or '',
                    order.last_payment_attempt.strftime('%Y-%m-%d')
                    if order.last_payment_attempt else '',
                    str(PaymentStatusEnum.values.get(order.payment_status)),
                    float(order.income) if order.income else '',
                    order.retailcrm_id or ''
                ]
                items = order.items.all()
                if items:
                    for item in items:
                        offers = ProductOffer.objects \
                            .filter(product_id=item.product_id, size=item.size_id) \
                            .order_by('status') \
                            .values_list('source_id', flat=True)[:1]

                        item_data = order_data + [
                            item.product_id,
                            item.size_id if item.size_id else '',
                            offers[0] if offers else '',
                            item.quantity,
                            float(item.product_base_price or 0),
                            float(item.base_price or 0),
                            float(item.price or 0)
                        ]

                        writer.writerow(item_data)
                else:
                    writer.writerow(order_data + ['' for x in range(7)])
