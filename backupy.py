# -*- coding: utf-8 -*-
"""
backupy {version}

Creates a zip-archive of the folder where the script is executed (or <root>
if given).

`backupy build` creates a csv-file in the <root> directory that contains
the directory structure that will be backed up, considering the selected
options. You can also edit this file manually to include / exclude certain
parts of the directory structure. An include/exclude option for deeper paths
has priority over less deep paths.

`backupy reset` deletes the csv-file for <root>.

`backupy zip` creates a compressed zip-file in the parent directory
of <root> named after <root> and the current datetime.

Usage:    
    backupy build [<root> -i <dir>... -e <dir>... --show=<MB> --filemax=<MB> --dp=<depth>]
    backupy reset [<root>]
    backupy zip [<root>]
    backupy -h|--help

Arguments:
    root         Base directory to backup. Defaults to current working dir

Options:
    -h --help       Show this help text
    -i <dir>...     Include *only* the given subdirectory + its children.
                    <dir> is interpreted relative to <root>.
                    Option can be repeated multiple times.
    -e <dir>...     Exclude the given subdirectory + its children from backup.
                    <dir> is interpreted relative to <root>.
                    Option can be repeated multiple times.
    --show=<MB>     Min. item size in MB to show in the csv-file. Triggers the
                    "granularity" at which manual edits can be applied later.
                    For smaller items the backup policy of the parent directory
                    is adopted [default: 1]
    --filemax=<MB>  Size-filter to exclude files larger <MB> from backup.
                    A negative value disables the option [default: -1]
    --dp=<depth>    Max. recursion depth for editing backup paths. A negative
                    value doesn't limit the recursion depth [default: -1]
"""
import csv
import datetime
import logging
import math
import numpy as np
import os, sys

from colorama import Fore, Back, Style
from docopt import docopt
from pathlib import Path
from zipfile import ZipFile, ZIP_LZMA

# Definition of globals and classes
__all__ = ["Backup", "BackupPath", "BackupPathStructure"]
__version__ = '0.1'
__doc__ = __doc__.format(version=__version__)

BACKUPY_CFG = ".backupy.cfg"  # suffix for configuration file
BACKUPY_LOG = ".backupy.log"  # suffix for log file


def print_size(size, split=False, digits=1, fixedwidth=True):
    """Pretty-print a size value in KB, MB, GB or TB with given number
    of total digits, resulting in total string length of `digits + 4`
    """
    if size >= 1E15:
        suffix = "P"
        size /= 1E15
    elif size >= 1E12:
        suffix = "T"
        size /= 1E12
    elif size >= 1E9:
        suffix = "G"
        size /= 1E9
    elif size >= 1E6:
        suffix = "M"
        size /= 1E6
    elif size >= 1E3:
        suffix = "K"
        size /= 1E3
    else:
        suffix = "B"
    if suffix == "B":
        size = "{:3.0f}".format(size)
        if fixedwidth:
            size += " " * (digits + 1)
    else:
        if fixedwidth:
            size = "{{:{:d}.{:d}f}}".format(digits + 4, digits)\
                                    .format(size)
        else:
            size = "{{:.{:d}f}}".format(digits).format(size)
    if split:
        return (size, suffix)
    return size + " " + suffix
    #val2 = round(x, -int(math.floor(math.log10(abs(x)))))


def get_n_digits(number):
    """Without floating point part"""
    return int(math.floor(math.log10(abs(number)))) + 1


def get_filename_backupy(root):
    """Return canonic filename for backup configuration file
    with respect to the given base directory
    """
    return os.path.normpath(os.path.join(root, BACKUPY_CFG))


def get_filename_log(root):
    """Return canonic filename for log file
    with respect to the given base directory
    """
    return os.path.normpath(os.path.join(root, BACKUPY_LOG))

    
