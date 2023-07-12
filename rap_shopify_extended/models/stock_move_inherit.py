# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class StockMove(models.Model):
    _inherit = "stock.move"

    shopify_refund_id = fields.Char(
        string='Shopify Refund',
        help='Credit Card Company')


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    adjust_in_shopify = fields.Boolean(
        string='Adjusted in Shopify?',
    )
    stock_upd_option = fields.Selection(
        string='Stock Shopify UPD',
        selection=[('int', 'Internal'), ('recep', 'Reception'), ('no', 'Not apply')],
        compute='_compute_update_option_stock',
        store=True
    )
    sent_shopify_count = fields.Integer(
        string='Sended count',
        default=0
    )

    @api.depends('reference', 'move_id', 'move_id.location_dest_id',
                 'move_id.location_dest_id.is_stock', 'move_id.state')
    def _compute_update_option_stock(self):
        for rec in self:
            # No state means this stock_move_line dont have to be updated in shopify
            update_stock = 'no'
            if rec.reference and '/' in rec.reference:
                # Split to identify which type of movement is
                # Could be IN, INT, OUT, RET, Product  qty updated
                prefix = rec.reference.split('/')[1]
                print('TYPE : {}'.format(prefix))
                if prefix == 'IN' and rec.move_id.location_dest_id.is_stock and rec.move_id.state == 'done':
                    update_stock = 'recep'
                if prefix == 'INT' and (rec.move_id.location_dest_id.is_stock or rec.move_id.location_id.is_stock)\
                        and rec.move_id.state == 'done':
                    update_stock = 'int'
            rec.stock_upd_option = update_stock
