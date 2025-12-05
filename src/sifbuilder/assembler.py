import argparse
import datetime
import io
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Iterable

import argparser_adapter
import yaml
from argparser_adapter import ChoiceCommand, ArgparserAdapter

import sifbuilder
from sifbuilder import builder_logger
from sifbuilder.subversion_parser import subversion_info

APPTAINER = Path('/usr/bin/apptainer')


def executable(path, flags):
    # O_CREAT | O_WRONLY => create file for writing
    # 0o755 sets the file mode at creation
    return os.open(path, flags, 0o755)


_TEMPLATE = """BootStrap: localimage
From: {base} 

%post
	export DEBIAN_FRONTEND=noninteractive
	apt-get -qq update 
"""

_ENV = """%environment
    export LC_ALL=C"""

_EKEY = 'env'
_RKEY = 'run'
_LKEY = 'labels'
_HKEY = 'help'
_IKEY = 'install'

actionchoice = argparser_adapter.Choice("action", True, help='Action:')


class Builder:

    def __init__(self):
        """Parse local status for software. Read config value and determine debian packages to install"""
        self.force = False
        self.nolog = False
        self.build_wrappers = False
        self.software: list[str] = []
        self._control : Path |None = None
        self.apps = {}
        self.origins = {}

    @property
    def control(self):
        return self._control

    @control.setter
    def control(self,value):
        if value:
            self._control = Path(value)
            if not self.control.is_file():
                raise FileNotFoundError(self.control.as_posix())

    def load(self, primary):
        """load configuration"""
        with open(primary) as f:
            aconfig = yaml.safe_load(f)
        self.base = Path(aconfig['base'])
        self.installed = aconfig['installed']
        self.wrapper_dir = Path(aconfig['wrappers'])
        if not self.base.is_file():
            raise FileNotFoundError(f"Invalid base {self.base.as_posix()}")
        if not self.wrapper_dir.is_dir():
            if not self.wrapper_dir.parent.is_dir():
                raise FileNotFoundError(f"invalid wrapper parent directory {self.wrapper_dir.parent.as_posix()}")
            self.wrapper_dir.mkdir()
        product = aconfig['product']
        self.defpath = Path(product + '.def')
        self.sifpath = Path(product + '.sif')

    #    def _set_path(self,current:Path,config,key)->Path:
    #        if (v := config.get(key)) is not None:
    #            vpath = Path(v)
    #            if current is None or current == v:
    #                return v
    #        return current
    #

    def configure(self, yamls: Iterable[str | Path]) -> None:
        if not yamls:
            return
        paths = [Path(y) for y in yamls]
        bad = [m for m in paths if not m.is_file()]
        if bad:
            raise ValueError(f"Missing yaml file {','.join(bad)}")
        configs = []
        for p in paths:
            builder_logger.debug(f"Evaluate {p.as_posix()}")
            try:
                with open(p) as f:
                    dc = yaml.safe_load(f)
                    if dc.get('sifassembly', False):
                        self.origins[dc['app']] = p
                        builder_logger.info(f"Reading {p.as_posix()}")
                        configs.append(dc)
            except Exception as e:
                builder_logger.info(f"Fail to parse {p.as_posix()} {e}")
        ordered = {c['app']: c for c in configs}
        for appname in sorted(ordered.keys()):
            app_cfg = ordered[appname]
            app = app_cfg['app']
            self.apps[app] = (app_d := {})
            pkgs = app_cfg.get('packages', None)
            f: io.StringIO
            if pkgs:
                with io.StringIO() as f:
                    print(f"    apt-get -qq install {' '.join(pkgs)}", file=f)
                    app_d[_IKEY] = f.getvalue()

            edict = app_cfg.get("environment", {})
            if edict:
                with io.StringIO() as f:
                    for env, value in edict.get('append', {}).items():
                        print(f'    export {env}=${env}:{value}', file=f)
                    app_d[_EKEY] = f.getvalue()
            if (rspec := app_cfg.get("run", None)) is not None:
                if isinstance(rspec, dict):
                    for app, cmd in rspec.items():
                        with io.StringIO() as f:
                            print(f'    {cmd}', file=f)
                            if app in self.apps:
                                app_d[_RKEY] = f.getvalue()
                            else:
                                self.apps[app] = {_RKEY: f.getvalue()}
                elif isinstance(rspec, list):
                    with io.StringIO() as f:
                        for cmd in rspec:
                            print(f'    {cmd}', file=f)
                        app_d[_RKEY] = f.getvalue()
                else:
                    raise ValueError(f"Unsuported {_RKEY} {type(rspec)}")
            labels = app_cfg.get("labels", {})
            if labels:
                with io.StringIO() as f:
                    for env, value in labels.items():
                        print(f'    {env} {value}', file=f)
                    app_d[_LKEY] = f.getvalue()
            help = app_cfg.get('help', [])
            if help:
                with io.StringIO() as f:
                    for h in help:
                        print(f'    {h}', file=f)
                    app_d[_HKEY] = f.getvalue()
            self.software.extend(s.upper() for s in app_cfg.get('software',[]))

    @ChoiceCommand(actionchoice)
    def version(self):
        print(sifbuilder.__version__)

    @ChoiceCommand(actionchoice)
    def generate(self):
        """generate def file"""
        if self.defpath.exists() and not self.force:
            raise ValueError(f"{self.defpath.as_posix()} already present")
        builder_logger.info(f"generating {self.defpath.as_posix()}")
        with open(self.defpath, 'w') as f:
            print(_TEMPLATE.format(base=self.base), file=f)
            self._add_enviroment(f)
            self._add_source_labels(f)
            for app, data in self.apps.items():
                for scifkey in (_IKEY, _RKEY, _LKEY, _EKEY, _HKEY):
                    if (stanza := data.get(scifkey, None)) is not None:
                        print(f'\n%app{scifkey} {app}', file=f)
                        print(stanza, file=f)
            self.__add_runscript(f)
        print(f"Wrote {self.defpath}")
        self._update_control()

    def _add_enviroment(self, f):
        """Add environment setting from config, if any"""
        print(_ENV, file=f)

    def _add_source_labels(self,f):
        print('%labels',file=f)
        for origin, p in self.origins.items():
            ident = subversion_info(p).ident()
            print(f'    org.nmrbox.{origin}: "{ident}"',file=f)

    def __add_runscript(self, f):
        return
        runlist = self.config.get("run", [])
        if runlist:
            print('\n%runscript', file=f)
            for cmd in runlist:
                print(f'   {cmd} ', file=f)

    def _check_paths(self):
        """Check paths, raise error or overwrite, depending on self.force"""
        if not APPTAINER.is_file():
            raise ValueError(f"{APPTAINER.as_posix()} not found. Install apptainer debian package")
        if not self.defpath.is_file() or self.force:
            self.generate()
        if self.sifpath.exists():
            if not self.force:
                raise ValueError(f"{self.sifpath.as_posix()} already present")
            if self.sifpath.is_dir():
                shutil.rmtree(self.sifpath)
            else:
                self.sifpath.unlink()
        self.sifpath.parent.mkdir(exist_ok=True)

    def _run(self, cmd_i):
        """Run a command after displaying to user. Exit on error"""
        cmd = [item.as_posix() if isinstance(item, Path) else item for item in cmd_i]
        print(f"Running: {' '.join(cmd)}")
        if self.nolog:
            subprocess.run(cmd)
        else:
            sname = self.sifpath.name
            ts = datetime.datetime.now().strftime(f"{sname}-%b%d-%H:%M:%S.log")
            with open(ts, 'w') as logfile:
                print(f"logging to {logfile.name}")
                cp = subprocess.run(cmd, stdout=logfile, stderr=subprocess.STDOUT)
                if cp.returncode != 0:
                    print(f"Returned: {cp.returncode}")
                    sys.exit(cp.returncode)

    def _update_control(self):
        if self.control and self.software:
            current = set()
            with open(self.control) as f:
                content = f.readlines()
            output = []
            for line in content:
                if line.startswith('XB-Nmrbox-Software') or line.startswith('XB-Nmrbox-Include'):
                    parts = line.split(':')
                    if len(parts) != 2:
                        raise ValueError(f"{line} did not split into two")
                    current.add(parts[1].strip().upper())
                else:
                    output.append(line.rstrip(' \n'))
            updated = set(self.software)
            if updated == current:
                builder_logger.info(f"Control unchanged")
                return
            ordered = sorted(self.software)
            assert len(ordered) > 0
            with open(self.control,'w') as f:
                for line in output:
                    print(line,file=f)
                print(f"XB-Nmrbox-Software: {ordered[0]}",file=f)
                for index, software in enumerate(ordered[1:]):
                    print(f"XB-Nmrbox-Include{index}: {software}",file=f)
            print(f"{self.control.as_posix()} updated")
            self.control = None # make idempotent

    @ChoiceCommand(actionchoice)
    def sif(self):
        """Build single sif from def file"""
        self._check_paths()
        if self.build_wrappers:
            self.wrappers()

        cmd = [APPTAINER, 'build']
        if (uid := os.geteuid()) != 0:
            builder_logger.debug(f"uid is {uid}, adding fakeroot")
            cmd.append('--fakeroot')
        cmd.extend((self.sifpath, self.defpath))
        self._run(cmd)
        self._update_control()

    @ChoiceCommand(actionchoice)
    def sandbox(self):
        """Build writable sandbox directory from def file"""
        self._check_paths()
        self._run((APPTAINER, 'build', '--sandbox', self.sifpath, self.defpath))

    @ChoiceCommand(actionchoice)
    def wrappers(self):
        """Generate wrappers to invoke app in container"""
        for app, data in self.apps.items():
            if 'run' in data:
                wfile = self.wrapper_dir / app
                if wfile.is_file() and not self.force:
                    builder_logger.warning(f"{wfile.as_posix()} exists")
                    continue
                with open(wfile, 'w', opener=executable) as f:
                    print('#!/bin/bash', file=f)
                    print(f'exec {APPTAINER} run --app {app} {self.installed} "$@"', file=f)
                builder_logger.info(f"Generated {wfile.as_posix()}")


