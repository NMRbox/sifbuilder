import logging
import importlib.metadata 
builder_logger = logging.getLogger(__name__)
__version__ =  importlib.metadata.version('sifbuilder') 

class Package:
    """A debian package supporting NMRbox software"""
    _FIELDS = ('Version', 'Nmrbox-Software', 'Nmrbox-Version')

    def __init__(self, data):
        self.package = data['Package']
        self.pkg_vers = data['Version']
        self.software = data['Nmrbox-Software'].upper()
        self.software_vers = data['Nmrbox-Version']

    def __eq__(self, other):
        return self.software == other.software and self.software_vers == other.software_vers

    def __hash__(self):
        return hash(self.software) & hash(self.software_vers)

    @property
    def package_spec(self) -> str:
        """Package specifier for apt-get"""
        return f"{self.package}={self.pkg_vers}"

    @property
    def software_description(self) -> str:
        """Package specifier for apt-get"""
        return f"{self.software} {self.software_vers}"

    @property
    def isdata(self)->bool:
        """Return true if data package"""
        return 'data' in self.package

    @staticmethod
    def parse(data):
        """Create Package if all fields present in data else return None"""
        if all([f in data for f in Package._FIELDS]):
            return Package(data)
        return None

from subversion_parser import SvnInfo
