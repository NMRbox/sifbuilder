import collections
from dataclasses import dataclass
from typing import List

from debian import debian_support

from sifbuilder import builder_logger, Package


def _splitter(line: str):
    """Split a line with : in it.
    Strip whitespace, return None, None if : not present"""
    if ':' in line:
        key, value = line.split(':', maxsplit=1)
        return key, value.strip('\n').strip()
    return None, None


def _maxpackage(data: List[Package]) -> List[Package]:
    """Find the Package(s) with the maximum debian version number"""
    n = len(data)
    if n == 0:
        return data
    if n == 1:
        return data
    pkg_latest = collections.defaultdict(list)
    for d in data:
        pkg_latest[d.package].append(d)
    result: List[Package] = []
    for pkg, versions in pkg_latest.items():
        assert versions
        if len(versions) == 1:
            result.append(versions[0])
            continue
        latest = versions[0]
        for p in versions[1:]:
            cresult = debian_support.version_compare(p.pkg_vers, latest.pkg_vers)
            assert cresult != 0
            if cresult == 1:
                latest = p
        result.append(latest)

    return result


def _maxpackage_vers(data: List, attribute: str) -> str:
    """Find maximum package versions of data
    :data list to examine
    :param attribute name of attribute version is present in"""
    assert data
    if len(data) == 1:
        return getattr(data[0], attribute)
    highest = getattr(data[0], attribute)
    for c in data[1:]:
        cvers = getattr(c, attribute)
        if debian_support.version_compare(cvers, highest) == 1:
            highest = cvers
    return highest


@dataclass
class Software:
    software: str
    version: str
    packages: List[Package]
    data_packages: List[Package]

    def __str__(self):
        return f'{self.software} {self.version}'

    def __post_init__(self):
        """If no main packages, make data packages main packages"""
        if len(self.packages) == 0:
            assert self.data_packages
            self.packages = self.data_packages
            self.data_packages = []

    @property
    def max_package_vers(self) -> str:
        """Max version of all packages"""
        return _maxpackage_vers(self.packages, 'pkg_vers')

    @staticmethod
    def latest_packages(data: List['Software']) -> List['Software']:
        """Return the Software objects corresponding to the latest debian package versions"""
        mv = _maxpackage_vers(data, 'max_package_vers')
        sw = [s for s in data if s.max_package_vers == mv]
        return sw


"""Parse local status file to map Software to debian packages"""


def parse_nmrbox_list(src: str = '/var/lib/apt/lists/apt.nmrbox.org_ubuntu20_nmrbox_Packages'):
    packages = collections.defaultdict(list)
    bag = {}
    builder_logger.info(f"Parsing {src}")
    with open(src) as f:
        for line in f:
            key, value = _splitter(line)
            if key is not None:
                if key == 'Package':
                    if (p := Package.parse(bag)) is not None:
                        packages[p.software].append(p)
                    bag = {key: value}
                    continue
                bag[key] = value
    index = collections.defaultdict(lambda: {})
    for sw, pkglist in packages.items():
        if sw == 'UTILITY':
            continue
        software_versions = collections.defaultdict(list)
        p: Package
        for p in pkglist:
            assert p.software == sw
            software_versions[p.software_vers].append(p)
        for swvers, pkglist in software_versions.items():
            code = []
            data = []
            for p in pkglist:
                if p.isdata:
                    data.append(p)
                else:
                    code.append(p)
            software = Software(sw, swvers, _maxpackage(code), _maxpackage(data))
            index[sw][swvers] = software
    return index


if __name__ == "__main__":
    index = parse_nmrbox_list()
    so = index['NMRPIPE']
    print(index)
