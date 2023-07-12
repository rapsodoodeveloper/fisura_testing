# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class ProductAttribute(models.Model):
    _inherit = 'product.attribute'

    is_color = fields.Boolean(
        string='Is color'
    )