@dataclass
class ParseSpec:
    directories: Iterable[str]
    depth: int


@dataclass
class ParseOut:
    yamls: Iterable[Path]


class _DirectoryParser:
    """Helper to find YAMLS"""

    def __init__(self, p: ParseSpec):
        self.spec = p
        self.yamls: List[Path] = []

    def _parse(self, directories, depth):
        for dpath in directories:
            if not dpath.is_dir():
                raise ValueError(f"{dpath.as_posix()} is not a directory")
            for p in Path(dpath).glob('*yaml'):
                self.yamls.append(p)
            if depth > 0:
                subs = [d for d in dpath.iterdir() if d.is_dir()]
                self._parse(subs, depth - 1)

    def parse(self)->List[Path]:
        """Find and return YAMLS"""
        if self.spec.directories:
            dpaths = [Path(d) for d in self.spec.directories]
            self._parse(dpaths, self.spec.depth)
            if len(set(self.yamls)) != len(self.yamls):
                raise ValueError(f"Duplicate file name? {','.join(self.yamls)}")
            return self.yamls


def main():
    logging.basicConfig()
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('primary', help="primary configuration file")
    builder = Builder()
    adapter = ArgparserAdapter(builder)
    adapter.register(parser)
    parser.add_argument('-d', '--directory', action='append', help="Directory to scan for yamls")
    parser.add_argument('--depth', type=int, default=0, help="How far to descond into directories looking for yamls")
    parser.add_argument('-l', '--loglevel', default='WARN', help="Python logging level")
    parser.add_argument('--force', action='store_true', help="Overwrite existing def and sif")
    parser.add_argument('--nolog', action='store_true', help="Apptainer output to stdout/stderr instead of log files")
    parser.add_argument('--wrappers', action='store_true', help="Generate wrappers with 'sif'")
    parser.add_argument('--control', help="Add software tags to control file")

    args = parser.parse_args()
    builder_logger.setLevel(getattr(logging, args.loglevel))
    builder.force = args.force
    builder.nolog = args.nolog
    builder.build_wrappers = args.wrappers
    builder.control = args.control
    builder.load(args.primary)
    dp = _DirectoryParser(ParseSpec(args.directory, args.depth))
    yamls = dp.parse()
    builder.configure(yamls)

    adapter.call_specified_methods(args)


if __name__ == "__main__":
    main()
