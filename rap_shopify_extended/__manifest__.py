# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    'name': "Shopify Extended",
    'summary': 'Changes in Shopify-Odoo Connector',
    'author': "Rapsodoo Iberia",
    'website': "https://www.rapsodoo.com/es/",
    'category': 'Uncategorized',
    'license': 'LGPL-3',
    'version': '15.0.1.2.29',

    'depends': [
        'base',
        'shopify_ept',
        'product',
        'raps_bimani_purchase'
    ],
    'data': [
        'data/res_partner_default.xml',
        'data/crons.xml',
        'security/ir.model.access.csv',
        'views/account_payment.xml',
        'views/product_template_view.xml',
        'views/shopify_product_template_view.xml',
        'views/sale_order_inherit_view.xml',
        'views/product_attribute_inherit.xml',
        'views/account_move_inherit.xml',
        'views/stock_picking_inherit.xml',
        'views/shopify_location_inherit.xml',
        'views/shopify_odoo_location.xml',
        'views/stock_location_inherit.xml',
        'views/process_import_export_inherit.xml',
        'views/shopify_payment_gateway_inherit.xml',
        'views/shopify_customer_account.xml',
        'views/order_data_queue_inherit.xml'
    ],
    'post_init_hook': 'parameter_config',
    'application': False,
}
