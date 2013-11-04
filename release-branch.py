#!/usr/bin/env python
#
# GIT Branch-by-Feature
#
# Release-branch recreation script
#
# @author Ivo Verberk
#
# Based in large part on:
#  - https://github.com/affinitybridge/git-bpf/blob/master/lib/git_bpf/commands/recreate-branch.rb
#  - https://github.com/git/git/blob/master/contrib/rerere-train.sh

import argparse
import subprocess
import sys
import re
import os

prefix = "BPF-PREFIX"
 
parser = argparse.ArgumentParser(prog='recreate-branch.py',description='GIT (release) branch recreation script')

parser.add_argument('-a','--base', help='A reference to the commit from which the source branch is based, defaults to \'master\'.', required=False, default='master')
parser.add_argument('-b','--branch',help='Instead of deleting the source branch and replacing it with a new branch of the same name, leave the source branch and create a new branch.', required=False)
parser.add_argument('-x','--exclude', help='Specify a comma seperated list of branches to be excluded.', required=False)
parser.add_argument('-l','--list', action='store_true', help='Process source branch for merge commits and list them. Will not make any changes to any branches.', required=False)
parser.add_argument('-d','--discard', action='store_true', help='Discard the existing local source branch and checkout a new source branch from the remote if one exists. If no remote is specified with -r, gitbpf will use the configured remote, or origin if none is configured.',required=False)
parser.add_argument('-r','--remote', help='Specify the remote repository to work with. Only works with the -d option.', required=False, default='origin')
parser.add_argument('-i','--integration', help='Specify a comma seperated list of (integration) branches to pre-fill the rerere cache with.', required=False)
parser.add_argument('-v','--verbose', action='store_true', help='Show additional (debug) information.', required=False)
parser.add_argument('-C','--no-rerere-cache', action='store_true', help='Disable prefilling of the rerere cache.', required=False, default=False)
parser.add_argument('source', help='The source branch to recreate.')

args = parser.parse_args()

