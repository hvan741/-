import datetime
import math
from time import sleep

import retailcrm
from django.conf import settings
from django.core.management.base import BaseCommand

from handbooks.api.service import get_order_statuses_codes

from ...api import service
from ...models import Order


class Command(BaseCommand):
    """Обновляем статусы платежей за 24 часа"""

    def handle(self, *args, **options):
        from_dt = datetime.date.today() - datetime.timedelta(days=183)

        orders = Order.objects\
            .filter(retailcrm_id__isnull=False, created__gte=from_dt, status__is_stop=False)\
            .values_list('retailcrm_id', flat=True)

        retailcrm_client = retailcrm.v5(settings.RETAIL_CRM_URL, settings.RETAIL_CRM_API_KEY)
        statuses_codes = get_order_statuses_codes()

        count = orders.count()
        limit = 490
        print(f'Checking order statuses from retailcrm: {count}')
        for page in range(math.ceil(count / limit)):
            orders_batch = orders[page * limit:(page + 1) * limit]

            service.check_order_statuses_from_retailcrm(
                orders_batch, retailcrm_client=retailcrm_client, statuses_codes=statuses_codes
            )
            sleep(.1)
