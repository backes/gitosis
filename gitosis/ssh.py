"""
Gitosis code to handle SSH public keys.
"""
import os, errno, re
import logging

# C0103 - 'log' is a special name
# pylint: disable-msg=C0103
log = logging.getLogger('gitosis.ssh')

_ACCEPTABLE_USER_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_.-]*(@[a-zA-Z][a-zA-Z0-9.-]*)?$')

def isSafeUsername(user):
    """
    Is the username safe to use a a filename?
    """
    match = _ACCEPTABLE_USER_RE.match(user)
    return (match is not None)

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

        if not isSafeUsername(basename):
            log.warn('Unsafe SSH username in keyfile: %r', filename)
            continue

        path = os.path.join(keydir, filename)
        fp = file(path)
        for line in fp:
            line = line.rstrip('\n')
            yield (basename, line)
        fp.close()

COMMENT = '### autogenerated by gitosis, DO NOT EDIT'

def generateAuthorizedKeys(keys):
    """
    Genarate the lines for the Gitosis ~/.ssh/authorized_keys.
    """
    TEMPLATE = ('command="gitosis-serve %(user)s",no-port-forwarding,'
                +'no-X11-forwarding,no-agent-forwarding,no-pty %(key)s')

    yield COMMENT
    for (user, key) in keys:
        yield TEMPLATE % dict(user=user, key=key)

#Protocol 1 public keys consist of the following space-separated fields: options, bits, exponent, modulus, comment. 
#Protocol 2 public key consist of: options, keytype, base64-encoded key, comment.
_COMMAND_OPTS_SAFE_CMD = \
  'command="(/[^ "]+/)?gitosis-serve [^"]+"'
_COMMAND_OPTS_SAFE = \
  'no-port-forwarding' \
+'|no-X11-forwarding' \
+'|no-agent-forwarding' \
+'|no-pty' \
+'|from="[^"]*"'
_COMMAND_OPTS_UNSAFE = \
  'environment="[^"]*"' \
+'|command="[^"]*"' \
+'|permitopen="[^"]*"' \
+'|tunnel="[^"]+"'

_COMMAND_RE = re.compile(
	'^'+_COMMAND_OPTS_SAFE_CMD \
	+'(,('+_COMMAND_OPTS_SAFE+'))+' \
	+' .*')

def filterAuthorizedKeys(fp):
    """
    Read lines from ``fp``, filter out autogenerated ones.

    Note removes newlines.
    """

    for line in fp:
        line = line.rstrip('\n')
        if line == COMMENT:
            continue
        if _COMMAND_RE.match(line):
            continue
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
