#!/usr/bin/env python3
"""
Generate YAML configuration files for NMRBox software packages.

This script analyzes Debian packages to find executables and generates
YAML configuration files with package metadata and executable paths.
"""

import os
import sys
import re
import argparse
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

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
    
    with open(list_file, 'r') as f:
        for line in f:
            file_path = Path(line.strip())
            
            # Check if file exists and is executable
            if not file_path.exists():
                continue
                
            if not os.access(file_path, os.X_OK):
                continue
            
            # Check if file is in a PATH directory
            if file_path.parent in path_dirs:
                executables.append((file_path.name, str(file_path)))
    
    return executables

def parse_dpkg_status(package_name):
    """
    Parse /var/lib/dpkg/status to find Nmrbox-Software and Nmrbox-Version fields.
    
    Args:
        package_name: Name of the Debian package
        
    Returns:
        Tuple of (software_name, version_type) or (None, None) if not found
    """
    status_file = Path("/var/lib/dpkg/status")
    
    if not status_file.exists():
        print(f"Error: Status file not found: {status_file}", file=sys.stderr)
        return None, None
    
    software_name = None
    version_type = None
    in_package = False
    
    with open(status_file, 'r') as f:
        for line in f:
            line = line.strip()
            
            # Start of a package entry
            if line.startswith('Package:'):
                pkg = line.split(':', 1)[1].strip()
                in_package = (pkg == package_name)
                
            # If we're in the right package, look for our fields
            if in_package:
                if line.startswith('Nmrbox-Software:'):
                    software_name = line.split(':', 1)[1].strip()
                elif line.startswith('Nmrbox-Version:'):
                    version_type = line.split(':', 1)[1].strip()
                    
            # Empty line indicates end of package entry
            if not line and in_package:
                break
    
    return software_name, version_type

def generate_yaml_config(package_name, output_file=None, verbose=False):
    """
    Generate YAML configuration file for a package.
    
    Args:
        package_name: Name of the Debian package
        output_file: Output file path (default: <package_name>.yaml)
        verbose: Print detailed information
    """
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    
    # Parse package information
    if verbose:
        print(f"Parsing package information for: {package_name}")
    
    software_name, version_type = parse_dpkg_status(package_name)
    
    if not software_name:
        print(f"Error: Could not find Nmrbox-Software field for {package_name}", file=sys.stderr)
        print(f"Package may not be an NMRBox software package", file=sys.stderr)
        sys.exit(1)
    
    if verbose:
        print(f"Found software: {software_name}")
        if version_type:
            print(f"Version type: {version_type}")
    
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
    
    config['sifassembly'] = True
    config.yaml_set_comment_before_after_key('sifassembly', 
                                            after='Whether this software needs SIF assembly')
    
    config['app'] = software_name
    config.yaml_set_comment_before_after_key('app', 
                                            after='Application name')
    
    config['packages'] = [package_name]
    config.yaml_set_comment_before_after_key('packages', 
                                            after='Debian packages to install')
    
    config['software'] = software_name
    config.yaml_set_comment_before_after_key('software', 
                                            after='Software identifier')
    
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
        config.yaml_set_comment_before_after_key('run', 
                                                before='Executable commands and their target paths')
    
    # Determine output filename
    if output_file is None:
        output_file = f"{package_name}.yaml"
    
    # Write YAML file
    with open(output_file, 'w') as f:
        yaml.dump(config, f)
    
    print(f"Generated: {output_file}")
    
    if not verbose:
        print(f"  Software: {software_name}")
        print(f"  Package: {package_name}")
        print(f"  Executables: {len(executables)}")
    
    if executables and not verbose:
        print(f"  Commands:")
        for exe_name, _ in executables:
            print(f"    - {exe_name}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate YAML configuration files for NMRBox software packages.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s nmrbox-nmr-poky
  %(prog)s nmrbox-nmr-poky -o poky.yaml
  %(prog)s nmrbox-nmr-spinach --verbose
        """
    )
    
    parser.add_argument(
        'package',
        help='Name of the Debian package'
    )
    
    parser.add_argument(
        '-o', '--output',
        metavar='FILE',
        help='Output file path (default: <package-name>.yaml)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print detailed information during processing'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.0'
    )
    
    args = parser.parse_args()
    
    generate_yaml_config(args.package, args.output, args.verbose)

if __name__ == "__main__":
    main()
