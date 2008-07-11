"""
Gitosis code to handle SSH authorized_keys files
"""
import os, errno, re
import logging
from gitosis import sshkey

# C0103 - 'log' is a special name
# pylint: disable-msg=C0103
log = logging.getLogger('gitosis.ssh')

def readKeys(keydir):
    """
    Read SSH public keys from ``keydir/*.pub``
    """
    for filename in os.listdir(keydir):
        if filename.startswith('.'):
            continue
        basename, ext = os.path.splitext(filename)
        if ext != '.pub':
            continue

        if not sshkey.isSafeUsername(basename):
            log.warn('Unsafe SSH username in keyfile: %r', filename)
            continue

        path = os.path.join(keydir, filename)
        fp = file(path)
        for line in fp:
            line = line.rstrip('\n')
            if line.startswith('#'):
                continue
            line = line.strip()
            if len(line) > 0:
                yield (basename, sshkey.get_ssh_pubkey(line))
        fp.close()

COMMENT = '### autogenerated by gitosis, DO NOT EDIT'
SSH_KEY_ACCEPTED_OPTIONS = ['from']

def generateAuthorizedKeys(keys):
    """
    Genarate the lines for the Gitosis ~/.ssh/authorized_keys.
    """
    TEMPLATE = ('%(options)s %(key)s %(comment)s')
    OPTIONS = ('command="gitosis-serve %(user)s",no-port-forwarding,'
               +'no-X11-forwarding,no-agent-forwarding,no-pty')

    yield COMMENT
    for (user, key) in keys:
        options = OPTIONS % dict(user=user, )
        for k in SSH_KEY_ACCEPTED_OPTIONS:
            if k in key.options:
                options += (',%s="%s"' % (k, key.options[k]))
        yield TEMPLATE % dict(user=user, key=key.key, comment=key.comment, options=options)

_GITOSIS_CMD_RE = '(/[^ "]+/)?gitosis-serve [^ "]+$'
_COMMAND_RE = re.compile(_GITOSIS_CMD_RE)

def filterAuthorizedKeys(fp):
    """
    Read lines from ``fp``, filter out autogenerated ones.

    Note removes newlines.
    """

    for line in fp:
        line = line.rstrip('\n')
        if line == COMMENT:
            continue
        try:
            key = sshkey.get_ssh_pubkey(line)
            if 'command' in key.options and \
                _COMMAND_RE.match(key.options['command']):
                continue
        except sshkey.MalformedSSHKey:
            pass
        yield line

def writeAuthorizedKeys(path, keydir):
    """
    Update the Gitosis ~/.ssh/authorized_keys for the new Gitosis SSH key data.
    """
    tmp = '%s.%d.tmp' % (path, os.getpid())
    try:
        in_ = file(path)
    except IOError, ex: #pragma: no cover
        if ex.errno == errno.ENOENT:
            in_ = None
        else:
            raise

    try:
        out = file(tmp, 'w')
        try:
            if in_ is not None:
                for line in filterAuthorizedKeys(in_):
                    print >> out, line

            keygen = readKeys(keydir)
            for line in generateAuthorizedKeys(keygen):
                print >> out, line

            os.fsync(out)
        finally:
            out.close()
    finally:
        if in_ is not None:
            in_.close()
    os.rename(tmp, path)
