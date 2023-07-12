# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class StockLocation(models.Model):
    _inherit = 'stock.location'

    is_default_return = fields.Boolean(
        string='Is a Default Return Location?'
    )
