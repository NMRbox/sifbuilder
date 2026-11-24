import logging
import subprocess
import sys
from pathlib import Path

from sifbuilder import builder_logger


class UnversionedError(ValueError):
    """File is not under subversion control"""


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
            status = getattr(self, '_status', '').strip()
            raise ValueError(f"not committed to subversion (schedule={self.Schedule} status={status!r}); "
                             "commit it, or use --force")
        url = self.URL.split('//')[1]
        rev = getattr(self, 'Last_Changed_Rev', 'uncommitted')
        suffix = '' if self._synced else ' (uncommitted)'
        return f'{url} {rev}{suffix}'


    @staticmethod
    def parse(yfile: Path)-> 'SourceInfo':
        builder_logger.info(f"svn parsing {yfile.as_posix()}")
        if not yfile.is_file():
            raise ValueError(f"{yfile.as_posix()} is not a file")
        st = subprocess.run(('svn', 'status', yfile.as_posix()), capture_output=True, text=True)
        if st.returncode == 0 and st.stdout.startswith('?'):
            raise UnversionedError("not under version control; run 'svn add' and 'svn commit', or use --force")
        info = SourceInfo()
        cp = subprocess.run(('svn', 'info', yfile.as_posix()), capture_output=True, text=True)
        if cp.returncode != 0:
            raise ValueError(f"svn info failed: {cp.stderr.strip()}")
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
                raise ValueError(f"svn status failed: {cp.stderr.strip()}")
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
