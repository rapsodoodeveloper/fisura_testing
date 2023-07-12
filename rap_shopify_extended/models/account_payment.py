# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountPayment(models.Model):
    _name = 'shopify.account.payment'
    _description = 'Account related to payment method and location'

    instance_id = fields.Many2one(
        comodel_name='shopify.instance.ept',
        string='Instance')
    payment_gateway_id = fields.Many2one(
        comodel_name='shopify.payment.gateway.ept',
        string='Payment Gateway')
    shopify_location_id = fields.Many2one(
        comodel_name='shopify.location.ept',
        string='Shopify Location')
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account')

    @api.constrains('payment_gateway_id', 'shopify_location_id', 'account_id')
    def _check_name(self):
        for rec in self:
            account_payment_gateway = self.search(
                [('shopify_location_id', '=', rec.shopify_location_id.id),
                 ('payment_gateway_id', '=', rec.payment_gateway_id.id),
                 ('id', '!=', rec.id)])
            if account_payment_gateway:
                raise ValidationError(_('Already exists an account for this Location.'))