def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.
    
    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is one of "yes" or "no".
    """
    valid = {"yes":"yes",   "y":"yes",  "ye":"yes",
             "no":"no",     "n":"no"}
    if default == None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while 1:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return default
        elif choice in valid.keys():
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "\
                             "(or 'y' or 'n').\n")

def branchExists(branch, remote=None):
    """ Check if a (remote) branch exists in the repository 
    """
    if remote:
        ref = "refs/remotes/%s/%s" % (remote, branch)
    else:
        ref = branch if "refs/heads/" in branch else "refs/heads/" + branch
    
    return run(["git", "show-ref", "--verify", "--quiet", ref])

def refExists(ref):
    """ Check if a ref exists in the repository 
    """
    return run(["git", "show-ref", "--tags", "--heads", ref])

def getMergedBranches(base, source):
    """ Get a list of all merged branches from 'base' till the tip of 'source'
    """
    branches = []
    merges = run(['git', 'rev-list', '--parents', '--merges', '--reverse', "%s...%s" % (base, source)])

    if isinstance(merges, basestring):
        merges = merges.strip()

        for commits in merges.split('\n'):
            parents = re.split('\s',commits)
            parents.pop(0)
            for parent in parents:
                name = run(['git', 'name-rev', parent, '--name-only']).strip()
                alt_base = run(['git', 'name-rev', base, '--name-only']).strip()
                if not source in name and not alt_base in name and not re.match('remote\/\w+\/HEAD', name):
                    m = re.search('(.*)~.*', name)
                    if m:
                        name = m.group(1)
                    if not name in branches:
                        branches.append(name)
    return branches

def run(arguments):
    """ Run an arbitrary command and return True or the output, if any.
        Return False on error.
    """
    try:
        output = subprocess.check_output(arguments, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        if args.verbose:
            print e
        return False

    return output if output else True

def terminate(msg=""):
    """ Abort the script with an error message
    """
    print msg
    sys.exit(1)

# Check if we are in the root of the GIT repositoru
if not os.path.exists(".git"):
    terminate('This script can only be run in the GIT root directory.')

# Sepcify the target branch
if args.branch == None:
    args.branch = args.source

# Check if base ref exists
if not refExists(args.base):
    terminate('Error: base ref does not exist.')
    
# Discard the source branch and fetch from remote    
if args.discard:
    if not run(['git', 'fetch', args.remote]):
        terminate("Error: Could not fetch from remote '%s' repository." % args.remote)

    if branchExists(args.source, args.remote):
        if query_yes_no("This will delete your local '%s' branch if it exists and create it afresh from the %s remote." % (args.source, args.remote), "no") == 'no':
            terminate('Aborted.')

        run(['git', 'checkout', args.base])
        run(['git', 'branch', '-D', args.source])
        run(['git', 'checkout', args.source])

# Check if the source branch exists
if not branchExists(args.source):
    terminate("Cannot recreate branch %s as it doesn't exist." % args.source)

# Check if custom target branch already exists
if args.branch != args.source and branchExists(args.branch):
    terminate("Cannot create branch %s as it already exists." % args.branch)

# Check if we can pre-fill the rerere cache
if not args.no_rerere_cache:
    print "\n* Pre-filling the rerere cache\n"

    # Always learn from the source branch
    rerere_branches = [args.source]
    if args.integration:
        # Additionally, learn from any integration branches
        rerere_branches += args.integration.split(',')

    # Fill the rerere cache
    for rerere_branch in rerere_branches:
        branch = run(['git', 'symbolic-ref', '-q', 'HEAD'])
        if not branch:
            original_HEAD = run(['git', 'rev-parse', '--verify', 'HEAD']) 
            if not original_HEAD:
                terminate('Not on any branch and no commit yet?')

        if not os.path.exists(".git/rr-cache"):
            os.makedirs(".git/rr-cache")

        merges = run(['git', 'rev-list', '--parents', args.base + '..' + rerere_branch])
        if not merges:
            print "Could not find any merge commits."
        else:    
            merges = merges.strip()
            for commits in merges.split('\n'):
                parents = re.split('\s',commits)
                if len(parents) > 2:
                    commit = parents[0]
                    parent1 = parents[1]
                    other_parents = parents[2]
                    run(['git', 'checkout', '-q', parent1 + '^0'])
                    if run(['git', 'merge', '-q', other_parents]):
                        # Merges cleanly
                        continue
                    if os.listdir(".git/rr-cache"):
                        run(['git', 'show', '-s', '--pretty=format:"Learning from %h %s"' + commit])
                        run(['git', 'rerere'])
                        run(['git', 'checkout', '-q', commit, '--', '.'])
                        run(['git', 'rerere'])
                    run(['git', 'reset', '-q', '--hard'])

            if not branch:  
                run(['git', 'checkout', original_HEAD.strip()])
            else:
                run(['git', 'checkout', branch.replace('refs/heads/','').strip()])

print "1. Processing branch '%s' for merge-commits..." % args.source

# Get a list of merged branches
branches = getMergedBranches(args.base, args.source)

if not branches:
    terminate("No feature branches detected, '%s' matches '%s'." % (args.source, args.base))

if args.list:
    terminate("Branches to be merged:\n%s" % "\n".join(branches))

# Exclude branches
if args.exclude:
    for exclude in args.exclude.split(','):
        # Strip remotes/../../ from branch
        branches = [branch for branch in branches if exclude.lower() != re.sub(r'^remotes\/\w+\/([\w\-\/]+)$', r'\1', branch).lower()]

print "\n\
The following branches will be merged when the new '%s' branch is created:\n\n\
  %s\
\n\nIf you see something unexpected check:\n\
  a) that your '%s' branch is up to date\n\
  b) if '%s' is a branch, make sure it is also up to date.\n\
\n\
If there are any non-merge commits in '%s', they will not be included in '%s'. You have been warned.\n" \
% (args.branch, "\n  ".join(branches), args.source, args.base, args.source, args.branch)

if query_yes_no("Proceed with %s branch recreation?" % args.source, "yes") == 'no':
    terminate('Aborted.')

tmp_source = prefix + '-' + args.source

print "\n2. Creating backup of '%s', '%s'..." % (args.source, tmp_source)

if branchExists(tmp_source):
    print "Cannot create branch '%s' as one already exists. To continue, '%s' must be removed." % (tmp_source, tmp_source)
    if query_yes_no("Would you like to forcefully destroy branch '%s' and continue?" % tmp_source, "yes") == 'yes':
        run(['git', 'brach', '-D', tmp_source])
    else:
        terminate('Aborted.')

run(['git','branch', '-m', args.source, tmp_source])

print "3. Creating new '%s' branch based on '%s'..." % (args.branch, args.base)

run(['git', 'checkout', '-b', args.branch, args.base, '--quiet'])

print "4. Merging in feature branches..."

for branch in branches:
    print " - '%s'" % branch
    if not run(['git', 'merge', '--quiet', '--no-ff', '--no-edit', branch]):
        # Check if rerere is enabled
        rerere_enabled = run(['git', 'config', 'rerere.enabled']).strip()
        if rerere_enabled == '0':
            print "Enabling git rerere for this repository"
            run(['git', 'config', 'rerere.enabled', '1'])
        else:    
            print "Possible conflict found, checking rerere status ->",
            status = run(['git', 'rerere', 'status'])

        # We expect True, show error on False or string or if rerere wasn't enabled
        if rerere_enabled == '0' or isinstance(status, basestring) or not status:
            print "conflict could not be resolved automatically."
            print
            print "There is a merge conflict with branch '%s' that has no rerere." % args.branch
            print "Record a resolution by resolving the conflict."
            print "Then run the following command to return your repository to its original state."
            print
            print "git checkout %s && git branch -D %s && git branch -m %s" % (tmp_source, args.branch, args.branch)
            print
            print "If you do not want to resolve the conflict, it is safe to just run the above command to restore your repository to the state it was in before executing this command."
            terminate()
        else:
            run(['git', 'commit', '-a', '--no-edit'])
            print "conflict has been resolved automatically."

print "5. Cleaning up temporary branches ('%s')" % tmp_source

if args.source != args.branch:
    run(['git', 'branch', '-m', tmp_source, args.source])
else:
    run(['git', 'branch', '-D', tmp_source])