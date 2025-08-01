from time import sleep

import retailcrm
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from snippets.utils.email import send_trigger_email

from ...api import service
from ...models import Order


class Command(BaseCommand):
    """Обновляем статусы платежей за 24 часа"""

    def handle(self, *args, **options):
        orders = Order.objects.filter(
            retailcrm_id__isnull=True
        ).exclude(
            Q(order_number__startswith='m') |
            Q(order_number__startswith='t')
        )
        # .filter(
        #     Q(
        #         Q(payment_status=PaymentStatusEnum.PAID)
        #         & Q(payment_type__payment_method__in=PaymentTypeEnum.online_types)
        #     )
        #     | ~Q(payment_type__payment_method__in=PaymentTypeEnum.online_types)
        # )

        retailcrm_client = retailcrm.v5(settings.RETAIL_CRM_URL, settings.RETAIL_CRM_API_KEY)

        print('Uploading orders to retailcrm: %s' % orders.count())
        for order in orders.iterator():
            first_send = not bool(order.retail_crm_log)
            result = service.upload_order_to_retailcrm(
                order, retailcrm_client=retailcrm_client
            )

            if not result and first_send:
                send_trigger_email(
                    f'Не удалось отправить заказ №{order.order_number} '
                    f'в RetailCRM',
                    obj=order,
                    fields=order.fast_order_email_fields,
                )
            sleep(.05)