class BackupPath(object):
    """Taken from https://stackoverflow.com/a/49912639/3104974"""
    display_filename_prefix_middle = "├─ "
    display_filename_prefix_last = "└─ "
    display_parent_prefix_middle = "   "
    display_parent_prefix_last = "│  "
    def __init__(self, path, parent_path, is_last,
                 namefilter=lambda x: True,
                 sizefilter=lambda x: True):
        self.path = Path(str(path))
        self.parent = parent_path
        self.is_last = is_last
        self.is_visible = True
        self.size = 0 if self.path.is_dir() else os.path.getsize(self.path)
        self.n_files = 1 if path.is_file() else 0
        if self.parent:
            self.depth = self.parent.depth + 1
        else:
            self.depth = 0
        self.backup = namefilter(self) and sizefilter(self)
         
        # update size, n_files and backup to all parents
        prnt = self.parent
        child = self
        while prnt is not None:
            prnt.size += child.size
            prnt.n_files += 1 if child.path.is_file() else 0
            prnt.backup |= self.backup  # if any child is backed up,
                                        # then also the parent
            prnt = prnt.parent

    @classmethod
    def make_namefilter(cls, include=[], exclude=[]):
        def func(bp):
            result = True
            if bp.path in include:
                result = True
            elif bp.path in exclude:
                result = False
            elif bp.parent:
                result = func(bp.parent)
            return result
        return func
            
    @classmethod
    def make_tree(cls, root, parent=None, is_last=False, dir_first=True,
                  include=[], exclude=[], filemax=0):
        """Entry method for creating a recursive path structure.
        """
        root = Path(str(root))
        if filemax > 0:
            sizefilter = lambda s: s.size < filemax
        else:
            sizefilter = lambda s: True

        backup_root = cls(root, parent, is_last,
                          cls.make_namefilter(include, exclude),
                          sizefilter)
        yield backup_root

        
        sort_key = lambda s: (s.is_file() if dir_first else s.is_dir(),
                              str(s).lower())
        children = sorted(list(path
                               for path in root.iterdir()),
                          key=sort_key)
        count = 1
        for path in children:
            is_last = count == len(children)
            if path.is_dir():
                yield from cls.make_tree(path,
                                         parent=backup_root,
                                         is_last=is_last,
                                         dir_first=dir_first,
                                         include=include,
                                         exclude=exclude,
                                         filemax=filemax)
            else:
                yield cls(path, backup_root, is_last,
                          cls.make_namefilter(include, exclude),
                          sizefilter)
            count += 1
    
    def displaysize(self, split=False):
        """String for file / directory size with fixed width of 7 characters.
        Examples: " 1.3 M", "345   B"
        """
        return print_size(self.size, split, digits=1, fixedwidth=True)
    
    @property
    def displaynfiles(self):
        """String for number of files of a directory, or "" for a file"""
        if self.path.is_dir():
            return " ({} files)".format(self.n_files)
        return ""

    def displayname(self, sizeannotate=1E6, basic=False):
        """String for path / file incl. size and number of files
        for a directory
        """
        result = ""
        result += self.path.name if self.depth > 0 else ""
        if self.path.is_dir():
            result += os.sep
        if basic:
            return result
        
        if sizeannotate and self.size > sizeannotate:
            result += f" {self.displaysize()}"
        result += self.displaynfiles
        return result

    def display(self):
        """Concatenating self.displayname with tree-prefixes"""
        if not self.is_visible:
            return ''
        if self.parent is None:
            return self.displayname(basic=True)

        _filename_prefix = (self.display_filename_prefix_last
                            if self.is_last
                            else self.display_filename_prefix_middle)

        parts = ['{!s}{!s}'.format(_filename_prefix,
                                    self.displayname(basic=True))]

        parent = self.parent
        while parent and parent.parent is not None:
            parts.append(self.display_parent_prefix_middle
                         if parent.is_last
                         else self.display_parent_prefix_last)
            parent = parent.parent

        return ''.join(reversed(parts))
    

class BackupPathStructure(object):
    """Convenience class for managing a set of recursive BackupPath objects
    """
    display_style_big_entry = Back.YELLOW + Style.DIM
    display_style_backup_all = Fore.YELLOW
    style_big_entry_quantile = 0.1
    max_display = 1000
    
    csv_delimiter = "*"
    csv_quoting = csv.QUOTE_NONE
    csv_escapechar = "?"
    
    def __init__(self, root, include=[], exclude=[],
                 show=1E6, filemax=-1, max_depth=-1, dir_first=True):
        """
        root: base directory 
        include, exclude: lists of directory or files that shall explicitly
            be included in or excluded from the backup. Regardless of other
            parameters these parts of the directory structure will always
            appear in the config-file, so you can edit them manually
        show: Size in bytes. Smaller entries are displayed only when in
            `include` or `exclude`
        filemax: Files larger than this value in bytes are included in display,
            but excluded from backup (-1 to deactivate)
        max_depth: Entries in a deeper folder-level than this are excluded
            from display (-1 to deactivate)
        dir_first: If False, files are listed first, then directories
        """
        self.root = Path(str(root))
        self.dir_first = dir_first
        self.include = include
        self.exclude = exclude
        self.show = show
        self.filemax = filemax
        self.tree = BackupPath.make_tree(self.root,
                                         include=include,
                                         exclude=exclude,
                                         filemax=filemax,
                                         dir_first=dir_first)
        self.backuppaths = []
        self.sizedist = []
        self.max_depth_display = max_depth
        self.max_depth_is = 0
        for bp in self.tree:
            self.max_depth_is = max(self.max_depth_is, bp.depth)
            self.backuppaths.append(bp)
            if bp.path.is_file():
                self.sizedist.append(bp.size)
        self.sizedist.sort(reverse=True)
        self.size_total = sum(self.sizedist)
        self.size_highlight = np.quantile(
            self.sizedist, 1 - self.style_big_entry_quantile)
