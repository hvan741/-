# Generated by Django 4.2.4 on 2023-09-25 13:37

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('handbooks', '0006_pickpointmaxboxsize_pickuppointoperator_and_more'),
        ('orders', '0005_orderitem_card_orderitem_size'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='delivery_point',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='handbooks.selfdeliverypoint', verbose_name='Пункт доставки'),
        ),
    ]
