# -*- coding: utf-8 -*-
# Part of Aselcis. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from odoo.tools import float_compare

class ResPartner(models.Model):
    _inherit = 'res.partner'

    cyc = fields.Selection([('yes', 'YES'), ('no', 'NO'), 
                            ('anonymous', 'ANONYMOUS'),('public organisms','Public Organisms'),
                            ('linked_businesses','Linked Businesses'),('individuals','Individuals'),
                            ('countries_without_coverage','Countries without coverage')],)
    credit_granted = fields.Float(string='Credit granted')
