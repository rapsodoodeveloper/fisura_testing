# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShopifyPaymentGatewayEpt(models.Model):
    _inherit = "shopify.payment.gateway.ept"

    is_standard_payment_gateway = fields.Boolean(
        string='Is Standard Payment Gateway?'
    )

    @api.constrains('is_standard_payment_gateway')
    def _check_standard_payment_gateway(self):
        standard_payment = self.search([('is_standard_payment_gateway', '=', True)])
        if standard_payment and len(standard_payment) > 1:
            raise ValidationError(_('A web location already exists.'))
