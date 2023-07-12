# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class ShopifyInstanceEpt(models.Model):
    _inherit = 'shopify.instance.ept'

    account_payment_ids = fields.One2many(
        comodel_name='shopify.account.payment',
        inverse_name='instance_id',
        string='Account Payment')
    customer_account_payment_ids = fields.One2many(
        comodel_name='shopify.customer.account',
        inverse_name='instance_id',
        string='Customer Account')
    shopify_odoo_loc_ids = fields.One2many(
        comodel_name='shopify.odoo.location',
        inverse_name='instance_id',
        string='Shopify/Odoo Location mapping')
