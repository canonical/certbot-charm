#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd

import configparser
import os
import shutil
import subprocess
import sys


class Deploy:
    def __init__(self, path, configpath="/etc/certbot-charm/config.ini"):
        super().__init__()
        self._path = path
        self._domain = os.path.basename(path)
        self._config = configparser.ConfigParser()
        self._config.read(configpath)

    def run(self):
        self._copy_file("cert.pem", "cert-path", ".crt")
        self._copy_file("chain.pem", "chain-path", "_chain.pem")

        dst = self._config["deploy"]["combined-path"]
        if dst:
            if os.path.isdir(dst):
                dst = os.path.join(dst, self._domain + ".pem")
            with open(dst, "wb") as outf:
                with open(os.path.join(self._path, "fullchain.pem"), "rb") as inf:
                    shutil.copyfileobj(inf, outf)
                with open(os.path.join(self._path, "privkey.pem"), "rb") as inf:
                    shutil.copyfileobj(inf, outf)

        self._copy_file("fullchain.pem", "fullchain-path", "_fullchain.pem")
        self._copy_file("privkey.pem", "key-path", ".key")

        cmd = self._config["deploy"]["command"]
        if cmd:
            try:
                subprocess.run(cmd, shell=True)
            except subprocess.CalledProcessError as err:
                print("error running deploy command: ", err, file=sys.stderr)

    def _copy_file(self, srcfile, dstkey, suffix):
        dst = self._config["deploy"].get(dstkey)
        if not dst:
            return
        if os.path.isdir(dst):
            dst = os.path.join(dst, self._domain + suffix)
        shutil.copyfile(os.path.join(self._path, srcfile), dst)


if __name__ == "__main__":
    Deploy(os.environ["RENEWED_LINEAGE"]).run()