# =============================================================================
#         # number of entries up to each depth-index
#         self.n_entries = [sum([len(_) for _ in self.sizes[:i+1]]) \
#                           for i in range(self.depthmax)]
#         self.max_depth = max([i if n <= self.max_entries else -1
#                              for i, n in enumerate(self.n_entries)])
# =============================================================================
        
    def scan(self, sizeannotate=1E8, display=True, ansi_highlight=True):
        """Main method for scanning the structure and returning a tuple
        of 6 values:
            - list of pretty names
            - list of path objects
            - list of sizes
            - list of sizes in percent
            - list of backup-flags
            - int for max. character length of pretty names
            
        """
        names = []
        names_raw = []
        sizes = []
        sizep = []
        backup = []
        names_len_max = 0
        for bp in self.backuppaths:
            # directory explicitly mentioned in include/exclude always show up
            explicit = bp.path in self.include + self.exclude
            if not explicit and (
                bp.depth > self.max_depth_display > -1 or \
                    (display and len(self.sizedist) > self.max_display\
                     and bp.size <= self.sizedist[self.max_display])
                ):
                # only display the `max_display` largest items
                continue
            _filename_prefix = (bp.display_filename_prefix_last
                                if bp.is_last
                                else bp.display_filename_prefix_middle)
    
            name = bp.displayname(sizeannotate, basic=False)#not display)
            if bp.size > self.size_highlight:
                style = self.display_style_big_entry
            else:
                style = ""
            if ansi_highlight:
                parts = ['{!s}{}{!s}{}'.format(_filename_prefix,
                                               style, name, Style.RESET_ALL)]
            else:
                parts = ['{!s}{!s}'.format(_filename_prefix, name)]
    
            parent = bp.parent
            while parent and parent.parent is not None:
                parts.append(bp.display_parent_prefix_middle
                             if parent.is_last
                             else bp.display_parent_prefix_last)
                parent = parent.parent
    
            if bp.path == self.root or bp.size > self.show or explicit:
                names.append(''.join(reversed(parts)))
                names_len_max = max(names_len_max, len(names[-1]))
                names_raw.append(bp.path)
                sizes.append(bp.displaysize())
                sizep.append(bp.size / self.size_total)
                backup.append(bp.backup)
        if display:
            return '\n'.join(names)
        return [names, names_raw, sizes, sizep, backup, names_len_max]
    
    @classmethod
    def from_backup_conf(cls, root):
        """Return BackupPathStructure from config file. It is expected
        that 'backupy build' was run first on the given root directory,
        otherwise an error is raised.
        """
        backup_conf = cls._read_backup_conf(root) 
        inst = cls(root, show=0)
        for bp in inst.backuppaths:
            parts = bp.path.relative_to(root).parts
            bc = backup_conf
            backup = backup_conf["."]
            for folder in parts:
                if folder in bc.keys():
                    bc = bc[folder]
                backup = bc["."]
            bp.backup = backup
        return inst
    
    def make_backup_conf(self):
        """Create config file on disk for the BackupPathStructure.
        This config file may be edited manually (i.e. backup-flag changed)
        """
        fn = get_filename_backupy(self.root)
        with open(fn, "w", encoding="utf-8", newline="\n") as csvfile:
            wrt = csv.writer(csvfile, 
                             delimiter=self.csv_delimiter,
                             quoting=self.csv_quoting,
                             escapechar=self.csv_escapechar)
            names, names_raw, sizes, sizep, backup, lmax = \
                self.scan(display=False, ansi_highlight=False)
            wrt.writerow(["    size ", "  size% ", " backup ",
                          f" {'path (human readable)': <{lmax}} ",
                          " path (read from script)"])
            for n, n2, ss, sp, b in zip(names, names_raw, sizes, sizep, backup):
                wrt.writerow([f" {ss} ", f" {100*sp:5.1f}% ",
                              f"      {int(b)} ",
                              f" {n: <{lmax}} ", f" {n2}" ])
        
        
    @classmethod
    def _read_backup_conf(cls, root):
        #"""Read backup conf as tuples of (backup-flag, path)"""
        """Read backup conf and return dict resembling the folder hierarchy.
        Each level contains the key "." with the backup-flag for the current
        folder an all others files and folders as keys:
            {".": True,
             some_folder: {".": True, ...},
             some_file: {".": False},
            }
        """
        fn = get_filename_backupy(root)
        if not os.path.exists(fn):
            raise IOError(f"No config file found for {root}. Please run "
                          "'backupy build' first")
        with open(fn, "r", encoding="utf-8",
                  newline="\n") as csvfile:
            rd = csv.reader(csvfile,
                            delimiter=cls.csv_delimiter,
                            quoting=cls.csv_quoting,
                            escapechar=cls.csv_escapechar)
            rd.__next__() # header
            #rows = {Path(n2.strip()): bool(int(b)) for ss, sp, b, n, n2 in rd}
            #rows = [(Path(n2.strip()), bool(int(b))) for ss, sp, b, n, n2 in rd]
            result = {}
            for ss, sp, b, n, n2 in rd:
                path, backup = Path(n2.strip()), bool(int(b))
                parts = path.relative_to(root).parts
                if len(parts) == 0:  # root
                    result["."] = backup
                
                res = result
                for folder in parts:
                    if folder not in res.keys():
                        res[folder] = {".": backup}
                    res = res[folder]                
        return result

        
