#!/usr/bin/env python3
import sys
import logging
import re

movenum = 0
moves = ['C10', 'C9', 'C8', 'C7', 'C6', 'pass']

def handle_cmd(cmd, args):
    global movenum

    if cmd == 'name':
        return False, 'test_bot'
    elif cmd == 'list_commands':
        return False, 'name\nfrisbee-reg_genmove\nfrisbee-play\nlist_commands\nkomi\nfrisbee-epsilon\nboardsize\nclear_board'
    elif cmd == 'frisbee-reg_genmove':
        movenum, move = movenum + 1, moves[movenum%len(moves)]

        return False, move
    elif cmd in ['frisbee-play', 'boardsize', 'komi', 'frisbee-epsilon']:
        return False, ''

    return True, 'unknown cmd'

logging.basicConfig(format="test_bot %(levelname)s: %(message)s", level=logging.DEBUG)

for raw_line in sys.stdin:
    if raw_line and raw_line[-1] != '\n':
        logging.warn("missing newline at the end")

    #logging.debug("got cmd %s" % (repr(raw_line)))
    line = re.sub(r'\s+', ' ', raw_line)
    line = re.sub(r'#.*', '', line)
    cmdline = line.strip().split()
    if not cmdline:
        continue

    cmdid = ''
    if re.match('\d+', cmdline[0]):
        cmdid = cmdline[0]
        cmdline = cmdline[1:]

    cmd, args = cmdline[0].lower(), cmdline[1:]

    try:
        err, ret = handle_cmd(cmd, args)
    except:
        err, ret = True, "exception occured"
        raise

    if err:
        output = '?%s %s\n\n'%(cmdid, ret)
    else:
        output = '=%s %s\n\n'%(cmdid, ret)

    #logging.debug("returning %s"%(repr(output)))
    print(output, end='')
    sys.stdout.flush()
