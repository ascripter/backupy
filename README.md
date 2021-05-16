# backupy 0.1
Command line tool for creating zip archives with tailored inclusions / exclusions

Creates a zip-archive of the folder where the script is executed (or `<root>` if given).

`backupy build` creates a csv-file in the `<root>` directory that contains
the directory structure that will be backed up, considering the selected
options. You can also edit this file manually to include / exclude certain
parts of the directory structure. An include/exclude option for deeper paths
has priority over less deep paths.

`backupy reset` deletes the csv-file for <root>.

`backupy zip` creates a compressed zip-file in the parent directory of `<root>` named after `<root>` and the current datetime.

Usage:
- `backupy build [<root> -i <dir>... -e <dir>... --show=<MB> --filemax=<MB> --dp=<depth>]`
- `backupy reset [<root>]`
- `backupy zip [<root>]`
- `backupy -h|--help`

Arguments:
- `root`: Base directory to backup. Defaults to current working dir

Options:
- `-h --help`: Show this help text
- `-i <dir>...`: Include *only* the given subdirectory + its children. `<dir>` is interpreted relative to `<root>`. Option can be repeated multiple times.
- `-e <dir>...`: Exclude the given subdirectory + its children from backup. `<dir>` is interpreted relative to `<root>`. Option can be repeated multiple times.
- `--show=<MB>`: Min. item size in MB to show in the csv-file. Triggers the "granularity" at which manual edits can be applied later. For smaller items the backup policy of the parent directory is adopted [default: `1`]
- `--filemax=<MB>`: Size-filter to exclude files larger `<MB>` from backup. A negative value disables the option [default: `-1`]
- `--dp=<depth>`: Max. recursion depth for editing backup paths. A negative value doesn't limit the recursion depth [default: `-1`]

## Known Issues
- logging can't deal with non-ASCII characters. Files are included to zip-archive while console raises `UnicodeEncodeError: 'charmap' codec can't encode character '\u0308' in position 54: character maps to <undefined>`. No entry in the log-files appears.

## Feature Ideas
- Show time needed for action (build, zip)
- Expose zip parameters to user
