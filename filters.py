from django.contrib import admin
from handbooks.models import OrderStatus


class OrderStatusFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    template = "admin/dropdown_filter.html"
    title = 'Статусы заказов'

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "order_status"

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return [(i.id, i.title) for i in
                OrderStatus.objects.filter(
                    is_active=True, orders__isnull=False).distinct()
                ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())


class OrderRetailCRMFilter(admin.SimpleListFilter):
    title = 'Отправлен в RetailCRM'

    parameter_name = 'sent_to_retailcrm'

    def lookups(self, request, model_admin):
        return [
            ('1', 'Да'),
            ('0', 'Нет')
        ]

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(retailcrm_id__isnull=False)

        if self.value() == '0':
            return queryset.filter(retailcrm_id__isnull=True)

        return queryset
