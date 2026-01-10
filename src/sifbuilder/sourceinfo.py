import logging
import subprocess
import sys
from pathlib import Path

from sifbuilder import builder_logger


class SourceInfo:
    __slots__ = ['Path',
                 'Name',
                 'URL',
                 'Schedule',
                 'Last_Changed_Rev',
                 '_synced',
                 '_status']

    def ident(self,force:bool=False)->str:
        """Return identifier for committed SVN file"""
        if not force and not self._synced:
            raise ValueError(f"Unsupported SVN state {self.Schedule} {self._status}")
        url = self.URL.split('//')[1]
        return f'{url} {self.Last_Changed_Rev}'


    @staticmethod
    def parse(yfile: Path)-> 'SourceInfo':
        builder_logger.info(f"svn parsing {yfile.as_posix()}")
        assert yfile.is_file()
        info = SourceInfo()
        cp = subprocess.run(cmd := ('svn', 'info', yfile.as_posix()), capture_output=True, text=True)
        if cp.returncode != 0:
            print(cp.stderr, file=sys.stderr)
            raise ValueError(f"Invalid subversion {yfile.as_posix()}")
        for out in cp.stdout.split('\n'):
            parts = out.split(':', maxsplit=1)
            if len(parts) == 2:
                field = parts[0].replace(' ', '_')
                we_want = field in info.__slots__
                builder_logger.debug(f"We want {field}? {we_want}")
                if we_want:
                    setattr(info,field,parts[1].strip())
        info._synced = True
        if info.Schedule == 'normal':
            cp = subprocess.run(('svn', 'status', yfile.as_posix()), capture_output=True, text=True)
            if cp.returncode != 0:
                print(cp.stderr, file=sys.stderr)
                raise ValueError(f"Invalid subversion status {yfile.as_posix()}")
            if cp.stdout:
                info._status = cp.stdout
                info._synced = False
        else:
            info._synced = False

        return info


if __name__ == "__main__":
    logging.basicConfig()
    builder_logger.setLevel(logging.DEBUG)
    i = SourceInfo.parse(Path(sys.argv[1]))
    print(i.ident())
