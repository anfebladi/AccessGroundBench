#!/bin/sh
set -eu

force=false
case "$#:${1-}" in
    0:) ;;
    1:--force) force=true ;;
    *)
        echo "Usage: $0 [--force]" >&2
        exit 2
        ;;
esac

script=$0
case $script in
    /*) ;;
    *) script=$(pwd -P)/$script ;;
esac
while [ -L "$script" ]; do
    target=$(readlink "$script") || {
        echo "install-agb: unable to resolve installer symlink: $script" >&2
        exit 1
    }
    case $target in
        /*) script=$target ;;
        *) script=$(dirname "$script")/$target ;;
    esac
done
script_dir=$(CDPATH= cd -P "$(dirname "$script")" 2>/dev/null && pwd -P) || {
    echo "install-agb: unable to locate scripts directory" >&2
    exit 1
}
launcher=$script_dir/agb

bin_dir=${XDG_BIN_HOME:-${HOME:?HOME must be set to install agb}}
destination=$bin_dir/agb
mkdir -p "$bin_dir"

if [ -L "$destination" ]; then
    existing=$(readlink "$destination")
    case $existing in
        /*) resolved=$existing ;;
        *)
            resolved_dir=$(CDPATH= cd -P "$(dirname "$destination")" 2>/dev/null && pwd -P) || resolved=''
            resolved=$resolved_dir/$existing
            ;;
    esac
    resolved_dir=$(CDPATH= cd -P "$(dirname "$resolved")" 2>/dev/null && pwd -P) || resolved=''
    [ "$resolved" = "$launcher" ] && {
        echo "agb is already installed at $destination"
        exit 0
    }
    if [ "$force" != true ]; then
        echo "install-agb: refusing to replace existing symlink: $destination (use --force)" >&2
        exit 1
    fi
elif [ -e "$destination" ]; then
    if [ "$force" != true ]; then
        echo "install-agb: refusing to replace existing file: $destination (use --force)" >&2
        exit 1
    fi
fi

if [ -e "$destination" ] || [ -L "$destination" ]; then
    [ -d "$destination" ] && {
        echo "install-agb: refusing to replace directory: $destination" >&2
        exit 1
    }
    rm -f "$destination"
fi
ln -s "$launcher" "$destination"
echo "Installed agb at $destination"
case :$PATH: in
    *:$bin_dir:*) ;;
    *) echo "Add $bin_dir to PATH to run 'agb' from any directory." ;;
esac
