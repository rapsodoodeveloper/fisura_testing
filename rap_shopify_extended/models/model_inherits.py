# Copyright 2023-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class OrderLine(models.Model):
    _inherit = 'sale.order.line'

    origin_line = fields.Char(
        string='Original Line'
    )


class StockMove(models.Model):
    _inherit = 'stock.move'

    qty_by_origin = fields.Float(
        string='Available Qty',
        compute='_compute_qty_available'
    )

    @api.depends('product_id', 'location_id')
    def _compute_qty_available(self):
        quant_env = self.env['stock.quant']
        for rec in self:
            qty = 0.0
            if rec.product_id and rec.location_id:
                quants = quant_env.search([('product_id', '=', rec.product_id.id),
                                           ('location_id', '=', rec.location_id.id)])
                qty = sum(quants.mapped('quantity'))
            rec.qty_by_origin = qty
