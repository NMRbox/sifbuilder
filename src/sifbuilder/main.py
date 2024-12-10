#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import shutil
import subprocess
import sys
from typing import List

import argparser_adapter
import yaml
from argparser_adapter import ChoiceCommand, ArgparserAdapter

from sifbuilder import _logger
from sifbuilder.statusparser import parse_nmrbox_list, Software

APPTAINER = '/usr/bin/apptainer'

_TEMPLATE = """BootStrap: localimage
From: {base} 

# software specified
{software}

# packages specified
{named_packages}

%post
	export DEBIAN_FRONTEND=noninteractive
	apt-get -qq update 
	apt-get -qq install {packages} 

%environment
    export LC_ALL=C
"""

actionchoice = argparser_adapter.Choice("action", True, help='Action:')


class Builder:

    def __init__(self):
        """Parse local status for software. Read config value and determine debian packages to install"""
        self.force = False
        self.nolog = False

    def configure(self, config):
        """Configure from YAML (most likely)"""
        self.config = config
        self.defpath = self.config['def']
        self.sifpath = self.config['sif']

    def _parse(self):
        """Parse config for packages to install"""
        self.inventory = dict(parse_nmrbox_list())
        self.software: List[Software] = []
        self.data = self.config['data']
        if (swdict := self.config['software']) is None:
            swdict = {}  # use empty placeholder to simplify indenting / program flow
        for s, vers in swdict.items():
            softwarename = s.upper()
            if softwarename not in self.inventory:
                raise ValueError(f"{softwarename} not found")
            if vers is None:
                candidates = list(self.inventory[softwarename].values())
                latest = Software.latest_packages(candidates)
                self.software.extend(latest)
                if _logger.isEnabledFor(logging.DEBUG):
                    lstr = ' '.join([str(s) for s in latest])
                    _logger.debug(f"{softwarename} resolves to {lstr}")
            else:
                available = self.inventory[softwarename]
                if (vstr := str(vers)) not in available:
                    raise ValueError(
                        f"Version {vstr} of software {softwarename} not found. " 
                        f"Valid values are: {','.join(available)}")
                self.software.append(added := available[vstr])
                _logger.debug(f"{softwarename} {vstr} resolves to {added}")
        self.debpackages: List[str] = []
        if (pkgdict := self.config['packages']) is None:
            pkgdict = {}
        for pkg, version in pkgdict.items():
            if version is None:
                adding = pkg
            else:
                adding = f'{pkg}={version}'
            self.debpackages.append(adding)
            _logger.debug(f"Adding {adding} from package: section")
        return self

    @ChoiceCommand(actionchoice)
    def generate(self):
        """generate def file"""
        self._parse()
        if os.path.exists(self.defpath) and not self.force:
            raise ValueError(f"{self.defpath} already present")
        software_packages = []
        for s in self.software:
            software_packages.extend(s.packages)
            _logger.debug(f"{s} adds {' '.join([p.package_spec for p in s.packages])}")
            if self.data:
                software_packages.extend(s.data_packages)
                _logger.debug(f"{s} data packages {' '.join([p.package_spec for p in s.data_packages])}")

        combined = self.debpackages + [p.package_spec for p in software_packages]
        pspec = ' '.join(combined)
        software = '\n'.join([f'# {s}' for s in self.software])
        named_packages = '\n'.join([f'# {p}' for p in self.debpackages])

        os.makedirs(os.path.dirname(self.defpath), exist_ok=True)
        with open(self.defpath, 'w') as f:
            print(_TEMPLATE.format(base=self.config['base'],
                                   packages=pspec,
                                   software=software,
                                   named_packages=named_packages),
                  file=f)
        print(f"Wrote {self.defpath}")

    def _check_paths(self):
        """Check paths, raise error or overwrite, depending on self.force"""
        if not os.path.isfile(APPTAINER):
            raise ValueError(f"{APPTAINER} not found. Install apptainer debian package")
        if not os.path.isfile(self.defpath):
            print(f"{self.defpath} not found", file=sys.stderr)
            sys.exit(1)
        if os.path.exists(self.sifpath):
            if not self.force:
                raise ValueError(f"{self.sifpath} already present")
            if os.path.isdir(self.sifpath):
                shutil.rmtree((self.sifpath))
            else:
                os.remove(self.sifpath)
        sdir = os.path.dirname(self.sifpath)
        os.makedirs(sdir, exist_ok=True)

    def _run(self, cmd):
        """Run a command after displaying to user"""
        print(f"Running: {' '.join(cmd)}")
        if self.nolog:
            subprocess.run(cmd)
        else:
            sname = os.path.basename(self.sifpath)
            ts = datetime.datetime.now().strftime(f"{sname}-%b%d-%H:%M:%S.log")
            with open(ts, 'w') as logfile:
                print(f"logging to {logfile.name}")
                subprocess.run(cmd, stdout=logfile, stderr=subprocess.STDOUT)

    @ChoiceCommand(actionchoice)
    def sif(self):
        """Build single sif from def file"""
        self._check_paths()
        self._run((APPTAINER, 'build', self.sifpath, self.defpath))

    @ChoiceCommand(actionchoice)
    def sandbox(self):
        """Build writable sandbox directory from def file"""
        self._check_paths()
        self._run((APPTAINER, 'build', '--sandbox', self.sifpath, self.defpath))


def main():
    logging.basicConfig()
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('yaml', help="yaml configuration file")
    builder = Builder()
    adapter = ArgparserAdapter(builder)
    adapter.register(parser)

    parser.add_argument('-l', '--loglevel', default='WARN', help="Python logging level")
    parser.add_argument('--force', action='store_true', help="Overwrite existing def and sif")
    parser.add_argument('--nolog', action='store_true', help="Apptainer output to stdout/stderr instead of log files")

    args = parser.parse_args()
    _logger.setLevel(getattr(logging, args.loglevel))
    with open(args.yaml) as f:
        config = yaml.safe_load(f)
    builder.configure(config)
    builder.force = args.force
    builder.nolog = args.nolog
    adapter.call_specified_methods(args)


if __name__ == "__main__":
    main()