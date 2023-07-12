# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    def write(self, vals):
        res = super(ProductTemplateAttributeValue, self).write(vals)
        for rec in self:
            if rec.product_tmpl_id.exported_in_shopify:
                if vals.get('price_extra'):
                    rec.product_tmpl_id.is_modified = True
        return res
