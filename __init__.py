from collections import OrderedDict


default_app_config = 'orders.apps.AppConfig'

ADDRESS_MAPPING = OrderedDict((
    ('locality', ''),
    ('postcode', ''),
    ('street', ''),
    ('building', ''),
    ('apartment', '')
))
