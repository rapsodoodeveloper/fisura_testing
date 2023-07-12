# -*- coding: utf-8 -*-
# Part of Aselcis. See LICENSE file for full copyright and licensing details.

import re
import datetime
from functools import partial
from odoo.tools.misc import formatLang
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ImpFechFact(models.Model):
    _name = 'imp.fech.fact'

    factura = fields.Float('Factura',size=256)
    fecha = fields.Float('Fecha',size=256)
    error = fields.Float('Error',size=256)

    def create(vals):
        inv = self.env['account.invoice']
        per = self.env['account.period']
        vals['error'] = ''

        if not 'factura' or not 'fecha' in vals:
            vals['error'] = 'Faltan datos'
        else:
            fecha = vals['fecha']
            invs = inv.search([('number','=',vals['factura'])])
            period = per.search([('date_start','<=',str(fecha)),('date_stop','>=',str(fecha))], limit=1)

            if len(invs)<1:
                vals['error'] = 'No existe la factura'
            else:
                inv.write({'date_invoice':fecha,'date_due':fecha,'period_id':period})

                mov = inv.move_id

                mov.write({'date':fecha, 'period_id':period})

                for lin in mov.line_id:
                    if lin.name == '/':
                        lin.write({'date_maturity':fecha})

        res = super(imp_fech_fact,self).create(vals)

        return res


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    p_org = fields.Float('Precio origen')
    p_usd = fields.Float('Precio USD')
    perct_arancel = fields.Float('% Arancel')


class ImpPrecioProd(models.Model):
    _name = 'imp.precio.prod'
    _description = 'Import Precio Producto'

    ref = fields.Char('Referencia producto', size=64)
    name = fields.Char('Nombre producto', size=64)
    precio_origen = fields.Float('Precio origen')
    precio_usd = fields.Float('Precio USD')
    error = fields.Char('No existe el producto', size=64)

    #Ya existe un onchange sobre la cuenta bancaria, lo sobreescribe
    def create(self, vals):
        res = super(ImpPrecioProd, self).create(vals)
        prod_obj = self.env['product.template']
        prod = False

        if 'ref' in vals:
            prod = prod_obj.search([('default_code','=',vals['ref'])], limit=1)

        if not prod and 'name' in vals:
            prod = prod_obj.search([('name','=',vals['name'])], limit=1)

        porg = 'precio_origen' in vals and vals['precio_origen'] or ''
        pusd = 'precio_usd' in vals and vals['precio_usd'] or ''

        if prod:
            prod_obj.write(prod,{'p_org':porg,'p_usd':pusd})
            self.unlink(res)
        else:
            self.write(res,{'error':'No se encuentra el producto'})       

        return res   
    

class ProductTemplatePvp(models.Model):
    _name = 'product.template.pvp'
    
    ref = fields.Char('Reference', size=1024)
    pvp = fields.Float('Pvp')

    def tramitar(self):
        for precio in self.search([]):
            prod = self.env['product.template'].search([('default_code','=',precio.ref)], limit=1)

            if prod:
                prod.write({'precio_pvp':precio.pvp})
                precio.unlink()
            
        return True


