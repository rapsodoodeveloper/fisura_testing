# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    shopify_prod_tmpl_id = fields.Many2one(
        comodel_name='shopify.product.template.ept',
        string='Shopify Product'
    )
    exported_in_shopify = fields.Boolean(
        string='Exported in Shopify',
        related='shopify_prod_tmpl_id.exported_in_shopify',
        store=True
    )
    is_modified = fields.Boolean(
        string='Update to Shopify'
    )
    is_shopify_default_prod = fields.Boolean(
        string='Default Shopify Product'
    )

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)
        from_shopify = self.env.context.get('shopify_import')
        for rec in self:
            if not from_shopify and rec.exported_in_shopify:
                for value in rec.get_fields_verify():
                    if vals.get(value):
                        rec.is_modified = True
        return res

    def unlink(self):
        for rec in self:
            if rec.is_shopify_default_prod:
                raise ValidationError(_('Sorry!! This product can not be deleted because is used for the Shopify flow.'))
        return super(ProductTemplate, self).unlink()

    @staticmethod
    def get_fields_verify():
        """
            Function to get the fields to be consider to detect important changes in a product.
            Return: List of strings(field's name)
        """
        return ['name', 'list_price', 'categ_id', 'barcode', 'default_code', 'weight', 'price_ids',
                'attribute_line_ids']
