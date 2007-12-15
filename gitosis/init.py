"""
Initialize a user account for use with gitosis.
"""

import logging
import os
import sys

from pkg_resources import resource_filename
from cStringIO import StringIO
from ConfigParser import RawConfigParser

from gitosis import repository
from gitosis import run_hook
from gitosis import ssh
from gitosis import util
from gitosis import app

# C0103 - 'log' is a special name
# pylint: disable-msg=C0103
log = logging.getLogger('gitosis.init')

def read_ssh_pubkey(fp=None):
    """Read an SSH public key from stdin."""
    if fp is None:
        fp = sys.stdin
    line = fp.readline()
    return line

class InsecureSSHKeyUsername(Exception):
    """Username contains not allowed characters"""

    def __str__(self):
        return '%s: %s' % (self.__doc__, ': '.join(self.args))

def ssh_extract_user(pubkey):
    """Find the username for a given SSH public key line."""
    _, user = pubkey.rsplit(None, 1)
    if ssh.isSafeUsername(user):
        return user
    else:
        raise InsecureSSHKeyUsername(repr(user))

def initial_commit(git_dir, cfg, pubkey, user):
    """Import the initial files into the gitosis-admin repository."""
    repository.fast_import(
        git_dir=git_dir,
        commit_msg='Automatic creation of gitosis repository.',
        committer='Gitosis Admin <%s>' % user,
        files=[
            ('keydir/%s.pub' % user, pubkey),
            ('gitosis.conf', cfg),
            ],
        )

def symlink_config(git_dir):
    """
    Place a symlink for the gitosis.conf file in the homedir of the gitosis
    user, to make possible to find initially.
    """
    dst = os.path.expanduser('~/.gitosis.conf')
    tmp = '%s.%d.tmp' % (dst, os.getpid())
    util.unlink(tmp)
    os.symlink(
        os.path.join(git_dir, 'gitosis.conf'),
        tmp,
        )
    os.rename(tmp, dst)

def init_admin_repository(git_dir, pubkey, user):
    """Create the initial gitosis-admin reposistory."""
    repository.init(
        path=git_dir,
        template=resource_filename('gitosis.templates', 'admin')
        )
    repository.init(
        path=git_dir,
        )
    if not repository.has_initial_commit(git_dir):
        log.info('Making initial commit...')
        # ConfigParser does not guarantee order, so jump through hoops
        # to make sure [gitosis] is first
        cfg_file = StringIO()
        print >> cfg_file, '[gitosis]'
        print >> cfg_file
        cfg = RawConfigParser()
        cfg.add_section('group gitosis-admin')
        cfg.set('group gitosis-admin', 'members', user)
        cfg.set('group gitosis-admin', 'writable', 'gitosis-admin')
        cfg.write(cfg_file)
        initial_commit(
            git_dir=git_dir,
            cfg=cfg_file.getvalue(),
            pubkey=pubkey,
            user=user,
            )

class Main(app.App):
    """gitosis-init program."""
    # W0613 - They also might ignore arguments here, where the descendant
    # methods won't.
    # pylint: disable-msg=W0613

    def create_parser(self):
        """Declare the input for this program."""
        parser = super(Main, self).create_parser()
        parser.set_usage('%prog [OPTS]')
        parser.set_description(
            'Initialize a user account for use with gitosis')
        return parser

    def read_config(self, options, cfg):
        """Ignore errors that result from non-existent config file."""
		# Pylint gets it wrong.
		# pylint: disable-msg=W0704
        try:
            super(Main, self).read_config(options, cfg)
        except app.ConfigFileDoesNotExistError:
            pass

    def handle_args(self, parser, cfg, options, args):
        """Parse the input for this program."""
        super(Main, self).handle_args(parser, cfg, options, args)

        os.umask(0022)

        log.info('Reading SSH public key...')
        pubkey = read_ssh_pubkey()
        user = ssh_extract_user(pubkey)
        if user is None:
            log.error('Cannot parse user from SSH public key.')
            sys.exit(1)
        log.info('Admin user is %r', user)
        log.info('Creating generated files directory...')
        generated = util.getGeneratedFilesDir(config=cfg)
        util.mkdir(generated)
        log.info('Creating repository structure...')
        repositories = util.getRepositoryDir(cfg)
        util.mkdir(repositories)
        admin_repository = os.path.join(repositories, 'gitosis-admin.git')
        init_admin_repository(
            git_dir=admin_repository,
            pubkey=pubkey,
            user=user,
            )
        log.info('Running post-update hook...')
        util.mkdir(os.path.expanduser('~/.ssh'), 0700)
        run_hook.post_update(cfg=cfg, git_dir=admin_repository)
        log.info('Symlinking ~/.gitosis.conf to repository...')
        symlink_config(git_dir=admin_repository)
        log.info('Done.')
