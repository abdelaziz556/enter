# Part of Odoo. See LICENSE file for full copyright and licensing details.
from freezegun import freeze_time

from odoo import Command
from odoo.tests import Form
from odoo.addons.mrp_account.tests.test_analytic_account import TestMrpAnalyticAccount


class TestMrpAnalyticAccountHr(TestMrpAnalyticAccount):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workcenter.write({
            'allow_employee': True,
            'employee_ids': [
                Command.create({
                    'name': 'Arthur Fu',
                    'pin': '1234',
                    'hourly_cost': 100,
                }),
                Command.create({
                    'name': 'Thomas Nific',
                    'pin': '5678',
                    'hourly_cost': 200,
                })
            ]
        })
        cls.employee1 = cls.env['hr.employee'].search([
            ('name', '=', 'Arthur Fu'),
        ])
        cls.employee2 = cls.env['hr.employee'].search([
            ('name', '=', 'Thomas Nific'),
        ])

    def test_mrp_employee_analytic_account(self):
        """Test when a wo requires employees, both aa lines for employees and for
        workcenters are correctly posted.
        """
        mo_form = Form(self.env['mrp.production'])
        mo_form.product_id = self.product
        mo_form.bom_id = self.bom
        mo_form.product_qty = 1.0
        mo_form.analytic_account_id = self.analytic_account
        mo = mo_form.save()
        mo.action_confirm()
        with freeze_time('2027-10-01 10:00:00'):
            mo.workorder_ids.start_employee(self.employee1.id)
            mo.workorder_ids.start_employee(self.employee2.id)
            self.env.flush_all()   # need flush to trigger compute
        with freeze_time('2027-10-01 11:00:00'):
            mo.workorder_ids.stop_employee(self.employee1.id)
            mo.workorder_ids.stop_employee(self.employee2.id)
            self.env.flush_all()   # need flush to trigger compute

        employee1_aa_line = mo.workorder_ids.employee_analytic_account_line_ids.filtered(lambda l: l.employee_id == self.employee1)
        employee2_aa_line = mo.workorder_ids.employee_analytic_account_line_ids.filtered(lambda l: l.employee_id == self.employee2)
        self.assertEqual(employee1_aa_line.amount, -100.0)
        self.assertEqual(employee2_aa_line.amount, -200.0)
        self.assertEqual(mo.workorder_ids.mo_analytic_account_line_id.amount, -10.0)
        self.assertEqual(employee1_aa_line.account_id, self.analytic_account)
        self.assertEqual(employee2_aa_line.account_id, self.analytic_account)
        new_account = self.env['account.analytic.account'].create({
            'name': 'test_analytic_account_change',
            'plan_id': self.analytic_plan.id,
        })
        mo.analytic_account_id = new_account
        self.assertEqual(employee2_aa_line.account_id, new_account)
        self.assertEqual(employee1_aa_line.account_id, new_account)

    def test_mrp_analytic_account_without_workorder(self):
        """
        Test adding an analytic account to a confirmed manufacturing order without a work order.
        """
        product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
        })
        component = self.env['product.product'].create({
            'name': 'Test  Component',
            'type': 'product',
        })
        mo_form = Form(self.env['mrp.production'])
        mo_form.product_id = product
        mo_form.product_qty = 1.0
        with mo_form.move_raw_ids.new() as move:
            move.product_id = component
            move.product_uom_qty = 1
        mo = mo_form.save()
        mo.action_confirm()
        self.assertEqual(mo.state, 'confirmed')

        mo.analytic_account_id = self.analytic_account
        self.assertEqual(mo.analytic_account_id, self.analytic_account)

        mo_form = Form(mo)
        mo_form.qty_producing = 1.0
        mo = mo_form.save()
        mo.button_mark_done()
        self.assertEqual(mo.state, 'done')

    def test_mrp_analytic_account_with_workorder(self):
        """
        Test adding an analytic account to a confirmed manufacturing order with work orders.
        """
        # add a workorder to the BoM
        self.bom.write({
            'operation_ids': [(0, 0, {
                    'name': 'Test Operation 2',
                    'workcenter_id': self.workcenter.id,
                    'time_cycle': 60,
                })
            ]
        })
        mo_form = Form(self.env['mrp.production'])
        mo_form.product_id = self.product
        mo_form.bom_id = self.bom
        mo_form.product_qty = 1.0
        mo = mo_form.save()
        mo.action_confirm()
        self.assertEqual(mo.state, 'confirmed')

        # set the workcenter to not "Requires Log In" to start the timer in WO and create "mrp.workcenter.productivity"
        self.workcenter.allow_employee = False

        # start the workorders
        mo.workorder_ids[0].button_start()
        mo.workorder_ids[1].button_start()
        self.assertEqual(mo.workorder_ids[0].state, 'progress')
        self.assertTrue(mo.workorder_ids[0].time_ids)
        self.assertEqual(mo.workorder_ids[1].state, 'progress')
        self.assertTrue(mo.workorder_ids[1].time_ids)

        mo.analytic_account_id = self.analytic_account
        self.assertEqual(mo.analytic_account_id, self.analytic_account)

        mo_form = Form(mo)
        mo_form.qty_producing = 1.0
        mo = mo_form.save()
        mo.button_mark_done()
        self.assertEqual(mo.state, 'done')
