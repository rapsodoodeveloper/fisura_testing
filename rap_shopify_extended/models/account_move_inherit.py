# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    shopify_location_id = fields.Many2one(
        string='Shopify Location',
        comodel_name='shopify.location.ept',
        compute='_compute_shopify_fields',
        store=True
    )
    shopify_payment_gateway_id = fields.Many2one(
        string='Shopify Payment Gateway',
        comodel_name='shopify.payment.gateway.ept',
        compute='_compute_shopify_fields',
        store=True
    )

    @api.depends('invoice_origin')
    def _compute_shopify_fields(self):
        sale_order_obj = self.env['sale.order']
        for rec in self:
            location = False
            payment_gateway = False
            if rec.invoice_origin:
                sale = sale_order_obj.search([('name', '=', rec.invoice_origin)])
                location = sale.shopify_location_id
                payment_gateway = sale.shopify_payment_gateway_id
            rec.update({'shopify_location_id': location, 'shopify_payment_gateway_id': payment_gateway})
