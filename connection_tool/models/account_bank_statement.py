# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, registry, _, SUPERUSER_ID, tools


_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    @api.multi
    def assert_balanced(self):
        if not self.ids:
            return True
        ctx = self._context
        if ctx.get('ConnectionTool', False) == True:
            return True
        else:
            return super(AccountMove, self).assert_balanced()
        return True


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_import_id = fields.Many2one('account.account', string='Adjustment Account (import)')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    @api.one
    @api.depends('company_id')
    def _get_account_import_id(self):
        self.account_import_id = self.company_id.account_import_id

    @api.one
    def _set_account_import_id(self):
        if self.account_import_id != self.company_id.account_import_id:
            self.company_id.account_import_id = self.account_import_id

   
    account_import_id = fields.Many2one('account.account', compute='_get_account_import_id', inverse='_set_account_import_id', required=False,
        string='Adjustment Account (import)', help="Adjustment Account (import).")


class AccountBankStatement(models.Model):
    _inherit = "account.bank.statement"

    def getAnalyticTagIdsTransactions(self, concepto_transaccion, conreplace=""):
        ctx = {}
        AccountAnalytic = self.env["account.analytic.account"]
        Tag = self.env["account.analytic.tag"]

        analytic_id, tag_id, code = None, None, ""
        concepto = concepto_transaccion.replace(conreplace, "")
        c3 = concepto[0:3].zfill(4)
        c2 = concepto[0:2].zfill(4)
        c1 = concepto[0:1].zfill(4)
        if c3.isdigit():
            code = "L%s"%c3
        elif c2.isdigit():
            code = "L%s"%c2
        elif c1.isdigit():
            code = "L%s"%c1
        analytic_id = AccountAnalytic.search_read([("code", "=", code)], fields=["name"])
        tag_id = Tag.search_read([("code", "=", code)], fields=["name", "code"])
        if(analytic_id or tag_id):
            ctx = {
                "tag_id": tag_id and tag_id[0].get("id") or False,
                "analytic_id": analytic_id and analytic_id[0]["id"] or False,
                "import_etl": True
            }
        return ctx

    def getProcessBankStatementLine(self):
        statementLines = self.env['account.bank.statement.line']

        Account = self.env["account.account"]
        LayoutLine = self.env['bank.statement.export.layout.line']
        AccountMoveLine = self.env['account.move.line']
        Afiliation = self.env["account.bank.afiliation"]
        AccountAnalytic = self.env["account.analytic.account"]
        Tag = self.env["account.analytic.tag"]

        self._end_balance()

        codigos = {
            1: {
                "C07": "1010101",
                "C19": "4900101",
                "C72": "1010101",
                "C76": "1010101",
                "C77": "1010101",
                "I01": "1010101",
                "I02": "1020001",
                "I72": "1010101",
                "T17": "1010101",
                "T20": "1010101",
                "T09": "1010101",
                "T91": "1010101",
                "V01": "1010101",
                "V02": "5990100",
                "V03": "1200004",
                "V09": "5990100",
                "V10": "1200004",
                "V40": "5990100",
                "V41": "1200004",
                "V42": "1010101",
                "V43": "5990100",
                "V44": "1200004",
                "V45": "1010101",
                "V46": "5990100",
                "V47": "1200004",
                "W02": "1010101",
                "W05": "5990100",
                "W06": "1200004",
                "W19": "5990100",
                "W20": "1200004",
                "W41": "1010101",
                "W83": "5990100",
                "W84": "1200004",
                "W85": "5990100",
                "W86": "1200004",
                "Y01": "1010101",
                "Y02": "1010101",
                "Y15": "1010101",
                "Y16": "1010101",
            },
            2: {
                "C07": "1010101",
                "C19": "1030900", # "4900101",
                "C20": "1030900",
                "C72": "1010101",
                "C76": "1010101",
                "C77": "1010101",
                "I01": "1010101",
                "I02": "1020001",
                "I72": "1010101",
                "T17": "1010101",
                "T20": "1010101",
                "T09": "1010101",
                "T91": "1010101",
                "V01": "1010101",
                "V02": "5990100",
                "V03": "1200004",
                "V09": "5990100",
                "V10": "1200004",
                "V40": "5990100",
                "V41": "1200004",
                "V42": "1010101",
                "V43": "5990100",
                "V44": "1200004",
                "V45": "1010101",
                "V46": "5990100",
                "V47": "1200004",
                "W02": "1010101",
                "W05": "5990100",
                "W06": "1200004",
                "W19": "5990100",
                "W20": "1200004",
                "W41": "1010101",
                "W83": "5090901", #"5990100",
                "W84": "1200004",
                "W85": "5090901", #"5990100",
                "W86": "1200004",
                "Y01": "1010101",
                "Y02": "1010101",
                "Y15": "1010101",
                "Y16": "1010101",
            }
        }

        # line_ids
        ctx = dict(self._context, force_price_include=False)
        for st_line in self.line_ids:
            if st_line.journal_entry_ids:
                continue

            folioOdoo = st_line.ref and st_line.ref[:10] or ''
            account_id = False

            res = False
            for layoutline_id in LayoutLine.search_read([
                        ('name', '=', folioOdoo)
                    ], fields=['id', 'name', 'cuenta_cargo', 'cuenta_abono', 'motivo_pago', 'referencia_numerica', 'layout_id', 'movel_line_ids', 'partner_id', 'importe']
                ):
                movel_line_ids = layoutline_id.get('movel_line_ids') and layoutline_id['movel_line_ids'] or []
                move_lines = AccountMoveLine.browse(movel_line_ids)
                line_residual = st_line.currency_id and st_line.amount_currency or st_line.amount
                line_currency = st_line.currency_id or st_line.journal_id.currency_id or st_line.company_id.currency_id
                total_residual = move_lines and sum(aml.currency_id and aml.amount_residual_currency or aml.amount_residual for aml in move_lines) or 0.0
                balance = total_residual - line_residual
                open_balance_dicts = []
                counterpart_aml_dicts = []
                amount_total = abs(line_residual)
                payment_aml_rec = self.env['account.move.line']
                for aml in move_lines:
                    if aml.full_reconcile_id:
                        continue
                    if aml.account_id.internal_type == 'liquidity':
                        payment_aml_rec |= aml
                    else:
                        amount = aml.currency_id and aml.amount_residual_currency or aml.amount_residual
                        if amount_total >= abs(amount):
                            amount_total -= abs(amount)
                            counterpart_aml_dicts.append({
                                'name': aml.name if aml.name != '/' else aml.move_id.name,
                                'debit': amount < 0 and -amount or 0,
                                'credit': amount > 0 and amount or 0,
                                'move_line': aml,
                            })
                        else:
                            counterpart_aml_dicts.append({
                                'name': aml.name if aml.name != '/' else aml.move_id.name,
                                'debit': balance < 0 and -balance or 0,
                                'credit': balance > 0 and balance or 0,
                                'move_line': aml,
                            })
                res = st_line.with_context(ctx).process_reconciliation(counterpart_aml_dicts, payment_aml_rec, open_balance_dicts)
            if res:
                continue

            codigo = codigos.get( st_line.company_id.id ) or codigos.get(1)
            transaccion = st_line.note.split("|")
            codigo_transaccion = transaccion and transaccion[0] or ""
            concepto_transaccion = transaccion and transaccion[1] or ""
            if (codigo_transaccion in codigo):
                for account_id in Account.search_read([('code_alias', 'ilike', codigo[codigo_transaccion]), ('company_id', '=', st_line.company_id.id)], fields=["name"]):
                    st_line.account_id = account_id.get("id")

                if codigo_transaccion == "T20":
                    ctx = { "import_etl": True }
                    st_line.with_context(ctx).fast_counterpart_creation()
                    continue

                if codigo_transaccion in ["Y01", "Y15"]:
                    ctx = self.getAnalyticTagIdsTransactions(concepto_transaccion, conreplace="CE662143")
                    _logger.info("------ codigo_transaccion- %s - %s "%(codigo_transaccion, ctx) )
                    if ctx:
                        st_line.with_context(ctx).fast_counterpart_creation()


                if codigo_transaccion in ["Y16"]:
                    ctx = self.getAnalyticTagIdsTransactions(concepto_transaccion, conreplace="CI")
                    _logger.info("------ codigo_transaccion- %s - %s "%(codigo_transaccion, ctx) )
                    if ctx:
                        st_line.with_context(ctx).fast_counterpart_creation()

                if codigo_transaccion in ["C72"]:
                    concepto_transaccion_tmp = st_line.ref
                    ctx = self.getAnalyticTagIdsTransactions(concepto_transaccion_tmp, conreplace="CI")
                    _logger.info("------ codigo_transaccion- %s - %s "%(codigo_transaccion, ctx) )
                    if ctx:
                        st_line.with_context(ctx).fast_counterpart_creation()

                for afiliation_id in Afiliation.search_read([("name", "ilike", st_line.name)], fields=["name", "description"], limit=1):
                    for tag_id in Tag.search_read([("afiliation_id", "=", afiliation_id.get("id"))], fields=["name", "code"]):
                        analytic_id = AccountAnalytic.search([("code", "=", tag_id.get("code"))])
                        ctx = {
                            "tag_id": tag_id.get("id"),
                            "analytic_id": analytic_id and analytic_id.id or False,
                            "import_etl": True
                        }
                        st_line.with_context(ctx).fast_counterpart_creation()
                        #for account_id in Account.search_read([('code_alias', 'ilike', codigo[codigo_transaccion]), ('company_id', '=', st_line.company_id.id)], fields=["name"]):
                        #    st_line.account_id = account_id.get("id")

        return True




# C72 -- Tomar de las referencias
# Y01|CE662143 + número de sucursal LXXXX
# Y15|CE662143 + número de sucursal LXXXX
# Y16| "CI" + número de sucursal 1, 2 o 3 dígit





class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _prepare_reconciliation_move_line(self, move, amount):
        res = super(AccountBankStatementLine, self)._prepare_reconciliation_move_line(move, amount)
        if self._context.get("import_etl"):
            res["analytic_tag_ids"] = [self._context.get("tag_id")] # [(6, 0, self._context.get("tag_id"))]
            res["analytic_account_id"] = self._context.get("analytic_id")
        return res

    @api.multi
    def _prepare_move_line_for_currency(self, aml_dict, date):
        self.ensure_one()
        res = super(AccountBankStatementLine, self)._prepare_move_line_for_currency(aml_dict, date)
        if self._context.get("import_etl"):
            aml_dict["analytic_tag_ids"] = [self._context.get("tag_id")] # [(6, 0, self._context.get("tag_id"))]
            aml_dict["analytic_account_id"] = self._context.get("analytic_id")