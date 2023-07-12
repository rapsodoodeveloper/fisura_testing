# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields
from datetime import datetime
import time
from odoo.addons.shopify_ept import shopify


class ShopifyProductProductEpt(models.Model):
    _inherit = "shopify.product.product.ept"

    variant_sequence = fields.Integer(
        string='Variant sequence',
        compute='_compute_variant_sequence'
    )

    def _compute_variant_sequence(self):
        for rec in self:
            sequence = 0
            if rec.product_id.product_tmpl_id:
                size = rec.product_id.product_tmpl_id.attribute_line_ids.filtered(lambda l: l.attribute_id.is_size)
                if size:
                    size_line = rec.product_id.product_template_attribute_value_ids.filtered(lambda l: l.attribute_id.is_size)
                    if size_line and size_line.name in size.value_ids.mapped('name'):
                        sequence = size.value_ids.mapped('name').index(size_line.name)
            rec.variant_sequence = sequence

    def update_products_in_shopify(self, instance, templates, is_set_price, is_set_images, is_publish,
                                   is_set_basic_detail):
        res = super(ShopifyProductProductEpt, self).update_products_in_shopify(instance, templates, is_set_price,
                                                                        is_set_images, is_publish, is_set_basic_detail)
        if res:
            for rec in templates:
                rec.product_to_update = False
        return res

    def shopify_set_template_value_in_shopify_obj(self, new_product, template, is_publish, is_set_basic_detail):
        """
        Overwrite the standard function to Drill down the details to be sended to shopify
        """
        context = self._context.get('shopify_upt_fields')
        published_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        if is_publish == "unpublish_product":
            new_product.published_at = None
            new_product.published_scope = "null"
            new_product.status = "draft"
        elif is_publish == "publish_product_global":
            new_product.published_scope = "global"
            new_product.published_at = published_at
        else:
            new_product.published_scope = "web"
            new_product.published_at = published_at
        instance = template.shopify_instance_id
        if is_set_basic_detail:
            if template.description:
                # new_product.body_html = template.description
                new_product.body_html = template.with_context(lang=instance.shopify_lang_id.code).description
            if template.template_suffix:
                new_product.template_suffix = template.template_suffix
            if not context or context['name']:
                # new_product.title = template.name
                new_product.title = template.with_context(lang=instance.shopify_lang_id.code).name
            if not context or context['categ']:
                new_product.product_type = template.shopify_product_category.name
            if not context or context['season']:
                new_product.vendor = template.product_tmpl_id.product_season_id.name or ''
        return True

    def prepare_vals_for_product_basic_details(self, variant_vals, variant, instance):
        """
        Overwrite the function to add a new Attribute not coming from the variants in Odoo
        """
        context = self._context.get('shopify_upt_fields')
        variant_vals.update({"grams": int(variant.product_id.weight * 1000),
                             "weight": variant.product_id.weight,
                             "weight_unit": "kg",
                             "requires_shipping": "true",
                             "taxable": variant.taxable and "true" or "false"
                             })
        if not context or context['name']:
            variant_vals.update({"title": variant.with_context(lang=instance.shopify_lang_id.code).name})
        if not context or context['option']:
            variant_vals.update({"barcode": variant.product_id.barcode or ""})
            variant_vals.update({"sku": variant.default_code})
            option_index = 0
            option_index_value = ["option1", "option2", "option3"]
            attribute_value_obj = self.env["product.template.attribute.value"]
            att_values = attribute_value_obj.search(
                [("id", "in", variant.product_id.product_template_attribute_value_ids.ids)],
                order="attribute_id")
            if variant.product_id.product_tmpl_id.vert_qlity_id.display_name and (not context or context['option']):
                # If the product has color, should be added to the variants vals in first position
                option_index = 1
                variant_vals.update(
                    {option_index_value[0]: variant.product_id.product_tmpl_id.vert_qlity_id.display_name})
            for att_value in att_values:
                if option_index > 3:
                    continue
                variant_vals.update(
                    {option_index_value[option_index]: att_value.with_context(lang=instance.shopify_lang_id.code).name})
                option_index = option_index + 1
        return variant_vals

    def prepare_export_update_product_attribute_vals(self, template, new_product):
        """
        Overwrite the function to add a new Attribute not coming from the variants in Odoo
        this new attribute Will be the color, taking always the first position in Shopify option List
        """
        context = self._context.get('shopify_upt_fields')
        if len(template.shopify_product_ids) >= 1 and (not context or context['option']):
            attribute_list = []
            attribute_position = 1
            product_attribute_line_obj = self.env["product.template.attribute.line"]
            instance = template.shopify_instance_id
            product_attribute_lines = product_attribute_line_obj.search(
                [("id", "in",
                  template.with_context(lang=instance.shopify_lang_id.code).product_tmpl_id.attribute_line_ids.ids)],
                order="attribute_id")
            if template.product_tmpl_id.vert_qlity_id and (not context or context['option']):
                # If the product has color, should be added to the Options in Shopify
                attribute_position = 2
                color = template.product_tmpl_id.vert_qlity_id.display_name
                attribute_list.append({"name": 'Color', "values": [color], "position": 1})
            for attribute_line in product_attribute_lines.filtered(lambda x: x.attribute_id.create_variant == "always"):
                info = {}
                attribute = attribute_line.attribute_id
                value_names = []
                for value in attribute_line.value_ids:
                    value_names.append(value.with_context(lang=instance.shopify_lang_id.code).name)

                info.update(
                    {"name": attribute.with_context(lang=instance.shopify_lang_id.code).name, "values": value_names,
                     "position": attribute_position})
                attribute_list.append(info)
                attribute_position = attribute_position + 1
            new_product.options = attribute_list
        if template.product_tmpl_id.price_ids:
            # Update Price at compare
            oldest = min(template.product_tmpl_id.price_ids)
            second_price = oldest.price
            for variant in new_product.variants:
                variant.update({'compare_at_price': second_price,
                                "presentment_prices": [
                                    {
                                        "price": {
                                            "amount": variant.get('price'),
                                            "currency_code": "EUR"
                                        },
                                        "compare_at_price": second_price
                                    }
                                ],
                                })
        return True

    def shopify_prepare_variant_vals(self, instance, variant, is_set_price, is_set_basic_detail):
        """
        Inherit to add a fix when a variant its added in Odoo to be send to shopify
        """
        variant_vals = super(ShopifyProductProductEpt, self).shopify_prepare_variant_vals(instance, variant,
                                                                                      is_set_price, is_set_basic_detail)
        if not variant.variant_id:
            variant_vals.update({"id": ''})
        return variant_vals

    def prepare_shopify_product_for_update_export(self, new_product, template, instance, is_set_basic_detail,
                                                  is_publish, is_set_price):
        """
        Overwrite the method to organize the attributes values
        """
        context = self._context.get('shopify_upt_fields')
        if is_set_basic_detail or is_publish:
            self.shopify_set_template_value_in_shopify_obj(new_product, template, is_publish, is_set_basic_detail)
        if (is_set_basic_detail and (not context or context['option'])) or is_set_price and not is_set_basic_detail:
            variants = []
            shopify_variants = template.shopify_product_ids
            if shopify_variants:
                tmpl_variants = shopify_variants.sorted(key=lambda prod: prod.variant_sequence)
            for variant in tmpl_variants:
                variant_vals = self.shopify_prepare_variant_vals(instance, variant, is_set_price,
                                                                 is_set_basic_detail)
                variants.append(variant_vals)
            new_product.variants = variants
        if is_set_basic_detail:
            self.prepare_export_update_product_attribute_vals(template, new_product)
        return True

    def shopify_export_products(self, instance, is_set_basic_detail, is_set_price, is_set_images, is_publish,
                                templates):
        """
        Inherit the standard function to add the creation of inventory level/locations
        """
        res = super(ShopifyProductProductEpt, self).shopify_export_products(instance, is_set_basic_detail, is_set_price,
                                                                            is_set_images, is_publish, templates)
        for template in templates:
            for product in template.shopify_product_ids:
                locations = self.env['shopify.location.ept'].search(
                    [('instance_id', '=', instance.id)]).mapped('shopify_location_id')
                for location in locations:
                    inventory_id = product.inventory_item_id
                    if location and inventory_id:
                        self.connect_inventory_level(instance, int(location), int(inventory_id))
        return res

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
            if hasattr(error,
                       "response") and error.response.code == 429 and error.response.msg == "Too Many Requests":
                time.sleep(int(float(error.response.headers.get('Retry-After', 5))))
                shopify.InventoryLevel.connect(location_id, inventory_id)
                pass
        return exception
