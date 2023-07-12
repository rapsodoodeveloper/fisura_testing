# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShopifyLocationEpt(models.Model):
    _inherit = 'shopify.location.ept'

    is_web_location = fields.Boolean(
        string='Is Web Location'
    )
    is_web_return_location = fields.Boolean(
        string='Is Web Return Location'
    )

    @api.constrains('is_web_return_location')
    def _check_return_location(self):
        shopify_location_env = self.search([('is_web_return_location', '=', True)])
        if shopify_location_env and len(shopify_location_env) > 1:
            raise ValidationError(_('A web return location already exists.'))

    @api.constrains('is_web_location')
    def _check_web_location(self):
        shopify_location = self.search([('is_web_location', '=', True)])
        if shopify_location and len(shopify_location) > 1:
            raise ValidationError(_('A web location already exists.'))
