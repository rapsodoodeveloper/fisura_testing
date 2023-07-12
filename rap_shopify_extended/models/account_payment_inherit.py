# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    shopify_location_id = fields.Many2one(
        string='Shopify Location',
        comodel_name='shopify.location.ept',
        compute='_compute_location',
        store=True
    )

    @api.depends('ref')
    def _compute_location(self):
        account_move_env = self.env['account.move']
        for rec in self:
            location = False
            if rec.ref:
                move = account_move_env.search([('name', '=', rec.ref)])
                location = move.shopify_location_id
            rec.shopify_location_id = location
