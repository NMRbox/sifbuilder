import subprocess
import sys
from pathlib import Path

from sifbuilder import SvnInfo


def subversion_info(yfile: Path)->SvnInfo:
    assert yfile.is_file()
    info = SvnInfo()
    cp = subprocess.run(('svn', 'info', yfile.as_posix()), capture_output=True, text=True)
    if cp.returncode != 0:
        print(cp.stderr, file=sys.stderr)
        raise ValueError(f"Invalid subversion {yfile.as_posix()}")
    for out in cp.stdout.split('\n'):
        parts = out.split(':', maxsplit=2)
        if len(parts) == 2:
            field = parts[0].replace(' ', '_')
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
    i = subversion_info(Path(sys.argv[1]))
    print(i.ident())
