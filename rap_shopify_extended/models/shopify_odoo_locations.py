# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _


class ShopifyOdooLocations(models.Model):
    _name = 'shopify.odoo.location'
    _description = 'Relate Odoo locations with shopify locations'

    location_id = fields.Many2one(
        string='Odoo Location',
        comodel_name='stock.location',
        domain="[('is_stock', '=',True)]"
    )
    shopify_location_id = fields.Many2one(
        string='Shopify Location',
        comodel_name='shopify.location.ept'
    )
    instance_id = fields.Many2one(
        string='Instance',
        comodel_name='shopify.instance.ept'
    )

