from django.urls import path, include
from rest_framework.routers import DefaultRouter

from orders.api import views

app_name = 'orders'

router = DefaultRouter()
router.register(r'', views.OrderHistoryView, basename='order_history')


urlpatterns = (
    path(
        '',
        views.OrderView.as_view(),
        name='order'
    ),
    path(
        'apply-coupon/',
        views.OrderApplyCouponView.as_view(),
        name='order_apply_coupon'
    ),
    path(
        'calc-price/',
        views.OrderCalcPriceView.as_view(),
        name='order_calc_price'
    ),
    path(
        'fast/',
        views.OrderFastView.as_view(),
        name='order_fast'
    ),
    path(
        'history/',
        include(router.urls)
    ),
)
