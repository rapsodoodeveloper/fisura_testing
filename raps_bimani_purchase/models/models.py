# Copyright 2022-TODAY Rapsodoo Iberia S.r.L. (www.rapsodoo.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models, fields, api, _


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    order_section = fields.Many2one(
        comodel_name='purchase.order.line',
        string='Section'
    )
    picking_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Operation Type',
        domain="['|',('warehouse_id', '=', False), "
               "('warehouse_id.company_id', '=', company_id),"
               " ('is_reception', '=', True)]"
    )
    location_dest_id = fields.Many2one(
        related='picking_type_id.default_location_dest_id'
    )

    @api.model
    def _first_picking_copy_vals(self, key, lines):
        """The data to be copied to new pickings is updated with data from the
        grouping key.  This method is designed for extensibility, so that
        other modules can store more data based on new keys."""
        vals = super(PurchaseOrderLine, self)._first_picking_copy_vals(key, lines)
        for key_element in key:
            if "location_dest_id" in key_element.keys():
                picking_type = self.env['stock.picking.type'].search(
                    [('default_location_dest_id', '=', key_element["location_dest_id"].id),
                     ('is_reception', '=', True)], limit=1)
                if picking_type:
                    vals["picking_type_id"] = picking_type.id
        return vals


class StockLocation(models.Model):
    _inherit = 'stock.location'

    is_stock = fields.Boolean(
        string='Is an Stock Location?'
    )


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def create(self, vals):
        res = super(PurchaseOrder, self).create(vals)
        if res.state in ['draft', 'sent', 'to approve', 'purchase']:
            res.generate_section_lines()
        return res

    def write(self, vals):
        res = super(PurchaseOrder, self).write(vals)
        for rec in self:
            if vals.get('order_line') and rec.state in ['draft', 'sent', 'to approve', 'purchase']:
                rec.generate_section_lines()
        return res

    def generate_section_lines(self):
        """"
        Function to generate sections for each line of the purchase order
        The point is to print in the sections the delivery address for each Destination,
         grouping the order_lines by destination
        """
        self.ensure_one()
        stock_env = self.env['stock.warehouse']
        sequence = 10
        if self.order_line:
            lines = self.order_line.filtered(lambda l: l.display_type != 'line_section' and l.location_dest_id)
            lines_no_dest = self.order_line.filtered(lambda l: l.display_type != 'line_section' and
                                                               not l.location_dest_id)
            lines = lines.sorted(key=lambda l: l.location_dest_id.barcode)
            locations = lines.mapped('location_dest_id')
            sections = self.order_line.filtered(lambda l: l.display_type == 'line_section')
            if sections:
                sections.unlink()
            for lct in locations:
                line_by_location = lines.filtered(lambda l: l.location_dest_id.id == lct.id)
                for line in line_by_location:
                    line.sequence = sequence
                    sequence += 1
                if line_by_location:
                    stock_warehouse = stock_env.search(['|', ('lot_stock_id', '=', lct.id),
                                                        ('wh_input_stock_loc_id', '=', lct.id)], limit=1)
                    self.create_line_section(stock_warehouse, sequence)
                    sequence += 1
            for line in lines_no_dest:
                line.sequence = sequence
                sequence += 1

    def create_line_section(self, stock_warehouse, sequence):
        """"
        Function to create a line section with the Delivery Address
        """
        order_env = self.env['purchase.order.line']
        address = 'Delivery address: {}, {}. {} CP: {}'.format(stock_warehouse.partner_id.street or '',
                                                               stock_warehouse.partner_id.city or '',
                                                               stock_warehouse.partner_id.state_id.name or '',
                                                               stock_warehouse.partner_id.zip or '')
        values_dict = {
            'display_type': 'line_section',
            'sequence': sequence,
            'order_id': self.id,
            'name': address,
            'date_planned': False,
            'location_dest_id': False,
            'account_analytic_id': False,
            'analytic_tag_ids': [[6, False, []]],
            'product_qty': 0,
            'qty_received_manual': 0,
            'qty_received': 0,
            'product_uom': False,
            'product_packaging_qty': 0,
            'product_packaging_id': False,
            'price_unit': 0,
            'taxes_id': [[6, False, []]]
        }
        if 'product_id' in self:
            values_dict.update({'product_id': False})
        if 'product_template_id' in self:
            values_dict.update({'product_template_id': False})
        order_env.create(values_dict)


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    is_reception = fields.Boolean(
        string='Is Reception'
    )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _update_picking_from_group_key(self, key):
        """The picking is updated with data from the grouping key.
        This method is designed for extensibility, so that other modules
        can store more data based on new keys."""
        super(StockPicking, self)._update_picking_from_group_key(key)
        for rec in self:
            for key_element in key:
                if "location_dest_id" in key_element.keys() and key_element["location_dest_id"]:
                    picking_type = self.env['stock.picking.type'].search(
                        [('default_location_dest_id', '=', key_element["location_dest_id"].id),
                         ('is_reception', '=', True)], limit=1)
                    if picking_type and picking_type != rec.picking_type_id:
                        rec.picking_type_id = picking_type
                        rec.name = rec.picking_type_id.sequence_id.next_by_id()
        return False
