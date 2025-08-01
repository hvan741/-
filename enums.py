from collections import OrderedDict

from snippets.models import BaseEnumerate


class ClientThemeEnum(BaseEnumerate):
    """Тема сайта/клиента"""

    DARK = 'dark'
    LIGHT = 'light'

    values = OrderedDict((
        (DARK, 'Тёмная'),
        (LIGHT, 'Светлая')
    ))


class OrderDeliveryStatusEnum(BaseEnumerate):
    """Статус доставки"""

    NEW_DELIVERY = 'new_delivery'
    DELIVERED = 'delivered'

    values = OrderedDict((
        (NEW_DELIVERY, 'Новаяя доставка'),
        (DELIVERED, 'Доставлено')
    ))

    default = NEW_DELIVERY
