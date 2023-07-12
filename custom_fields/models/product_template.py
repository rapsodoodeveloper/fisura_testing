# -*- coding: utf-8 -*-
# Part of Aselcis. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from odoo.tools import float_compare

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    eol = fields.Boolean(string='EOL')
    edp = fields.Boolean(string='EDP')
