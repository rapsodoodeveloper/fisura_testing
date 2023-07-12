# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        res = super(ProductProduct, self).write(vals)
        for rec in self:
            if rec.product_tmpl_id.exported_in_shopify:
                if vals.get('name') or vals.get('barcode') or vals.get('default_code') or vals.get('weight'):
                    rec.product_tmpl_id.is_modified = True
            if 'active' in vals and not rec.active:
                shop_prod = self.env['shopify.product.product.ept'].search([('product_id', '=', rec.id),
                                                                            ('active', 'in', [True, False])])
                shop_prod.unlink()
        return res
