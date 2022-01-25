#!/bin/bash

# Script non utilisé

# Get version information
# Use VERSION.py, VERSION, last commit, diff, and last upstream commit date

# Le répertoire de ce script:
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/utils.sh"

# Source code version:
src_version=$(grep SCOVERSION "$SCRIPT_DIR/../sco_version.py" | awk '{ print substr($3, 2, length($3)-2) }')


release_version=""

git status >& /dev/null
if [ $? = 0 ]
then
    # development install: use git
    # last commit
    git_last_commit_hash=$(git log -1 --format=%h)
    git_last_commit_date=$(git log -1 --format=%ci)

    git_up_commit_hash=$(git log -1 --format=%h origin/ScoDoc8)
    git_up_commit_date=$(git log -1 --format=%ci origin/ScoDoc8)

    # Check if git has local changes
    nchanges=$(git status --porcelain | grep -c -v '^??')
    if [ "$nchanges" -gt 0 ]
    then
        has_local_changes="yes"
    else
        has_local_changes="no"
    fi
    git_info=" ($git_up_commit_hash) $git_up_commit_date"
    if [ "$has_local_changes" = "yes" ]
    then
        git_info="$git_info (modified)"
    fi
else
    git_info=""
fi

# Synthetic one-line version:
sco_version="$release_version ($src_version)$git_info"


#
if [ "$1" = "-s" ]
then
    echo "$sco_version"
else
    echo src_version: "$src_version"
    echo git_last_commit_hash: "$git_last_commit_hash"
    echo git_last_commit_date: "$git_last_commit_date"
    echo git_up_commit_hash: "$git_up_commit_hash"
    echo git_up_commit_date: "$git_up_commit_date"
    echo has_local_diffs: "$has_local_changes"
    echo sco_version: "$sco_version"
fi
