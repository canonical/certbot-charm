#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd
# See LICENSE file for licensing details.

import base64
import binascii
import configparser
import logging
import os
import subprocess

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus


logger = logging.getLogger(__name__)


class UnsupportedPluginError(Exception):
    pass


class CertbotCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(
            self.on.get_dns_google_certificate_action,
            self._on_get_dns_google_certificate_action,
        )
        self.framework.observe(
            self.on.get_dns_route53_certificate_action,
            self._on_get_dns_route53_certificate_action,
        )

    def _on_install(self, _):
        _host.install_packages(
            "certbot",
            "python3-certbot-dns-google",
            "python3-certbot-dns-route53")
        _host.symlink(os.path.join(self.charm_dir, "bin/deploy.py"),
                      "/etc/letsencrypt/renewal-hooks/deploy/certbot-charm")

    def _on_config_changed(self, _):
        _host.write_config(
            self._config_path("config.ini"),
            {
                "DEFAULT": {
                    "cert-path": self.model.config["cert-path"],
                    "chain-path": self.model.config["chain-path"],
                    "combined-path": self.model.config["combined-path"],
                    "fullchain-path": self.model.config["fullchain-path"],
                    "key-path": self.model.config["key-path"],
                },
                "deploy": {
                    "command": self.model.config["deploy-command"],
                },
            }
        )
        try:
            self._write_base64(self._config_path("dns-google.json"),
                               self.model.config["dns-google-credentials"])
        except (ValueError, binascii.Error):
            logger.exception("invalid dns-google-credentials value")

    def _on_start(self, _):
        self.model.unit.status = BlockedStatus("certificate not yet acquired.")
        try:
            # attempt to get a certificate using the defaults, don't
            # worry if it fails.
            self._get_certificate()
        except Exception as err:
            logger.info("could not automatically acquire certificate", exc_info=err)

    def _on_stop(self, _):
        _host.unlink("/etc/letsencrypt/renewal-hooks/deploy/certbot-charm")

    def _on_get_dns_google_certificate_action(self, event):
        params = event.params
        if params.get("credentials"):
            try:
                path = self._config_path("dns-google-action.json")
                self._write_base64(path,
                                   event.params["credentials"])
                params["credentials-path"] = path
            except (ValueError, binascii.Error) as err:
                event.fail("invalid credentials: {}".format(err))
                return
        try:
            self._get_certificate(plugin="dns-google", **params)
        except Exception as err:
            event.fail("cannot get certificate: {}".format(err))

    def _on_get_dns_route53_certificate_action(self, event):
        params = event.params
        try:
            self._get_certificate(plugin="dns-route53", **params)
        except Exception as err:
            event.fail("cannot get certificate: {}".format(err))

    def _get_certificate(self, **kwargs):
        plugin = kwargs.get("plugin") or self.model.config["plugin"]
        if plugin == "dns-google":
            self._get_certificate_dns_google(**kwargs)
        elif plugin == "dns-route53":
            self._get_certificate_dns_route53(**kwargs)
        elif not plugin:
            raise UnsupportedPluginError("plugin not specified")
        else:
            raise UnsupportedPluginError("{} plugin not supported".format(plugin))

        domains = kwargs.get("domains") or self.model.config["domains"]
        domain = domains.split(",")[0]
        cmd = ["/etc/letsencrypt/renewal-hooks/deploy/certbot-charm"]
        env = dict(os.environ)
        env["RENEWED_LINEAGE"] = os.path.join("/etc/letsencrypt/live", domain)
        _host.run(cmd, env=env)
        self.model.unit.status = ActiveStatus("maintaining certificate for {}.".format(domain))

    def _get_certificate_dns_google(self, **kwargs):
        propagation = kwargs.get(
            "propagation-seconds") or self.model.config["dns-google-propagation-seconds"]
        path = kwargs.get("credentials-path") or self._config_path("dns-google.json")
        self._run_certbot(
            "--dns-google-credentials={}".format(path),
            "--dns-google-propagation-seconds={}".format(propagation),
            **kwargs
        )

    def _get_certificate_dns_route53(self, **kwargs):
        propagation = kwargs.get(
            "propagation-seconds") or self.model.config["dns-route53-propagation-seconds"]
        aws_access_key_id = kwargs.get(
            "aws-access-key-id") or self.model.config["dns-route53-aws-access-key-id"]
        aws_secret_access_key = kwargs.get(
            "aws-secret-access-key") or self.model.config["dns-route53-aws-secret-access-key"]
        kwargs["env"] = {
            "AWS_ACCESS_KEY_ID": aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": aws_secret_access_key,
        }
        self._run_certbot(
            "--dns-route53-propagation-seconds={}".format(propagation),
            **kwargs
        )

    def _run_certbot(self, *args, **kwargs):
        cmd = ["certbot", "certonly", "-n", "--no-eff-email"]
        plugin = kwargs.get("plugin") or self.model.config["plugin"]
        cmd.append("--{}".format(plugin))
        if kwargs.get("agree-tos") or self.model.config["agree-tos"]:
            cmd.append("--agree-tos")
        email = kwargs.get("email") or self.model.config["email"]
        if email:
            cmd.append("--email={}".format(email))
        domains = kwargs.get("domains") or self.model.config["domains"]
        if domains:
            cmd.append("--domains={}".format(domains))
        if args:
            cmd.extend(args)
        _host.run(cmd, env=kwargs.get("env"))

    def _config_path(self, filename):
        return os.path.join("/etc/certbot-charm", filename)

    def _write_base64(self, path, b64, mode=0o600):
        _host.write_file(path, base64.b64decode(b64), mode=mode)


class Host:
    def __init__(self, *args):
        super().__init__(*args)

    def install_packages(self, *packages):
        self.run(["apt-get", "update", "-q"])
        cmd = ["apt-get", "install", "-q", "-y"]
        cmd.extend(packages)
        self.run(cmd)

    def run(self, *args, **kwargs):
        subprocess.run(*args, **kwargs)

    def symlink(self, src, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.symlink(src, dst)
        except FileExistsError:
            os.remove(dst)
            os.symlink(src, dst)

    def unlink(self, path):
        try:
            os.unlink(path)
        except FileNotFoundError:
            # If the file doesn't exist then that's what we want.
            pass

    def write_config(self, path, config, mode=0o600):
        cp = configparser.ConfigParser()
        cp.read(path)
        for section, values in config.items():
            if section != "DEFAULT" and not cp.has_section(section):
                cp.add_section(section)
            for key, value in values.items():
                cp[section][key] = value

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            cp.write(f)
        os.chmod(path, mode)

    def write_file(self, path, content, mode=0o600):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        os.chmod(path, mode)


_host = Host()


if __name__ == "__main__":
    main(CertbotCharm)
