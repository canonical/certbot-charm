# Copyright 2020 Canonical Ltd
# See LICENSE file for licensing details.

import configparser
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call

import yaml

from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness
import charm


class TestCharm(unittest.TestCase):
    def test_install(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.charm.on.install.emit()
        charm._host.install_packages.assert_called_once_with([
            "certbot",
            "python3-certbot-dns-google",
            "python3-certbot-dns-rfc2136",
            "python3-certbot-dns-route53"])
        charm._host.symlink.assert_called_once_with(
            os.path.join(harness.charm.charm_dir, "bin/deploy.py"),
            "/etc/letsencrypt/renewal-hooks/deploy/certbot-charm")

    def test_config_changed(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        config = {
            "cert-path": "/cert/path",
            "chain-path": "/chain/path",
            "combined-path": "/combined/path",
            "deploy-command": "/bin/deploy",
            "fullchain-path": "/fullchain/path",
            "key-path": "/key/path",
        }
        harness.update_config(self._config(harness.charm, **config))
        charm._host.write_config.assert_called_once()
        args = charm._host.write_config.call_args[0]
        self.assertEqual(args[0], "/etc/certbot-charm/config.ini")
        self.assertEqual(args[1], {
            'DEFAULT': {
                'cert-path': '/cert/path',
                'chain-path': '/chain/path',
                'combined-path': '/combined/path',
                'fullchain-path': '/fullchain/path',
                'key-path': '/key/path'},
            'deploy': {
                'command': '/bin/deploy'}})
        charm._host.write_file.assert_any_call(
            "/etc/certbot-charm/dns-google.json", b"", mode=0o600)
        charm._host.write_file.assert_any_call(
            "/etc/certbot-charm/dns-rfc2136.ini", b"", mode=0o600)

    def test_start_no_certificate(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        harness.charm.on.start.emit()
        self.assertEqual(harness.charm.model.unit.status,
                         BlockedStatus('certificate not yet acquired.'))

    def test_start_get_certificate(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        config = {
            "agree-tos": True,
            "domains": "example.com",
            "email": "webmaster@example.com",
            "plugin": "dns-google",
        }
        harness.update_config(self._config(harness.charm, **config))
        harness.charm.on.start.emit()
        self.assertEqual(harness.charm.model.unit.status,
                         ActiveStatus('maintaining certificate for example.com.'))

    def test_stop(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.charm.on.stop.emit()
        charm._host.unlink.assert_called_once_with(
            "/etc/letsencrypt/renewal-hooks/deploy/certbot-charm")

    def test_deploy_action(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        event = Mock(params={"domain": "example.com"})
        harness.charm._on_deploy_action(event)
        charm._host.run.assert_called_once_with(
            ["/etc/letsencrypt/renewal-hooks/deploy/certbot-charm"],
            env={"RENEWED_LINEAGE": "/etc/letsencrypt/live/example.com"})

    def test_get_certificate_action_dns_google(self):
        os.environ["JUJU_ACTION_UUID"] = "1"
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        event = Mock(params={
            "agree-tos": True,
            "credentials": "AAAA",
            "domains": "action.example.com",
            "email": "webmaster@action.example.com",
            "propagation-seconds": 30,
            "plugin": "dns-google"})
        harness.charm._on_get_certificate_action(event)
        self.assertEqual(len(charm._host.run.call_args_list), 2)
        self.assertEqual(
            charm._host.run.call_args_list[0],
            call(["certbot", "certonly", "-n", "--no-eff-email", "--dns-google", "--agree-tos",
                  "--email=webmaster@action.example.com", "--domains=action.example.com",
                  "--dns-google-credentials=/etc/certbot-charm/action-1.cred",
                  "--dns-google-propagation-seconds=30"], env=None))
        self.assertEqual(charm._host.run.call_args_list[1][0], ([
                         '/etc/letsencrypt/renewal-hooks/deploy/certbot-charm'],))
        self.assertEqual(charm._host.run.call_args_list[1][1]["env"]
                         ["RENEWED_LINEAGE"], "/etc/letsencrypt/live/action.example.com")

    def test_get_certificate_action_dns_google_defaults(self):
        os.environ["JUJU_ACTION_UUID"] = "1"
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        config = {
            "agree-tos": True,
            "dns-google-credentials": "AAAA",
            "domains": "charm.example.com",
            "email": "webmaster@charm.example.com",
            "plugin": "dns-google",
            "propagation-seconds": 40}
        harness.update_config(self._config(harness.charm, **config))
        event = Mock(params={})
        harness.charm._on_get_certificate_action(event)
        self.assertEqual(len(charm._host.run.call_args_list), 2)
        self.assertEqual(
            charm._host.run.call_args_list[0],
            call(["certbot", "certonly", "-n", "--no-eff-email", "--dns-google", "--agree-tos",
                  "--email=webmaster@charm.example.com", "--domains=charm.example.com",
                  "--dns-google-credentials=/etc/certbot-charm/dns-google.json",
                  "--dns-google-propagation-seconds=40"], env=None))
        self.assertEqual(charm._host.run.call_args_list[1][0], ([
                         '/etc/letsencrypt/renewal-hooks/deploy/certbot-charm'],))
        self.assertEqual(charm._host.run.call_args_list[1][1]["env"]
                         ["RENEWED_LINEAGE"], "/etc/letsencrypt/live/charm.example.com")

    def test_get_certificate_action_dns_rfc2136(self):
        os.environ["JUJU_ACTION_UUID"] = "1"
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        event = Mock(params={
            "agree-tos": True,
            "credentials": "AAAA",
            "domains": "action.example.com",
            "email": "webmaster@action.example.com",
            "propagation-seconds": 30,
            "plugin": "dns-rfc2136"})
        harness.charm._on_get_certificate_action(event)
        self.assertEqual(len(charm._host.run.call_args_list), 2)
        self.assertEqual(
            charm._host.run.call_args_list[0],
            call(["certbot", "certonly", "-n", "--no-eff-email", "--dns-rfc2136", "--agree-tos",
                  "--email=webmaster@action.example.com", "--domains=action.example.com",
                  "--dns-rfc2136-credentials=/etc/certbot-charm/action-1.cred",
                  "--dns-rfc2136-propagation-seconds=30"], env=None))
        self.assertEqual(charm._host.run.call_args_list[1][0], ([
                         '/etc/letsencrypt/renewal-hooks/deploy/certbot-charm'],))
        self.assertEqual(charm._host.run.call_args_list[1][1]["env"]
                         ["RENEWED_LINEAGE"], "/etc/letsencrypt/live/action.example.com")

    def test_get_certificate_action_dns_rfc2136_defaults(self):
        os.environ["JUJU_ACTION_UUID"] = "1"
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        config = {
            "agree-tos": True,
            "dns-google-credentials": "AAAA",
            "domains": "charm.example.com",
            "email": "webmaster@charm.example.com",
            "plugin": "dns-rfc2136",
            "propagation-seconds": 40}
        harness.update_config(self._config(harness.charm, **config))
        event = Mock(params={})
        harness.charm._on_get_certificate_action(event)
        self.assertEqual(len(charm._host.run.call_args_list), 2)
        self.assertEqual(
            charm._host.run.call_args_list[0],
            call(["certbot", "certonly", "-n", "--no-eff-email", "--dns-rfc2136", "--agree-tos",
                  "--email=webmaster@charm.example.com", "--domains=charm.example.com",
                  "--dns-rfc2136-credentials=/etc/certbot-charm/dns-rfc2136.ini",
                  "--dns-rfc2136-propagation-seconds=40"], env=None))
        self.assertEqual(charm._host.run.call_args_list[1][0], ([
                         '/etc/letsencrypt/renewal-hooks/deploy/certbot-charm'],))
        self.assertEqual(charm._host.run.call_args_list[1][1]["env"]
                         ["RENEWED_LINEAGE"], "/etc/letsencrypt/live/charm.example.com")

    def test_get_certificate_action_fail(self):
        os.environ["JUJU_ACTION_UUID"] = "1"
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        event = Mock(params={
            "agree-tos": True,
            "credentials": "AAAA",
            "domains": "action.example.com",
            "email": "webmaster@action.example.com",
            "plugin": "dns-google",
            "propagation-seconds": 30})
        charm._host.run.side_effect = subprocess.CalledProcessError(1, "certbot")
        charm._host.exists.return_value = True
        harness.charm._on_get_certificate_action(event)
        event.fail.assert_called_once_with(
            "cannot get certificate: Command 'certbot' returned non-zero exit status 1.")
        charm._host.unlink.assert_called_once_with("/etc/certbot-charm/action-1.cred")

    def test_get_certificate_action_dns_route53(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        event = Mock(params={
            "agree-tos": True,
            "aws-access-key-id": "test-key-id",
            "aws-secret-access-key": "test-secret-key",
            "domains": "action.example.com",
            "email": "webmaster@action.example.com",
            "plugin": "dns-route53",
            "propagation-seconds": 30})
        harness.charm._on_get_certificate_action(event)
        self.assertEqual(len(charm._host.run.call_args_list), 2)
        expectCmd = [
            "certbot", "certonly", "-n", "--no-eff-email", "--dns-route53", "--agree-tos",
            "--email=webmaster@action.example.com", "--domains=action.example.com",
            "--dns-route53-propagation-seconds=30"]
        expectEnv = {"AWS_ACCESS_KEY_ID": "test-key-id",
                     "AWS_SECRET_ACCESS_KEY": "test-secret-key"}
        self.assertEqual(charm._host.run.call_args_list[0], call(expectCmd, env=expectEnv))
        self.assertEqual(charm._host.run.call_args_list[1][0], ([
                         '/etc/letsencrypt/renewal-hooks/deploy/certbot-charm'],))
        self.assertEqual(charm._host.run.call_args_list[1][1]["env"]
                         ["RENEWED_LINEAGE"], "/etc/letsencrypt/live/action.example.com")

    def test_get_certificate_action_dns_route53_defaults(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        config = {
            "agree-tos": True,
            "dns-route53-aws-access-key-id": "test-key-id",
            "dns-route53-aws-secret-access-key": "test-secret-key",
            "domains": "charm.example.com",
            "email": "webmaster@charm.example.com",
            "plugin": "dns-route53",
            "propagation-seconds": 40}
        harness.update_config(self._config(harness.charm, **config))
        event = Mock(params={})
        harness.charm._on_get_certificate_action(event)
        self.assertEqual(len(charm._host.run.call_args_list), 2)
        expectCmd = [
            "certbot", "certonly", "-n", "--no-eff-email", "--dns-route53", "--agree-tos",
            "--email=webmaster@charm.example.com", "--domains=charm.example.com",
            "--dns-route53-propagation-seconds=40"]
        expectEnv = {"AWS_ACCESS_KEY_ID": "test-key-id",
                     "AWS_SECRET_ACCESS_KEY": "test-secret-key"}
        self.assertEqual(charm._host.run.call_args_list[0], call(expectCmd, env=expectEnv))
        self.assertEqual(charm._host.run.call_args_list[1][0], ([
                         '/etc/letsencrypt/renewal-hooks/deploy/certbot-charm'],))
        self.assertEqual(charm._host.run.call_args_list[1][1]["env"]
                         ["RENEWED_LINEAGE"], "/etc/letsencrypt/live/charm.example.com")

    def test_get_certificate_no_plugin(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        with self.assertRaises(charm.UnsupportedPluginError):
            harness.charm._get_certificate("", False, "", "")

    def test_get_certificate_unknown_plugin(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        with self.assertRaises(charm.UnsupportedPluginError):
            harness.charm._get_certificate("no-such-plugin", False, "", "")

    def test_run_certbot_nothing_set(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        harness.update_config(self._config(harness.charm))
        harness.charm._run_certbot("test", False, "", "")
        charm._host.run.assert_called_once_with(
            ["certbot", "certonly", "-n", "--no-eff-email", "--test"], env=None)

    def test_run_certbot_params(self):
        charm._host = Mock()
        harness = Harness(charm.CertbotCharm)
        self.addCleanup(harness.cleanup)
        harness.begin()
        config = {
            "agree-tos": False,
            "domains": "charm.example.com,www.charm.example.com",
            "email": "webmaster@charm.example.com"}
        harness.update_config(self._config(harness.charm, **config))
        harness.charm._run_certbot(
            "test", True, "webmaster@params.example.com",
            "params.example.com,www.params.example.com",
            ["--extra-1", "--extra-2"], {"ENV1": "e1", "ENV2": "e2"})
        charm._host.run.assert_called_once_with(
            ["certbot", "certonly", "-n", "--no-eff-email", "--test", "--agree-tos",
             "--email=webmaster@params.example.com",
             "--domains=params.example.com,www.params.example.com",
             "--extra-1", "--extra-2"],
            env={"ENV1": "e1", "ENV2": "e2"})

    def _config(self, charm, **kwargs):
        config_path = charm.charm_dir / "config.yaml"
        if not config_path.is_file():
            return {}
        config_yaml = config_path.read_text()
        config_defs = yaml.load(config_yaml, Loader=yaml.SafeLoader)
        config = {}
        for k, v in config_defs.get("options", {}).items():
            config[k] = kwargs.get(k, v["default"])
        return config


class TestHost(unittest.TestCase):
    def test_exists(self):
        h = charm.Host()
        with tempfile.TemporaryDirectory() as dir:
            path = os.path.join(dir, "x")
            self.assertFalse(h.exists(path))
            with open(path, "w") as f:
                f.write("x")
            self.assertTrue(h.exists(path))

    def test_install_packages(self):
        h = charm.Host()
        h.run = Mock()
        h.install_packages(["pkg-a", "pkg-b", "pkg-c"])
        self.assertEqual(h.run.call_args_list, [
            call(["apt-get", "update", "-q"]),
            call(["apt-get", "install", "-q", "-y", "pkg-a", "pkg-b", "pkg-c"]),
        ])

    def test_symlink(self):
        h = charm.Host()
        with tempfile.TemporaryDirectory() as dir:
            afile = os.path.join(dir, "A")
            bfile = os.path.join(dir, "B")
            lfile = os.path.join(dir, "l")
            with open(afile, "w") as f:
                f.write("A")
            with open(bfile, "w") as f:
                f.write("B")
            h.symlink(afile, lfile)
            with open(lfile) as f:
                self.assertEqual(f.read(), "A")
            h.symlink(bfile, lfile)
            with open(lfile) as f:
                self.assertEqual(f.read(), "B")

    def test_unlink(self):
        h = charm.Host()
        with tempfile.TemporaryDirectory() as dir:
            afile = os.path.join(dir, "A")
            lfile = os.path.join(dir, "l")
            with open(afile, "w") as f:
                f.write("A")
            h.symlink(afile, lfile)
            self.assertTrue(os.path.exists(afile))
            self.assertTrue(os.path.exists(lfile))
            h.unlink(lfile)
            self.assertTrue(os.path.exists(afile))
            self.assertFalse(os.path.exists(lfile))
            h.unlink(lfile)
            self.assertTrue(os.path.exists(afile))
            self.assertFalse(os.path.exists(lfile))

    def test_write_config(self):
        h = charm.Host()
        with tempfile.TemporaryDirectory() as dir:
            path = os.path.join(dir, "cp")
            h.write_config(path, {"DEFAULT": {"a": "A"}, "test": {"b": "B"}}, mode=0o755)
            cp = configparser.ConfigParser()
            cp.read(path)
            self.assertEqual(cp["test"]["a"], "A")
            self.assertEqual(cp["test"]["b"], "B")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o755)

    def test_write_file(self):
        h = charm.Host()
        with tempfile.TemporaryDirectory() as dir:
            path = os.path.join(dir, "f")
            h.write_file(path, b"test", mode=0o755)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"test")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o755)
