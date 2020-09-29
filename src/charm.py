#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd
# See LICENSE file for licensing details.

import base64
import binascii
import configparser
import logging
import os
import subprocess
from typing import Any, List, Mapping, Tuple

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus


logger = logging.getLogger(__name__)


class UnsupportedPluginError(Exception):
    """Raised when an attempt is made to acquire a certificate using
    an unsupported plugin."""
    pass


class CertbotCharm(CharmBase):
    """Class that implements the certbot charm."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.get_certificate_action, self._on_get_certificate_action)

    def _on_install(self, _):
        """Handler for the install hook."""
        _host.install_packages([
            "certbot",
            "python3-certbot-dns-google",
            "python3-certbot-dns-route53"])
        _host.symlink(os.path.join(self.charm_dir, "bin/deploy.py"),
                      "/etc/letsencrypt/renewal-hooks/deploy/certbot-charm")

    def _on_config_changed(self, _):
        """Handler for the config-changed hook."""
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
        """Handler for the start hook."""
        self.model.unit.status = BlockedStatus("certificate not yet acquired.")
        try:
            # attempt to get a certificate using the defaults, don't
            # worry if it fails.
            self._get_certificate(
                self.model.config["plugin"],
                self.model.config["agree-tos"],
                self.model.config["email"],
                self.model.config["domains"])
        except Exception as err:
            logger.info("could not automatically acquire certificate", exc_info=err)

    def _on_stop(self, _):
        """Handler for the stop hook."""
        _host.unlink("/etc/letsencrypt/renewal-hooks/deploy/certbot-charm")

    def _on_get_certificate_action(self, event):
        """Implementation of the get-certificate action."""
        params = event.params
        credpath = self._config_path("action-{}.cred".format(os.environ["JUJU_ACTION_UUID"]))
        if params.get("credentials"):
            try:
                self._write_base64(credpath, event.params["credentials"])
                params["credentials-path"] = credpath
            except (ValueError, binascii.Error) as err:
                event.fail("invalid credentials: {}".format(err))
                return
        try:
            self._get_certificate(params.get("plugin", self.model.config["plugin"]),
                                  params.get("agree-tos", self.model.config["agree-tos"]),
                                  params.get("email", self.model.config["email"]),
                                  params.get("domains", self.model.config["domains"]),
                                  params)
        except Exception as err:
            event.fail("cannot get certificate: {}".format(err))
            # try and clean up any credentials as they won't be needed
            if _host.exists(credpath):
                try:
                    _host.unlink(credpath)
                except Exception:
                    pass

    def _dns_google_args(self, params: dict) -> Tuple[List[str], Mapping[str, str]]:
        """Calculate arguments for the dns-google plugin.

        Args:
            params: Plugin-specific parameters that will be converted to
              arguments or environment variables.
        """
        path = params.get("credentials-path", self._config_path("dns-google.json"))
        propagation = params.get("propagation-seconds",
                                 self.model.config["propagation-seconds"])
        return [
            "--dns-google-credentials={}".format(path),
            "--dns-google-propagation-seconds={}".format(propagation),
        ], None

    def _dns_route53_args(self, params: dict) -> Tuple[List[str], Mapping[str, str]]:
        """Calculate arguments for the dns-route53 plugin.

        Args:
            params: Plugin-specific parameters that will be converted to
              arguments or environment variables.
        """
        propagation = params.get("propagation-seconds",
                                 self.model.config["propagation-seconds"])
        aws_access_key_id = params.get(
            "aws-access-key-id", self.model.config["dns-route53-aws-access-key-id"])
        aws_secret_access_key = params.get(
            "aws-secret-access-key", self.model.config["dns-route53-aws-secret-access-key"])
        return [
            "--dns-route53-propagation-seconds={}".format(propagation),
        ], {
            "AWS_ACCESS_KEY_ID": aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": aws_secret_access_key,
        }

    def _get_certificate(self, plugin: str, agree_tos: bool, email: str, domains: str,
                         params: dict = {}) -> None:
        """Get and install a certificate.

        Use certbot to acquire a new certificate and run the charm's
        deploy script to install the certificate to the configured
        locations.

        Args:
            plugin: Name of the plugin to use to acquire the certificate.
            agree_tos: Agree to the the terms-of-service of the ACME server.
            email: Email address to assocaite with the certificate.
            domains: Comma separated list of domains the certificate is for.
            params: Additional plugin-specific parameters needed to
              retrieve the certificate.

        Raises:
            UnsupportedPluginError: The requested plugin is not supported
              by this charm.

        """
        try:
            args, env = getattr(self, "_{}_args".format(plugin.replace("-", "_")))(params)
        except (AttributeError, TypeError):
            raise UnsupportedPluginError('plugin "{}" not supported'.format(plugin))

        self._run_certbot(plugin, agree_tos, email, domains, args, env)

        domain = domains.split(",")[0]
        cmd = ["/etc/letsencrypt/renewal-hooks/deploy/certbot-charm"]
        env = dict(os.environ)
        env["RENEWED_LINEAGE"] = os.path.join("/etc/letsencrypt/live", domain)
        _host.run(cmd, env=env)
        self.model.unit.status = ActiveStatus("maintaining certificate for {}.".format(domain))

    def _run_certbot(self, plugin: str, agree_tos: bool, email: str, domains: str,
                     args: List[str] = None, env: Mapping[str, str] = None) -> None:
        """Run the certbot command.

        Runs a non-interactive certbot certonly command.

        Args:
            plugin: Name of the plugin to use to acquire the certificate.
            agree_tos: Agree to the the terms-of-service of the ACME server.
            email: Email address to assocaite with the certificate.
            domains: Comma separated list of domains the certificate is for.
            args: Additional, plugin-specific, arguments to add to the
              certbot command.
            env: Environment variables to set in the cerbot command.
        """
        cmd = ["certbot", "certonly", "-n", "--no-eff-email"]
        cmd.append("--{}".format(plugin))
        if agree_tos:
            cmd.append("--agree-tos")
        if email:
            cmd.append("--email={}".format(email))
        if domains:
            cmd.append("--domains={}".format(domains))
        if args:
            cmd.extend(args)
        _host.run(cmd, env=env)

    def _config_path(self, filename: str) -> str:
        """Calculate the location where the charm's configuration files
        should be stored."""
        return os.path.join("/etc/certbot-charm", filename)

    def _write_base64(self, path: str, b64: str, mode: int = 0o600):
        """Decode the base64 string and write to a file."""
        _host.write_file(path, base64.b64decode(b64), mode=mode)


class Host:
    """Interface into the host machine.

    This interface is used to make changes on the host machine on behalf
    of the charm. This class can be easily mocked for tests.
    """

    def __init__(self, *args):
        super().__init__(*args)

    def exists(self, path: str):
        """Wrapper for os.path.exists."""
        return os.path.exists(path)

    def install_packages(self, packages: List[str]):
        """Install apt packages.

        Args:
            packages: List of packages to install.
        """
        self.run(["apt-get", "update", "-q"])
        cmd = ["apt-get", "install", "-q", "-y"]
        cmd.extend(packages)
        self.run(cmd)

    def run(self, *args, **kwargs):
        """Run a subcommand.

        This is a wrapper for subprocess.run.
        """
        subprocess.run(*args, **kwargs)

    def symlink(self, src: str, dst: str):
        """Create, or update a symbolic link.

        Ensure there is a symbolic link from src to dst. If dst already
        exists the current file will be overwritten. Any required
        directories will be created for dst.

        Args:
            src: The path to link to.
            dst: The path of the new file.
        """
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.symlink(src, dst)
        except FileExistsError:
            os.remove(dst)
            os.symlink(src, dst)

    def unlink(self, path: str):
        """Remove a file.

        Removes the specified file, it is not an error if the file does
        not exist.

        Args:
            path: File to remove.
        """
        try:
            os.unlink(path)
        except FileNotFoundError:
            # If the file doesn't exist then that's what we want.
            pass

    def write_config(self, path: str, config: Mapping[str, Mapping[str, Any]], mode: int = 0o600):
        """Write configuration to file.

        Load the configuration file from the given path, if it exists.
        Update the configuration with the given config. Then write the
        configuration back to the given path.

        Args:
            path: Location of the config file.
            config: The configuration settings to set.
            mode: Permissions to apply to the after writing it.
        """
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

    def write_file(self, path: str, content: bytes, mode: int = 0o600):
        """Write a binary file.

        Args:
            path: Location of the config file.
            content: The bytes to write to the file.
            mode: Permissions to apply to the after writing it.
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        os.chmod(path, mode)


_host = Host()


if __name__ == "__main__":
    main(CertbotCharm)
