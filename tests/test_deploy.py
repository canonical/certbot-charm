# Copyright 2020 Canonical Ltd
# See LICENSE file for licensing details.

import configparser
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

import deploy


class TestDeploy(unittest.TestCase):
    def test_copy_files(self):
        with tempfile.TemporaryDirectory() as dir:
            os.mkdir(os.path.join(dir, "example.com"))
            os.mkdir(os.path.join(dir, "dest"))
            configfile = os.path.join(dir, "config.ini")
            certfile = os.path.join(dir, "example.com", "cert.pem")
            chainfile = os.path.join(dir, "example.com", "chain.pem")
            fullchainfile = os.path.join(dir, "example.com", "fullchain.pem")
            keyfile = os.path.join(dir, "example.com", "privkey.pem")

            config = configparser.ConfigParser()
            config.add_section("deploy")
            config["DEFAULT"]["cert-path"] = os.path.join(dir, "dest", "cert")
            config["DEFAULT"]["chain-path"] = os.path.join(dir, "dest", "chain")
            config["DEFAULT"]["combined-path"] = os.path.join(dir, "dest", "combined")
            config["DEFAULT"]["fullchain-path"] = os.path.join(dir, "dest", "fullchain")
            config["DEFAULT"]["key-path"] = os.path.join(dir, "dest", "key")
            config["deploy"]["command"] = ""
            with open(configfile, "w") as f:
                config.write(f)

            with open(certfile, "w") as f:
                f.write("CERTIFICATE\n")
            with open(chainfile, "w") as f:
                f.write("CHAIN\n")
            with open(fullchainfile, "w") as f:
                f.write("FULLCHAIN\n")
            with open(keyfile, "w") as f:
                f.write("KEY\n")

            d = deploy.Deploy(os.path.join(dir, "example.com"), configfile)
            d.run()

            with open(os.path.join(dir, "dest", "cert")) as f:
                b = f.read()
                self.assertEqual(b, "CERTIFICATE\n")
            with open(os.path.join(dir, "dest", "chain")) as f:
                b = f.read()
                self.assertEqual(b, "CHAIN\n")
            with open(os.path.join(dir, "dest", "combined")) as f:
                b = f.read()
                self.assertEqual(b, "FULLCHAIN\nKEY\n")
            with open(os.path.join(dir, "dest", "fullchain")) as f:
                b = f.read()
                self.assertEqual(b, "FULLCHAIN\n")
            with open(os.path.join(dir, "dest", "key")) as f:
                b = f.read()
                self.assertEqual(b, "KEY\n")

    def test_copy_files_dir(self):
        with tempfile.TemporaryDirectory() as dir:
            os.mkdir(os.path.join(dir, "example.com"))
            os.mkdir(os.path.join(dir, "dest"))
            configfile = os.path.join(dir, "config.ini")
            certfile = os.path.join(dir, "example.com", "cert.pem")
            chainfile = os.path.join(dir, "example.com", "chain.pem")
            fullchainfile = os.path.join(dir, "example.com", "fullchain.pem")
            keyfile = os.path.join(dir, "example.com", "privkey.pem")

            config = configparser.ConfigParser()
            config.add_section("deploy")
            config["DEFAULT"]["cert-path"] = os.path.join(dir, "dest")
            config["DEFAULT"]["chain-path"] = os.path.join(dir, "dest")
            config["DEFAULT"]["combined-path"] = os.path.join(dir, "dest")
            config["DEFAULT"]["fullchain-path"] = os.path.join(dir, "dest")
            config["DEFAULT"]["key-path"] = os.path.join(dir, "dest")
            config["deploy"]["command"] = ""
            with open(configfile, "w") as f:
                config.write(f)

            with open(certfile, "w") as f:
                f.write("CERTIFICATE\n")
            with open(chainfile, "w") as f:
                f.write("CHAIN\n")
            with open(fullchainfile, "w") as f:
                f.write("FULLCHAIN\n")
            with open(keyfile, "w") as f:
                f.write("KEY\n")

            d = deploy.Deploy(os.path.join(dir, "example.com"), configfile)
            d.run()

            with open(os.path.join(dir, "dest", "example.com.crt")) as f:
                b = f.read()
                self.assertEqual(b, "CERTIFICATE\n")
            with open(os.path.join(dir, "dest", "example.com_chain.pem")) as f:
                b = f.read()
                self.assertEqual(b, "CHAIN\n")
            with open(os.path.join(dir, "dest", "example.com.pem")) as f:
                b = f.read()
                self.assertEqual(b, "FULLCHAIN\nKEY\n")
            with open(os.path.join(dir, "dest", "example.com_fullchain.pem")) as f:
                b = f.read()
                self.assertEqual(b, "FULLCHAIN\n")
            with open(os.path.join(dir, "dest", "example.com.key")) as f:
                b = f.read()
                self.assertEqual(b, "KEY\n")

    def test_deploy_command(self):
        with tempfile.TemporaryDirectory() as dir:
            configfile = os.path.join(dir, "config.ini")
            config = configparser.ConfigParser()
            config.add_section("deploy")
            config["DEFAULT"]["cert-path"] = ""
            config["DEFAULT"]["chain-path"] = ""
            config["DEFAULT"]["combined-path"] = ""
            config["DEFAULT"]["fullchain-path"] = ""
            config["DEFAULT"]["key-path"] = ""
            config["deploy"]["command"] = "echo 'OK!'"
            with open(configfile, "w") as f:
                config.write(f)

            d = deploy.Deploy(os.path.join(dir, "example.com"), configfile)
            subprocess.run = Mock()
            d.run()
            subprocess.run.assert_called_once_with("echo 'OK!'", shell=True)

    def test_deploy_command_error(self):
        with tempfile.TemporaryDirectory() as dir:
            configfile = os.path.join(dir, "config.ini")
            config = configparser.ConfigParser()
            config.add_section("deploy")
            config["DEFAULT"]["cert-path"] = ""
            config["DEFAULT"]["chain-path"] = ""
            config["DEFAULT"]["combined-path"] = ""
            config["DEFAULT"]["fullchain-path"] = ""
            config["DEFAULT"]["key-path"] = ""
            config["deploy"]["command"] = "echo 'OK!'"
            with open(configfile, "w") as f:
                config.write(f)

            d = deploy.Deploy(os.path.join(dir, "example.com"), configfile)
            subprocess.run = Mock(side_effect=subprocess.CalledProcessError(1, "test"))
            d.run()
            subprocess.run.assert_called_once_with("echo 'OK!'", shell=True)
