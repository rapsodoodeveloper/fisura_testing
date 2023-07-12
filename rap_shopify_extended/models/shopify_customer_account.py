# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShopifyCustomerAccount(models.Model):
    _name = 'shopify.customer.account'
    _description = 'Customer account related to the payment method'

    instance_id = fields.Many2one(
        comodel_name='shopify.instance.ept',
        string='Instance')
    payment_gateway_id = fields.Many2one(
        comodel_name='shopify.payment.gateway.ept',
        string='Payment Gateway')
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account')

    @api.constrains('payment_gateway_id')
    def _check_account(self):
        for rec in self:
            account = self.search(
                [('payment_gateway_id', '=', rec.payment_gateway_id.id),
                 ('id', '!=', rec.id)])
            if account:
                raise ValidationError(_('Already exists a customer account for this payment method.'))