class Backup(object):
    def __init__(self, bps: BackupPathStructure):
        """Backup for given BackupPathStructure. Each BackupPath's backup-flag
        determines which files will be included in the zip archive.
        """
        self.root = bps.root
        self.bps = bps
        self.created = datetime.datetime.now()
    
    @property
    def filename_zip(self):
        dt = self.created.strftime("%Y-%m-%d_%H%M%S")
        return os.path.normpath(os.path.join(
            self.root.parent, f"{self.root.name}_{dt}.zip"    
        ))
        
    def backup(self):
        """Create the zip file and a log file
        """
        log_fn = get_filename_log(root)
        logging.basicConfig(filename=log_fn,
            #encoding='utf-8',
            level=logging.INFO,
            format='%(message)s')
        
        s = f"{self.created.strftime('%Y-%m-%d %H:%M:%S')} " + \
            f" creating {self.filename_zip}"
        logging.info(s)
        print(s)
        out = ZipFile(self.filename_zip, mode="x", compression=ZIP_LZMA)
        bpaths = self.bps.backuppaths
        n_files = [0, 0]
        s_files = [0, 0]
        for bp in bpaths:
            path = bp.path.relative_to(self.root)
            sz = f"({bp.displaysize()})" if bp.path.is_file() else "        "
            if bp.backup:
                ix = 0
                s = f"  + {sz} {str(path)}"
                out.write(bp.path, bp.path.relative_to(self.root))
            else:
                ix = 1
                s = f"  - {sz} {str(path)}"        
            if bp.path.is_file():
                n_files[ix] += 1
                s_files[ix] += os.path.getsize(bp.path)
                logging.info(s)
                print(s)
        out_sz = print_size(os.path.getsize(self.filename_zip),
                            fixedwidth=False)
        root_sz = print_size(bpaths[0].size, fixedwidth=False)
        comp_sz = print_size(s_files[0], fixedwidth=False)
        compr = 100 * (os.path.getsize(self.filename_zip) / s_files[0])
        n1, n2 = sum(n_files), n_files[0]
        nd = get_n_digits(n1)
        s = "              '+': File was included   '-': File was skipped\n" +\
            f"From {n1:{nd:d}d} files / {root_sz} in {self.root} there were\n" +\
            f"     {n2:{nd:d}d} files / {comp_sz} added to the archive and " +\
            f"compressed down to {out_sz} ({compr:.1f} %)\n"
        logging.info(s)
        print(s)

def clean_path(pth, base=os.getcwd(), mode="strict"):
    """If `pth` is relative, combine it with `base`, else take as is.
    `mode` sets the behaviour if the resulting path doesn't exist:
        "strict": sys.exit
        "warn": return `None` and display message
        "ignore": return `None`
    Return absolute `pathlib.Path` or `None`
    """
    assert mode in ("strict", "ignore", "warn")
    result = None
    if pth is not None:
        pth = pth.replace('"', "")  # remove quotes from quoted paths
        pth = pth.replace('%20', " ")
        if Path(pth).is_absolute():
            result = Path(pth)
        else:
            result = Path(os.path.normpath(os.path.join(base, pth)))
    else:
        result = Path(base)
    
    if not os.path.exists(result) and mode in ("strict", "warn"):
        sys.stdout.write(f'\nDirectory doesn\'t exist: "{result}"')
    if not os.path.exists(result) and mode in ("strict", ):
        sys.exit(1)
    if not os.path.exists(result):
        return None
    return result


