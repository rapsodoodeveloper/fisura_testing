# -*- coding: utf-8 -*-
# Part of Aselcis. See LICENSE file for full copyright and licensing details.

{
    'name': 'Tecnocode importador pedidos Fisura',
    'version': '1.0',
    "author": "Aselcis Consulting S.L",
    "website": "https://www.aselcis.com",
    'category': 'Sales',
    'depends': ['base', 'product', 'sale_management', 'stock'],
    'description': """
Importador de pedidos de venta para Fisura
    """,
    'data': [
        'security/ir.model.access.csv',
        'views/eci_pedidos_views.xml',
        'report/order.xml',
        'report/out_stock.xml'
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
