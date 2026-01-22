#!/usr/bin/env python3
"""
Generate YAML configuration files for NMRBox software packages.

This script analyzes Debian packages to find executables and generates
YAML configuration files with package metadata and executable paths.

Version: 1.3.0
"""

import os
import sys
import re
import argparse
import socket
from datetime import datetime
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

__version__ = "1.3.0"

def find_executables_in_package(package_name):
    """
    Find all executable files from a package that are on PATH.
    
    Args:
        package_name: Name of the Debian package
        
    Returns:
        List of (executable_name, full_path) tuples
    """
    list_file = Path(f"/var/lib/dpkg/info/{package_name}.list")
    
    if not list_file.exists():
        print(f"Error: Package list file not found: {list_file}", file=sys.stderr)
        return []
    
    # Get PATH directories
    path_dirs = os.environ.get('PATH', '').split(':')
    path_dirs = [Path(p) for p in path_dirs if p]
    
    executables = []
    
    try:
        with open(list_file, 'r') as f:
            for line in f:
                file_path = Path(line.strip())
                
                # Check if file exists and is executable
                try:
                    if not file_path.exists():
                        continue
                except PermissionError:
                    # Skip files we can't access
                    continue
                    
                try:
                    if not os.access(file_path, os.X_OK):
                        continue
                except PermissionError:
                    # Skip files we can't check permissions on
                    continue
                
                # Check if file is in a PATH directory
                if file_path.parent in path_dirs:
                    executables.append((file_path.name, str(file_path)))
    except PermissionError as e:
        print(f"Warning: Permission denied reading {list_file}: {e}", file=sys.stderr)
        return []
    
    return executables

def parse_dpkg_status(package_name=None):
    """
    Parse /var/lib/dpkg/status to find package information.
    
    Args:
        package_name: Name of specific package, or None to find all NMRBox packages
        
    Returns:
        If package_name is specified: Tuple of (software_name, version_type, version)
        If package_name is None: Dict of {package_name: (software_name, version_type, version)}
    """
    status_file = Path("/var/lib/dpkg/status")
    
    if not status_file.exists():
        print(f"Error: Status file not found: {status_file}", file=sys.stderr)
        return None if package_name else {}
    
    packages = {}
    current_package = None
    software_name = None
    version_type = None
    version = None
    
    try:
        with open(status_file, 'r') as f:
            for line in f:
                line = line.strip()
                
                # Start of a package entry
                if line.startswith('Package:'):
                    # Save previous package if it had Nmrbox-Software
                    if current_package and software_name:
                        packages[current_package] = (software_name, version_type, version)
                    
                    # Reset for new package
                    current_package = line.split(':', 1)[1].strip()
                    software_name = None
                    version_type = None
                    version = None
                    
                elif line.startswith('Version:'):
                    version = line.split(':', 1)[1].strip()
                    
                elif line.startswith('Nmrbox-Software:'):
                    software_name = line.split(':', 1)[1].strip()
                    
                elif line.startswith('Nmrbox-Version:'):
                    version_type = line.split(':', 1)[1].strip()
            
            # Don't forget the last package
            if current_package and software_name:
                packages[current_package] = (software_name, version_type, version)
    except PermissionError as e:
        print(f"Error: Permission denied reading {status_file}: {e}", file=sys.stderr)
        return None if package_name else {}
    
    if package_name:
        return packages.get(package_name, (None, None, None))
    else:
        return packages

def get_yaml_filename_from_package(package_name):
    """
    Generate YAML filename from package name by using the last part.
    
    Args:
        package_name: Full package name (e.g., 'nmrbox-nmr-poky')
        
    Returns:
        YAML filename (e.g., 'poky.yaml')
    """
    # Split on hyphens and take the last part
    parts = package_name.split('-')
    base_name = parts[-1]
    return f"{base_name}.yaml"

