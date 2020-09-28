#!/usr/bin/env python3
# Copyright 2020 Canonical Ltd

import configparser
import os
import shutil
import subprocess


def main():
    config = configparser.ConfigParser()
    config.read("/etc/certbot-charm/config.ini")
    path = os.environ["RENEWED_LINEAGE"]
    if config["deploy"]["cert-path"]:
        shutil.copyfile(os.path.join(path, "cert.pem"), config["deploy"]["cert-path"])
    if config["deploy"]["chain-path"]:
        shutil.copyfile(os.path.join(path, "chain.pem"), config["deploy"]["chain-path"])
    if config["deploy"]["combined-path"]:
        with open(config["deploy"]["combined-path"], "wb") as outf:
            with open(os.path.join(path, "fullchain.pem"), "rb") as inf:
                shutil.copyfileobj(inf, outf)
            with open(os.path.join(path, "privkey.pem"), "rb") as inf:
                shutil.copyfileobj(inf, outf)
    if config["deploy"]["fullchain-path"]:
        shutil.copyfile(
            os.path.join(path, "fullchain.pem"), config["deploy"]["fullchain-path"]
        )
    if config["deploy"]["key-path"]:
        shutil.copyfile(os.path.join(path, "privkey.pem"), config["deploy"]["key-path"])
    if config["deploy"]["command"]:
        try:
            subprocess.run(config["deploy"]["command"], shell=True)
        except subprocess.CalledProcessError as err:
            print("error running deploy command: ", err, file=os.stderr)


if __name__ == "__main__":
    main()
