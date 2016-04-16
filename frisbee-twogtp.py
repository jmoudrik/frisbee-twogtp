#!/usr/bin/env python3

import sys
import argparse

import copy
import logging
import subprocess
import re
import random

import gomill, gomill.boards, gomill.common, gomill.ascii_boards
from gomill.common import move_from_vertex, format_vertex

class GtpError(Exception):
    pass


def gtp_cut_response(response):
    """Cuts GTP response, returns pair
    (success, response) or None"""
    assert response
    assert response[0] in '=?'
    tail = re.search(r'^([=?])[0-9]*(.*)$', response, flags=re.DOTALL)
    if not tail:
        raise GtpError("invalid format")

    g = tail.groups()
    return g[0] == '=', g[1].strip()


class GtpBot:
    def __init__(self, bot_cmd, color):
        if isinstance(bot_cmd, str):
            bot_cmd = bot_cmd.split()
        self.bot_cmd = bot_cmd
        self.color = color
        self.has_passed = False

        self.p = subprocess.Popen(self.bot_cmd,
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=None)

        success, response = self.interact('list_commands')
        assert success
        self.commands = response.split('\n')

        success, response = self.interact('name')
        assert success
        self.name = response

    def __str__(self):
        return "%s" % (self.color)

    def close(self):
        self.p.terminate()

    def write(self, gtp_cmd):
        print("%s << %s"%(self, repr(gtp_cmd)))

        self.p.stdin.write(bytes(gtp_cmd + "\n", 'ascii'))
        self.p.stdin.flush()

    def read(self):
        response = self.raw_read()
        print("%s >> %s"%(self, repr(response)))

        cut = gtp_cut_response(response)
        return cut

    def interact(self, gtp_cmd):
        self.write(gtp_cmd)
        return self.read()

    def raw_read(self):
        lines = []
        prev = "######"
        while True:
            line = self.p.stdout.readline().decode('ascii')
            lines.append(line)
            if not line:
                break
            if prev[-1] == "\n" and line == "\n":
                break
            prev = line
        return "".join(lines)


def format_move(move):
    if move in ['pass', 'skip']:
        return move
    return format_vertex(move)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('-b', '--black', dest='black_cmd',
                        required=True, help='black command')
    parser.add_argument('-w', '--white', dest='white_cmd',
                        required=True, help='white command')
    parser.add_argument('-s', '--boardsize', dest='boardsize', help='boardsize',
                        type=int, default=19)
    parser.add_argument('-k', '--komi', dest='komi', type=float, default=7.5)
    parser.add_argument('-e', '--epsilon', dest='epsilon', help='frisbee epsilon',
                        type=float, default=0.2)
    parser.add_argument('--allow-invalid-moves', action='store_true',
                        help='Do we allow bots to play invalid moves?',
                        default=False, dest='allow_invalid')
    parser.add_argument('--print-board', action='store_true',
                        help='Should we print the board after each move?',
                        default=False, dest='print_board')

    return parser.parse_args()


def main():
    """
    bots should support the following nonstandard commands:
    frisbee-reg_genmove, frisbee-play, frisbee-epsilon

    # frisbee-reg_genmove
        just like a regular reg_genmove, but the bots may play "illegal moves",
        planning to legal neighbor

    # frisbee-play C MOVE
        just like regular play command, except that the MOVE may be
        either move (B11), PASS, or SKIP (which marks the involuntary pass)

    # frisbee-epsilon EPSILON
        set the epsilon, will be called once at the start of the game


B << boardsize 19
W << boardsize 19
B << frisbee-epsilon 0.2
W << frisbee-epsilon 0.2

B << reg_genmove B
B >> C13
B << play B C12
W << play B C12

W << reg_genmove W
W >> C13
B << play W skip
W << play B skip

...

B << reg_genmove B
B >> pass
B << play B pass
W << play B pass
    """

    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

    args = parse_args()

    black = GtpBot(args.black_cmd, 'B')
    white = GtpBot(args.white_cmd, 'W')

    black.interact('boardsize %d'%args.boardsize)
    white.interact('boardsize %d'%args.boardsize)

    black.interact('komi %.1f'%args.komi)
    white.interact('komi %.1f'%args.komi)

    # init state
    b = gomill.boards.Board(args.boardsize)
    player, opponent = black, white
    ko_move = None
    movenum = 0

    def is_move_valid(move, color):
        if move == ko_move:
            return False
        bc = copy.deepcopy(b)
        try:
            row, col = move
            bc.play(row, col, color.lower())
        except (IndexError, ValueError):  # out of board, point not empty
            return False
        return True

    def randomize_move(move):
        pr_sum, rnd = 0.0, random.random()
        row, col = move
        for dr, dc  in  [(1, 0), (0, 1), (-1, 0), (0, -1)]:
            pr_sum += args.epsilon
            if rnd <= pr_sum:
                return (row+dr, col+dc)
        return move

    def response2move(response):
        """
        handles frisbee rules.
        returns tuple (flag, move)
        where flag is True iff the move actually played is the same that player
        wanted. Move is either 'skip', 'pass', or tuple (row, col).

        """
        # normal pass
        if response.lower() == 'pass':
            return True, 'pass'

        # when we do not allow throwing to invalid moves
        # and player does anyway, this is counted as skip
        move = move_from_vertex(response, b.side)
        if not args.allow_invalid and not is_move_valid(move, player.color):
            logging.warn("Invalid move played by bot, even though"
                         " --allow-invalid-moves was not specified!")
            return False, 'skip'

        # landed on invalid position (involuntary pass)
        move_rnd = randomize_move(move)
        if not is_move_valid(move_rnd, player.color):
            return False, 'skip'

        return move == move_rnd, move_rnd

    try:
        while True:
            player.write('frisbee-reg_genmove %s'%(player.color))
            success, response = player.read()
            assert success

            player_has_his_way, move = response2move(response)

            player.has_passed = move == 'pass'
            if move in ['skip', 'pass']:
                ko_move = None
            else:
                row, col = move
                ko_move = b.play(row, col, player.color.lower())

            player.interact('frisbee-play %s %s'%(player.color, format_move(move)))
            opponent.interact('frisbee-play %s %s'%(player.color, format_move(move)))

            if args.print_board:
                print(re.sub(r' +', ' ', gomill.ascii_boards.render_board(b)))

            if player.has_passed and opponent.has_passed:
                break
            # update invariants
            player, opponent = opponent, player
            movenum += 1
    finally:
        player.write('quit')
        opponent.write('quit')

if __name__ == "__main__":
    main()
    pass
