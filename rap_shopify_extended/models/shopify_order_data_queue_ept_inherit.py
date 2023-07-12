# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import time
import logging
from datetime import timedelta
from odoo import models, fields, api

_logger = logging.getLogger("Shopify Order Queue")


class ShopifyOrderDataQueueEpt(models.Model):
    _inherit = "shopify.order.data.queue.ept"

    def shopify_create_order_data_queues(self, instance, from_date, to_date, created_by="import",
                                         order_type="unshipped"):
        """
        Inherit to change last order import date to 2 hours early.
        This method used to create order data queues.
        @param : self, instance,  from_date, to_date, created_by, order_type
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 06/11/2019.
        Task Id : 157350
        @change: Maulik Barad on Date 10-Sep-2020.
        """
        order_data_queue_line_obj = self.env["shopify.order.data.queue.line.ept"]
        start = time.time()
        order_queues = []
        instance.connect_in_shopify()
        if order_type != "shipped":
            queue_type = 'unshipped'
            for order_status_id in instance.shopify_order_status_ids:
                order_status = order_status_id.status
                order_ids = self.shopify_order_request(instance, from_date, to_date, order_status)

                if order_ids:
                    order_queues = order_data_queue_line_obj.create_order_data_queue_line(order_ids,
                                                                                          instance,
                                                                                          queue_type,
                                                                                          created_by)
                    if len(order_ids) >= 250:
                        order_queue_list = self.list_all_orders(order_ids, instance, created_by, queue_type)
                        order_queues += order_queue_list
                instance.last_date_order_import = to_date - timedelta(hours=2)
        else:
            order_queues = self.shopify_shipped_order_request(instance, from_date, to_date, created_by="import",
                                                              order_type="shipped")
            instance.last_shipped_order_import_date = to_date - timedelta(hours=2)
        end = time.time()
        _logger.info("Imported Orders in %s seconds.", str(end - start))
        return order_queues