def generate_yaml_config(package_name, output_file=None, verbose=False):
    """
    Generate YAML configuration file for a package.
    
    Args:
        package_name: Name of the Debian package
        output_file: Output file path (default: <last-part>.yaml)
        verbose: Print detailed information
    """
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    yaml.explicit_start = True  # Add --- at start
    yaml.explicit_end = True    # Add ... at end
    yaml.indent(mapping=2, sequence=2, offset=2)  # Proper indentation
    
    # Parse package information
    if verbose:
        print(f"Parsing package information for: {package_name}")
    
    software_name, version_type, pkg_version = parse_dpkg_status(package_name)
    
    if not software_name:
        print(f"Error: Could not find Nmrbox-Software field for {package_name}", file=sys.stderr)
        print(f"Package may not be an NMRBox software package", file=sys.stderr)
        return False
    
    if verbose:
        print(f"Found software: {software_name}")
        if version_type:
            print(f"Version type: {version_type}")
        if pkg_version:
            print(f"Package version: {pkg_version}")
    
    # Find executables
    if verbose:
        print("Searching for executables...")
    
    executables = find_executables_in_package(package_name)
    
    if not executables:
        print(f"Warning: No executables found on PATH for {package_name}", file=sys.stderr)
    elif verbose:
        print(f"Found {len(executables)} executable(s)")
    
    # Create YAML structure
    config = CommentedMap()
    
    # Add header comment with generation metadata
    hostname = socket.gethostname()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    program_name = os.path.basename(sys.argv[0])
    
    header_comment = (
        f"Generated by: {program_name} v{__version__}\n"
        f"Host: {hostname}\n"
        f"Date: {timestamp}\n"
        f"Package: {package_name}"
    )
    
    if pkg_version:
        header_comment += f"\nPackage Version: {pkg_version}"
    
    config.yaml_set_start_comment(header_comment)
    
    config['sifassembly'] = True
    
    config['app'] = software_name
    
    # Use CommentedSeq for proper list indentation
    packages_list = CommentedSeq([package_name])
    config['packages'] = packages_list
    
    config['software'] = software_name
    
    # Add run section with executables
    if executables:
        run_section = CommentedMap()
        
        # Sort executables by name for consistent output
        executables.sort(key=lambda x: x[0])
        
        for exe_name, exe_path in executables:
            # Target path is always /usr/software/bin/<exe_name>
            target_path = f"/usr/software/bin/{exe_name}"
            run_section[exe_name] = target_path
        
        config['run'] = run_section
    
    # Determine output filename
    if output_file is None:
        output_file = get_yaml_filename_from_package(package_name)
    
    # Write YAML file
    try:
        with open(output_file, 'w') as f:
            yaml.dump(config, f)
    except PermissionError as e:
        print(f"Error: Permission denied writing to {output_file}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error writing {output_file}: {e}", file=sys.stderr)
        return False
    
    print(f"Generated: {output_file}")
    
    if not verbose:
        print(f"  Software: {software_name}")
        print(f"  Package: {package_name}")
        print(f"  Executables: {len(executables)}")
    
    if executables and not verbose:
        print(f"  Commands:")
        for exe_name, _ in executables:
            print(f"    - {exe_name}")
    
    return True

def process_all_packages(verbose=False):
    """
    Find and process all packages with Nmrbox-Software field.
    
    Args:
        verbose: Print detailed information
    """
    if verbose:
        print("Scanning /var/lib/dpkg/status for NMRBox packages...")
    
    packages = parse_dpkg_status()
    
    if not packages:
        print("No NMRBox packages found", file=sys.stderr)
        return
    
    print(f"Found {len(packages)} NMRBox package(s)")
    print()
    
    success_count = 0
    
    for package_name in sorted(packages.keys()):
        try:
            if generate_yaml_config(package_name, verbose=verbose):
                success_count += 1
        except PermissionError as e:
            print(f"Warning: Permission denied processing {package_name}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error processing {package_name}: {e}", file=sys.stderr)
        print()
    
    print(f"Successfully generated {success_count}/{len(packages)} YAML files")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate YAML configuration files for NMRBox software packages.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate YAML for a specific package
  %(prog)s nmrbox-nmr-poky
  
  # Generate with custom output filename
  %(prog)s nmrbox-nmr-poky -o custom.yaml
  
  # Process all NMRBox packages
  %(prog)s --all
  
  # Verbose mode
  %(prog)s nmrbox-nmr-spinach --verbose
        """
    )
    
    parser.add_argument(
        'package',
        nargs='?',
        help='Name of the Debian package (required unless --all is used)'
    )
    
    parser.add_argument(
        '-o', '--output',
        metavar='FILE',
        help='Output file path (default: <last-part-of-package>.yaml)'
    )
    
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='Process all packages with Nmrbox-Software field'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print detailed information during processing'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.all:
        if args.package:
            parser.error("Cannot specify package name with --all")
        if args.output:
            parser.error("Cannot specify --output with --all")
        process_all_packages(args.verbose)
    else:
        if not args.package:
            parser.error("Package name required (or use --all)")
        generate_yaml_config(args.package, args.output, args.verbose)

if __name__ == "__main__":
    main()
