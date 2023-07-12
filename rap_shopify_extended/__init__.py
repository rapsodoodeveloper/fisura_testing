# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from . import models
from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def parameter_config(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_shopify_products(env)


def update_shopify_products(env):
    """
    Method that sets the is_shopify_default_prod field to true to avoid deleting these products
    """
    products = env['product.template'].search(['|', ('name', 'like', 'Shopify'), ('name', '=', 'TIP Product')])
    _logger.info("Change the price included boolean for {} taxes".format(len(products)))
    for prod in products:
        prod.is_shopify_default_prod = True
