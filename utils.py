from django.db.models.functions import Length


FIRST_ORDER = 110


def generate_order_number():
    from orders.models import Order

    last_order = Order.objects.order_by(Length('order_number').desc(), '-order_number').first()
    last_order_number = int(last_order.order_number) if last_order else FIRST_ORDER

    return f'{last_order_number + 1}'
