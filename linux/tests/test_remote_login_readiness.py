"""Readiness is evidence, never a substitute for a headless greeter test."""
import copy
import unittest

from monitorize.platform.remote_login_readiness import evaluate_readiness


class RemoteLoginReadinessTest(unittest.TestCase):
    def setUp(self):
        self.facts = dict(
            manager='plasmalogin.service', manager_active=True,
            manager_version='plasma-login-manager-6.7.5', module=True,
            bootstrap=True, seat='seat0', greeter=True,
            connectors=[dict(name='card7-Virtual-2', monitorize=True,
                             status='connected', enabled='enabled',
                             edid_valid=True, modes=['1920x1080'])],
            kms_capability=True, input_access=True, render_access=True,
            identity_access=True, encoder_verified=None,
            framebuffer_verified=None,
        )

    def report(self, **changes):
        facts = copy.deepcopy(self.facts)
        facts.update(changes)
        return evaluate_readiness(facts)

    def check(self, name, **changes):
        return next(item for item in self.report(**changes)['checks'] if item['name'] == name)

    def test_absent_module_is_failure(self):
        self.assertEqual(self.check('vkms_module', module=False)['status'], 'FAIL')

    def test_disconnected_connector_is_not_ready(self):
        self.facts['connectors'][0]['status'] = 'disconnected'
        self.assertEqual(self.check('vkms_output')['status'], 'FAIL')

    def test_connected_without_framebuffer_is_not_capture_proof(self):
        self.assertEqual(self.check('framebuffer')['status'], 'UNKNOWN')
        self.assertFalse(self.report()['ready'])

    def test_wrong_seat_fails(self):
        self.assertEqual(self.check('seat', seat='seat1')['status'], 'FAIL')

    def test_missing_capability_explains_remedy(self):
        result = self.check('kms_capability', kms_capability=False)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('setcap', result['detail'])

    def test_inaccessible_identity_needs_boot_accessible_state(self):
        result = self.check('identity_access', identity_access=False)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('boot-accessible', result['detail'])

    def test_encoder_cannot_be_inferred_from_render_node(self):
        self.assertEqual(self.check('encoder')['status'], 'UNKNOWN')
        self.assertEqual(self.check('encoder', encoder_verified=False)['status'], 'FAIL')

    def test_missing_greeter_during_desktop_is_unknown(self):
        self.assertEqual(self.check('greeter', greeter=False)['status'], 'UNKNOWN')

    def test_physical_outputs_do_not_count_as_vkms(self):
        self.assertEqual(self.check('vkms_output', connectors=[dict(
            name='card0-eDP-1', monitorize=False, status='connected',
            enabled='enabled', edid_valid=True, modes=['1920x1080'])])['status'], 'FAIL')

    def test_unknown_manager_is_not_approved(self):
        self.assertEqual(self.check('display_manager', manager='gdm.service')['status'], 'UNKNOWN')

    def test_permission_denied_is_unknown_not_missing(self):
        for field, name in [('module', 'vkms_module'), ('bootstrap', 'vkms_bootstrap'),
                            ('input_access', 'input_access')]:
            self.assertEqual(self.check(name, **{field: None})['status'], 'UNKNOWN')

    def test_live_proof_remains_separate_even_with_static_passes(self):
        report = self.report(framebuffer_verified=True, encoder_verified=True)
        self.assertFalse(report['ready'])
        self.assertEqual(report['live_validation'], 'REQUIRED')
