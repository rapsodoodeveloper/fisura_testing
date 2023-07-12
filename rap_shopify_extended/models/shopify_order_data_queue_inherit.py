# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import logging
from odoo import models, fields

_logger = logging.getLogger("Shopify Order Queue Line")


class ShopifyOrderDataQueueLineEpt(models.Model):
    _inherit = "shopify.order.data.queue.line.ept"

    ignore_rec = fields.Boolean(
        string='Ignore'
    )

    def get_queue_data_failed_orders(self):
        """
        This method is used to find order queue which queue lines have state in Failed and is_action_require is False.
        If cronjob has tried more than 3 times to process any queue then it marks that queue has need process
        to manually.
        @Return: List of Order queue with queue_lines in failed status
        """
        order_queue_ids = []
        self.env.cr.execute(
            """update shopify_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()

        # Query to get the Queue with lines in draft/failed status
        query = """select queue.id
                   from shopify_order_data_queue_line_ept as queue_line
                   inner join shopify_order_data_queue_ept as queue on queue_line.shopify_order_data_queue_id = queue.id
                   where queue_line.state='failed' or queue_line.state='draft'
                   ORDER BY queue_line.create_date desc"""
        self._cr.execute(query)
        order_queue_list = self._cr.fetchall()
        if not order_queue_list:
            return False
        # Put in a list all the Queue Ids to be returned
        for result in order_queue_list:
            if result[0] not in order_queue_ids:
                order_queue_ids.append(result[0])
        return order_queue_ids

    def auto_import_queue_data_failed_orders(self):
        """
        Function to force the execution of the Failed Orders Proccess
        Function called by a Cron, the function avoid the exceptions and proccess only the rigth queue_lines
        """
        shopify_order_queue_line_obj = self.env["shopify.order.data.queue.line.ept"]
        order_queue_ids = self.get_queue_data_failed_orders()
        if order_queue_ids:
            self.env.cr.execute(
                """update shopify_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
            self._cr.commit()
            for order_queue_id in order_queue_ids:
                # For each line in draft or failed status
                # Should be executed another try to proccess
                order_queue_line_batch = shopify_order_queue_line_obj.search(
                    [("shopify_order_data_queue_id", "=", order_queue_id),
                     ("state", "in", ('draft', 'failed'))])
                try:
                    order_queue_line_batch.process_import_order_queue_data()
                except Exception:
                    # Ignore the exception to avoid queue blocks
                    continue
        return True

    def process_import_order_queue_data(self, update_order=False):
        """Inherit this function to execute the update_shopify_order always.
            This method processes order queue lines.
            :param update_order: It is used for webhook. While we receive update order webhook response and it
            creates a queue and when auto cron job processing at that time it checks to need to update values in
            existing order if updte_order is True then it will perform opration as received response of order,
            If the update order is False then it will continue order and queue mark as done.
            @author: Haresh Mori @Emipro Technologies Pvt.Ltd on date 07/10/2019.
            Task Id : 157350
        """
        sale_order_obj = self.env["sale.order"]
        common_log_obj = self.env["common.log.book.ept"]

        queue_id = self.shopify_order_data_queue_id if len(self.shopify_order_data_queue_id) == 1 else False
        if queue_id:
            instance = queue_id.shopify_instance_id
            if not instance.active:
                _logger.info("Instance %s is not active.", instance.name)
                return True

            if queue_id.shopify_order_common_log_book_id:
                log_book_id = queue_id.shopify_order_common_log_book_id
            else:
                model_id = common_log_obj.log_lines.get_model_id("sale.order")
                log_book_id = common_log_obj.shopify_create_common_log_book("import", instance, model_id)

            queue_id.is_process_queue = True
            created_by = queue_id.created_by
            sale_order_obj.update_shopify_order(self, log_book_id, created_by)
            queue_id.write({'is_process_queue': False, 'shopify_order_common_log_book_id': log_book_id})
            if log_book_id and not log_book_id.log_lines:
                log_book_id.unlink()

            if instance.is_shopify_create_schedule:
                queue_id.create_schedule_activity(queue_id)
