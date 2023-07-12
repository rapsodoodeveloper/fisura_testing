# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api


class ShopifyProductTemplateEpt(models.Model):
    _inherit = "shopify.product.template.ept"

    product_to_update = fields.Boolean(
        string='Update to Shopify'
    )

    @api.model
    def create(self, values):
        """
        Inherit the standard method to update the shopify product template in odoo product.
        """
        res = super(ShopifyProductTemplateEpt, self).create(values)
        if res.product_tmpl_id:
            res.product_tmpl_id.shopify_prod_tmpl_id = res.id
        return res

    def write(self, vals):
        res = super(ShopifyProductTemplateEpt, self).write(vals)
        for rec in self:
            if vals.get('name') or vals.get('shopify_product_category') or vals.get('shopify_product_ids'):
                rec.product_to_update = True
                rec.product_tmpl_id.is_modified = False
        return res

    def sync_product_with_existing_template(self, shopify_template, skip_existing_product, template_data, instance,
                                            product_category, model_id, log_book_id, product_data_line_id,
                                            order_data_line_id):
        """
         Inherit the standard method to add properties to the product template in Odoo.
        """
        res = super(ShopifyProductTemplateEpt, self).sync_product_with_existing_template(
                                                    shopify_template, skip_existing_product, template_data, instance,
                                                    product_category, model_id, log_book_id, product_data_line_id,
                                                    order_data_line_id)
        if res:
            self.get_product_properties(res, template_data)
        return res

    def get_product_properties(self, res, template_data):
        """
        Function to add properties to product template.
        """
        product = res.product_tmpl_id.with_context({'shopify_import': True})
        # Update product category
        product.categ_id = res.shopify_product_category
        # Update product code and price from variant
        if template_data.get('variants'):
            product_code = self.get_product_code(template_data)
            price = self.get_product_price(template_data)
            product.update({
                'code': product_code,
                'list_price': price
            })
            # Update vertical quality and serial if exists in odoo
            vertical_qlity, vert_quality_serial = self.get_vertical_quality(template_data)
            if vertical_qlity and vert_quality_serial:
                res.product_tmpl_id.update({
                    'vert_qlity_id': vertical_qlity,
                    'vert_qlity_serial_id': vert_quality_serial
                })
        # Update product season with shopify vendor
        if template_data.get("vendor"):
            product_season = self.get_product_season(template_data.get("vendor"))
            product.product_season_id = product_season
        # Delete color attribute from product template in odoo
        if res.product_tmpl_id.attribute_line_ids:
            for rec in res.product_tmpl_id.attribute_line_ids:
                if rec.attribute_id.is_color:
                    rec.unlink()

    def sync_new_product(self, template_data, instance, product_category, model_id, log_book_id, product_data_line_id,
                         order_data_line_id):
        """
        Inherit the standard method to add properties to the product template in Odoo.
        """
        res = super(ShopifyProductTemplateEpt, self).sync_new_product(template_data, instance, product_category,
                                                                      model_id, log_book_id, product_data_line_id,
                                                                      order_data_line_id)
        if res:
            self.get_product_properties(res, template_data)
        return res

    def get_product_season(self, vendor):
        """
        Search for product season and create if not found.
        """
        product_season_obj = self.env["product.season"]
        product_season = product_season_obj.search([("name", "=", vendor)], limit=1)
        if not product_season:
            product_season = product_season_obj.create({"name": vendor})
        return product_season

    def get_vertical_quality(self, template_data):
        sku = template_data.get('variants')[0].get('sku')
        vertical_qlity = self.env['vertical.quality']
        vert_quality_serial = self.env['vertical.quality.serial']
        if sku:
            sku = sku.replace("/", "-")
            split_sku = sku.split("-")
            if len(split_sku) > 2:
                color = False
                code_color = split_sku[2]
                code_color = code_color.lstrip('0')
                for item in template_data.get('options'):
                    if item.get('name') == 'Color':
                        color = item.get('values')[0]
                if color and code_color:
                    vertical_qlity = vertical_qlity.search([('code', '=', code_color),
                                                            ('name', '=', color)], limit=1)
                    if vertical_qlity:
                        serial = vert_quality_serial.search([('vert_quality_ids', 'in', vertical_qlity.id)])
                        if len(serial) == 1:
                            vert_quality_serial = serial
        return vertical_qlity, vert_quality_serial

    @staticmethod
    def get_product_code(template_data):
        """
        Function to get the product code from variant SKU.
        """
        sku = template_data.get('variants')[0].get('sku')
        product_code = ''
        if sku:
            sku = sku.replace("/", "-")
            code = sku.split("-")
            if len(code) > 1:
                product_code = '{}-{}'.format(code[0], code[1])
        return product_code

    @staticmethod
    def get_product_price(template_data):
        """
        Function to get de product price from variant price.
        """
        price = 0
        if template_data.get('variants')[0].get('price'):
            price = float(template_data.get('variants')[0].get('price'))
        return price