#Esta clase es donde van a cargarse inicialmente las columnas, sin más informacion
#Pretrata los datos para crear lineas y pedidos excel que se puedan importar más directamente
class LineasExcel(models.Model):
    _name = 'lineas.excel'
    
    col1 = fields.Char('Columna 1', size=1024)
    col2 = fields.Char('Columna 2', size=1024)
    col3 = fields.Char('Columna 3', size=1024)
    col4 = fields.Char('Columna 4', size=1024)
    col5 = fields.Char('Columna 5', size=1024)
    col6 = fields.Char('Columna 6', size=1024)
    col7 = fields.Char('Columna 7', size=1024)
    col8 = fields.Char('Columna 8', size=1024)
    col9 = fields.Char('Columna 9', size=1024)
    col10 = fields.Char('Columna 10', size=1024)

    def tramitar(self):
        ''' Este metodo realiza el trabajo de pretratado. Revisa cada linea e identifica que contiene
        '''
        #Crea el pedido de excel para ir rellenandolo
        pedido = self.env['lineas.excelpedidos'].create(vals={})
        
        #Variables de control
        date, payment, vat, deliver, notes, phone, email, EAN = False, False, False, False, False, False, False, False
        client = {}
        
        # Carga todas las lineas. Cuando encuentra para que vale, procesa y salta
        for linea in self.search([]):
            #Despues de encontrar la linea de las cabeceras, todo son lineas de pedido
            if EAN:
                self._read_ean(linea, pedido)
                continue
                
            #Comprueba si es la linea de fecha (2)
            if not date and linea.col2 == 'Order Date':
                self._read_date(linea, pedido)
                date = True
                continue
            
            #Comprueba si es la linea de método de pago (7)
            if not payment and linea.col7 == 'Payment Method':
                self._read_payment(linea, pedido)
                payment = True
                continue
                        
            #Comprueba si es la linea del VAT (7)
            if not vat and linea.col7 == 'VAT Number':
                if linea.col8:
                    client['vat'] = (linea.col8).strip()
                    vat = True
                    continue
            
            #Comprueba si es la linea dirección de entrega (cliente?) (2)
            if not deliver and linea.col2 == 'Delivery Address':
                client['delivery'] = self._read_deliver(linea, pedido)
                deliver = True
                continue
            
            #Comprueba si existen notas (delivery resquests) (2)
            if not notes and linea.col2 == 'Delivery Requests':
                self._read_notes(linea, pedido)
                notes = True
                continue
            
            #Comprueba el telefono (2)
            if not phone and linea.col2 == 'Tel':
                client['phone'] = linea.col3
                phone = True
                continue
            
            #Comprueba el email (2)
            if not email and linea.col2 == 'E-Mail':
                client['email'] = (linea.col3).strip()
                email = True
                continue
            
            #Comprueba si llega un EAN (3 a partir de la fila que ponga EAN)
            if not EAN and linea.col3 == 'EAN':
                EAN = True
                continue

        cliente = self.buscar_cliente(client, pedido)
        client = cliente.get('values')
        
        #Idioma
        idioma = client.lang
        idioma_id = self.env['res.lang'].search([('code', 'ilike', idioma)], limit=1)
        pedido.write({'cliente': client.id, 'tarifa': client.property_product_pricelist.id, 'idioma': idioma_id})
        #Borra todas las lineas
        self.search([]).unlink()
        if cliente.get('created', False):
            return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'name': 'Warning',
            'params': {
                   'title': 'Se ha creado el cliente',
                   'text': 'Revise los datos del cliente antes de crear el pedido.',
                   'sticky': True
                    }
                }

    #Leer la fecha
    def _read_date(self, linea, pedido):
        date = linea.col3
        if self.validar_fecha(date):
            pedido.write({'fecha_pedido': date})
    
    #Leer el pago
    def _read_payment(self, linea, pedido):
        payment_name = linea.col8
        #intenta encontrar el método de pago
        payment = self.env['account.payment.term'].search([('name', 'ilike', payment_name)], limit=1)
        if payment:
            pedido.write({'payment':payment.id})
   
    #Leer la linea de entrega
    def _read_deliver(self, linea, pedido):
        #Varias lineas a leer
        retailor = self.search([('col2', '=', 'Retailer')], limit=1)
        if retailor and retailor.col3:
            return {'name': retailor.col3, 'direc1': linea.col6, 'direc2': linea.col7, 'cp': linea.col8, 'city': linea.col9, 'country': linea.col10}
        else:
            return {'name': linea.col3, 'direc1': linea.col6, 'direc2': linea.col7, 'cp': linea.col8, 'city': linea.col9, 'country': linea.col10}

    #Leer las notas
    def _read_notes(self, linea, pedido):
        notes = linea.col3
        pedido.write({'notes': notes})
    
    #Leer las lineas de pedido
    def _read_ean(self, linea, pedido):
        ean = linea.col3
        if ean:
            ean = ean.strip()
        vals = {'sku': linea.col2,
                'ean': ean,
                'product': linea.col4,
                'price': linea.col6,
                'quantity': linea.col7,
                'dto': linea.col9,
                'pedido': pedido.id
                }
        self.env['lineas.excellineas'].create(vals)
    
    #Busca el cliente
    def buscar_cliente(self, cliente, pedido):
        obj_client = self.env['res.partner']

        created = False
        #Primera busca por el VAT
        client = 'vat' in cliente and obj_client.search([('vat', '=', cliente['vat'])], limit=1) or False
        
        '''if not client:
            #Si no lo ha encontrado, lo intenta por email
            client = obj_client.search(cr, uid, [('email', '=', cliente['email'])])'''
        if not client:
            if not cliente.get('delivery').get('direc1') and not cliente.get('delivery').get('direc2'):
                raise UserError(_("Falta la dirección del cliente "+(cliente['delivery']['name'] or '')))
            if len(cliente['delivery']['direc1'])>40 or len(cliente['delivery']['direc2'])>40:
                raise UserError(_("Revise la dirección del cliente, excede de 40 caracteres"))
            #No esta en el sistema, lo crea
            country_id = self.env['res.country'].search([('name', '=', cliente['delivery']['country'])])
            vals = {'name': cliente['delivery']['name'],
                    'city': cliente['delivery']['city'],
                    'email': cliente['email'],
                    'phone': cliente['phone'],
                    'street': cliente['delivery']['direc1'],
                    'street2': cliente['delivery']['direc2'],
                    'vat': 'vat' in cliente and cliente['vat'] or '',
                    'zip': cliente['delivery']['cp'],
                    #no saltar avisos por no meter los datos
                    # 'per_wr':True,
                    }
    
            client = obj_client.create(vals)
            created = True
        
        res = {'created': created, 'values':client}
        return res
    
    #Valida la fecha
    def validar_fecha(self, fecha):
        if fecha and '-' in fecha:
        #Intenta validar, si hay caracteres no validos, error
            try:
                dat = fecha.split('-')

                if len(dat)==3 and int(dat[0]) <= 31 and int(dat[1]) <= 12:
                    return fecha
                else:
                    return False
            except:
                return False

