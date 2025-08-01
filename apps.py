from django.apps import AppConfig as BaseAppConfig


class AppConfig(BaseAppConfig):
    name = 'orders'
    verbose_name = 'Заказы'
