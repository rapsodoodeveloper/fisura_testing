# Copyright 2023-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class ShopifyQueueProcess(models.TransientModel):
    _inherit = 'shopify.queue.process.ept'

    def process_order_queue_manually(self):
        """
        Overwrite the standard method to add a parameter to the search
        """
        model = self._context.get('active_model')
        shopify_order_queue_line_obj = self.env["shopify.order.data.queue.line.ept"]
        order_queue_ids = self._context.get('active_ids')
        if model == "shopify.order.data.queue.line.ept":
            order_queue_ids = shopify_order_queue_line_obj.search([('id', 'in', order_queue_ids)]).mapped(
                "shopify_order_data_queue_id").ids
        self.env.cr.execute(
            """update shopify_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for order_queue_id in order_queue_ids:
            order_queue_line_batch = shopify_order_queue_line_obj.search(
                [("shopify_order_data_queue_id", "=", order_queue_id),
                 ("state", "in", ('draft', 'failed')),
                 ('ignore_rec', '=', False)])
            order_queue_line_batch.process_import_order_queue_data()
        return True