#Esta clase contiene las lineas de los pedidos
class LineasExcellineas(models.Model):
    _name = 'lineas.excellineas'

    sku = fields.Char('SKU', size=256)
    ean = fields.Char('EAN',size=256)
    product = fields.Char('Producto', size=1024)
    price = fields.Char('Precio',size=256)
    dto = fields.Char('Descuento',size=256)
    quantity = fields.Char('Cantidad', size=256)
    pedido = fields.Many2one('lineas.excelpedidos', 'Pedido', ondelete="cascade")
    error = fields.Boolean('Errores')

    # Busca el producto de esa linea y devuelve el ID. Devuelve -1 si no encuentra el producto
    def buscar_producto(self, linea):
        id_pro = False
        #Si es transporte, devuelve el producto transporte
        if linea.sku == 'TRANSP':
            id_pro = self.env['product.product'].search([('name', 'ilike', 'Gastos de transporte')], limit=1)
        else:
            if linea.ean:
                id_pro = self.env['product.product'].search([('product_tmpl_id.barcode', '=', linea.ean)], limit=1)
        if id_pro:
            return id_pro
        else:
            return -1


#Esta clase almacena la informacion de los pedidos de venta. Desde aqui se tramitan para crearlos            
class LineasExcelpedidos(models.Model):
    _name = 'lineas.excelpedidos'

    name = fields.Char('Nombre', size=256)
    num_pedido = fields.Char('Nº pedido',size=256)
    fecha_pedido = fields.Char('Fecha de pedido', size=256)
    lineas = fields.One2many('lineas.excellineas', 'pedido', 'Lineas')
    cliente = fields.Many2one('res.partner', 'Cliente')
    comercial = fields.Many2one('res.users', 'Comercial')
    payment = fields.Many2one('account.payment.term', 'Pago')
    error = fields.Boolean('Errores')
    notes = fields.Char('Notas', size=512)
    tarifa = fields.Many2one('product.pricelist', 'Tarifa')
    idioma = fields.Many2one('res.lang', 'Idioma')

    @api.constrains('fecha_pedido')
    def _check_date(self):
        try:
            datetime.datetime.strptime(self.fecha_pedido, '%Y/%m/%d')
        except ValueError:
            raise UserError(_("Incorrect data format, should be YYYY/MM/DD"))

    #Crea los pedidos registrados y sus lineas
    def crear_pedidos(self):
        inv_obj = self.env['product.template']
        
        #Si existe algun error, cambia a true
        any_error = False
        
        #Recorre cada ID
        for pedido in self.search([]):
            #pedido sin stock
            pedido_ss = False
            ss_id = False

            if not pedido.fecha_pedido:
                 raise UserError(_("Falta la feha del pedido de "+(pedido.cliente and pedido.cliente.name or '<sin cliente>')+"!!!"))
            
            self.env.context = dict(self.env.context)
            self.env.context.update({'lang': pedido.idioma.code})
            
            try:
                date_order = datetime.datetime.strptime(pedido.fecha_pedido, "%Y/%m/%d")
            except Exception:
                raise UserError(_("El campo de fecha de pedido no coincide con el formato de fecha Debes agregarlo en formato 'YYYY/MM/DD'."))
            #Primero crea el pedido si no existe
            id_ped = self.env['sale.order'].search([('name', '=', pedido.num_pedido)], limit=1)
            if not id_ped:
                #Variables
                vals_pedido = { 'partner_invoice_id': pedido.cliente.id,
                                'partner_shipping_id': pedido.cliente.id,
                                'date_order': date_order,
                                'partner_id': pedido.cliente.id,
                                'note': pedido.notes,
                                'pricelist_id': pedido.tarifa.id,
                                'user_id': pedido.comercial.id,
                              }
        
                try:
                    id_ped = self.env['sale.order'].create(vals_pedido)
                except Exception as e:
                    raise UserError(_("%s" % str(e)))
        
                if pedido.num_pedido == '/':
                    # obj_pedido = self.env['sale.order'].browse(id_ped)
                    pedido.num_pedido = id_ped.name

            #Pone errores a 0
            pedido.error = False
            pedido_lineas = pedido.lineas.filtered(lambda line: line.product)
            #Crea cada linea. Si ocurre un error añade un cod de error y la linea no se borra
            for linea in pedido_lineas:
                #Errores a 0
                linea.error = False
                #ID del producto
                id_prod = linea.buscar_producto(linea)
                #Si es -1, el producto no existe, error
                if id_prod == -1:
                    any_error = True
                    linea.error = True
                    pedido.error = True
                    raise UserError(_("Producto no disponible, configúrelo amablemente."))
                    continue
                else:
                    #Producto
                    # name = prod.name

                    # if id_prod.description_purchase:
                        # name += '\n' + id_prod.description_purchase
                    name = id_prod.name_get()[0][1]
                    if id_prod.description_sale:
                        name += '\n'+id_prod.description_sale
                        
                    try:
                        if '%' in linea.dto:
                            dto = float((linea.dto).replace('%', ''))
                            dto = float(linea.dto.replace(',', '.'))
                        else:
                            dto = 0.0
                    except:
                        dto = 0.0
                    
                    #Caracteres raros en el precio
                    if linea.price:
                        price = linea.price
                        price =  re.sub("[^0-9,.]", "", price)
                        price = float(price.replace(',', '.'))

                    #Variables
                    vals_linea = { 'order_id': id_ped.id,
                                   'product_id': id_prod.id,
                                   'product_uom_qty': float(linea.quantity),
                                   'discount': dto,
                                   'name': name,
                                 }
                    #Para el transporte si añade el precio
                    if linea.sku == 'TRANSP':
                        vals_linea['price_unit'] = price
            
                    try:
                        id_lin = self.env['sale.order.line'].create(vals_linea)
                    except Exception as e:
                        raise UserError(_("%s" % str(e)))
                    
        #Si todo va bien, borra el pedido del listado, sino, las lineas que no hayan dado lugar a error TODO
        remove_orders = self.search([('error', '=', False)])
        remove_orders.unlink()
        remove_lines = self.env['lineas.excellineas'].search([('error', '=', False)])
        #self.pool.get('lineas.excellineas').unlink(cr, uid, remove_lines)

        #Si hubo algun error, aviso
        if any_error:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'name': 'Warning',
                'params': {
                   'title': 'Error en la importación',
                   'text': 'Se han producido errores en algunas lineas de pedido. Reviselas y vuelva a intentarlo.',
                   'sticky': False
                }
            }

    @api.model
    def create(self, vals):
        if not vals.get('num_pedido', False):
            vals['num_pedido'] = '/'
        
        #Añadir el comercial que ha cargado el pedido
        vals['comercial'] = self.env.user.id
        res = super(LineasExcelpedidos, self).create(vals)
        
        return res


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amount_untaxed_with_stock = fields.Monetary(string='Untaxed Amount With Stock', store=True, readonly=True, compute='_amount_all_with_stock')
    amount_by_group_with_stock = fields.Binary(string="Tax amount by group with Stock", compute='_amount_by_group_with_stock', help="type: [(name, amount, base, formated amount, formated base)]")
    amount_tax_with_stock = fields.Monetary(string='Taxes with Stock', store=True, readonly=True, compute='_amount_all_with_stock')
    amount_total_with_stock = fields.Monetary(string='Total with Stock', store=True, readonly=True, compute='_amount_all_with_stock')
    amount_untaxed_out_of_stock = fields.Monetary(string='Untaxed Amount Out Of Stock', store=True, readonly=True, compute='_amount_all_out_of_stock')
    amount_tax_out_of_stock = fields.Monetary(string='Taxes Out Of Stock', store=True, readonly=True, compute='_amount_all_out_of_stock')
    amount_total_out_of_stock = fields.Monetary(string='Total with Stock', store=True, readonly=True, compute='_amount_all_out_of_stock')
    amount_by_group_out_of_stock = fields.Binary(string="Tax amount by group Out Of Stock", compute='_amount_by_group_out_of_stock', help="type: [(name, amount, base, formated amount, formated base)]")



    @api.depends('order_line.price_total_with_stock')
    def _amount_all_with_stock(self):
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                if line.quantity_available >= 1:
                    amount_untaxed += line.price_subtotal_with_stock
                    amount_tax += line.price_tax_with_stock

            order.update({
                'amount_untaxed_with_stock': amount_untaxed,
                'amount_tax_with_stock': amount_tax,
                'amount_total_with_stock': amount_untaxed + amount_tax,
            })

    @api.depends('order_line.price_subtotal_out_of_stock')
    def _amount_all_out_of_stock(self):
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                if line.quantity_available <= 0 or line.product_uom_qty > line.product_id.qty_available:
                    amount_untaxed += line.price_subtotal_out_of_stock
                    amount_tax += line.price_tax_out_of_stock

            order.update({
                'amount_untaxed_out_of_stock': amount_untaxed,
                'amount_tax_out_of_stock': amount_tax,
                'amount_total_out_of_stock': amount_untaxed + amount_tax,
            })

    def _amount_by_group_with_stock(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            fmt = partial(formatLang, self.with_context(lang=order.partner_id.lang).env, currency_obj=currency)
            res = {}
            for line in order.order_line:
                if line.quantity_available >= 1:
                    price_reduce = line.price_unit * (1.0 - line.discount / 100.0)
                    taxes = line.tax_id.compute_all(price_reduce, quantity=line.quantity_available, product=line.product_id, partner=order.partner_shipping_id)['taxes']
                    for tax in line.tax_id:
                        group = tax.tax_group_id
                        res.setdefault(group, {'amount': 0.0, 'base': 0.0})
                        for t in taxes:
                            if t['id'] == tax.id or t['id'] in tax.children_tax_ids.ids:
                                res[group]['amount'] += t['amount']
                                res[group]['base'] += t['base']
            res = sorted(res.items(), key=lambda l: l[0].sequence)
            order.amount_by_group_with_stock = [(
                l[0].name, l[1]['amount'], l[1]['base'],
                fmt(l[1]['amount']), fmt(l[1]['base']),
                len(res),
            ) for l in res]

    def _amount_by_group_out_of_stock(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            fmt = partial(formatLang, self.with_context(lang=order.partner_id.lang).env, currency_obj=currency)
            res = {}
            for line in order.order_line:
                if line.quantity_available <= 0 or line.product_uom_qty > line.product_id.qty_available:
                    out_quantity = line.product_uom_qty - line.quantity_available
                    price_reduce = line.price_unit * (1.0 - line.discount / 100.0)
                    taxes = line.tax_id.compute_all(price_reduce, quantity=out_quantity, product=line.product_id, partner=order.partner_shipping_id)['taxes']
                    for tax in line.tax_id:
                        group = tax.tax_group_id
                        res.setdefault(group, {'amount': 0.0, 'base': 0.0})
                        for t in taxes:
                            if t['id'] == tax.id or t['id'] in tax.children_tax_ids.ids:
                                res[group]['amount'] += t['amount']
                                res[group]['base'] += t['base']
            res = sorted(res.items(), key=lambda l: l[0].sequence)
            order.amount_by_group_out_of_stock = [(
                l[0].name, l[1]['amount'], l[1]['base'],
                fmt(l[1]['amount']), fmt(l[1]['base']),
                len(res),
            ) for l in res]
            

    def update_stock_available_quantity(self):
        if self.state in ['draft','sent']:
            for line in self.order_line:
                line._compute_quantity_available()
                line._compute_amount_with_stock()
                line._compute_amount_out_of_stock()
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    price_subtotal_with_stock = fields.Monetary(compute='_compute_amount_with_stock', string='Subtotal with stock', readonly=True)
    price_tax_with_stock = fields.Float(compute='_compute_amount_with_stock', string='Total Tax with stock', readonly=True)
    price_total_with_stock = fields.Monetary(compute='_compute_amount_with_stock', string='Total with stock', readonly=True)
    quantity_available = fields.Float(string='Quantity Available', store=True, compute='_compute_quantity_available')
    price_subtotal_out_of_stock = fields.Monetary(compute='_compute_amount_out_of_stock', string='Subtotal Out Of stock', readonly=True)    
    price_tax_out_of_stock = fields.Float(compute='_compute_amount_out_of_stock', string='Total Tax Out Of stock', readonly=True)
    price_total_out_of_stock = fields.Monetary(compute='_compute_amount_out_of_stock', string='Total Out Of stock', readonly=True)

    @api.depends('product_uom_qty')
    def _compute_quantity_available(self):
        product_list = []
        for line in self:
            line.quantity_available = 0.0
            dict_product = {}
            product_on_hand = 0.0
            warehouse_ids = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)])
            for warehouse_id in warehouse_ids:
                product_on_hand += self.env['stock.quant']._get_available_quantity(product_id=line.product_id, location_id=warehouse_id.lot_stock_id, lot_id=None, package_id=None, owner_id=None, strict=True, allow_negative=False)
            for product in product_list:
                if product['product'] == line.product_id.id:
                    product_on_hand -= product['quantity']
            if product_on_hand >= 1:
                if product_on_hand >= line.product_uom_qty:
                    dict_product.update(
                        product=line.product_id.id,
                        quantity=line.product_uom_qty
                    )
                    line.quantity_available = line.product_uom_qty
                else:
                    dict_product.update(
                        product=line.product_id.id,
                        quantity=product_on_hand
                    )
                    line.quantity_available = product_on_hand
                product_list.append(dict_product)
            

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount_with_stock(self):
        """
        Compute the amounts of the SO line For Stock available Products.
        """
        for line in self:
            line.price_tax_with_stock = 0.0
            line.price_total_with_stock = 0.0
            line.price_subtotal_with_stock = 0.0
            if line.quantity_available >= 1:
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.quantity_available, product=line.product_id, partner=line.order_id.partner_shipping_id)
                line.update({
                    'price_tax_with_stock': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                    'price_total_with_stock': taxes['total_included'],
                    'price_subtotal_with_stock': taxes['total_excluded'],
                })
                if self.env.context.get('import_file', False) and not self.env.user.user_has_groups('account.group_account_manager'):
                    line.tax_id.invalidate_cache(['invoice_repartition_line_ids'], [line.tax_id.id])


    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount_out_of_stock(self):
        """
        Compute the amounts of the SO line For Stock not available Products.
        """
        for line in self:
            line.price_tax_out_of_stock = 0.0
            line.price_total_out_of_stock = 0.0
            line.price_subtotal_out_of_stock = 0.0
            if line.quantity_available <= 0 or line.product_uom_qty > line.product_id.qty_available:
                out_quantity = line.product_uom_qty - line.quantity_available
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                taxes = line.tax_id.compute_all(price, line.order_id.currency_id, out_quantity, product=line.product_id, partner=line.order_id.partner_shipping_id)
                line.update({
                    'price_tax_out_of_stock': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                    'price_total_out_of_stock': taxes['total_included'],
                    'price_subtotal_out_of_stock': taxes['total_excluded'],
                })
                if self.env.context.get('import_file', False) and not self.env.user.user_has_groups('account.group_account_manager'):
                    line.tax_id.invalidate_cache(['invoice_repartition_line_ids'], [line.tax_id.id])
