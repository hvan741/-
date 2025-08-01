import retailcrm
from django.conf import settings
from django.core.management.base import BaseCommand

from coupons.models import Coupon, CouponEntry
from handbooks.models import DeliveryType, PaymentType
from snippets.enums import PaymentStatusEnum

from ...models import Order


class Command(BaseCommand):
    """Обновляем данные заказов из retail crm"""

    def handle(self, *args, **options):
        retailcrm_client = retailcrm.v5(settings.RETAIL_CRM_URL, settings.RETAIL_CRM_API_KEY)
        res = retailcrm_client.orders(limit=100, page=1, filters={'numbers': ['AM3751']})
        r_orders = res.get_response().get('orders', [])
        for r_order in r_orders:
            print(r_order)
            print(r_order.get('id'))
            order_obj = Order.objects.filter(retailcrm_id=r_order.get('id')).first()

            if order_obj:
                if r_order.get('delivery'):
                    if r_order.get('delivery').get('code'):
                        print(r_order.get('delivery').get('code'))
                        delivery_type_obj = DeliveryType.objects.get(
                            retail_code=r_order.get('delivery').get('code')
                        )
                        order_obj.delivery_type = delivery_type_obj

                payments = r_order.get('payments')
                if payments:
                    payment = r_order.get('payments').get(order_obj.id)
                    if payment:
                        payment_type_obj = PaymentType.objects.get(retail_code=payment.get('type'))
                        order_obj.payment_type = payment_type_obj
                        order_obj.payment_status = (
                            PaymentStatusEnum.PAID
                            if payment.get('status') == 'paid'
                            else PaymentStatusEnum.NOT_PAID
                        )

                custom_fields = r_order.get('customFields')

                if custom_fields.get('coupon'):
                    coupon_obj = Coupon.objects.get(passphrase=custom_fields.get('coupon'))
                    coupon_entry = CouponEntry.objects.get(coupon=coupon_obj, order=order_obj)
                    order_obj.coupon = coupon_obj
                    order_obj.coupon_entry = coupon_entry