def clean_paths(pths, base=os.getcwd(), mode="strict"):
    """Same as `clean_path` but for a list of paths. `mode`behaviour:
        "strict": sys.exit if any of the paths doesn't exist
        "warn": Replace non-existent paths with `None` and display message
        "ignore": Replace non-existent paths with `None`
    Return list of `pathlib.Path` objects or `None`
    """
    assert mode in ("strict", "ignore", "warn")
    mode_ = {"strict": "warn", "warn": "warn", "ignore": "ignore"}[mode]
    result = []
    for pth in pths:
        result.append(clean_path(pth, base, mode_))
    if None in result and mode == "strict":
        sys.exit(1)
    return result


def clean_number(x, name, typ=float, mode="strict"):
    assert mode in ("strict", "ignore", "warn")
    try:
        return typ(x)
    except ValueError:
        if mode in ("strict", "warn"):
            sys.stdout.write(f"\nMust be a number: {name}={x}")
        if mode == "strict":
            sys.exit(1)
        return None
  
    
def cmd_build(root, include, exclude, show, filemax, dp):
    """Command line interface function for building the config file.
    See docstring for usage of the parameters.
    """
    sys.stdout.write(f"\nBuilding backup tree for \"{root}\"")
    if show > 0:
        sys.stdout.write(f"\n...showing only files >{show} MB.")
    if filemax > 0:
        sys.stdout.write(f"\n...files >{filemax} MB are excluded from backup.")
    if dp > -1:
        sys.stdout.write(f"\n...max. tree depth to display = {dp} (deeper "
                         "files will be considered, but not shown)")
    if include:
        sys.stdout.write("\n...*Only* these subdirectories will be included:")
        for i in include:
            sys.stdout.write(f"\n    {i}")
    if exclude:
        sys.stdout.write("\n...These subdirectories will be excluded:")
        for e in exclude:
            sys.stdout.write(f"\n    {e}")
    
    inp_ = "x"
    while inp_.lower() != "y":
        inp_ = input('\nContinue processing? (y/n)')
        if inp_.lower() == "n":
            sys.stdout.write("Aborted by user")
            sys.exit(1)
    
    paths = BackupPathStructure(root, include, exclude,
                                show*1E6, filemax*1E6, dp, dir_first=True)
    
    paths.make_backup_conf()
    sys.stdout.write(f"\nConfig file written to {get_filename_backupy(root)}")


def cmd_reset(root):
    """Command line interface function for deleting the config file.
    """    
    fn = get_filename_backupy(root)
    if os.path.exists(fn):
        os.remove(fn)
        sys.stdout.write(f"\nSuccessfully deleted backup configuration: {fn}")
    else:
        sys.stdout.write(f"\nBackup configuration doesn't exist: {fn}")


def cmd_zip(root):
    """Command line interface function for creating the zip archive
    from the config file.
    """    
    paths = BackupPathStructure.from_backup_conf(root)
    fn = get_filename_backupy(root)
    sys.stdout.write(f"Creating zip file for \"{root}\"")
    if not os.path.exists(fn):
        sys.stdout.write("\nAborted. Backup configuration doesn't "
                         "exist: {fn}. Run the command 'backupy build' first")
        return

    backup = Backup(paths)
    bp_root = backup.bps.backuppaths[0]
    sz = print_size(bp_root.size, fixedwidth=False)
    sys.stdout.write(f" with a size (uncompressed) of {sz}")
    inp_ = "x"
    while inp_.lower() != "y":
        inp_ = input('\nContinue processing? (y/n)')
        if inp_.lower() == "n":
            sys.stdout.write("Aborted by user")
            sys.exit(1)
    backup.backup()
    

if __name__ == "__main__":
    #print(sys.argv)
    args = docopt(__doc__, version=__version__,
                  options_first=False)
    #for k, v in args.items():
    #    print(f"    '{k}' = {v} {type(v)}")
    root = clean_path(args['<root>'])
    include = clean_paths(args['-i'])
    exclude = clean_paths(args['-e'])
    show = clean_number(args['--show'], '--show')
    filemax = clean_number(args['--filemax'], '--filemax')
    dp = clean_number(args['--dp'], '--dp', int)
    sys.stdout.write("\n")
    if args['build'] is True:
        cmd_build(root, include, exclude, show, filemax, dp)
    elif args['reset'] is True:
        cmd_reset(root)
    elif args['zip'] is True:
        cmd_zip(root)
