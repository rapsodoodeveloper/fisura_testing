# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    'name': "Bimani Purchase",
    'summary': 'Changes to be consider in Bimani Odoo enviroment',
    'author': "Rapsodoo Iberia",
    'website': "https://www.rapsodoo.com/es/",
    'category': 'Inventory/Purchase',
    'license': 'LGPL-3',
    'version': '15.0.1.1.2',

    'depends': [
        'stock',
        'purchase',
        'purchase_location_by_line'
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/views_inherit.xml',
    ],
    'application': False,
}
