# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _
import logging
import time
from odoo.addons.shopify_ept import shopify

_logger = logging.getLogger("Shopify Operations")


class ShopifyProcessImportExport(models.TransientModel):
    _inherit = 'shopify.process.import.export'

    shopify_is_update_name = fields.Boolean(
        string="Update Name?",
        default=False,
        help="The product's Name will be updated in shopify store"
    )
    shopify_is_update_categ = fields.Boolean(
        string="Update Family?",
        default=False,
        help="The product's Family will be updated in shopify store"
    )
    shopify_is_update_product_season = fields.Boolean(
        string="Update Season?",
        default=False,
        help="The product's Season will be updated in shopify store"
    )
    shopify_is_update_product_option = fields.Boolean(
        string="Update Attribute?",
        default=False,
        help="The product's Attribute will be updated in shopify store"
    )

    @api.onchange('shopify_is_update_basic_detail')
    def onchange_update_basic_detail(self):
        fields = self.get_fields_to_update()
        for rec in fields:
            if self.shopify_is_update_basic_detail:
                self[rec] = True
            else:
                self[rec] = False

    @staticmethod
    def get_fields_to_update():
        return ['shopify_is_update_name', 'shopify_is_update_categ', 'shopify_is_update_product_season',
                'shopify_is_update_product_option']

    def update_stock_in_shopify_cron(self):
        """
        This method is used to export stock to shopify automatically
        Will be sent all the stock products with stock moves
        """
        location_map_env = self.env["shopify.odoo.location"]
        prod_prod_ept = self.env['shopify.product.product.ept']
        # Search all the stock_move_line Internal/Reception not updated in shopify
        stock_lines = self.env['stock.move.line'].search([
            ('stock_upd_option', 'in', ['int', 'recep']),
            ('sent_shopify_count', '<', 100),
            ('adjust_in_shopify', '=', False)]).sorted(key=lambda l: l.picking_id.date_done)
        for line in stock_lines:
            shopify_prod = prod_prod_ept.search([('product_id', '=', line.product_id.id)])
            if shopify_prod:
                instance = shopify_prod.shopify_instance_id
                location_orig = location_map_env.search([("instance_id", "=", instance.id),
                                                         ('location_id', '=', line.location_id.id)])
                location_dest = location_map_env.search([("instance_id", "=", instance.id),
                                                         ('location_id', '=', line.location_dest_id.id)])
                qty = line.qty_done
                # If exist the location in Odoo but its not mapped with the shopify id should be ignore
                if (line.location_id and not location_orig and line.location_id.is_stock) or\
                        (line.location_dest_id and not location_dest and line.location_dest_id.is_stock):
                    continue
                # If its type 'recep' and there is not destiny location (anything should be updated)
                if line.stock_upd_option == 'recep' and not location_dest:
                    line.adjust_in_shopify = True
                    continue
                # If its type 'int' and there is no origin/destiny locations (anything should be updated)
                if line.stock_upd_option == 'int' and not location_orig and not location_dest:
                    line.adjust_in_shopify = True
                    continue
                if location_dest:
                    self.post_location_dest(line, instance, location_dest, shopify_prod, qty, location_orig)

                if line.stock_upd_option == 'int' and location_orig:
                    self.post_location_orig(line, instance, location_orig, shopify_prod, int(abs(qty) * -1))
            else:
                # If product doesnt exist the counter should increase until the top (100)
                line.sent_shopify_count += 1

    def post_location_dest(self, line, instance, location_dest, product, qty, exist_origin):
        """"
        Function to POST to Stock Adjustment to Destination Location
        Add quantity to the actual stock in Shopify
        """
        in_adjust = self.post_stock_adjust(instance, location_dest.shopify_location_id.shopify_location_id,
                                           product.inventory_item_id, int(qty))
        if line.stock_upd_option == 'recep':
            if not in_adjust:
                line.adjust_in_shopify = True
            else:
                line.sent_shopify_count += 1
        if line.stock_upd_option == 'int' and not in_adjust and not exist_origin:
            line.adjust_in_shopify = True

    def post_location_orig(self, line, instance, location_orig, product, qty):
        """"
        Function to POST to Stock Adjustment to Origin Location
        Only used when Its an internal movement
        The same quantity Added to the Destination should be rested to the origin
        """
        int_adjust = self.post_stock_adjust(instance, location_orig.shopify_location_id.shopify_location_id,
                                            product.inventory_item_id, int(qty))
        if not int_adjust:
            line.adjust_in_shopify = True
        else:
            line.sent_shopify_count += 1

    def post_stock_adjust(self, instance, location, inv_item, qty):
        """"
            Function to call the "Adjust" method in Shopify_ept module
            @Parameters:
                instance: Instance obj.
                location: String(Number of Shopify Location).
                inv_item: String(Inventory Id of the product in shopify).
                qty: Quantity to be adjust.
            @Return: True if there is an exception, False if not.
        """
        exception = False
        try:
            # Connect Shopify instance
            # Execute the post to adjust de product_stock
            instance.connect_in_shopify()
            shopify.InventoryLevel.adjust(location, inv_item, qty)
        except Exception as error:
            exception = True
            if hasattr(error, "response") and error.response.code == 404 and error.response.msg == "Not Found":
                # The reason could be because the location its not associated with the inventory item
                # Try to create the inventory level
                self.generate_location(location, inv_item)
                try:
                    shopify.InventoryLevel.adjust(location, inv_item, qty)
                    exception = False
                except Exception as error2:
                    pass
            elif hasattr(error, "response") and error.response.code == 429 and error.response.msg == "Too Many Requests":
                time.sleep(int(float(error.response.headers.get('Retry-After', 5))))
                try:
                    shopify.InventoryLevel.adjust(location, inv_item, qty)
                    exception = False
                except Exception as error3:
                    pass
                pass
        return exception

    @staticmethod
    def generate_location(location, inv_item):
        """"
            Function to call the "connect" method in Shopify_ept module
            @Parameters:
                location: String(Number of Shopify Location).
                inv_item: String(Inventory Id of the product in shopify).
            @Return: True if there is an exception, False if not.
        """
        exception = False
        try:
            # Execute the post to connect inventory_level
            shopify.InventoryLevel.connect(location, inv_item)
        except Exception as error:
            exception = True
            if hasattr(error, "response") and error.response.code == 429 and error.response.msg == "Too Many Requests":
                time.sleep(int(float(error.response.headers.get('Retry-After', 5))))
                shopify.InventoryLevel.connect(location, inv_item)
                pass
        return exception

    @staticmethod
    def connect_inventory_level(instance, location_id, inventory_id):
        """"
            Function to call the "Connect" method in Shopify_ept module
            Connect an inventory Item with a location
            @Parameters:
                instance: Instance obj.
                location: Integer(Location Id in Shopify).
                inv_item: Integer(Product inventory Id in shopify)
            @Return: True if there is an exception, False if not.
        """
        exception = False
        try:
            # Connect Shopify instance
            # Execute the post to connect de product_stock
            instance.connect_in_shopify()
            shopify.InventoryLevel.connect(location_id, inventory_id)
        except Exception as error:
            exception = True
            pass
        return exception

    def manual_update_product_to_shopify(self):
        """
        Inherit the function to add values into the context.
        This context values will be used for other functions to define which values will be sended to Shopify
        """
        context = dict(self._context)
        context.update({'shopify_upt_fields': {'name': self.shopify_is_update_name,
                                               'categ': self.shopify_is_update_categ,
                                               'option': self.shopify_is_update_product_option,
                                               'season': self.shopify_is_update_product_season}
                        })
        self.env.context = context
        res = super(ShopifyProcessImportExport, self).manual_update_product_to_shopify()
        return res

    def set_payments_to_draft(self):
        """
        Method To set to draft all posted payments
        """
        payment = self.env['account.payment'].search([('state', '=', 'posted'), ('amount', '!=', 0.0)], limit=500)
        _logger.info("******PAYMENTS O BE PROCCESS************: {}".format(len(payment)))
        for rec in payment:
            rec.action_draft()
            _logger.info("Set to draft payment: {}".format(rec.name))

