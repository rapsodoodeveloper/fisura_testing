# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _
import json
from datetime import datetime
import logging
from odoo.tools import float_compare
from odoo.addons.shopify_ept import shopify

_logger = logging.getLogger("Shopify Order")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def prepare_shopify_customer_and_addresses(self, order_response, pos_order, instance, order_data_line, log_book):
        """
        Inherit the standard method to assign a default user if the sale order doesn't have one.
        """
        partner_env = self.env['res.partner']
        if not order_response.get("customer", {}):
            default_customer = partner_env.search([('name', '=', "Default Bimani POS")])
            if default_customer:
                order_response["email"] = default_customer.email
                order_response["customer"] = {
                    "email": default_customer.email,
                    "first_name": "",
                    "last_name": "",
                    "tags": ""
                }
        res = super(SaleOrder, self).prepare_shopify_customer_and_addresses(order_response, pos_order, instance,
                                                                            order_data_line, log_book)
        return res

    def _create_invoices(self, grouped=False, final=False, date=None):
        """
        Function to assign the account according to the payment gateway and shopify location.
        """
        res = super(SaleOrder, self)._create_invoices(grouped=False, final=False, date=None)
        shopify_location = self.env['shopify.location.ept'].search([('is_web_location', '=', True)])
        location = self.shopify_location_id if self.shopify_location_id else shopify_location
        self.shopify_location_id = location.id
        self.set_account_to_invoice(res, location)
        return res

    def set_account_to_invoice(self, res, location):
        account_payment_env = self.env['shopify.account.payment']
        account_analytic_env = self.env['account.analytic.default']
        account_payment = account_payment_env.search(
            [('instance_id', '=', self.shopify_instance_id.id),
             ('shopify_location_id', '=', location.id),
             ('payment_gateway_id', '=', False)])
        account_payment_gateway = account_payment_env.search(
            [('instance_id', '=', self.shopify_instance_id.id),
             ('shopify_location_id', '=', location.id),
             ('payment_gateway_id', '=', self.shopify_payment_gateway_id.id)])
        if account_payment or account_payment_gateway:
            res.invoice_line_ids.account_id = account_payment_gateway.account_id or account_payment.account_id
        account_analytic_tag = account_analytic_env.search(
            [('account_id', '=', res.invoice_line_ids[0].account_id.id)], limit=1)
        if account_analytic_tag:
            res.invoice_line_ids.analytic_tag_ids = account_analytic_tag.analytic_tag_ids
        # set the analytic tags to the IVA account
        move_line = res.mapped('line_ids').filtered(lambda l: l.account_id.code[:2] == '47')
        if move_line:
            analytic_account = account_analytic_env.search([('account_id', '=', move_line.account_id.id)])
            if analytic_account:
                move_line.analytic_account_id = analytic_account.analytic_id
                move_line.analytic_tag_ids = analytic_account.analytic_tag_ids
        self.update_customer_account(res)

    def update_customer_account(self, res):
        move_line = res.mapped('line_ids').filtered(lambda l: l.account_id.code[:2] == '43')
        if move_line:
            if not self.shopify_payment_ids:
                payment = self.shopify_payment_gateway_id
            else:
                payment = self.env['shopify.payment.gateway.ept'].search([
                    ('shopify_instance_id', '=', self.shopify_instance_id.id),
                    ('is_standard_payment_gateway', '=', True)])
            customer_account = self.env['shopify.customer.account'].search([
                ('instance_id', '=', self.shopify_instance_id.id),
                ('payment_gateway_id', '=', payment.id)])
            if customer_account:
                move_line.account_id = customer_account.account_id
            if res.invoice_line_ids[0].analytic_account_id:
                move_line.analytic_account_id = res.invoice_line_ids[0].analytic_account_id
            if res.invoice_line_ids[0].analytic_tag_ids:
                move_line.analytic_tag_ids = res.invoice_line_ids[0].analytic_tag_ids

    def reconcile_payment_ept(self, payment_id, invoice):
        """
        Inherit the standard function to change the customer account in payment
        """
        account_move_line = invoice.mapped('line_ids').filtered(lambda l: l.account_id.code[:2] == '43')
        line = payment_id.line_ids.filtered(lambda l: l.account_id.code[:2] == '43')
        line.account_id = account_move_line.account_id
        res = super(SaleOrder, self).reconcile_payment_ept(payment_id, invoice)
        return res

    def import_shopify_orders(self, order_data_lines, log_book):
        """
        Inherit the standard function change the behavior when importing shipped orders with refunds.
        :param order_data_lines: Order Data Queue Line.
        :param log_book: Common Log Book.
        :return: Imported orders.
        """
        order_risk_obj = self.env["shopify.order.risk"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        order_ids = []
        commit_count = 0
        instance = log_book.shopify_instance_id

        instance.connect_in_shopify()

        for order_data_line in order_data_lines:
            if commit_count == 5:
                self._cr.commit()
                commit_count = 0
            commit_count += 1
            order_data = order_data_line.order_data
            order_response = json.loads(order_data)

            order_number = order_response.get("order_number")
            shopify_financial_status = order_response.get("financial_status")
            _logger.info("Started processing Shopify order(%s) and order id is(%s)", order_number,
                         order_response.get("id"))

            date_order = self.convert_order_date(order_response)
            if str(instance.import_order_after_date) > date_order:
                message = "Order %s is not imported in Odoo due to configuration mismatch.\n Received order date is " \
                          "%s. \n Please check the order after date in shopify configuration." % (order_number,
                                                                                                  date_order)
                _logger.info(message)
                self.create_shopify_log_line(message, order_data_line, log_book, order_response.get("name"))
                continue

            pos_order = order_response.get("source_name", "") == "pos"
            partner, delivery_address, invoice_address = self.prepare_shopify_customer_and_addresses(
                order_response, pos_order, instance, order_data_line, log_book)
            if not partner:
                continue

            lines = order_response.get("line_items")
            if self.check_mismatch_details(lines, instance, order_number, order_data_line, log_book):
                _logger.info("Mismatch details found in this Shopify Order(%s) and id (%s)", order_number,
                             order_response.get("id"))
                order_data_line.write({"state": "failed", "processed_at": datetime.now()})
                continue

            sale_order = self.shopify_create_order(instance, partner, delivery_address, invoice_address,
                                                   order_data_line, order_response, log_book, lines, order_number)
            if not sale_order:
                message = "Configuration missing in Odoo while importing Shopify Order(%s) and id (%s)" % (
                    order_number, order_response.get("id"))
                _logger.info(message)
                self.create_shopify_log_line(message, order_data_line, log_book, order_response.get("name"))
                continue
            order_ids.append(sale_order.id)

            location_vals = self.set_shopify_location_and_warehouse(order_response, instance, pos_order)
            sale_order.write(location_vals)

            risk_result = shopify.OrderRisk().find(order_id=order_response.get("id"))
            if risk_result:
                order_risk_obj.shopify_create_risk_in_order(risk_result, sale_order)
                risk = sale_order.risk_ids.filtered(lambda x: x.recommendation != "accept")
                if risk:
                    sale_order.is_risky_order = True

            _logger.info("Starting auto workflow process for Odoo order(%s) and Shopify order is (%s)",
                         sale_order.name, order_number)
            message = ""
            try:
                if sale_order.shopify_order_status == "fulfilled":
                    sale_order.auto_workflow_process_id.with_context(
                        log_book_id=log_book.id).shipped_order_workflow_ept(sale_order)
                    if order_data_line and order_data_line.shopify_order_data_queue_id.created_by == "scheduled_action":
                        created_by = 'Scheduled Action'
                    else:
                        created_by = self.env.user.name
                    # Below code add for create partially/fully refund
                    message = self.create_shipped_order_refund(shopify_financial_status, order_response, sale_order,
                                                               created_by)
                elif sale_order.shopify_order_status == "partial":
                    continue
                    # TODO Review this code to be deleted. Bimani dont make Partial but for some reason sometime we get this status
                    # sale_order.process_order_fullfield_qty(order_response)
                    # sale_order.with_context(log_book_id=log_book.id).process_orders_and_invoices_ept()
                    # if order_data_line and order_data_line.shopify_order_data_queue_id.created_by == \
                    #         "scheduled_action":
                    #     created_by = 'Scheduled Action'
                    # else:
                    #     created_by = self.env.user.name
                    # # Below code add for create partially/fully refund
                    # message = self.create_shipped_order_refund(shopify_financial_status, order_response, sale_order,
                    #                                            created_by)
                else:
                    sale_order.with_context(log_book_id=log_book.id).process_orders_and_invoices_ept()
            except Exception as error:
                if order_data_line:
                    order_data_line.write({"state": "failed", "processed_at": datetime.now(),
                                           "sale_order_id": sale_order.id})
                message = "Receive error while process auto invoice workflow, Error is:  (%s)" % (error)
                _logger.info(message)
                self.create_shopify_log_line(message, order_data_line, log_book, order_response.get("name"))
                continue
            _logger.info("Done auto workflow process for Odoo order(%s) and Shopify order is (%s)", sale_order.name,
                         order_number)

            if message:
                model_id = common_log_line_obj.get_model_id(self._name)
                common_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                  order_data_line, log_book)
                order_data_line.write({'state': 'failed', 'processed_at': datetime.now()})
            else:
                order_data_line.write({"state": "done", "processed_at": datetime.now(),
                                       "sale_order_id": sale_order.id})
            _logger.info("Processed the Odoo Order %s process and Shopify Order (%s)", sale_order.name, order_number)
        return order_ids

    def search_existing_shopify_order(self, order_response, instance, order_number):
        shopify_location_obj = self.env["shopify.location.ept"]
        res = super(SaleOrder, self).search_existing_shopify_order(order_response, instance, order_number)
        # When order is fulfilled, check if the location has changed. In case the order location is different, then
        # update the order with the new location
        if res and order_response.get("fulfillments"):
            # Get the location in the fulfillments
            new_location_id = order_response.get("fulfillments")[0].get("location_id")
            shopify_location = False
            if new_location_id:
                # Search the location in shopify
                shopify_location = shopify_location_obj.search(
                    [("shopify_location_id", "=", new_location_id),
                     ("instance_id", "=", instance.id)], limit=1)
            # Get the warehouse for that location
            if shopify_location and shopify_location.warehouse_for_order:
                warehouse_id = shopify_location.warehouse_for_order
            else:
                warehouse_id = instance.shopify_warehouse_id
            # If the warehouse is different of sale warehouse, then update sale warehouse
            if warehouse_id and warehouse_id != res.warehouse_id:
                res.update(
                    {'warehouse_id': warehouse_id.id,
                     'shopify_order_status': order_response.get("fulfillment_status")})
                updated_picking = self.get_picking_to_update(res)
        return res

    def get_picking_to_update(self, res):
        """
            This method will get the Picking to update the Order.
            @param res: Order.
            @return: Updated Picking.
        """
        stock_location_env = self.env["stock.location"]
        # Current picking
        if res.picking_ids:
            picking = res.picking_ids[0]
            # Get the warehouse location for the order
            location_id = stock_location_env.search([("id", "=", res.warehouse_id.lot_stock_id.id)])
            # Search the picking type by order warehouse and sequence code
            picking_type = self.env["stock.picking.type"].search(
                [("warehouse_id", "=", res.warehouse_id.id),
                 ("sequence_code", "=", picking.picking_type_id.sequence_code)])
            for rec in res.picking_ids:
                # Get the name according to picking type
                name = picking_type.sequence_id.next_by_id()
                # To change the picking type, the picking state must be draft
                pick_state = rec.state
                rec.state = 'draft'
                # Update the picking
                rec.update({
                    'location_id': location_id,
                    'picking_type_id': picking_type,
                    'name': name,
                    'state': pick_state})
                rec.move_line_ids.location_id = location_id
            return True
        return False

    def fulfilled_picking_for_shopify(self, pickings):
        """
        Overwrite the function to FIX an error in the original code
        """
        skip_sms = {"skip_sms": True}
        for picking in pickings.filtered(lambda x: x.state not in ['cancel', 'done']):
            if picking.state != "assigned":
                if picking.move_lines.move_orig_ids:
                    completed = self.fulfilled_picking_for_shopify(picking.move_lines.move_orig_ids.picking_id)
                    if not completed:
                        return False
                picking.action_assign()
                # order in shopify
                if picking.sale_id and (
                        picking.sale_id.is_pos_order or picking.sale_id.shopify_order_status == "fulfilled"):
                    for move_id in picking.move_ids_without_package:
                        vals = self.prepare_vals_for_move_line(move_id, picking)
                        picking.move_line_ids.create(vals)
                    picking._action_done()
                    return True
                if picking.state != "assigned":
                    return False
            result = picking.with_context(**skip_sms).button_validate()
            if isinstance(result, dict):
                dict(result.get("context")).update(skip_sms)
                context = result.get("context")  # Merging dictionaries.
                model = result.get("res_model", "")
                # model can be stock.immediate.transfer or stock backorder.confirmation
                if model:
                    record = self.env[model].with_context(context).create({})
                    record.process()
            if picking.state == "done":
                picking.message_post(body=_("Picking is done by Webhook as Order is fulfilled in Shopify."))
                pickings.updated_in_shopify = True
                return result
        return True

    def create_shopify_refund(self, refunds_data, total_refund, created_by=""):
        """
        Overwrite the Standard function to make fixes in the behavior:
            * Consider could be more than one refund Item
        """
        is_full_refund = True if float_compare(self.amount_total, total_refund, precision_digits=2) == 0 else False
        if not self.invoice_ids:
            return [0]
        invoices = self.invoice_ids.filtered(lambda x: x.move_type == "out_invoice")
        refunds = self.invoice_ids.filtered(lambda x: x.move_type == "out_refund")
        exist_refund = str(refunds_data[0].get('id')) in refunds.mapped('shopify_refund_id')
        if not exist_refund:
            # create a new credit note for the total amount
            self.create_credit_note(invoices, refunds_data, created_by)
            return [True]
        for invoice in invoices:
            if not invoice.state == "posted":
                return [2]
        return [4]

    def create_credit_note(self, invoices, refunds_data, created_by):
        """"
        Function to create a Reversal move when a refund is created
            @param refunds_data: Data of refunds.
            @param total_refund: Total refund amount.
            @param created_by: created by refund.
        """
        refund_date = self.convert_order_date(refunds_data[0])
        move_reversal = self.env["account.move.reversal"].with_context({"active_model": "account.move",
                                                                        "active_ids": invoices[0].ids}).create({
            "refund_method": "refund",
            "date": refund_date,
            "reason": "Refunded from shopify" if len(refunds_data) > 1 else refunds_data[0].get("note"),
            "journal_id": invoices[0].journal_id.id})
        move_reversal.reverse_moves()
        move_reversal.new_move_ids.message_post(body=_("Credit note generated by %s as Order refunded in "
                                                       "Shopify.", created_by))
        move_reversal.new_move_ids.write(
            {"is_refund_in_shopify": True, "shopify_refund_id": refunds_data[0].get('id')})
        shopify_location = self.shopify_location_id.shopify_location_id
        len_refund = len(refunds_data)
        if len_refund and refunds_data[len_refund - 1].get('refund_line_items'):
            # check if the refund has location to restock
            shopify_location = refunds_data[len_refund - 1].get('refund_line_items')[0].get('location_id')
        # check if the return location is different from the order location
        if shopify_location and str(shopify_location) != self.shopify_location_id.shopify_location_id:
            # search the return location
            location = self.env['shopify.location.ept'].search([('shopify_location_id', '=', shopify_location)])
            # set the invoice account according to the return location
            self.set_account_to_invoice(move_reversal.new_move_ids, location)
        move_reversal.new_move_ids.action_post()
        self.paid_credit_note(move_reversal.new_move_ids)
        return move_reversal

    @api.model
    def update_shopify_order(self, queue_lines, log_book, created_by):
        """
        Overwrite the function to make some fixes:
            * If refunded should consider if already exist others refund to get the rigth qty amount
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        picking_obj = self.env['stock.picking']
        orders = self
        for queue_line in queue_lines:
            message = ""
            shopify_instance = queue_line.shopify_instance_id
            order_data = json.loads(queue_line.order_data)
            shopify_status = order_data.get("financial_status")
            order = self.search_existing_shopify_order(order_data, shopify_instance, order_data.get("order_number"))
            if not order:
                created_order = self.import_shopify_orders(queue_line, log_book)
                # if len(created_order) is 0 it means that the order cannot be created
                if len(created_order) == 0:
                    continue
                order = self.browse(created_order)
            # check if the order data has new fulfillment items to create new sale order lines
            order.check_sale_order_line(order_data)
            # Below condition use for, In shopify store there is full refund.
            if order_data.get('cancel_reason'):
                cancelled = order.cancel_shopify_order()
                if not cancelled:
                    message = "System can not cancel the order {0} as one of the Delivery Order " \
                              "related to it is in the 'Done' status.".format(order.name)

            # Below condition use for, In shopify store there is fulfilled order.
            elif order_data.get('fulfillment_status') == 'fulfilled':
                fulfilled = order.fulfilled_shopify_order()
                # Update shopify_order_status if the order is fulfilled
                if fulfilled:
                    picking = picking_obj.search([('state', '=', 'done'),
                                                  ('origin', '=', order.name)])
                    if picking:
                        order.shopify_order_status = order_data.get('fulfillment_status')
                if isinstance(fulfilled, bool) and not fulfilled:
                    message = "There is not enough stock to complete Delivery for order [" \
                              "%s]" % order_data.get('name')
                elif not fulfilled:
                    message = "There is not enough stock to complete Delivery for order [" \
                              "%s]" % order_data.get('name')
            if shopify_status == "refunded" and len(order_data.get('refunds')) == 1:
                # If its refunded
                # Should consider if the are more refunds to get the right qty
                if not message:
                    total_refund = 0.0
                    for refund in order_data.get('refunds'):
                        for transaction in refund.get('transactions'):
                            if transaction.get('kind') == 'refund' and transaction.get('status') == 'success':
                                total_refund += float(transaction.get('amount'))
                    refunded = order.create_shopify_refund(order_data.get("refunds"), total_refund, created_by)
                    if refunded[0] is True and not order_data.get('cancel_reason'):
                        new_picking, picking_type = order.create_picking_return(order_data.get("refunds"))
                    if refunded[0] == 0:
                        message = "- Refund can only be generated if it's related order " \
                                  "invoice is found.\n- For order [%s], system could not find the " \
                                  "related order invoice. " % (order_data.get('name'))
                    elif refunded[0] == 2:
                        message = "- Refund can only be generated if it's related order " \
                                  "invoice is in 'Post' status.\n- For order [%s], system found " \
                                  "related invoice but it is not in 'Post' status." % (
                                      order_data.get('name'))
                    elif refunded[0] == 3:
                        message = "- Partial refund is received from Shopify for order [%s].\n " \
                                  "- System do not process partial refunds.\n" \
                                  "- Either create partial refund manually in Odoo or do full " \
                                  "refund in Shopify." % (order_data.get('name'))
            if shopify_status == "refunded" and len(order_data.get('refunds')) > 1:
                # If is "refunded" and there are more than one refunds
                # Means will be a normal partial refund
                message = order.create_shopify_partially_refund(order_data.get("refunds"), order_data.get('name'),
                                                                created_by)
            elif shopify_status == "partially_refunded" and order_data.get("refunds"):
                # If its "partially_refunded"
                # Should be created a new partial refund
                message = order.create_shopify_partially_refund(order_data.get("refunds"), order_data.get('name'),
                                                                created_by)
            if shopify_status == "paid" and len(order_data.get('refunds')) >= 1 and order_data.get("gateway") != "Aplazame":
                shopify_location = order_data.get('refunds')[0].get('refund_line_items')[0].get('location_id')
                web_location = False
                if shopify_location:
                    web_location = self.env['shopify.location.ept'].search([
                        ('shopify_location_id', '=', shopify_location),
                        ('is_web_return_location', '=', True)])
                    # if location is True, means that is a web change
                if web_location:
                    new_picking, picking_type = order.create_picking_return(order_data.get("refunds"))
                else:
                    message = order.create_shopify_partially_refund(order_data.get("refunds"), order_data.get('name'),
                                                                    created_by)
            self.prepare_vals_shopify_multi_payment_refund(order_data.get("refunds"), order)
            if message:
                model_id = common_log_line_obj.get_model_id(self._name)
                common_log_line_obj.shopify_create_order_log_line(message, model_id,
                                                                  queue_line, log_book)
                queue_line.write({'state': 'failed', 'processed_at': datetime.now()})
            else:
                queue_line.state = "done"
        return orders

    def check_sale_order_line(self, order_data):
        """
        Function to check if the order has been modified with new fulfillment lines. In that case, it is necessary to
        create and add new lines to the order.
        :param order_data: Order data from Shopify
        """
        order_line_env = self.env['sale.order.line']
        fulfillments = order_data.get('fulfillments')
        instance = self.shopify_instance_id
        new_lines = []
        location = self.shopify_location_id
        fulfillments_date = fields.Date.today()
        for fulfill in fulfillments:
            for item in fulfill.get('line_items'):
                # search if a fulfillment line exists in the sale order
                line = order_line_env.search([('order_id', '=', self.id),
                                              ('shopify_line_id', '=', item.get('id'))])
                # if the line item do not exist in the order then we need to create the sale_order_line
                if not line:
                    fulfillments_date = self.convert_order_date(fulfill)
                    if len(order_data.get('payment_gateway_names')) > 1:
                        payment_vals = self.prepare_order_multi_payment(order_data)
                        if payment_vals:
                            self.update({'shopify_payment_ids': payment_vals, 'is_shopify_multi_payment': True})
                    if str(fulfill.get('location_id')) != self.shopify_location_id.shopify_location_id:
                        shopify_location = fulfill.get('location_id')
                        location = self.env['shopify.location.ept'].search(
                            [('shopify_location_id', '=', shopify_location)])
                        self.warehouse_id = location.warehouse_for_order
                    # create the sale order line
                    new_lines = self.create_shopify_order_lines(fulfill.get('line_items'), order_data, instance)
        # check if there is new order lines
        if len(new_lines) > 0:
            # if there is new sale order lines it is necessary to confirm the order again
            self.action_confirm()
            # create and validate the invoice for the new lines
            self.generate_invoice(new_lines, location, fulfillments_date)

    def generate_invoice(self, order_line_list, location, fulfillments_date):
        """
        Function to create and validate the invoice for the new lines
        :param order_line_list: list of new lines
        """
        # search the journal for sales
        journal_id = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        # prepare the value dictionary to create the invoice
        vals = {
            'ref': self.client_order_ref or '',
            'move_type': 'out_invoice',
            'invoice_origin': self.name,
            'partner_id': self.partner_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'fiscal_position_id': self.partner_id.property_account_position_id and
                                  self.partner_id.property_account_position_id.id or False,
            'company_id': self.company_id.id,
            'invoice_user_id': self.user_id.id,
            'journal_id': journal_id.id,
            'currency_id': self.currency_id.id,
            'team_id': self.team_id.id,
            'invoice_line_ids': [],
            'date': fulfillments_date,
            'invoice_date': fulfillments_date
        }
        # add the invoice lines according to the order line list
        for rec in order_line_list:
            fpos = vals['fiscal_position_id']
            account = False
            accounts = rec.product_id.product_tmpl_id.get_product_accounts(fpos)
            account = accounts['income']
            vals['invoice_line_ids'].append((0, 0,
                                             {'product_id': rec.product_id.id,
                                              'quantity': rec.product_uom_qty,
                                              'analytic_account_id': self.analytic_account_id.id if self.analytic_account_id else False,
                                              'price_unit': rec.price_unit,
                                              'account_id': account.id,
                                              'company_id': self.company_id.id,
                                              'name': rec.product_id.partner_ref,
                                              'product_uom_id': rec.product_uom and rec.product_uom.id or rec.product_id.uom_id.id,
                                              'sale_line_ids': [(6, 0, [rec.id])],
                                              'tax_ids': rec.tax_id,
                                              }))
        # create the invoice
        invoice_obj = self.env['account.move'].create(vals)
        # call method to set the account to the invoice
        self.set_account_to_invoice(invoice_obj, location)
        # validate the new invoice
        invoice_obj.action_post()
        # create and validate the payment for the invoice
        if self.auto_workflow_process_id.register_payment:
            self.paid_invoice_ept(invoice_obj)

    def _prepare_invoice(self):
        """
        Inherit
        This method would let the invoice date will be the same as the order date and also set the sale journal.
        Migration done by Haresh Mori on September 2021
        """
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.auto_workflow_process_id:
            if self.auto_workflow_process_id.invoice_date_is_order_date:
                invoice_vals.update({"invoice_date": self.date_order.date()})
        return invoice_vals

    def create_shopify_partially_refund(self, refunds_data, order_name, created_by=""):
        """
        Overwrite the function to Post the New Move and generate the Posted Payment
        """
        account_move_obj = self.env['account.move']
        stock_move_env = self.env['stock.move']
        message = False
        location = self.shopify_location_id
        if not self.invoice_ids:
            message = "- Partially refund can only be generated if it's related order " \
                      "invoice is found.\n- For order [%s], system could not find the " \
                      "related order invoice. " % order_name
            return message
        invoices = self.invoice_ids.filtered(lambda x: x.move_type == "out_invoice")
        for invoice in invoices:
            if not invoice.state == "posted":
                message = "- Partially refund can only be generated if it's related order " \
                          "invoice is in 'Post' status.\n- For order [%s], system found " \
                          "related invoice but it is not in 'Post' status." % order_name
                return message
        for refund_data_line in refunds_data:
            existing_refund = account_move_obj.search([("shopify_refund_id", "=", refund_data_line.get('id')),
                                                       ("shopify_instance_id", "=", self.shopify_instance_id.id)])
            refunded_move = stock_move_env.search([('shopify_refund_id', '=', str(refund_data_line.get('id')))])
            if existing_refund or refunded_move:
                continue
            if refund_data_line.get('refund_line_items'):
                new_moves = self.with_context(check_move_validity=False).create_move_and_delete_not_necessary_line(
                    refund_data_line, invoices, created_by)
                count = 0
                for new_move in new_moves:
                    if refund_data_line.get('order_adjustments') and count == 0:
                        self.create_refund_adjustment_line(refund_data_line.get('order_adjustments'), new_move,
                                                           refund_data_line)
                        count += 1
                    new_move.with_context(check_move_validity=False)._recompute_tax_lines()
                    new_move.with_context(check_move_validity=False)._recompute_dynamic_lines()
                    shopify_location = refund_data_line.get('refund_line_items')[0].get('location_id')
                    # check if the return location is different from the order location
                    if shopify_location:
                        dev_location = self.env['shopify.location.ept'].search(
                            [('shopify_location_id', '=', shopify_location),
                             ('is_web_return_location', '=', True)])
                        # if return location is Almacen Devoluciones, the credit note location should not change
                        if not dev_location and str(shopify_location) != self.shopify_location_id.shopify_location_id:
                            # search the return location
                            location = self.env['shopify.location.ept'].search([
                                ('shopify_location_id', '=', shopify_location)])
                    # set the invoice account according to the return location
                    self.set_account_to_invoice(new_move, location)
                    new_move.action_post()
                    self.paid_credit_note(new_move)
            else:
                # if refund_data_line do not have line items is a return from the changed order
                if refund_data_line.get('order_adjustments'):
                    # create a new credit note from order_adjustments value
                    self.create_reversal_adjustment_line(refund_data_line, refunds_data, invoices, location, created_by)
        new_picking, picking_type = self.create_picking_return(refunds_data)
        return message

    def create_reversal_adjustment_line(self, refund_data_line, refunds_data, invoices, location, created_by):
        """
        This method is used to create a reverse move for refund without lines (return from changed order).
        """
        refund_date = self.convert_order_date(refund_data_line)
        move_reversal = self.env["account.move.reversal"].with_context(
            {"active_model": "account.move", "active_ids": invoices[0].ids}, check_move_validity=False).create(
            {"refund_method": "refund",
             "reason": "Partially Refunded from shopify" if len(refunds_data) > 1 else refund_data_line.get("note"),
             "journal_id": invoices[0].journal_id.id, "date": refund_date})
        move_reversal.reverse_moves()
        new_move = move_reversal.new_move_ids
        new_move.write({'is_refund_in_shopify': True, 'shopify_refund_id': refund_data_line.get('id')})
        new_move.invoice_line_ids.with_context(check_move_validity=False).unlink()
        # add the invoice line with the default product for adjustment
        move_line = self.create_refund_adjustment_line(refund_data_line.get('order_adjustments'), new_move,
                                                       refund_data_line)
        new_move.message_post(body=_("Credit note generated by %s as Order partially "
                                     "refunded in Shopify. This credit note has been created from "
                                     "<a href=# data-oe-model=sale.order data-oe-id=%d>%s</a>") % (
                                       created_by, self.id, self.name))
        self.message_post(body=_(
            "Partially credit note created <a href=# data-oe-model=account.move data-oe-id=%d>%s</a> via %s") % (
                                   new_move.id, new_move.name, created_by))
        new_move.with_context(check_move_validity=False)._recompute_tax_lines()
        if move_line:
            new_move.with_context(check_move_validity=False)._recompute_dynamic_lines()
            # assign the move line to the first order line
            self.order_line[0].update({'invoice_lines': [(4, move_line.id)]})
            # set the invoice account according to the return location
            self.set_account_to_invoice(new_move, location)
            new_move.action_post()
            self.paid_credit_note(new_move)
        return new_move

    def create_refund_adjustment_line(self, order_adjustments, move_ids, refund_data_line):
        """
        Overwrite the original function.
        This method is used to create an invoice line in a new move to manage the adjustment refund.
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 19/05/2021.
        Task Id : 173066 - Manage Partial refund in the Shopify
        """
        account_move_line_obj = self.env['account.move.line']
        adjustment_product = self.env.ref('shopify_ept.shopify_refund_adjustment_product', False)
        adjustments_amount = 0.0
        move_line = False
        for order_adjustment in order_adjustments:
            adjustments_amount += float(order_adjustment.get('amount', 0.0))
        if abs(adjustments_amount) > 0:
            move_vals = {'product_id': adjustment_product.id, 'quantity': 1, 'price_unit': -adjustments_amount,
                         'move_id': move_ids.id, 'partner_id': move_ids.partner_id.id,
                         'name': adjustment_product.display_name}
            new_move_vals = account_move_line_obj.new(move_vals)
            new_move_vals._onchange_product_id()
            new_vals = account_move_line_obj._convert_to_write(
                {name: new_move_vals[name] for name in new_move_vals._cache})
            # update tax_ids
            new_vals.update({'quantity': 1, 'price_unit': -adjustments_amount,
                             'tax_ids': [(6, 0, adjustment_product.taxes_id.ids)]})
            move_line = account_move_line_obj.with_context(check_move_validity=False).create(new_vals)
        return move_line

    def paid_credit_note(self, invoices):
        """
        This method auto paid the credit note for the provided invoices
        @Params: Invoices(Refunded: generating the credit note)
        """
        self.ensure_one()
        account_payment_obj = self.env['account.payment']
        for invoice in invoices:
            if self.auto_workflow_process_id.register_payment and invoice.amount_residual:
                vals = self.prepare_payment_data(self.auto_workflow_process_id, invoice)
                payment_id = account_payment_obj.create(vals)
                payment_id.action_post()
                self.reconcile_payment_ept(payment_id, invoice)
        return True

    def prepare_payment_data(self, auto_workflow_process_id,  invoice):
        """
        This method use to prepare a vals dictionary for credit note payment
        @Params:
            'auto_workflow_process_id': Workflow proccess related with the SO
            'invoice': Invoice to get the data to generate the payment
        """
        return {
            'journal_id': auto_workflow_process_id.journal_id.id,
            'ref': invoice.payment_reference,
            'currency_id': invoice.currency_id.id,
            'payment_type': 'outbound',
            'date': invoice.date,
            'partner_id': invoice.commercial_partner_id.id,
            'amount': invoice.amount_residual,
            'payment_method_id': auto_workflow_process_id.inbound_payment_method_id.id,
            'partner_type': 'customer'
        }

    def create_picking_return(self, refunds_data):
        """
        This method use to prepare a vals dictionary for stock picking return and create it.
        @Params:
            'location_dev': Location to return the order
            'picking_id': Picking to get the picking and the original location
        """
        new_picking = False
        picking_type = False
        order_line_env = self.env['sale.order.line']
        return_line_env = self.env['stock.return.picking.line']
        stock_move_env = self.env['stock.move']
        stock_picking_env = self.env['stock.picking']
        for refund in refunds_data:
            if refund.get('refund_line_items'):
                picking_return = False
                picking_created = False
                order_line_dict = []
                refunded_move = stock_move_env.search([('shopify_refund_id', '=', str(refund.get('id')))])
                if not refunded_move:
                    for line_item in refund.get('refund_line_items'):
                        # obtain the line to return
                        line_item_id = line_item.get('line_item_id')
                        # get the sale order line that contain the shopify line item id
                        order_line = order_line_env.search([
                            ('order_id', '=', self.id),
                            ('shopify_line_id', '=', str(line_item_id))
                        ])
                        # find the picking to return through the stock move for the order line
                        stock_move = stock_move_env.search([('sale_line_id', '=', order_line.id),
                                                            ('to_refund', '=', False)], limit=1)
                        if stock_move:
                            picking_id = stock_move.picking_id
                            # add the lines for the stock picking
                            order_line_dict.append(
                                {
                                    'order_line': order_line,
                                    'quantity': line_item.get('quantity'),
                                    'move': stock_move.id,
                                    'picking': picking_id,
                                    'location': line_item.get('location_id')
                                }
                            )
                    # create the lines for the picking return
                    for value in order_line_dict:
                        # get the return location for the picking
                        if not picking_created:
                            location_dev = self.get_location(value.get('location'))
                            if location_dev:
                                picking_return = self.create_stock_return_picking(location_dev, value.get('picking'))
                                picking_created = True
                        if picking_return:
                            vals_line = {
                                'product_id': value.get('order_line').product_id.id,
                                'quantity': value.get('quantity'),
                                'wizard_id': picking_return.id,
                                'move_id': value.get('move'),
                                'to_refund': True
                            }
                            return_line_env.create(vals_line)
                            # create the new stock picking for the return
                    if picking_return:
                        new_picking, picking_type = picking_return._create_returns()
                    picking = stock_picking_env.browse(new_picking)
                    self.fulfilled_picking_for_shopify(picking)
                    stock_move_to_update = stock_move_env.search([('picking_id', '=', picking.id)])
                    if stock_move_to_update:
                        stock_move_to_update.write({'shopify_refund_id': str(refund.get('id'))})
        return new_picking, picking_type

    def create_stock_return_picking(self, location_dev, picking_id):
        """
        This method use to prepare a vals dictionary for stock picking return and create it.
        @Params:
            'location_dev': Location to return the order
            'picking_id': Picking to get the picking and the original location
        """
        vals = {
            'picking_id': picking_id.id,
            'original_location_id': picking_id.location_id.id,
            'parent_location_id': picking_id.location_id.location_id.id,
            'location_id': location_dev.id
        }
        # create the picking return
        picking_return = self.env['stock.return.picking'].create(vals)
        return picking_return

    def get_location(self, location_id):
        """
        This method use to get the return location of the order.
        @Params:
            'location_id': Location_id from shopify refund line
        """
        if location_id:
            shopify_location_env = self.env['shopify.location.ept']
            shopify_location = shopify_location_env.search([('shopify_location_id', '=', location_id)])
            if not shopify_location.is_web_location:
                location_dev = shopify_location.warehouse_for_order.lot_stock_id
            else:
                web_return = shopify_location_env.search([('is_web_return_location', '=', True)], limit=1)
                location_dev = web_return.warehouse_for_order.lot_stock_id
        else:
            location_dev = self.env['stock.location'].search([('is_default_return', '=', True)], limit=1)
        return location_dev

    def auto_shipped_order_ept(self, customers_location, is_mrp_installed=False):
        """
        Overwrite the function to create the stock picking after import a shipped order.
        """
        order_lines = self.order_line.filtered(lambda l: l.product_id.type != 'service')
        vendor_location = self.env['stock.location'].search(['|', ('company_id', '=', self.company_id.id),
                                                             ('company_id', '=', False), ('usage', '=', 'supplier')],
                                                            limit=1)
        for order_line in order_lines:
            bom_lines = []
            if is_mrp_installed:
                bom_lines = self.check_for_bom_product(order_line.product_id)
            for bom_line in bom_lines:
                self.create_and_done_stock_move_ept(order_line, customers_location, bom_line=bom_line)
            if not bom_lines and order_line.product_id.is_drop_ship_product:
                self.create_and_done_stock_move_ept(order_line, customers_location, vendor_location=vendor_location)
            elif not bom_lines or not is_mrp_installed:
                # create the picking after confirming the order
                order_line._action_launch_stock_rule()
                picking_ids = self.picking_ids
                self.fulfilled_picking_for_shopify(picking_ids)
        return True

    def set_price_based_on_refund(self, move_line):
        """
        Overwriting the function to fix sub_total_tax_dict key to get it  and
        consider if the total_price has the taxes included
        """
        if not move_line.tax_ids.include_base_amount:
            total_adjust_amount = 0.0
            for line in move_line.sale_line_ids:
                if move_line.quantity != line.product_uom_qty:
                    tax_dict = json.loads(line.order_id.tax_totals_json)
                    sub_total_tax_dict = tax_dict.get('groups_by_subtotal').get('Untaxed Amount') or\
                                         tax_dict.get('groups_by_subtotal').get('Importe libre de impuestos')
                    total_tax_amount = 0.0
                    for tax in sub_total_tax_dict:
                        total_tax_amount += tax.get('tax_group_amount')
                    total_adjust_amount = total_tax_amount / line.product_uom_qty
            move_line.price_unit += total_adjust_amount
        return True

    def prepare_order_multi_payment(self, order_data):
        """ This method is use to prepare a values for the multi payment.
            @author: Meera Sidapara @Emipro Technologies Pvt. Ltd on date 16/11/2021 .
            Task_id:179257 - Manage multiple payment.
        """
        instance = self.shopify_instance_id
        payment_gateway_obj = self.env["shopify.payment.gateway.ept"]
        payment_list_vals = []
        try:
            instance.connect_in_shopify()
            transactions = shopify.Transaction().find(order_id=order_data.get('id'))
            payment_list_vals = self.process_transactions(instance, payment_gateway_obj, transactions)
        except Exception as error:
            pass
        return payment_list_vals

    def process_transactions(self, instance, payment_gateway_obj, transactions):
        workflow = self.auto_workflow_process_id
        payment_list_vals = []
        for transaction in transactions:
            result = transaction.to_dict()
            if result.get('kind') in ['capture', 'sale'] and result.get('status') == 'success':
                payment_transaction_id = result.get('id')
                gateway = result.get('gateway')
                amount = result.get('amount')
                new_payment_gateway = payment_gateway_obj.search([('code', '=', gateway),
                                                                  ('shopify_instance_id', '=', instance.id)],
                                                                 limit=1)
                order_transaction = self.shopify_payment_ids.filtered(
                    lambda l: l.payment_transaction_id == str(payment_transaction_id))
                if new_payment_gateway and not order_transaction:
                    payment_list = (0, 0, {'payment_gateway_id': new_payment_gateway.id,
                                           'workflow_id': workflow.id, 'amount': amount,
                                           'payment_transaction_id': payment_transaction_id,
                                           'remaining_refund_amount': amount})
                    payment_list_vals.append(payment_list)
        return payment_list_vals

    def create_shopify_order_lines(self, lines, order_response, instance):
        """
        Overwrite the original function to add
        """
        total_discount = order_response.get("total_discounts", 0.0)
        order_number = order_response.get("order_number")
        order_line_list = []
        for line in lines:
            is_custom_line, is_gift_card_line, product = self.search_custom_tip_gift_card_product(line, instance)
            price = line.get("price")
            if instance.order_visible_currency:
                price = self.get_price_based_on_customer_visible_currency(line.get("price_set"), order_response, price)
            order_line = self.shopify_create_sale_order_line(line, product, line.get("quantity"),
                                                             product.name, price,
                                                             order_response)
            order_line_list.append(order_line)
            if is_gift_card_line:
                line_vals = {'is_gift_card_line': True}
                if line.get('name'):
                    line_vals.update({'name': line.get('name')})
                order_line.write(line_vals)

            if is_custom_line:
                order_line.write({'name': line.get('name')})

            if line.get('duties'):
                self.create_shopify_duties_lines(line.get('duties'), order_response, instance)

            if float(total_discount) > 0.0:
                discount_amount = 0.0
                for discount_allocation in line.get("discount_allocations"):
                    discount_amount += float(discount_allocation.get("amount"))
                if discount_amount > 0.0:
                    _logger.info("Creating discount line for Odoo order(%s) and Shopify order is (%s)", self.name,
                                 order_number)
                    disc_line = self.shopify_create_sale_order_line({}, instance.discount_product_id, 1,
                                                                    product.name, float(discount_amount) * -1,
                                                                    order_response, previous_line=order_line,
                                                                    is_discount=True)
                    order_line_list.append(disc_line)
                    # Add the origin_line when its a Discount product line
                    disc_line.update({"origin_line": order_line.shopify_line_id})
                    _logger.info("Created discount line for Odoo order(%s) and Shopify order is (%s)", self.name,
                                 order_number)
        return order_line_list

    def create_move_and_delete_not_necessary_line(self, refunds_data, invoices, created_by):
        """
        Overwrite the original function.
        This method is used to create a reverse move of invoice and delete the invoice lines from the newly
        created move which product not refunded in Shopify.
        """
        shopify_line_data = []
        exist_move_ids = []
        shopify_line_ids_with_qty = {}
        new_moves = []
        for refund_line in refunds_data.get('refund_line_items'):
            inv_shopify_id = invoices.invoice_line_ids.filtered(
                lambda l: l.sale_line_ids.shopify_line_id and str(refund_line.get('line_item_id')) in l.sale_line_ids.shopify_line_id)
            shopify_line_data.append({'move': inv_shopify_id.move_id, 'ref': refund_line})
            if inv_shopify_id.move_id and (inv_shopify_id.move_id not in exist_move_ids):
                exist_move_ids.append(inv_shopify_id.move_id)
            shopify_line_ids_with_qty.update({refund_line.get('line_item_id'): refund_line.get('quantity')})
        for exist_move in exist_move_ids:
            delete_move_lines = self.env['account.move.line']
            shopify_line_ids = []
            refunds_x_move = list(filter(lambda x: x.get('move') == exist_move, shopify_line_data))
            for rec in refunds_x_move:
                shopify_line_ids.append(rec.get('ref').get('line_item_id'))
            refund_date = self.convert_order_date(refunds_data)
            move_reversal = self.env["account.move.reversal"].with_context(
                {"active_model": "account.move", "active_ids": exist_move.ids}, check_move_validity=False).create(
                {"refund_method": "refund",
                 "reason": "Partially Refunded from shopify" if len(refunds_data) > 1 else refunds_data.get("note"),
                 "journal_id": exist_move.journal_id.id, "date": refund_date})

            move_reversal.reverse_moves()
            new_move = move_reversal.new_move_ids
            new_move.write({'is_refund_in_shopify': True, 'shopify_refund_id': refunds_data.get('id')})
            for new_move_line in new_move.invoice_line_ids:
                shopify_line_id = new_move_line.sale_line_ids.shopify_line_id
                origin_line = new_move_line.sale_line_ids.origin_line
                # Lines dont need to be consider in the reversal
                # Will be deleted at the end
                if (shopify_line_id and int(shopify_line_id) not in shopify_line_ids) or (origin_line and int(origin_line) not in shopify_line_ids):
                    delete_move_lines += new_move_line
                    delete_move_lines.recompute_tax_line = True
                # If its not a Discount Product line
                # Set the qty and taxes
                elif new_move_line.product_id.id != self.shopify_instance_id.discount_product_id.id:
                    new_move_line.quantity = shopify_line_ids_with_qty.get(int(shopify_line_id))
                    new_move_line.recompute_tax_line = True
                    self.set_price_based_on_refund(new_move_line)
                # If its a Discount Product line
                elif origin_line and new_move_line.product_id.id == self.shopify_instance_id.discount_product_id.id and\
                        int(origin_line) in shopify_line_ids:
                    origin = new_move.invoice_line_ids.filtered(lambda l: l.sale_line_ids.shopify_line_id == origin_line)
                    new_move_line.quantity = shopify_line_ids_with_qty.get(int(origin_line))
                    if origin.sale_line_ids.product_uom_qty:
                        new_move_line.price_unit = new_move_line.price_unit / origin.sale_line_ids.product_uom_qty
                    new_move_line.recompute_tax_line = True
                    self.set_price_based_on_refund(new_move_line)
            new_move.message_post(body=_("Credit note generated by %s as Order partially "
                                         "refunded in Shopify. This credit note has been created from "
                                         "<a href=# data-oe-model=sale.order data-oe-id=%d>%s</a>") % (
                                           created_by, self.id, self.name))
            self.message_post(body=_(
                "Partially credit note created <a href=# data-oe-model=account.move data-oe-id=%d>%s</a> via %s") % (
                                       new_move.id, new_move.name, created_by))
            if delete_move_lines:
                delete_move_lines.with_context(check_move_validity=False).unlink()
                new_move.with_context(check_move_validity=False)._recompute_tax_lines()
            new_moves.append(new_move)
        return new_moves

    def create_shipped_order_refund(self, shopify_financial_status, order_response, sale_order, created_by):
        """ This method is used to create partially or fully refund in shopify order.
            @param : self
            @return: message
            @author: Meera Sidapara @Emipro Technologies Pvt. Ltd on date 27 November 2021 .
            Task_id: 179249
        """
        message = ""
        if shopify_financial_status == "refunded":
            total_refund = 0.0
            for refund in order_response.get('refunds'):
                for transaction in refund.get('transactions'):
                    if transaction.get('kind') == 'refund' and transaction.get('status') == 'success':
                        total_refund += float(transaction.get('amount'))
            refunded = sale_order.create_shopify_refund(order_response.get("refunds"), total_refund, created_by)
            if refunded[0] is True and not order_response.get('cancel_reason'):
                new_picking, picking_type = sale_order.create_picking_return(order_response.get("refunds"))
            if refunded[0] == 0:
                message = "- Refund can only be generated if it's related order " \
                          "invoice is found.\n- For order [%s], system could not find the " \
                          "related order invoice. " % (order_response.get('name'))
            elif refunded[0] == 2:
                message = "- Refund can only be generated if it's related order " \
                          "invoice is in 'Post' status.\n- For order [%s], system found " \
                          "related invoice but it is not in 'Post' status." % (
                              order_response.get('name'))
            elif refunded[0] == 3:
                message = "- Partial refund is received from Shopify for order [%s].\n " \
                          "- System do not process partial refunds.\n" \
                          "- Either create partial refund manually in Odoo or do full " \
                          "refund in Shopify." % (order_response.get('name'))
        elif shopify_financial_status == "partially_refunded" and order_response.get("refunds"):
            message = sale_order.create_shopify_partially_refund(order_response.get("refunds"),
                                                                 order_response.get('name'), created_by)
        self.prepare_vals_shopify_multi_payment_refund(order_response.get("refunds"), sale_order)
        return message
