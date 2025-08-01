import datetime

from django.core.management.base import BaseCommand

from handbooks.enums import PaymentTypeEnum
from snippets.enums import PaymentStatusEnum
from snippets.utils.datetime import utcnow

from ...api.service import update_payment_status
from ...models import Order


class Command(BaseCommand):
    """Обновляем статусы платежей за 24 часа"""

    def handle(self, *args, **options):
        yesterday = utcnow() - datetime.timedelta(days=1)
        payments = Order.objects.filter(
            payment_status=PaymentStatusEnum.NOT_PAID,
            payment_type__payment_method__in=PaymentTypeEnum.online_types,
            created__gte=yesterday,
            payment_gateway_order_id__isnull=False
        )

        print('Check payment status total: %s' % payments.count())
        for payment in payments.iterator():
            payment = update_payment_status(payment)

            if payment.payment_status == PaymentStatusEnum.PAID:
                print('PAID %s' % payment)
            else:
                print('Not paid %s' % payment)
